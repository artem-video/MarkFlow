"""GigaAM v3 and Parakeet-v3 through onnx-asr (the stack measured in stage 0.4, docs/bench/asr.md).

Install on the PC:  pip install -e .[asr]   (onnx-asr + onnxruntime-gpu 1.22 for CUDA 12).
Pitfall from the benchmark: faster-whisper pulls the CPU `onnxruntime`, which silently shadows the GPU one —
keep only `onnxruntime-gpu` installed. `load()` refuses to run on CPU unless allow_cpu=True.
"""

from __future__ import annotations

import gc
import glob
import os
from pathlib import Path
from typing import Any, Callable

from markflow.domain.transcript import Word
from markflow.infra.asr.chunking import split_points, tokens_to_words
from markflow.infra.media.ffmpeg import FfmpegAudio

MODELS = {
    "gigaam-v3": "gigaam-v3-rnnt",
    "parakeet-v3": "nemo-parakeet-tdt-0.6b-v3",
}


class AsrError(RuntimeError):
    pass


def _add_cuda_dlls() -> None:
    """cuBLAS / cuDNN DLLs shipped by pip nvidia-* wheels must be on the DLL path on Windows."""
    if os.name != "nt":
        return
    import site

    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
            except OSError:
                pass


def _default_loader(model_id: str, allow_cpu: bool) -> Any:
    _add_cuda_dlls()
    import onnx_asr
    import onnxruntime as ort

    try:
        ort.preload_dlls()
    except Exception:  # older onnxruntime has no preload_dlls
        pass
    has_gpu = "CUDAExecutionProvider" in ort.get_available_providers()
    if not has_gpu and not allow_cpu:
        raise AsrError("onnxruntime sees no CUDA GPU (is the CPU 'onnxruntime' package shadowing "
                       "'onnxruntime-gpu'?). Fix the install or pass allow_cpu=True.")
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if has_gpu else ["CPUExecutionProvider"]
    return onnx_asr.load_model(model_id, providers=providers).with_timestamps()


class OnnxAsrEngine:
    def __init__(self, name: str, model: Any, read: Callable[[Path], tuple[Any, int]]):
        self.name, self._model, self._read = name, model, read

    def transcribe(self, wav: Path) -> list[Word]:
        if self._model is None:
            raise AsrError(f"{self.name}: engine is closed")
        samples, rate = self._read(wav)
        words: list[Word] = []
        cuts = split_points(samples, rate)
        for a, b in zip(cuts, cuts[1:]):
            result = self._model.recognize(samples[a:b], sample_rate=rate)
            if result.tokens and result.timestamps:
                words += tokens_to_words(list(result.tokens), list(result.timestamps), (b - a) / rate,
                                         offset=a / rate, engine=self.name)
        return words

    def close(self) -> None:
        self._model = None
        gc.collect()


class OnnxAsrFactory:
    """Implements application.ports.AsrEngineFactory."""

    def __init__(self, name: str, allow_cpu: bool = False,
                 loader: Callable[[str, bool], Any] = _default_loader):
        if name not in MODELS:
            raise AsrError(f"unknown ASR model {name!r}; known: {sorted(MODELS)}")
        self.name, self._allow_cpu, self._loader = name, allow_cpu, loader

    def load(self) -> OnnxAsrEngine:
        model = self._loader(MODELS[self.name], self._allow_cpu)
        return OnnxAsrEngine(self.name, model, FfmpegAudio(Path(".")).read)
