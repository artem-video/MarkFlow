@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === MarkFlow: замер новых моделей (Canary, FastConformer-ru, T-one, Whisper без VAD, русский Whisper) ===
echo Первый запуск качает модели (несколько ГБ). Окно не закрывай.
python -m pip install --quiet --upgrade faster-whisper "onnx-asr[gpu,hub]"
python tools\bench_asr.py run --models whisper-turbo-novad,whisper-ru-novad,canary-v2,fastconformer-ru,t-one
python tools\bench_asr.py report
echo.
echo ГОТОВО. Результаты: %~dp0..\bench_out\asr.md
pause
