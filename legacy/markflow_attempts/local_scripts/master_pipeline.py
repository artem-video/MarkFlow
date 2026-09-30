import os
import re
import sys
import subprocess

# Автоматическая доустановка библиотек, если их нет
for pkg in ["beautifulsoup4", "yt-dlp", "rapidfuzz"]:
    try:
        if pkg == "beautifulsoup4":
            import bs4
        else:
            __import__(pkg)
    except ImportError:
        print(f"Installing missing package: {pkg}...")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg])

import xml.etree.ElementTree as ET
from xml.dom import minidom
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
# ================= КОНФИГУРАЦИЯ ПУТЕЙ =================
HTML_SCRIPT_PATH = r"C:\Users\Artem\Videos\Макашенец\МОЙ ЮТУБ_МОДНАЯ ПРОПАГАНДА\_.html"
VO_PATH = r"D:\Макашенец\МОДНАЯ ПРОПАГАНДА\VO_MAKASHENETS_20260904.wav"
BASE_DIR = r"D:\Макашенец\МОДНАЯ ПРОПАГАНДА"
DOWNLOAD_DIR = os.path.join(BASE_DIR, "_downloads")
OUTPUT_XML_PATH = os.path.join(BASE_DIR, "MODNAYA_PROPAGANDA_FULL_EDIT.xml")

CAM_FILES = [
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0001.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0002.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0003.MP4"),
    os.path.join(BASE_DIR, "МОДНАЯ ПРОПАГАНДА", "Копия 20260828_B0004.MP4")
]

FPS = 60
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= 1. ПАРСИНГ СЦЕНАРИЯ И КОММЕНТАРИЕВ =================
def parse_html_script(path):
    print("[1/5] Парсинг HTML сценария и комментариев...")
    if not os.path.exists(path):
        print(f"ОШИБКА: Файл сценария не найден: {path}")
        return [], []

    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    tasks = []
    paragraphs = []

    # Читаем текст сценария и якоря
    for p in soup.find_all(["p", "div", "li"]):
        txt = p.get_text().strip()
        if txt:
            paragraphs.append(txt)

    # Ищем все ссылки и комментарии
    link_idx = 1
    for a in soup.find_all("a", href=True):
        href = a['href']
        if any(d in href for d in ["youtube.com", "youtu.be", "rutube.ru", "vk.com", "t.me"]):
            # Проверяем, есть ли таймкод рядом или в ссылке
            context = a.parent.get_text() if a.parent else ""
            tc_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', context)
            src_tc = tc_match.group(1) if tc_match else None
            
            tasks.append({
                "id": link_idx,
                "url": href,
                "anchor": context[:80].strip(),
                "src_timecode": src_tc,
                "filename": f"{link_idx:03d}_clip.mp4"
            })
            link_idx += 1

    print(f"-> Найдено блоков текста: {len(paragraphs)}, ссылок на лайвы: {len(tasks)}")
    return paragraphs, tasks

# ================= 2. СКАЧИВАНИЕ ЛАЙВОВ (ПАРАЛЛЕЛЬНО) =================
def download_single_live(task):
    out_tmpl = os.path.join(DOWNLOAD_DIR, f"{task['id']:03d}_clip.%(ext)s")
    final_mp4 = os.path.join(DOWNLOAD_DIR, task['filename'])
    
    if os.path.exists(final_mp4):
        print(f"[SKIP] Уже скачан: {task['filename']}")
        return task

    print(f"[DOWNLOADING] #{task['id']}: {task['url']}")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        "--no-playlist",
        task['url']
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return task

def run_parallel_downloads(tasks):
    print(f"[2/5] Запуск параллельной выкачки {len(tasks)} лайвов...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(download_single_live, tasks))
    print("-> Все лайвы скачаны.")
    return results

# ================= 3. ТРАНСКРИБАЦИЯ НАЧИТКИ (ASR) =================
def transcribe_audio(audio_path):
    print("[3/5] Транскрибация VO начитки через Whisper (локально)...")
    if not os.path.exists(audio_path):
        print(f"ВНИМАНИЕ: Файл начитки {audio_path} не найден! Включаем фоллбэк таймингов.")
        return []
    
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="ru", word_timestamps=True)
        words_data = []
        for seg in result.get("segments", []):
            words_data.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip()
            })
        print(f"-> Распознано {len(words_data)} реплик.")
        return words_data
    except Exception as e:
        print(f"Ошибка ASR: {e}. Используем линейную разметку.")
        return []

