@echo off
cd /d "%~dp0"
git checkout claude/adoring-turing-sfhe0z
echo === MarkFlow: gate 2 (draft of MODNAYA PROPAGANDA) ===
echo Do not close this window. First run downloads the speech models and may take 20-40 minutes.
git pull
python -m pip install --quiet -e .[dev,asr]
python -m pip uninstall -y onnxruntime
python -m pip install --quiet --force-reinstall --no-deps onnxruntime-gpu==1.22.0
python -c "import onnxruntime as o; p=o.get_available_providers(); print('GPU:', 'CUDAExecutionProvider' in p, p)"
python -m acceptance.gate2 acceptance\episodes\modnaya_propaganda.yaml
echo.
echo Reports: acceptance\reports\
git add acceptance\reports
git commit -m "Gate 2 report from the PC"
git push
echo.
echo DONE. If the last lines say FAIL, the list above says why. Tell Claude: "Gate 2 done".
pause
