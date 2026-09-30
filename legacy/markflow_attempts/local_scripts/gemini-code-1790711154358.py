import xml.etree.ElementTree as ET
from xml.dom import minidom

def build_premiere_xml(output_path, clips, markers, fps=60):
    xmeml = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(xmeml, "sequence")
    ET.SubElement(sequence, "name").text = "МОДНАЯ ПРОПАГАНДА — Тестовый черновик (Auto-Cut)"
    
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(fps)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    
    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    v_track = ET.SubElement(video, "track")
    
    audio = ET.SubElement(media, "audio")
    a_track_1 = ET.SubElement(audio, "track")
    a_track_2 = ET.SubElement(audio, "track")

    current_timeline_frame = 0

    # Расстановка нарезанных клипов (A-roll)
    for idx, clip in enumerate(clips):
        in_frame = int(clip["in_sec"] * fps)
        out_frame = int(clip["out_sec"] * fps)
        duration = out_frame - in_frame
        
        # Видеоклип (V1)
        v_clip = ET.SubElement(v_track, "clipitem", id=f"clipitem-v-{idx+1}")
        ET.SubElement(v_clip, "name").text = clip["source_name"]
        ET.SubElement(v_clip, "duration").text = str(duration)
        v_rate = ET.SubElement(v_clip, "rate")
        ET.SubElement(v_rate, "timebase").text = str(fps)
        ET.SubElement(v_clip, "in").text = str(in_frame)
        ET.SubElement(v_clip, "out").text = str(out_frame)
        ET.SubElement(v_clip, "start").text = str(current_timeline_frame)
        ET.SubElement(v_clip, "end").text = str(current_timeline_frame + duration)
        
        file_elem = ET.SubElement(v_clip, "file", id="file-source-1")
        ET.SubElement(file_elem, "name").text = clip["source_name"]
        ET.SubElement(file_elem, "pathurl").text = clip["source_url"]
        
        # Аудиоклипы (A1 и A2)
        for a_idx, a_track in enumerate([a_track_1, a_track_2]):
            a_clip = ET.SubElement(a_track, "clipitem", id=f"clipitem-a{a_idx+1}-{idx+1}")
            ET.SubElement(a_clip, "name").text = clip["source_name"]
            ET.SubElement(a_clip, "duration").text = str(duration)
            a_rate = ET.SubElement(a_clip, "rate")
            ET.SubElement(a_rate, "timebase").text = str(fps)
            ET.SubElement(a_clip, "in").text = str(in_frame)
            ET.SubElement(a_clip, "out").text = str(out_frame)
            ET.SubElement(a_clip, "start").text = str(current_timeline_frame)
            ET.SubElement(a_clip, "end").text = str(current_timeline_frame + duration)
            ET.SubElement(a_clip, "file", id="file-source-1")

        current_timeline_frame += duration

    # Добавление режиссерских маркеров и подсказок Макашенца
    for m in markers:
        marker_frame = int(m["time_sec"] * fps)
        marker_elem = ET.SubElement(sequence, "marker")
        ET.SubElement(marker_elem, "name").text = m["title"]
        ET.SubElement(marker_elem, "comment").text = (
            f"🎙 ЯКОРЬ: {m['anchor']}\n"
            f"💡 ИДЕЯ: {m['idea']}\n"
            f"🔊 SFX: {m.get('sfx', 'нет')}\n"
            f"🔍 ТЕГИ: {m['tags']}"
        )
        ET.SubElement(marker_elem, "in").text = str(marker_frame)
        ET.SubElement(marker_elem, "out").text = str(marker_frame)

    # Запись в файл
    rough_string = ET.tostring(xmeml, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))

# Тестовая выборка чистовых дублей первых 5 минут
clips_data = [
    {
        "source_name": "Копия Keyed-Video_2608311425_0001.mov",
        "source_url": "file://localhost/C:/Users/Artem/Videos/%D0%9C%D0%B0%D0%BA%D0%B0%D1%88%D0%B5%D0%BD%D0%B5%D1%86/%D0%9C%D0%9E%D0%94%D0%9D%D0%90%D0%AF%20%D0%9F%D0%A0%D0%9E%D0%9F%D0%90%D0%93%D0%90%D0%9D%D0%94%D0%90/%D0%9A%D0%BE%D0%BF%D0%B8%D1%8F%20Keyed-Video_2608311425_0001.mov",
        "in_sec": 14.20,
        "out_sec": 52.80
    },
    {
        "source_name": "Копия Keyed-Video_2608311425_0001.mov",
        "source_url": "file://localhost/C:/Users/Artem/Videos/%D0%9C%D0%B0%D0%BA%D0%B0%D1%88%D0%B5%D0%BD%D0%B5%D1%86/%D0%9C%D0%9E%D0%94%D0%9D%D0%90%D0%AF%20%D0%9F%D0%A0%D0%9E%D0%9F%D0%90%D0%93%D0%90%D0%9D%D0%94%D0%90/%D0%9A%D0%BE%D0%BF%D0%B8%D1%8F%20Keyed-Video_2608311425_0001.mov",
        "in_sec": 68.15,
        "out_sec": 114.40
    },
    {
        "source_name": "Копия Keyed-Video_2608311425_0001.mov",
        "source_url": "file://localhost/C:/Users/Artem/Videos/%D0%9C%D0%B0%D0%BA%D0%B0%D1%88%D0%B5%D0%BD%D0%B5%D1%86/%D0%9C%D0%9E%D0%94%D0%9D%D0%90%D0%AF%20%D0%9F%D0%A0%D0%9E%D0%9F%D0%90%D0%93%D0%90%D0%9D%D0%94%D0%90/%D0%9A%D0%BE%D0%BF%D0%B8%D1%8F%20Keyed-Video_2608311425_0001.mov",
        "in_sec": 131.05,
        "out_sec": 188.60
    }
]

markers_data = [
    {
        "time_sec": 24.5,
        "title": "🎮 HUD / ВЫБОР СКИНА",
        "anchor": "выходит план даллеса всё-таки работает",
        "idea": "Игровая плашка ачивки или стат-карточка с разблокировкой",
        "sfx": "Taco Bell",
        "tags": "dulles plan / план даллеса / achievement unlocked / video game hud"
    },
    {
        "time_sec": 78.0,
        "title": "💥 СФЕРАЙЗ / ПЫПА",
        "anchor": "владимир владимирович",
        "idea": "Надувание лица через Spherize на тупом синхроне",
        "sfx": "Vine Boom",
        "tags": "spherize face / funny zoom / vine boom"
    }
]

build_premiere_xml("MODNAYA_PROPAGANDA_ROUGHCUT_TEST.xml", clips_data, markers_data)