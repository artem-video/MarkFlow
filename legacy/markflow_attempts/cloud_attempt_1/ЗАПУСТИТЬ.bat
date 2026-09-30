@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title MarkFlow — Автомонтаж Макашенец

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║         MarkFlow — автоматический черновой монтаж        ║
echo ║         Модная пропаганда ч2  •  60fps  •  4K            ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM ── НАСТРОЙКИ ─────────────────────────────────────────────────────────────
REM Путь к основному видео (поменяй если лежит в другом месте)
set "VIDEO_PATH=C:\Users\Artem\Videos\Макашенец\МОДНАЯ ПРОПАГАНДА\Копия Keyed-Video_2608311425_0001.mov"

REM Остальное трогать не нужно
set "SCRIPT_DIR=%~dp0"
set "AUDIO_FILE=%SCRIPT_DIR%audio_standup.wav"
set "WORDS_FILE=%SCRIPT_DIR%words.json"
set "GDOC_FILE=%SCRIPT_DIR%gdoc_raw.json"
set "SCENARIO_TXT=%SCRIPT_DIR%сценарий.txt"
set "OUTPUT_DIR=%SCRIPT_DIR%output_final"
set "PROJECT_NAME=Модная пропаганда ч2"
set "FPS=60.0"

REM ── ШАГ 0: Проверка Python и ffmpeg ───────────────────────────────────────
echo [0/5] Проверка зависимостей...

python --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo   ОШИБКА: Python не найден.
    echo   Скачай с https://www.python.org/downloads/ и перезапусти батник.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Python: %%v

ffmpeg -version > nul 2>&1
if errorlevel 1 (
    echo.
    echo   ОШИБКА: ffmpeg не найден.
    echo   Скачай с https://ffmpeg.org/download.html
    echo   Распакуй и добавь папку bin в PATH.
    echo   Или установи через winget: winget install ffmpeg
    pause
    exit /b 1
)
echo   ffmpeg: OK

echo   Устанавливаю faster-whisper (если ещё нет)...
python -m pip install -q faster-whisper 2> nul
echo   faster-whisper: OK
echo.

REM ── ШАГ 1: Сценарий → gdoc_raw.json ──────────────────────────────────────
echo [1/5] Подготовка сценария...

if exist "%GDOC_FILE%" (
    echo   gdoc_raw.json уже есть — пропускаю.
    goto STEP2
)

if not exist "%SCENARIO_TXT%" (
    echo.
    echo   НУЖЕН СЦЕНАРИЙ. Сделай так:
    echo.
    echo   1. Открой Google Doc:
    echo      https://docs.google.com/document/d/1ZfKaT_PS7PbRUqQhY4b_1Cdl_KYPUhV_EtNGQJJJZRI/
    echo   2. Файл → Скачать → Обычный текст (.txt)
    echo   3. Переименуй скачанный файл в:  сценарий.txt
    echo   4. Положи рядом с этим батником (в папку %SCRIPT_DIR%)
    echo   5. Запусти батник снова.
    echo.
    pause
    exit /b 1
)

echo   Конвертирую сценарий.txt → gdoc_raw.json...
python -c "
import json, sys
with open(r'%SCENARIO_TXT%', encoding='utf-8', errors='replace') as f:
    text = f.read()
with open(r'%GDOC_FILE%', 'w', encoding='utf-8') as f:
    json.dump({'fileContent': text}, f, ensure_ascii=False)
print('  Готово: ' + str(len(text)) + ' символов')
"
if errorlevel 1 (
    echo   ОШИБКА при конвертации сценария
    pause
    exit /b 1
)

:STEP2
echo.

REM ── ШАГ 2: Извлечение аудио ───────────────────────────────────────────────
echo [2/5] Извлечение аудио из видео...

if exist "%AUDIO_FILE%" (
    echo   audio_standup.wav уже есть — пропускаю.
    echo   (удали файл если нужно перекодировать заново)
    goto STEP3
)

if not exist "%VIDEO_PATH%" (
    echo.
    echo   ОШИБКА: Видео не найдено по пути:
    echo   %VIDEO_PATH%
    echo.
    echo   Поменяй переменную VIDEO_PATH в начале батника.
    pause
    exit /b 1
)

echo   Извлекаю аудио из %VIDEO_PATH%
echo   (только звук, видео не копируется — займёт 5-15 мин)
echo.
ffmpeg -i "%VIDEO_PATH%" -vn -acodec pcm_s16le -ar 16000 -ac 1 "%AUDIO_FILE%" -y
if errorlevel 1 (
    echo.
    echo   ОШИБКА при извлечении аудио. Проверь путь к видео.
    pause
    exit /b 1
)
echo   Аудио сохранено → %AUDIO_FILE%

:STEP3
echo.

REM ── ШАГ 3: Транскрипция (ASR) ─────────────────────────────────────────────
echo [3/5] Транскрипция речи (ASR)...

if exist "%WORDS_FILE%" (
    echo   words.json уже есть — пропускаю.
    echo   (удали файл если нужно перетранскрибировать заново)
    goto STEP4
)

echo   Запускаю Whisper large-v3 (первый раз скачает ~3 ГБ модель)
echo   На CPU ~75 мин видео → ~40-60 мин транскрипции
echo   Можно оставить и уйти попить кофе.
echo.
python "%SCRIPT_DIR%markflow\tools\run_asr.py" "%AUDIO_FILE%" -o "%WORDS_FILE%"
if errorlevel 1 (
    echo.
    echo   ОШИБКА при транскрипции.
    echo   Попробуй быструю модель: добавь --model medium в строку выше.
    pause
    exit /b 1
)
echo   Транскрипция готова → %WORDS_FILE%

:STEP4
echo.

REM ── ШАГ 4: Сборка монтажа ─────────────────────────────────────────────────
echo [4/5] Сборка монтажа (пайплайн MarkFlow)...

python -m markflow.pipeline.run_pipeline ^
    --gdoc_json "%GDOC_FILE%" ^
    --words_json "%WORDS_FILE%" ^
    --video_path "%VIDEO_PATH%" ^
    --out_dir "%OUTPUT_DIR%" ^
    --project_name "%PROJECT_NAME%" ^
    --fps %FPS%

if errorlevel 1 (
    echo.
    echo   ОШИБКА в пайплайне. Смотри сообщения выше.
    pause
    exit /b 1
)

:STEP5
echo.

REM ── ГОТОВО ────────────────────────────────────────────────────────────────
echo [5/5] Готово!
echo.
echo   Файлы созданы в папке:
echo   %OUTPUT_DIR%\
echo.
echo   ┌─────────────────────────────────────────────────────────┐
echo   │  Модная_пропаганда_ч2.xml  ← ОТКРЫВАЙ ЭТОТ            │
echo   │  В Premiere: File → Import → выбери .xml файл           │
echo   │  Появится сиквенс с клипами и маркерами ЛАЙВ            │
echo   └─────────────────────────────────────────────────────────┘
echo.

REM Открываем папку с результатом
explorer "%OUTPUT_DIR%"

pause
