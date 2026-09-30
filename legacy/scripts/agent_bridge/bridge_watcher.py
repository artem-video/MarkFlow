# -*- coding: utf-8 -*-
"""
Локальный "сторож" для MarkFlow: смотрит папку jobs/, выполняет задания
(сейчас — расшифровка аудио через faster-whisper на GPU, если есть),
кладёт результат в results/. Работает до перезагрузки или закрытия окна.
Ничего никуда не отправляет по сети сам — только читает/пишет локальные файлы.
"""
import json, os, sys, time, traceback, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOBS = BASE / "jobs"
RESULTS = BASE / "results"
LOGS = BASE / "logs"
JOBS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOGS / "watcher.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def get_model():
    from faster_whisper import WhisperModel
    device = "cpu"
    compute_type = "int8"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
    except Exception:
        pass
    log(f"Загружаю модель Whisper (device={device}, compute_type={compute_type})...")
    return WhisperModel("large-v3-turbo", device=device, compute_type=compute_type)

_model = None

def transcribe_job(job):
    global _model
    if _model is None:
        _model = get_model()
    audio_path = job["audio_path"]
    language = job.get("language", "ru")
    log(f"Транскрибирую: {audio_path}")
    segments, info = _model.transcribe(audio_path, language=language, word_timestamps=True, vad_filter=True)
    out = {"language": info.language, "duration": info.duration, "segments": []}
    for seg in segments:
        out["segments"].append({
            "start": seg.start, "end": seg.end, "text": seg.text,
            "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (seg.words or [])]
        })
    return out

def handle(job_file):
    job_id = job_file.stem
    try:
        job = json.loads(job_file.read_text(encoding="utf-8"))
        jtype = job.get("type", "transcribe")
        if jtype == "transcribe":
            result = transcribe_job(job)
        else:
            raise ValueError(f"Неизвестный тип задания: {jtype}")
        (RESULTS / f"{job_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (RESULTS / f"{job_id}.ok").write_text("ok", encoding="utf-8")
        log(f"Готово: {job_id}")
    except Exception as e:
        err = traceback.format_exc()
        (RESULTS / f"{job_id}.error").write_text(err, encoding="utf-8")
        log(f"Ошибка в {job_id}: {e}")
    finally:
        done_dir = JOBS / "_done"
        done_dir.mkdir(exist_ok=True)
        shutil.move(str(job_file), str(done_dir / job_file.name))

def main():
    log("Сторож запущен. Жду задания в jobs/ ...")
    while True:
        for job_file in sorted(JOBS.glob("*.json")):
            handle(job_file)
        time.sleep(3)

if __name__ == "__main__":
    main()
