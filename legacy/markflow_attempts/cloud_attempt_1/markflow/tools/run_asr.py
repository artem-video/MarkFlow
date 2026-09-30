#!/usr/bin/env python3
"""
run_asr.py — транскрибирует аудио/видео в words.json для MarkFlow.

Использует faster-whisper с моделью large-v3 (лучшее качество для русского).
При первом запуске скачивает модель ~3 ГБ, потом кэшируется.

Использование:
  python3 markflow/tools/run_asr.py audio.wav -o words.json
  python3 markflow/tools/run_asr.py video.mov -o words.json --model medium
"""
import json
import sys
import argparse


def transcribe(audio_path: str, model_size: str = "large-v3", language: str = "ru") -> list[dict]:
    from faster_whisper import WhisperModel

    print(f"Загружаю модель {model_size}...", flush=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"Транскрибирую: {audio_path}", flush=True)
    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    print(f"Язык: {info.language} (вероятность {info.language_probability:.2f})", flush=True)

    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })
        print(f"\r  {seg.end:.0f}s [{len(words)} слов]", end="", flush=True)

    print(f"\nГотово: {len(words)} слов")
    return words


def main():
    parser = argparse.ArgumentParser(description="ASR для MarkFlow пайплайна")
    parser.add_argument("audio", help="Путь к аудио или видео файлу")
    parser.add_argument("-o", "--output", default="words.json", help="Выходной файл")
    parser.add_argument("--model", default="large-v3",
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help="Модель Whisper (large-v3 = лучше, medium = быстрее)")
    parser.add_argument("--language", default="ru", help="Код языка")
    args = parser.parse_args()

    words = transcribe(args.audio, model_size=args.model, language=args.language)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    print(f"Сохранено → {args.output}")
    if words:
        print(f"Первые 3 слова: {words[:3]}")


if __name__ == "__main__":
    main()
