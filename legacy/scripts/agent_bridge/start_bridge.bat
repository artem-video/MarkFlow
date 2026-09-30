@echo off
cd /d "%~dp0"
echo Проверяю Python-зависимости (один раз, дальше не нужно)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper
python -c "import torch" 2>nul
if errorlevel 1 (
    echo Ставлю PyTorch с поддержкой CUDA под вашу RTX 4060...
    python -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu121
)
echo Запускаю сторожа в фоне. Это окно можно закрыть.
start "MarkFlow Bridge" /min pythonw "%~dp0bridge_watcher.py"
timeout /t 2 >nul
