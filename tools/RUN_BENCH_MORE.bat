@echo off
cd /d "%~dp0.."
echo === MarkFlow: full GPU benchmark - old models again + 5 new ===
echo First run downloads several GB. Do not close this window.
python -m pip install --quiet --upgrade faster-whisper "onnx-asr[gpu,hub]"
python tools\bench_asr.py run --force --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3
python tools\bench_asr.py run --models whisper-turbo-novad,whisper-ru-novad,canary-v2,fastconformer-ru,t-one
python tools\bench_asr.py report
echo.
echo DONE. Results: %~dp0..\bench_out\asr.md
pause
