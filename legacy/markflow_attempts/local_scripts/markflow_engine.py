import os
import re
import sys
import json
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor

# ================= 0. ПРОВЕРКА И ДОУСТАНОВКА ЗАВИСИМОСТЕЙ =================
REQUIRED_LIBS = ["beautifulsoup4", "yt-dlp", "rapidfuzz", "openai-whisper"]
for lib in REQUIRED_LIBS:
    try:
        if lib == "beautifulsoup4":
            import bs4
        elif lib == "openai-whisper":
            import whisper
        else:
            __import__(lib)
    except ImportError:
        print(f"[SETUP] Установка необходимой библиотеки: {lib}...")
        subprocess.run([sys.executable, "-m", "pip", "install", lib], check=True)

from bs4 import BeautifulSoup
from rapidfuzz import fuzz
import whisper

# ================= 1. КОНФИГУРАЦИЯ ПРОЕКТА =================
BASE_DIR = r"D:\Макашенец\МОДНАЯ ПРОПАГАНДА"
HTML_SCRIPT = r"C:\Users\Artem\Videos\Макашенец\МОЙ ЮТУБ_МОДНАЯ ПРОПАГАНДА\_.html"
DOWNLOAD_DIR = os.path.join(BASE_DIR, "_downloads")
XML_OUTPUT = os.path.join(BASE_DIR, "MODNAYA_PROPAGANDA_MARKFLOW_MASTER.xml")

CAM_FILES = [
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0001.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0002.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0003.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0004.MP4")
]
VO_FILE = os.path.join(BASE_DIR, "VO_MAKASHENETS_20260904.wav")

FPS = 29.97
TIMEBASE = 30
NTSC = "TRUE"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= 2. ПАРСЕР СЦЕНАРИЯ И РЕЖИССЕРСКИХ ССЫЛОК =================
def clean_google_url(raw_url):
    if "google.com/url?q=" in raw_url:
        m = re.search(r'google\.com/url\?q=([^&]+)', raw_url)
        if m:
            raw_url = unquote(m.group(1))
    parsed = urlparse(raw_url)
    clean_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    qs = parse_qs(parsed.query)
    if "watch" in parsed.path and "v" in qs:
        clean_base += f"?v={qs['v'][0]}"
    return raw_url, clean_base

def parse_tc_to_seconds(text):
    if not text:
        return 0
    m = re.search(r'(?:(\d{1,2}):)?(\d{1,2}):(\d{2})', text)
    if m:
        h = int(m.group(1)) if m.group(1) else 0
        mn = int(m.group(2))
        s = int(m.group(3))
        return h * 3600 + mn * 60 + s
    t_sec = re.search(r'[?&]t=(\d+)', text)
    if t_sec:
        return int(t_sec.group(1))
    return 0

def extract_script_and_lives(html_path):
    print("\n>>> [1/5] Парсинг сценария и извлечение лайвов...")
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    script_blocks = []
    unique_sources = {} # clean_url -> video_id
    live_inserts = []

    # Читаем текст сценария
    for el in soup.find_all(["p", "h1", "h2", "h3", "li"]):
        txt = el.get_text().strip()
        if len(txt) > 5 and not txt.startswith("http"):
            script_blocks.append(txt)

    # Собираем все режиссерские ссылки
    link_counter = 1
    for a in soup.find_all("a", href=True):
        href = a['href']
        if any(d in href for d in ["youtube.com", "youtu.be", "rutube.ru", "vk.com", "t.me"]):
            raw_url, clean_base = clean_google_url(href)
            if clean_base not in unique_sources:
                v_id = f"SRC_{len(unique_sources)+1:03d}"
                unique_sources[clean_base] = {
                    "id": v_id,
                    "url": clean_base,
                    "filename": f"{v_id}.mp4",
                    "path": os.path.join(DOWNLOAD_DIR, f"{v_id}.mp4")
                }
            else:
                v_id = unique_sources[clean_base]["id"]

            context = a.parent.get_text() if a.parent else ""
            tc_sec = parse_tc_to_seconds(raw_url) or parse_tc_to_seconds(context)

            live_inserts.append({
                "insert_id": link_counter,
                "video_id": v_id,
                "source_info": unique_sources[clean_base],
                "anchor": context[:100].strip(),
                "tc_start_sec": tc_sec,
                "duration_sec": 8.0 # Дефолтный хронометраж цитаты/лайва
            })
            link_counter += 1

    print(f"-> Сценарий: {len(script_blocks)} абзацев")
    print(f"-> Ссылок в тексте: {len(live_inserts)}, Уникальных файлов для загрузки: {len(unique_sources)}")
    return script_blocks, unique_sources, live_inserts

