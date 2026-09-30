@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === MarkFlow: полный замер на видеокарте (старые модели заново + 5 новых) ===
echo Первый запуск качает модели (несколько ГБ). Окно не закрывай.
python -m pip install --quiet --upgrade faster-whisper "onnx-asr[gpu,hub]"
python tools\bench_asr.py run --force --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3
python tools\bench_asr.py run --models whisper-turbo-novad,whisper-ru-novad,canary-v2,fastconformer-ru,t-one
python tools\bench_asr.py report
echo.
echo ГОТОВО. Результаты: %~dp0..\bench_out\asr.md
pause