# ================= 4. АЛАЙНМЕНТ СЦЕНАРИЯ И КОММЕНТОВ =================
def align_script_to_timeline(tasks, segments):
    print("[4/5] Привязка комментов и лайвов к таймлайну...")
    aligned = []
    
    # Если расшифровка есть — матчим через fuzzy search
    for t in tasks:
        best_time = 0.0
        best_score = 0
        for seg in segments:
            score = fuzz.partial_ratio(t["anchor"].lower(), seg["text"].lower())
            if score > best_score:
                best_score = score
                best_time = seg["start"]
        
        # Если не нашли соответствие, ставим с шагом 30 сек
        final_time = best_time if best_score > 60 else (t["id"] * 30.0)
        t["timeline_sec"] = final_time
        aligned.append(t)
    
    aligned.sort(key=lambda x: x["timeline_sec"])
    return aligned

# ================= 5. ГЕНЕРАТОР FCP7 XML =================
def generate_premiere_project(aligned_tasks, output_xml):
    print("[5/5] Сборка полного многослойного FCP7 XML...")
    xmeml = ET.Element("xmeml", version="4")
    project = ET.SubElement(xmeml, "project")
    ET.SubElement(project, "name").text = "МОДНАЯ ПРОПАГАНДА"
    
    children = ET.SubElement(project, "children")
    seq = ET.SubElement(children, "sequence", id="sequence-main")
    ET.SubElement(seq, "name").text = "МОДНАЯ ПРОПАГАНДА — Master Assembly"
    
    rate = ET.SubElement(seq, "rate")
    ET.SubElement(rate, "timebase").text = str(FPS)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    
    timecode = ET.SubElement(seq, "timecode")
    tc_rate = ET.SubElement(timecode, "rate")
    ET.SubElement(tc_rate, "timebase").text = str(FPS)
    ET.SubElement(tc_rate, "ntsc").text = "FALSE"
    ET.SubElement(timecode, "string").text = "00:00:00:00"
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"
    
    media = ET.SubElement(seq, "media")
    
    # Видеодорожки: V1 (Камера), V2 (Лайвы B-Roll)
    video = ET.SubElement(media, "video")
    v_format = ET.SubElement(video, "format")
    v_sample = ET.SubElement(v_format, "samplecharacteristics")
    v_s_rate = ET.SubElement(v_sample, "rate")
    ET.SubElement(v_s_rate, "timebase").text = str(FPS)
    ET.SubElement(v_s_rate, "ntsc").text = "FALSE"
    ET.SubElement(v_sample, "width").text = "1920"
    ET.SubElement(v_sample, "height").text = "1080"
    
    v_track_1 = ET.SubElement(video, "track") # V1
    v_track_2 = ET.SubElement(video, "track") # V2
    
    # Аудиодорожки: A1-A2 (VO), A3-A4 (SFX / Звук лайвов)
    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "numOutputChannels").text = "4"
    a_format = ET.SubElement(audio, "format")
    a_sample = ET.SubElement(a_format, "samplecharacteristics")
    ET.SubElement(a_sample, "depth").text = "16"
    ET.SubElement(a_sample, "samplerate").text = "48000"
    
    a_track_1 = ET.SubElement(audio, "track")
    a_track_2 = ET.SubElement(audio, "track")
    a_track_3 = ET.SubElement(audio, "track")
    a_track_4 = ET.SubElement(audio, "track")

    # 1. Раскладываем чистовой войсовер (A1, A2) сплошной колбасой
    vo_url = "file://localhost/" + VO_PATH.replace("\\", "/")
    vo_dur_sec = 1800 # 30 мин запас
    vo_dur_frames = int(vo_dur_sec * FPS)
    
    for a_num, a_trk in enumerate([a_track_1, a_track_2], start=1):
        a_clip = ET.SubElement(a_trk, "clipitem", id=f"vo-clip-{a_num}")
        ET.SubElement(a_clip, "name").text = "VO_MAKASHENETS_20260904.wav"
        ET.SubElement(a_clip, "duration").text = str(vo_dur_frames)
        r = ET.SubElement(a_clip, "rate")
        ET.SubElement(r, "timebase").text = str(FPS)
        ET.SubElement(r, "ntsc").text = "FALSE"
        ET.SubElement(a_clip, "in").text = "0"
        ET.SubElement(a_clip, "out").text = str(vo_dur_frames)
        ET.SubElement(a_clip, "start").text = "0"
        ET.SubElement(a_clip, "end").text = str(vo_dur_frames)
        
        f = ET.SubElement(a_clip, "file", id="vo-file")
        ET.SubElement(f, "name").text = "VO_MAKASHENETS_20260904.wav"
        ET.SubElement(f, "pathurl").text = vo_url
        st = ET.SubElement(a_clip, "sourcetrack")
        ET.SubElement(st, "mediatype").text = "audio"
        ET.SubElement(st, "trackindex").text = str(a_num)

    # 2. Раскладываем исходники камеры B0001-B0004 на V1
    cam_cursor = 0
    for idx, c_path in enumerate(CAM_FILES, start=1):
        c_name = os.path.basename(c_path)
        c_url = "file://localhost/" + c_path.replace("\\", "/")
        c_dur = int(450 * FPS) # по ~7.5 мин кусок
        
        v_clip = ET.SubElement(v_track_1, "clipitem", id=f"cam-v-{idx}")
        ET.SubElement(v_clip, "name").text = c_name
        ET.SubElement(v_clip, "duration").text = str(c_dur)
        r = ET.SubElement(v_clip, "rate")
        ET.SubElement(r, "timebase").text = str(FPS)
        ET.SubElement(r, "ntsc").text = "FALSE"
        ET.SubElement(v_clip, "in").text = "0"
        ET.SubElement(v_clip, "out").text = str(c_dur)
        ET.SubElement(v_clip, "start").text = str(cam_cursor)
        ET.SubElement(v_clip, "end").text = str(cam_cursor + c_dur)
        
        f = ET.SubElement(v_clip, "file", id=f"cam-file-{idx}")
        ET.SubElement(f, "name").text = c_name
        ET.SubElement(f, "pathurl").text = c_url
        cam_cursor += c_dur

    # 3. Раскладываем скачанные лайвы на V2 и звук лайвов на A3-A4
    for idx, t in enumerate(aligned_tasks, start=1):
        live_file = os.path.join(DOWNLOAD_DIR, t["filename"])
        live_url = "file://localhost/" + live_file.replace("\\", "/")
        start_frame = int(t["timeline_sec"] * FPS)
        clip_dur = int(8 * FPS) # дефолтный кусок перебивки 8 сек
        
        # V2 Клип
        l_clip = ET.SubElement(v_track_2, "clipitem", id=f"live-v-{idx}")
        ET.SubElement(l_clip, "name").text = t["filename"]
        ET.SubElement(l_clip, "duration").text = str(clip_dur)
        r = ET.SubElement(l_clip, "rate")
        ET.SubElement(r, "timebase").text = str(FPS)
        ET.SubElement(r, "ntsc").text = "FALSE"
        ET.SubElement(l_clip, "in").text = "0"
        ET.SubElement(l_clip, "out").text = str(clip_dur)
        ET.SubElement(l_clip, "start").text = str(start_frame)
        ET.SubElement(l_clip, "end").text = str(start_frame + clip_dur)
        
        lf = ET.SubElement(l_clip, "file", id=f"live-f-{idx}")
        ET.SubElement(lf, "name").text = t["filename"]
        ET.SubElement(lf, "pathurl").text = live_url
        
        # Добавляем маркер с инфой режиссера
        m_elem = ET.SubElement(seq, "marker")
        ET.SubElement(m_elem, "name").text = f"ЛАЙВ #{t['id']}"
        ET.SubElement(m_elem, "comment").text = f"URL: {t['url']}\nЯКОРЬ: {t['anchor']}\nTC: {t.get('src_timecode', 'нет')}"
        ET.SubElement(m_elem, "in").text = str(start_frame)
        ET.SubElement(m_elem, "out").text = str(start_frame)

    ET.SubElement(seq, "duration").text = str(max(cam_cursor, vo_dur_frames))

    # Экспорт XML
    xml_str = ET.tostring(xmeml, encoding="utf-8")
    dom = minidom.parseString(xml_str)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    if pretty.startswith('<?xml'):
        pretty = pretty.split('\n', 1)[1]
    
    with open(output_xml, "w", encoding="utf-8") as f:
        f.write(header + pretty)
    
    print(f"\n[ГОТОВО] Секвенция собрана: {output_xml}")

# ================= ЗАПУСК =================
if __name__ == "__main__":
    script_texts, tasks = parse_html_script(HTML_SCRIPT_PATH)
    
    # Параллельно качаем лайвы и транскрибируем войсовер
    with ThreadPoolExecutor(max_workers=2) as main_executor:
        future_dl = main_executor.submit(run_parallel_downloads, tasks)
        future_asr = main_executor.submit(transcribe_audio, VO_PATH)
        
        downloaded_tasks = future_dl.result()
        segments = future_asr.result()

    # Сводим тайминги
    aligned_tasks = align_script_to_timeline(downloaded_tasks, segments)
    
    # Генерируем проект
    generate_premiere_project(aligned_tasks, OUTPUT_XML_PATH)