# ================= 3. РОБОТ ЗАГРУЗКИ УНИКАЛЬНЫХ МЕДИА =================
def download_worker(source_item):
    v_id = source_item["id"]
    url = source_item["url"]
    out_tmpl = os.path.join(DOWNLOAD_DIR, f"{v_id}.%(ext)s")
    target_mp4 = source_item["path"]

    if os.path.exists(target_mp4):
        print(f"  [OK] Уже загружен: {v_id}.mp4")
        return target_mp4

    print(f"  [DOWNLOADING] {v_id} -> {url}")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        "--no-playlist",
        url
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target_mp4

def download_all_unique_sources(unique_sources):
    print("\n>>> [2/5] Параллельная загрузка уникальных лайвов (yt-dlp)...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(download_worker, unique_sources.values()))
    print("-> Загрузка всех медиа завершена.")

# ================= 4. ASR И РАСПОЗНАВАНИЕ СЛОВ =================
def extract_and_transcribe(media_path, asr_model):
    name = os.path.splitext(os.path.basename(media_path))[0]
    wav_path = os.path.join(BASE_DIR, f"{name}_16k.wav")
    json_path = os.path.join(BASE_DIR, f"{name}_words.json")

    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"  [AUDIO] Экспорт 16kHz WAV: {name}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", media_path,
        "-vn", "-ar", "16000", "-ac", "1",
        wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"  [ASR] Распознавание речи: {name}...")
    res = asr_model.transcribe(wav_path, language="ru", word_timestamps=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    return res

# ================= 5. CUT / ALIGNMENT ENGINE (ЕГОР-СТАЙЛ) =================
def run_alignment_and_cut(script_blocks, cam_transcripts, live_inserts):
    print("\n>>> [3/5] Сверка сценария с дублями съёмки (Forced Alignment)...")
    timeline_a_roll = []
    
    # 0.11 с до речи, 0.26 с после речи (тайминги Егора)
    PAD_BEFORE = 0.11
    PAD_AFTER = 0.26

    current_timeline_time = 0.0

    for b_idx, block_text in enumerate(script_blocks):
        best_match = None
        best_score = 0
        
        # Ищем фразу во всех исходниках съёмки
        for cam_idx, cam_data in enumerate(cam_transcripts):
            cam_path = CAM_FILES[cam_idx]
            segments = cam_data.get("segments", [])
            
            for s_idx, seg in enumerate(segments):
                score = fuzz.partial_ratio(block_text.lower(), seg["text"].lower())
                
                # Если совпало и это повторный дубль — последний побеждает
                if score > 68 and score >= best_score:
                    best_score = score
                    in_s = max(0.0, seg["start"] - PAD_BEFORE)
                    out_s = seg["end"] + PAD_AFTER
                    best_match = {
                        "cam_path": cam_path,
                        "cam_name": os.path.basename(cam_path),
                        "in_sec": in_s,
                        "out_sec": out_s,
                        "duration_sec": out_s - in_s,
                        "text": seg["text"],
                        "block_ref": block_text
                    }

        if best_match:
            best_match["timeline_start"] = current_timeline_time
            best_match["timeline_end"] = current_timeline_time + best_match["duration_sec"]
            current_timeline_time = best_match["timeline_end"]
            timeline_a_roll.append(best_match)

    print(f"-> Смонтировано чистовых кусков A-Roll: {len(timeline_a_roll)}")

    # Привязка лайвов по тексту сценария
    print("\n>>> [4/5] Разметка лайвов на дорожку V2...")
    aligned_lives = []
    for live in live_inserts:
        best_t = None
        best_s = 0
        for clip in timeline_a_roll:
            sc = fuzz.partial_ratio(live["anchor"].lower(), clip["block_ref"].lower())
            if sc > best_s:
                best_s = sc
                best_t = clip["timeline_start"]

        if best_s > 50 and best_t is not None:
            live["timeline_sec"] = best_t
            aligned_lives.append(live)

    print(f"-> Успешно привязано лайвов к репликам: {len(aligned_lives)}")
    return timeline_a_roll, aligned_lives

# ================= 6. ВАЛИДНЫЙ ГЕНЕРАТОР FCP7 XML =================
def build_fcp_xml(a_roll, lives, output_xml_path):
    print("\n>>> [5/5] Сборка эталонного FCP7 XML проекта...")
    xmeml = ET.Element("xmeml", version="4")
    project = ET.SubElement(xmeml, "project")
    ET.SubElement(project, "name").text = "МОДНАЯ ПРОПАГАНДА"
    
    children = ET.SubElement(project, "children")
    seq = ET.SubElement(children, "sequence", id="sequence-master")
    ET.SubElement(seq, "name").text = "МОДНАЯ ПРОПАГАНДА — Автосборка"

    total_duration_sec = a_roll[-1]["timeline_end"] if a_roll else 3600
    total_duration_frames = int(total_duration_sec * FPS)
    ET.SubElement(seq, "duration").text = str(total_duration_frames)

    rate = ET.SubElement(seq, "rate")
    ET.SubElement(rate, "timebase").text = str(TIMEBASE)
    ET.SubElement(rate, "ntsc").text = NTSC

    # Таймкод
    tc = ET.SubElement(seq, "timecode")
    tc_rate = ET.SubElement(tc, "rate")
    ET.SubElement(tc_rate, "timebase").text = str(TIMEBASE)
    ET.SubElement(tc_rate, "ntsc").text = NTSC
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "DF"

    media = ET.SubElement(seq, "media")
    video = ET.SubElement(media, "video")
    
    # Спецификация 1080p 29.97fps
    v_format = ET.SubElement(video, "format")
    v_sample = ET.SubElement(v_format, "samplecharacteristics")
    v_s_rate = ET.SubElement(v_sample, "rate")
    ET.SubElement(v_s_rate, "timebase").text = str(TIMEBASE)
    ET.SubElement(v_s_rate, "ntsc").text = NTSC
    ET.SubElement(v_sample, "width").text = "1920"
    ET.SubElement(v_sample, "height").text = "1080"
    ET.SubElement(v_sample, "anamorphic").text = "FALSE"
    ET.SubElement(v_sample, "pixelaspectratio").text = "square"
    ET.SubElement(v_sample, "fielddominance").text = "none"

    track_v1 = ET.SubElement(video, "track") # A-Roll Камера
    track_v2 = ET.SubElement(video, "track") # B-Roll Лайвы

    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "numOutputChannels").text = "4"
    a_format = ET.SubElement(audio, "format")
    a_sample = ET.SubElement(a_format, "samplecharacteristics")
    ET.SubElement(a_sample, "depth").text = "16"
    ET.SubElement(a_sample, "samplerate").text = "48000"

    track_a1 = ET.SubElement(audio, "track") # Звук камеры L
    track_a2 = ET.SubElement(audio, "track") # Звук камеры R
    track_a3 = ET.SubElement(audio, "track") # Звук лайвов L
    track_a4 = ET.SubElement(audio, "track") # Звук лайвов R

    # Хелпер создания метаданных файла
    def append_file_def(parent_elem, f_id, name, path_url, dur_sec, has_v=True, has_a=True):
        f = ET.SubElement(parent_elem, "file", id=f_id)
        ET.SubElement(f, "name").text = name
        ET.SubElement(f, "pathurl").text = path_url
        f_rate = ET.SubElement(f, "rate")
        ET.SubElement(f_rate, "timebase").text = str(TIMEBASE)
        ET.SubElement(f_rate, "ntsc").text = NTSC
        ET.SubElement(f, "duration").text = str(int(dur_sec * FPS))
        f_med = ET.SubElement(f, "media")
        if has_v:
            v = ET.SubElement(f_med, "video")
            s = ET.SubElement(v, "samplecharacteristics")
            sr = ET.SubElement(s, "rate")
            ET.SubElement(sr, "timebase").text = str(TIMEBASE)
            ET.SubElement(sr, "ntsc").text = NTSC
            ET.SubElement(s, "width").text = "1920"
            ET.SubElement(s, "height").text = "1080"
        if has_a:
            a = ET.SubElement(f_med, "audio")
            s = ET.SubElement(a, "samplecharacteristics")
            ET.SubElement(s, "depth").text = "16"
            ET.SubElement(s, "samplerate").text = "48000"
            ET.SubElement(a, "channelcount").text = "2"
        return f

    # 1. Раскладка A-Roll на V1 + A1/A2
    for idx, clip in enumerate(a_roll, 1):
        in_f = int(clip["in_sec"] * FPS)
        out_f = int(clip["out_sec"] * FPS)
        st_f = int(clip["timeline_start"] * FPS)
        end_f = int(clip["timeline_end"] * FPS)
        dur_f = out_f - in_f
        
        file_url = "file://localhost/" + clip["cam_path"].replace("\\", "/")
        f_id = f"cam-file-{os.path.basename(clip['cam_path'])}"

        # V1
        v_clip = ET.SubElement(track_v1, "clipitem", id=f"aroll-v-{idx}")
        ET.SubElement(v_clip, "name").text = clip["cam_name"]
        ET.SubElement(v_clip, "duration").text = str(int(3600 * FPS))
        r = ET.SubElement(v_clip, "rate")
        ET.SubElement(r, "timebase").text = str(TIMEBASE)
        ET.SubElement(r, "ntsc").text = NTSC
        ET.SubElement(v_clip, "in").text = str(in_f)
        ET.SubElement(v_clip, "out").text = str(out_f)
        ET.SubElement(v_clip, "start").text = str(st_f)
        ET.SubElement(v_clip, "end").text = str(end_f)
        append_file_def(v_clip, f_id, clip["cam_name"], file_url, 3600)

        # Линковка V1 к A1 и A2
        for t_idx, a_name in enumerate(["a1", "a2"], 1):
            lnk = ET.SubElement(v_clip, "link")
            ET.SubElement(lnk, "linkclipref").text = f"aroll-{a_name}-{idx}"
            ET.SubElement(lnk, "mediatype").text = "audio"
            ET.SubElement(lnk, "trackindex").text = str(t_idx)
            ET.SubElement(lnk, "clipindex").text = str(idx)

        # A1 и A2
        for a_idx, a_track in enumerate([track_a1, track_a2], 1):
            a_clip = ET.SubElement(a_track, "clipitem", id=f"aroll-a{a_idx}-{idx}")
            ET.SubElement(a_clip, "name").text = clip["cam_name"]
            ET.SubElement(a_clip, "duration").text = str(int(3600 * FPS))
            ar = ET.SubElement(a_clip, "rate")
            ET.SubElement(ar, "timebase").text = str(TIMEBASE)
            ET.SubElement(ar, "ntsc").text = NTSC
            ET.SubElement(a_clip, "in").text = str(in_f)
            ET.SubElement(a_clip, "out").text = str(out_f)
            ET.SubElement(a_clip, "start").text = str(st_f)
            ET.SubElement(a_clip, "end").text = str(end_f)
            append_file_def(a_clip, f_id, clip["cam_name"], file_url, 3600)
            
            st = ET.SubElement(a_clip, "sourcetrack")
            ET.SubElement(st, "mediatype").text = "audio"
            ET.SubElement(st, "trackindex").text = str(a_idx)

    # 2. Раскладка лайвов на V2 + A3/A4
    for idx, live in enumerate(lives, 1):
        s_info = live["source_info"]
        live_dur_f = int(live["duration_sec"] * FPS)
        in_f = int(live["tc_start_sec"] * FPS)
        out_f = in_f + live_dur_f
        st_f = int(live["timeline_sec"] * FPS)
        end_f = st_f + live_dur_f

        file_url = "file://localhost/" + s_info["path"].replace("\\", "/")
        f_id = f"live-file-{s_info['id']}"

        # V2
        l_v_clip = ET.SubElement(track_v2, "clipitem", id=f"live-v-{idx}")
        ET.SubElement(l_v_clip, "name").text = s_info["filename"]
        ET.SubElement(l_v_clip, "duration").text = str(int(7200 * FPS))
        r = ET.SubElement(l_v_clip, "rate")
        ET.SubElement(r, "timebase").text = str(TIMEBASE)
        ET.SubElement(r, "ntsc").text = NTSC
        ET.SubElement(l_v_clip, "in").text = str(in_f)
        ET.SubElement(l_v_clip, "out").text = str(out_f)
        ET.SubElement(l_v_clip, "start").text = str(st_f)
        ET.SubElement(l_v_clip, "end").text = str(end_f)
        append_file_def(l_v_clip, f_id, s_info["filename"], file_url, 7200)

        # A3 и A4 (звук лайва)
        for a_idx, a_track in enumerate([track_a3, track_a4], 1):
            l_a_clip = ET.SubElement(a_track, "clipitem", id=f"live-a{a_idx}-{idx}")
            ET.SubElement(l_a_clip, "name").text = s_info["filename"]
            ET.SubElement(l_a_clip, "duration").text = str(int(7200 * FPS))
            ar = ET.SubElement(l_a_clip, "rate")
            ET.SubElement(ar, "timebase").text = str(TIMEBASE)
            ET.SubElement(ar, "ntsc").text = NTSC
            ET.SubElement(l_a_clip, "in").text = str(in_f)
            ET.SubElement(l_a_clip, "out").text = str(out_f)
            ET.SubElement(l_a_clip, "start").text = str(st_f)
            ET.SubElement(l_a_clip, "end").text = str(end_f)
            append_file_def(l_a_clip, f_id, s_info["filename"], file_url, 7200)
            
            st = ET.SubElement(l_a_clip, "sourcetrack")
            ET.SubElement(st, "mediatype").text = "audio"
            ET.SubElement(st, "trackindex").text = str(a_idx)

        # Маркер в точку вставки
        m = ET.SubElement(seq, "marker")
        ET.SubElement(m, "name").text = f"ЛАЙВ #{live['insert_id']}"
        ET.SubElement(m, "comment").text = f"URL: {s_info['url']} | TC: {live['tc_start_sec']}s | ЯКОРЬ: {live['anchor']}"
        ET.SubElement(m, "in").text = str(st_f)
        ET.SubElement(m, "out").text = str(st_f)

    # Генерация XML
    xml_raw = ET.tostring(xmeml, encoding="utf-8")
    dom = minidom.parseString(xml_raw)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    if pretty.startswith('<?xml'):
        pretty = pretty.split('\n', 1)[1]

    with open(output_xml_path, "w", encoding="utf-8") as f:
        f.write(header + pretty)

    print(f"\n[УСПЕХ] Готовый проект собран: {output_xml_path}")

# ================= 7. ЕДИНАЯ ТОЧКА ВХОДА =================
if __name__ == "__main__":
    # 1. Парсинг сценария и ссылок
    script_blocks, unique_sources, live_inserts = extract_script_and_lives(HTML_SCRIPT)

    # 2. Выкачка уникальных лайвов в _downloads
    download_all_unique_sources(unique_sources)

    # 3. Инициализация ASR и транскрибация исходников
    print("\n>>> Инициализация Whisper (GPU/CPU)...")
    asr_model = whisper.load_model("base")
    
    cam_transcripts = []
    for cam in CAM_FILES:
        cam_transcripts.append(extract_and_transcribe(cam, asr_model))

    # 4. Сверка дублей (cut) и привязка лайвов
    a_roll, aligned_lives = run_alignment_and_cut(script_blocks, cam_transcripts, live_inserts)

    # 5. Генерация валидного XML для Premiere
    build_fcp_xml(a_roll, aligned_lives, XML_OUTPUT)