import xml.etree.ElementTree as ET
from xml.dom import minidom

def make_valid_premiere_xml(output_path, clips, markers, fps=60):
    xmeml = ET.Element("xmeml", version="4")
    project = ET.SubElement(xmeml, "project")
    ET.SubElement(project, "name").text = "MarkFlow Project"
    
    children = ET.SubElement(project, "children")
    sequence = ET.SubElement(children, "sequence", id="sequence-1")
    ET.SubElement(sequence, "name").text = "МОДНАЯ ПРОПАГАНДА — AutoCut Test"
    ET.SubElement(sequence, "duration").text = "0" # обновится в конце
    
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(fps)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    
    # Секция таймкода
    timecode = ET.SubElement(sequence, "timecode")
    tc_rate = ET.SubElement(timecode, "rate")
    ET.SubElement(tc_rate, "timebase").text = str(fps)
    ET.SubElement(tc_rate, "ntsc").text = "FALSE"
    ET.SubElement(timecode, "string").text = "00:00:00:00"
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"
    
    media = ET.SubElement(sequence, "media")
    
    # Видео часть и настройки формата кадра 1080p60
    video = ET.SubElement(media, "video")
    v_format = ET.SubElement(video, "format")
    v_sample = ET.SubElement(v_format, "samplecharacteristics")
    v_s_rate = ET.SubElement(v_sample, "rate")
    ET.SubElement(v_s_rate, "timebase").text = str(fps)
    ET.SubElement(v_s_rate, "ntsc").text = "FALSE"
    ET.SubElement(v_sample, "width").text = "1920"
    ET.SubElement(v_sample, "height").text = "1080"
    ET.SubElement(v_sample, "anamorphic").text = "FALSE"
    ET.SubElement(v_sample, "pixelaspectratio").text = "square"
    ET.SubElement(v_sample, "fielddominance").text = "none"
    
    v_track = ET.SubElement(video, "track")
    
    # Аудио часть
    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "numOutputChannels").text = "2"
    a_format = ET.SubElement(audio, "format")
    a_sample = ET.SubElement(a_format, "samplecharacteristics")
    ET.SubElement(a_sample, "depth").text = "16"
    ET.SubElement(a_sample, "samplerate").text = "48000"
    
    a_track_1 = ET.SubElement(audio, "track")
    a_track_2 = ET.SubElement(audio, "track")

    curr_timeline_frame = 0

    for idx, c in enumerate(clips):
        in_frame = int(c["in_sec"] * fps)
        out_frame = int(c["out_sec"] * fps)
        duration = out_frame - in_frame
        clip_id_suffix = f"-{idx+1}"
        
        # --- V1 ---
        v_clip = ET.SubElement(v_track, "clipitem", id=f"clipitem-v{clip_id_suffix}")
        ET.SubElement(v_clip, "name").text = c["source_name"]
        ET.SubElement(v_clip, "duration").text = str(int(c.get("src_total_sec", 1800) * fps))
        v_c_rate = ET.SubElement(v_clip, "rate")
        ET.SubElement(v_c_rate, "timebase").text = str(fps)
        ET.SubElement(v_c_rate, "ntsc").text = "FALSE"
        ET.SubElement(v_clip, "in").text = str(in_frame)
        ET.SubElement(v_clip, "out").text = str(out_frame)
        ET.SubElement(v_clip, "start").text = str(curr_timeline_frame)
        ET.SubElement(v_clip, "end").text = str(curr_timeline_frame + duration)
        
        # Полное описание файла источника
        f_elem = ET.SubElement(v_clip, "file", id="source-file-1")
        ET.SubElement(f_elem, "name").text = c["source_name"]
        ET.SubElement(f_elem, "pathurl").text = c["source_url"]
        f_rate = ET.SubElement(f_elem, "rate")
        ET.SubElement(f_rate, "timebase").text = str(fps)
        ET.SubElement(f_rate, "ntsc").text = "FALSE"
        ET.SubElement(f_elem, "duration").text = str(int(c.get("src_total_sec", 1800) * fps))
        
        f_media = ET.SubElement(f_elem, "media")
        f_v = ET.SubElement(f_media, "video")
        f_v_sample = ET.SubElement(f_v, "samplecharacteristics")
        f_v_s_rate = ET.SubElement(f_v_sample, "rate")
        ET.SubElement(f_v_s_rate, "timebase").text = str(fps)
        ET.SubElement(f_v_s_rate, "ntsc").text = "FALSE"
        ET.SubElement(f_v_sample, "width").text = "1920"
        ET.SubElement(f_v_sample, "height").text = "1080"
        
        f_a = ET.SubElement(f_media, "audio")
        f_a_sample = ET.SubElement(f_a, "samplecharacteristics")
        ET.SubElement(f_a_sample, "depth").text = "16"
        ET.SubElement(f_a_sample, "samplerate").text = "48000"
        ET.SubElement(f_a, "channelcount").text = "2"
        
        # Связки дорожек
        link_v = ET.SubElement(v_clip, "link")
        ET.SubElement(link_v, "linkclipref").text = f"clipitem-v{clip_id_suffix}"
        ET.SubElement(link_v, "mediatype").text = "video"
        ET.SubElement(link_v, "trackindex").text = "1"
        ET.SubElement(link_v, "clipindex").text = str(idx + 1)
        
        link_a1 = ET.SubElement(v_clip, "link")
        ET.SubElement(link_a1, "linkclipref").text = f"clipitem-a1{clip_id_suffix}"
        ET.SubElement(link_a1, "mediatype").text = "audio"
        ET.SubElement(link_a1, "trackindex").text = "1"
        ET.SubElement(link_a1, "clipindex").text = str(idx + 1)
        
        link_a2 = ET.SubElement(v_clip, "link")
        ET.SubElement(link_a2, "linkclipref").text = f"clipitem-a2{clip_id_suffix}"
        ET.SubElement(link_a2, "mediatype").text = "audio"
        ET.SubElement(link_a2, "trackindex").text = "2"
        ET.SubElement(link_a2, "clipindex").text = str(idx + 1)

        # --- A1 & A2 ---
        for a_num, a_trk in enumerate([a_track_1, a_track_2], start=1):
            a_clip = ET.SubElement(a_trk, "clipitem", id=f"clipitem-a{a_num}{clip_id_suffix}")
            ET.SubElement(a_clip, "name").text = c["source_name"]
            ET.SubElement(a_clip, "duration").text = str(int(c.get("src_total_sec", 1800) * fps))
            a_c_rate = ET.SubElement(a_clip, "rate")
            ET.SubElement(a_c_rate, "timebase").text = str(fps)
            ET.SubElement(a_c_rate, "ntsc").text = "FALSE"
            ET.SubElement(a_clip, "in").text = str(in_frame)
            ET.SubElement(a_clip, "out").text = str(out_frame)
            ET.SubElement(a_clip, "start").text = str(curr_timeline_frame)
            ET.SubElement(a_clip, "end").text = str(curr_timeline_frame + duration)
            ET.SubElement(a_clip, "file", id="source-file-1")
            
            # Source track assignment
            sourcetrack = ET.SubElement(a_clip, "sourcetrack")
            ET.SubElement(sourcetrack, "mediatype").text = "audio"
            ET.SubElement(sourcetrack, "trackindex").text = str(a_num)

        curr_timeline_frame += duration

    sequence.find("duration").text = str(curr_timeline_frame)

    # Маркеры
    for m in markers:
        m_frame = int(m["time_sec"] * fps)
        m_elem = ET.SubElement(sequence, "marker")
        ET.SubElement(m_elem, "name").text = m["title"]
        ET.SubElement(m_elem, "comment").text = f"ЯКОРЬ: {m['anchor']}\nИДЕЯ: {m['idea']}\nSFX: {m.get('sfx', 'нет')}"
        ET.SubElement(m_elem, "in").text = str(m_frame)
        ET.SubElement(m_elem, "out").text = str(m_frame)

    # Сборка XML со строгим заголовком
    xml_str = ET.tostring(xmeml, encoding="utf-8")
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    
    # Добавляем стандартный doctype FCP XML
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    if pretty_xml.startswith('<?xml'):
        pretty_xml = pretty_xml.split('\n', 1)[1]
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + pretty_xml)

