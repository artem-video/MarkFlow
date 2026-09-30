import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

OUTPUT_PATH = r"D:\Макашенец\МОДНАЯ ПРОПАГАНДА\MODNAYA_PROPAGANDA_FINAL.xml"
FPS = 60

# Исходники съемки (V1)
CAM_FILES = [
    {
        "id": "cam-file-1",
        "name": "Копия 20260828_B0001.MP4",
        "path": "file://localhost/D:/Макашенец/МОДНАЯ ПРОПАГАНДА/МОДНАЯ ПРОПАГАНДА/Копия 20260828_B0001.MP4",
        "duration": 27000
    },
    {
        "id": "cam-file-2",
        "name": "Копия 20260828_B0002.MP4",
        "path": "file://localhost/D:/Макашенец/МОДНАЯ ПРОПАГАНДА/МОДНАЯ ПРОПАГАНДА/Копия 20260828_B0002.MP4",
        "duration": 27000
    },
    {
        "id": "cam-file-3",
        "name": "Копия 20260828_B0003.MP4",
        "path": "file://localhost/D:/Макашенец/МОДНАЯ ПРОПАГАНДА/МОДНАЯ ПРОПАГАНДА/Копия 20260828_B0003.MP4",
        "duration": 27000
    },
    {
        "id": "cam-file-4",
        "name": "Копия 20260828_B0004.MP4",
        "path": "file://localhost/D:/Макашенец/МОДНАЯ ПРОПАГАНДА/МОДНАЯ ПРОПАГАНДА/Копия 20260828_B0004.MP4",
        "duration": 27000
    }
]

VO_FILE = {
    "id": "vo-file-1",
    "name": "VO_MAKASHENETS_20260904.wav",
    "path": "file://localhost/D:/Макашенец/МОДНАЯ ПРОПАГАНДА/VO_MAKASHENETS_20260904.wav",
    "duration": 108000
}

def create_file_element(file_info, has_video=True, has_audio=True):
    elem = ET.Element("file", id=file_info["id"])
    ET.SubElement(elem, "name").text = file_info["name"]
    ET.SubElement(elem, "pathurl").text = file_info["path"]
    
    rate = ET.SubElement(elem, "rate")
    ET.SubElement(rate, "timebase").text = str(FPS)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    ET.SubElement(elem, "duration").text = str(file_info["duration"])
    
    media = ET.SubElement(elem, "media")
    if has_video:
        v = ET.SubElement(media, "video")
        sample = ET.SubElement(v, "samplecharacteristics")
        s_rate = ET.SubElement(sample, "rate")
        ET.SubElement(s_rate, "timebase").text = str(FPS)
        ET.SubElement(s_rate, "ntsc").text = "FALSE"
        ET.SubElement(sample, "width").text = "1920"
        ET.SubElement(sample, "height").text = "1080"
    
    if has_audio:
        a = ET.SubElement(media, "audio")
        sample = ET.SubElement(a, "samplecharacteristics")
        ET.SubElement(sample, "depth").text = "16"
        ET.SubElement(sample, "samplerate").text = "48000"
        ET.SubElement(a, "channelcount").text = "2"
        
    return elem

# Построение дерева
xmeml = ET.Element("xmeml", version="4")
project = ET.SubElement(xmeml, "project")
ET.SubElement(project, "name").text = "МОДНАЯ ПРОПАГАНДА"
children = ET.SubElement(project, "children")

sequence = ET.SubElement(children, "sequence", id="sequence-main")
ET.SubElement(sequence, "name").text = "МОДНАЯ ПРОПАГАНДА — Master"
ET.SubElement(sequence, "duration").text = "108000"

rate = ET.SubElement(sequence, "rate")
ET.SubElement(rate, "timebase").text = str(FPS)
ET.SubElement(rate, "ntsc").text = "FALSE"

timecode = ET.SubElement(sequence, "timecode")
tc_rate = ET.SubElement(timecode, "rate")
ET.SubElement(tc_rate, "timebase").text = str(FPS)
ET.SubElement(tc_rate, "ntsc").text = "FALSE"
ET.SubElement(timecode, "string").text = "00:00:00:00"
ET.SubElement(timecode, "frame").text = "0"
ET.SubElement(timecode, "displayformat").text = "NDF"

media = ET.SubElement(sequence, "media")

# Видео: V1
video = ET.SubElement(media, "video")
v_format = ET.SubElement(video, "format")
v_sample = ET.SubElement(v_format, "samplecharacteristics")
v_s_rate = ET.SubElement(v_sample, "rate")
ET.SubElement(v_s_rate, "timebase").text = str(FPS)
ET.SubElement(v_s_rate, "ntsc").text = "FALSE"
ET.SubElement(v_sample, "width").text = "1920"
ET.SubElement(v_sample, "height").text = "1080"
v_track = ET.SubElement(video, "track")

# Аудио: A1, A2
audio = ET.SubElement(media, "audio")
ET.SubElement(audio, "numOutputChannels").text = "2"
a_format = ET.SubElement(audio, "format")
a_sample = ET.SubElement(a_format, "samplecharacteristics")
ET.SubElement(a_sample, "depth").text = "16"
ET.SubElement(a_sample, "samplerate").text = "48000"
a_track_1 = ET.SubElement(audio, "track")
a_track_2 = ET.SubElement(audio, "track")

# 1. Заполняем V1 клипами с камеры
current_cursor = 0
for idx, cam in enumerate(CAM_FILES, 1):
    clip = ET.SubElement(v_track, "clipitem", id=f"cam-clip-{idx}")
    ET.SubElement(clip, "name").text = cam["name"]
    ET.SubElement(clip, "duration").text = str(cam["duration"])
    c_rate = ET.SubElement(clip, "rate")
    ET.SubElement(c_rate, "timebase").text = str(FPS)
    ET.SubElement(c_rate, "ntsc").text = "FALSE"
    ET.SubElement(clip, "in").text = "0"
    ET.SubElement(clip, "out").text = str(cam["duration"])
    ET.SubElement(clip, "start").text = str(current_cursor)
    ET.SubElement(clip, "end").text = str(current_cursor + cam["duration"])
    clip.append(create_file_element(cam, has_video=True, has_audio=True))
    current_cursor += cam["duration"]

# 2. Заполняем A1 и A2 чистым войсовером
for trk_idx, a_track in enumerate([a_track_1, a_track_2], 1):
    clip = ET.SubElement(a_track, "clipitem", id=f"vo-clip-{trk_idx}")
    ET.SubElement(clip, "name").text = VO_FILE["name"]
    ET.SubElement(clip, "duration").text = str(VO_FILE["duration"])
    c_rate = ET.SubElement(clip, "rate")
    ET.SubElement(c_rate, "timebase").text = str(FPS)
    ET.SubElement(c_rate, "ntsc").text = "FALSE"
    ET.SubElement(clip, "in").text = "0"
    ET.SubElement(clip, "out").text = str(VO_FILE["duration"])
    ET.SubElement(clip, "start").text = "0"
    ET.SubElement(clip, "end").text = str(VO_FILE["duration"])
    clip.append(create_file_element(VO_FILE, has_video=False, has_audio=True))
    
    st = ET.SubElement(clip, "sourcetrack")
    ET.SubElement(st, "mediatype").text = "audio"
    ET.SubElement(st, "trackindex").text = str(trk_idx)

# Экспорт
xml_str = ET.tostring(xmeml, encoding="utf-8")
dom = minidom.parseString(xml_str)
pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
if pretty.startswith('<?xml'):
    pretty = pretty.split('\n', 1)[1]

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(header + pretty)

print(f"Готово: {OUTPUT_PATH}")