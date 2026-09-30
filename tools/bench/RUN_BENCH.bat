@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === MarkFlow: замер расшифровки и Google Диска ===
echo Первый запуск ставит нужное и качает модели (несколько ГБ) - это нормально. Окно не закрывай.
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper numpy psutil google-auth requests nvidia-cublas-cu12 nvidia-cudnn-cu12 "onnx-asr[hub]" onnxruntime-gpu
python tools\bench_asr.py all --varlamov "%~1"
echo.
python tools\drive_stream_probe.py
echo.
echo ГОТОВО. Результаты: %~dp0bench_out\asr.md и drive.md
pause
