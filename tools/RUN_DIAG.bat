@echo off
cd /d "%~dp0.."
python tools\diag_gpu.py > bench_out\diag.txt 2>&1
echo Done. Now tell Claude: ready
pause