clips_data = [
    {
        "source_name": "Копия Keyed-Video_2608311425_0001.mov",
        "source_url": "file://localhost/C:/Users/Artem/Videos/%D0%9C%D0%B0%D0%BA%D0%B0%D1%88%D0%B5%D0%BD%D0%B5%D1%86/%D0%9C%D0%9E%D0%94%D0%9D%D0%90%D0%AF%20%D0%9F%D0%A0%D0%9E%D0%9F%D0%90%D0%93%D0%90%D0%9D%D0%94%D0%90/%D0%9A%D0%BE%D0%BF%D0%B8%D1%8F%20Keyed-Video_2608311425_0001.mov",
        "src_total_sec": 1731,
        "in_sec": 14.20,
        "out_sec": 52.80
    },
    {
        "source_name": "Копия Keyed-Video_2608311425_0001.mov",
        "source_url": "file://localhost/C:/Users/Artem/Videos/%D0%9C%D0%B0%D0%BA%D0%B0%D1%88%D0%B5%D0%BD%D0%B5%D1%86/%D0%9C%D0%9E%D0%94%D0%9D%D0%90%D0%AF%20%D0%9F%D0%A0%D0%9E%D0%9F%D0%90%D0%93%D0%90%D0%9D%D0%94%D0%90/%D0%9A%D0%BE%D0%BF%D0%B8%D1%8F%20Keyed-Video_2608311425_0001.mov",
        "src_total_sec": 1731,
        "in_sec": 68.15,
        "out_sec": 114.40
    }
]

markers_data = [
    {
        "time_sec": 24.5,
        "title": "🎮 HUD / ВЫБОР СКИНА",
        "anchor": "выходит план даллеса всё-таки работает",
        "idea": "Игровая плашка ачивки или стат-карточка с разблокировкой",
        "sfx": "Taco Bell"
    }
]

make_valid_premiere_xml("MODNAYA_PROPAGANDA_ROUGHCUT_TEST.xml", clips_data, markers_data)