@echo off
cd /d "%~dp0"
git checkout claude/adoring-turing-sfhe0z
echo === MarkFlow: gate 3 (draft checked after Premiere re-saved it) ===
git pull
python -m acceptance.gate3 --episode acceptance\episodes\modnaya_propaganda.yaml
git add acceptance\reports
git commit -m "Gate 3 report from the PC"
git push
echo.
echo DONE. Tell Claude: "Gate 3 done".
pause
