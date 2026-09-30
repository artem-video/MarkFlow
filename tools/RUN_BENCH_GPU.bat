@echo off
cd /d "%~dp0.."
echo === MarkFlow: GPU fix and re-measure GigaAM / Parakeet ===
echo Do not close this window.
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install --quiet onnxruntime-gpu==1.22.0
python -c "import onnxruntime as o; print(\"ORT\", o.__version__, o.get_available_providers())"
python tools\bench_asr.py run --force --models gigaam-v2-rnnt,gigaam-v3-rnnt,parakeet-v3
python tools\bench_asr.py report
echo.
echo DONE. Results: %~dp0..\bench_out\asr.md
pause
