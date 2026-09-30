@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === MarkFlow: повторный замер GigaAM / Parakeet на видеокарте ===
python tools\bench_asr.py run --force --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3
python tools\bench_asr.py report
echo.
echo ГОТОВО. Результаты: %~dp0..\bench_out\asr.md
pause
