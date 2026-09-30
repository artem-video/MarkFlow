# ASR benchmark - summary (stage 0.4), 2026-09-30

Machine: RTX 4060 Laptop 8 GB. Clips: 10 min B0002, 5 min Keyed take (with retakes), two 5 min lives.
Raw table: `bench_out/asr.md` on the PC (not committed).

## Speed (seconds of audio per second of work, GPU)
- Parakeet-v3: ~92-100x. GigaAM v2/v3 RNNT: ~54-70x. Whisper large-v3-turbo: 5-14x with VAD, 34-42x without VAD.
- The last two ONNX re-runs ran on CPU (12-25x) - NOT comparable. Cause: `faster-whisper` pulls the CPU `onnxruntime`,
  which shadows `onnxruntime-gpu`. Fix is in `tools/RUN_BENCH_GPU.bat` (uninstall both, install only `onnxruntime-gpu==1.22.0`).
  That final GPU re-run was not confirmed.

## Text accuracy on lives (WER vs channel transcript, lower = better)
- Whisper turbo 8.5-9.2 %, GigaAM v3 7.9-9.9 %, GigaAM v2 8.4-10.7 %, Parakeet-v3 8.8-10.3 % - effectively tied.
- Weaker: T-one 12-14 %, FastConformer-ru 12-17 % (inserts extra words), Whisper-ru 10-13 %, Whisper turbo without VAD 8.5-11.6 %.
- Canary-v2: returns no word timestamps - unusable for cutting.

## Retakes (Keyed take, words found)
- Whisper turbo with VAD 403 (drops retakes), without VAD 485, Parakeet 598, GigaAM 673-674.
- For a rough cut that must SEE every retake, GigaAM / Parakeet are safer than Whisper.

## Not decided
- Final model choice is Artem's. Candidates: Parakeet-v3 (fastest, best text) or GigaAM v3 (sees the most retakes).
- Word-boundary "loud %" metric does not discriminate models - not used for the choice.
