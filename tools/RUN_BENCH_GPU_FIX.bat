@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === MarkFlow: повторный замер GigaAM / Parakeet на видеокарте ===
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install --quiet "onnxruntime-gpu==1.22.0" nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-cuda-runtime-cu12 nvidia-curand-cu12
python tools\bench_asr.py run --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3
python tools\bench_asr.py report
echo.
echo ГОТОВО. Результаты: %~dp0..\bench_out\asr.md
pause
