# faster-whisper -> SRT, one short line per title (house style: ~26 chars, one line)
import sys, os, glob, re, site
for sp in site.getsitepackages():
    for d in glob.glob(os.path.join(sp, 'nvidia', '*', 'bin')):
        os.add_dll_directory(d); os.environ['PATH'] = d + os.pathsep + os.environ['PATH']
from faster_whisper import WhisperModel
src, dst, model_name = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else 'large-v3')
NOVAD = len(sys.argv) > 4 and sys.argv[4] == 'novad'
try:
    model = WhisperModel(model_name, device='cuda', compute_type='float16'); dev = 'cuda'
    segs, info = model.transcribe(src, language='ru', word_timestamps=True, vad_filter=not NOVAD, beam_size=5)
    segs = list(segs)
except Exception as e:
    print('GPU failed, CPU fallback:', e)
    model = WhisperModel('medium', device='cpu', compute_type='int8'); dev = 'cpu'
    segs, info = model.transcribe(src, language='ru', word_timestamps=True, vad_filter=not NOVAD, beam_size=5)
    segs = list(segs)
MAX = 32
cues = []
for s in segs:
    cur = []
    for w in (s.words or []):
        t = w.word.strip()
        if not t: continue
        text = ' '.join(x[2] for x in cur + [(0, 0, t)])
        if cur and len(text) > MAX:
            cues.append(cur); cur = []
        cur.append((w.start, w.end, t))
        if re.search(r'[.!?…]$', t) and len(' '.join(x[2] for x in cur)) > 12:
            cues.append(cur); cur = []
    if cur: cues.append(cur)
def ts(x):
    ms = int(round(x * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'
with open(dst, 'w', encoding='utf-8') as f:
    for i, c in enumerate(cues, 1):
        f.write(f"{i}\n{ts(c[0][0])} --> {ts(c[-1][1])}\n{' '.join(x[2] for x in c)}\n\n")
import json
ws=[{'s':round(w.start,3),'e':round(w.end,3),'w':w.word.strip()} for sg in segs for w in (sg.words or [])]
json.dump(ws, open(dst+'.words.json','w',encoding='utf-8'), ensure_ascii=False)
print(f'OK {len(cues)} cues, device={dev}, model={model_name if dev=="cuda" else "medium"}')
