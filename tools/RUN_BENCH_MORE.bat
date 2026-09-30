@echo off
cd /d "%~dp0.."
echo === MarkFlow: GPU benchmark part 2 ===
echo Do not close this window.
python -m pip install --quiet --upgrade faster-whisper "onnx-asr[gpu,hub]"
rem the line below is essential: newer onnxruntime-gpu wants CUDA 13 and silently falls back to CPU
python -m pip install --quiet onnxruntime-gpu==1.22.0 nvidia-cublas-cu12 nvidia-cudnn-cu12
python -c "import onnxruntime as o; print(\"ORT\", o.__version__, o.get_available_providers())"
python tools\bench_asr.py run --force --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3,canary-v2,fastconformer-ru,t-one
python tools\bench_asr.py report
echo.
echo DONE. Results: %~dp0..\bench_out\asr.md
pause
