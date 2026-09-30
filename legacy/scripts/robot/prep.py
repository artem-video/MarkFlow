# prep.py <job.json> [result.json] [log.txt] [--no-asr]
# Готовит план сборки шортса: точные границы кусков по словам, планы (склейки), кадрирование,
# титры (.corrected.srt), проверка распознаванием собранного звука -> work\ПЛАН_<name>.md + <name>_plan.json
import sys, os, json, re, math, glob, shutil, subprocess, difflib, time, wave, traceback
import numpy as np
ROOT = os.path.dirname(os.path.abspath(__file__)); SHORTS = os.path.dirname(ROOT); WORK = os.path.join(ROOT, 'work')
FPS = 25.0; FR = 1 / FPS
NO_ASR = '--no-asr' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]
JOB = args[0] if args else None; RES = args[1] if len(args) > 1 else None; LOGF = args[2] if len(args) > 2 else None
T0 = time.time()
def log(*m):
    s = time.strftime('%H:%M:%S') + '  ' + ' '.join(str(x) for x in m)
    try: print(s, flush=True)
    except Exception: pass
    if LOGF:
        with open(LOGF, 'a', encoding='utf-8') as f: f.write(s + '\n')
class PrepError(Exception): pass

def find_ffmpeg():
    f = shutil.which('ffmpeg')
    if f: return f
    g = glob.glob(os.path.join(os.environ.get('USERPROFILE', ''), '.stacher', '**', 'ffmpeg.exe'), recursive=True)
    if g: return g[0]
    raise PrepError('не найден ffmpeg (ни в PATH, ни в %USERPROFILE%\\.stacher)')
FF = None
def run(a): return subprocess.run([FF] + a, capture_output=True, stdin=subprocess.DEVNULL)

def fr_floor(t): return math.floor(round(t / FR, 3)) * FR
def fr_ceil(t): return math.ceil(round(t / FR, 3)) * FR
def fr_round(t): return round(t / FR) * FR
def r2(t): return round(t + 1e-9, 2)
def tc(s):
    if isinstance(s, (int, float)): return float(s)
    v = 0.0
    for x in str(s).strip().replace(',', '.').split(':'): v = v * 60 + float(x)
    return v

# ---------- text ----------
def norm(s): return re.sub(r'[^0-9a-zа-я*]', '', (s or '').lower().replace('ё', 'е'))
def toks(s): return [t for t in (norm(x) for x in re.split(r'[\s\-–—]+', s or '')) if t]
def tok_sim(h, w):
    if not h or not w: return 0.0
    if '*' in h:
        rx = '^' + '.*'.join(re.escape(x) for x in re.split(r'\*+', h)) + '$'
        return 1.0 if re.match(rx, w) else 0.3
    return difflib.SequenceMatcher(None, h, w).ratio()
def seq_sim(ht, wt):
    if not ht or len(wt) < len(ht): return 0.0
    return sum(tok_sim(a, b) for a, b in zip(ht, wt)) / len(ht)

OBSC = [r'х[уy][йеёяию]', r'пизд', r'^(на|по|за|от|вы|до|у|раз|рас|из|съ|об|под|пере|при|про)?[её]б(а|у|л|н|ё|и|е|ы|щ)',
        r'^бля', r'^сук(а|и|е|у|ой)$', r'^муда[кч]', r'^пид[оа]р', r'^залуп']
def is_mat(w): n = norm(w); return bool(n) and any(re.search(p, n) for p in OBSC)
def censor(w):
    m = re.match(r'^(\W*)([\w\-]+?)(\W*)$', w)
    if not m or not is_mat(w): return w
    a, core, b = m.groups()
    return a + core[0] + '***' + (core[-1] if len(core) > 2 else '') + b

# ---------- audio ----------
def pcm(src, t0, dur, sr=16000):
    raw = run(['-v', 'error', '-ss', f'{max(0, t0):.3f}', '-t', f'{dur:.3f}', '-i', src, '-vn', '-ac', '1', '-ar', str(sr), '-f', 's16le', '-']).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32)
BIN = 0.01
def envelope(src, t0, t1):
    t0 = max(0.0, t0); a = pcm(src, t0, t1 - t0); n = int(16000 * BIN)
    k = len(a) // n
    if k < 5: raise PrepError(f'не удалось прочитать звук {t0:.2f}-{t1:.2f}')
    e = np.sqrt(np.mean(a[:k * n].reshape(k, n) ** 2, axis=1))
    e = np.convolve(e, np.ones(3) / 3, mode='same')   # ~30 ms smoothing
    return t0, e
def ix(t0, t, n): return min(n - 1, max(0, int(round((t - t0) / BIN))))

def quiet_runs(e, a, b, q, minlen=4):
    e = np.convolve(e, np.ones(5) / 5, mode='same')   # extra smoothing: ignore 10-20 ms blips inside a pause
    runs = []; k = a
    while k <= b:
        if e[k] <= q:
            m = k
            while m + 1 <= b and e[m + 1] <= q: m += 1
            if m - k + 1 >= minlen: runs.append((k, m))
            k = m + 1
        else: k += 1
    return runs

def refine_start(src, W, i):
    """start = PAD_S before the speech onset of W[i]; the gap = longest quiet run near the word start"""
    ws = W[i]['s']; pe = W[i - 1]['e'] if i > 0 else ws - 1.0
    t0, e = envelope(src, ws - 1.2, ws + 1.2); n = len(e)
    a, b = ix(t0, max(min(pe, ws) - 0.1, ws - 0.9), n), ix(t0, ws + 0.3, n)
    pk = np.percentile(e[ix(t0, ws, n):ix(t0, ws + 0.8, n) + 1], 95); mn = e[a:b + 1].min()
    runs = quiet_runs(e, a, b, mn + 0.08 * (pk - mn))
    if runs:
        wi = ix(t0, ws, n); g0, g = max(runs, key=lambda r: (r[1] - r[0]) * BIN - 0.3 * abs(r[1] - wi) * BIN - 0.6 * max(0, r[1] - wi - 10) * BIN)
    else: g0 = g = a + int(np.argmin(e[a:b + 1]))
    thr = e[g] + THR * max(0, pk - e[g])
    on = next((k for k in range(g, n) if e[k] > thr), g)
    ton = t0 + on * BIN
    st = max(ton - PAD_S, t0 + g0 * BIN)
    return fr_floor(st), ton

def refine_end(src, W, j):
    """end = after the last word with a tail, but always before the next word's onset"""
    we = W[j]['e']; ns = W[j + 1]['s'] if j + 1 < len(W) else we + 2.0
    t0, e = envelope(src, we - 1.2, we + 1.6); n = len(e)
    a, b = ix(t0, we - 0.25, n), ix(t0, min(max(ns + 0.45, we + 0.8), we + 1.2), n)
    pk = np.percentile(e[ix(t0, we - 0.8, n):ix(t0, we, n) + 1], 95); mn = e[a:b + 1].min()
    runs = quiet_runs(e, a, b, mn + 0.08 * (pk - mn))
    if runs:
        wi = ix(t0, we, n); g, g1 = max(runs, key=lambda r: (r[1] - r[0]) * BIN - 0.3 * abs(r[0] - wi) * BIN - 0.6 * max(0, wi - 10 - r[0]) * BIN)
    else: g = g1 = a + int(np.argmin(e[a:b + 1]))
    thr = e[g] + THR * max(0, pk - e[g])
    off = next((k for k in range(g, -1, -1) if e[k] > thr), g)
    nxt = next((k for k in range(g1, n) if e[k] > thr), n - 1)
    toff = t0 + (off + 1) * BIN; tnx = t0 + nxt * BIN
    en = min(toff + 0.40, tnx - 0.08)
    if en < toff + 0.04: en = min(toff + 0.04, tnx - 0.02)
    c = fr_ceil(en)
    if c > tnx - 0.02: c = fr_floor(en)
    return c, toff, tnx
THR = 0.15; PAD_S = 0.08

# ---------- video ----------
def make_proxy(src, t0, t1, dst):
    p = run(['-v', 'error', '-y', '-ss', f'{t0:.3f}', '-i', src, '-t', f'{t1 - t0:.3f}', '-an', '-vf', 'scale=480:270',
             '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-g', '25', dst])
    if not os.path.exists(dst): raise PrepError('не удалось сделать прокси: ' + p.stderr.decode('utf-8', 'replace')[-300:])
def scene_cuts(proxy, t0, thr=0.3):
    p = run(['-v', 'info', '-i', proxy, '-an', '-vf', f"select='gt(scene,{thr})',showinfo", '-f', 'null', '-'])
    out = []
    for line in p.stderr.decode('utf-8', 'replace').splitlines():
        if 'pts_time:' in line: out.append(r2(fr_round(t0 + float(line.split('pts_time:')[1].split()[0]))))
    return out
_det = None
def detector():
    global _det
    if _det is None:
        try: import cv2
        except ImportError:
            log('нет opencv — ставлю opencv-python-headless (один раз)')
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'opencv-python-headless'], capture_output=True, stdin=subprocess.DEVNULL)
            import cv2
        import tempfile
        mp = os.path.join(WORK, 'models', 'yunet.onnx')
        if not os.path.exists(mp): raise PrepError('нет модели лиц work\\models\\yunet.onnx')
        tmpm = os.path.join(tempfile.gettempdir(), 'yunet_prep.onnx')   # OpenCV on Windows can't open Cyrillic paths
        if not os.path.exists(tmpm) or os.path.getsize(tmpm) != os.path.getsize(mp): shutil.copyfile(mp, tmpm)
        try: _det = cv2.FaceDetectorYN.create(tmpm, '', (960, 540), 0.8)
        except Exception as ex: raise PrepError(f'OpenCV {cv2.__version__} не смог загрузить модель лиц: {ex}')
    return _det
VISW = 1080 / 3413.33
def framing(proxy, t0, a, b):
    raw = run(['-v', 'error', '-ss', f'{a - t0:.3f}', '-t', f'{b - a:.3f}', '-i', proxy, '-an', '-vf', 'fps=5,scale=960:540',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']).stdout
    fsz = 960 * 540 * 3; fr = np.frombuffer(raw, np.uint8)
    if fr.size < fsz: return dict(card=True, scale=56.25, pos_x=0.5, note='карточка (нет кадров)', cover=0.0, face_w=0.0)
    fr = fr[:fr.size // fsz * fsz].reshape(-1, 540, 960, 3)
    xs, wd = [], []
    gray = fr.mean(axis=3)
    diff = float(np.mean(np.abs(np.diff(gray, axis=0)))) if len(gray) > 1 else 0.0
    mid = gray[len(gray) // 2]; dark = float(np.mean(mid < 25)); bright = float(np.mean(mid > 200))
    for f in fr:
        _, d = detector().detect(f)
        if d is None: continue
        d = [x for x in d if x[2] >= 40]
        if d: x = max(d, key=lambda x: x[2] * x[3]); xs.append((x[0] + x[2] / 2) / 960); wd.append(x[2] / 960)
    cover = len(xs) / len(fr); mw = float(np.median(wd)) if wd else 0.0
    info = dict(cover=round(cover, 2), face_w=round(mw, 3), motion=round(diff, 2), dark=round(dark, 2))
    static = diff < 1.0
    if cover < 0.4 or mw < 0.06:
        if static: return dict(card=True, scale=56.25, pos_x=0.5, note='карточка', **info)
        return dict(card=False, scale=177.7778, pos_x=0.5, note='без лица (б-ролл) — проверить', **info)
    if static and (dark > 0.4 or bright > 0.6):
        return dict(card=True, scale=56.25, pos_x=0.5, note='карточка', **info)
    best = None
    for c in np.arange(min(xs), max(xs) + 0.001, 0.005):
        v = sum(1 for x in xs if abs(x - c) < VISW / 2 - 0.04) / len(fr); s = (v, -abs(c - np.median(xs)))
        if best is None or s > best[0]: best = (s, c)
    pos = 0.5 - (best[1] - 0.5) * 3.1605
    return dict(card=False, scale=177.7778, pos_x=round(min(0.8, max(0.2, pos)), 4), note='', **info)

# ---------- asr ----------
def python_asr(wav, out_srt, vad):
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'transcribe.py'), wav, out_srt, 'large-v3', 'vad' if vad else 'novad'],
                       capture_output=True, stdin=subprocess.DEVNULL)
    wj = out_srt + '.words.json'
    if not os.path.exists(wj): raise PrepError('распознавание не удалось: ' + (p.stdout + p.stderr).decode('utf-8', 'replace')[-400:])
    log('  ', ' '.join(p.stdout.decode('utf-8', 'replace').strip().splitlines()[-1:]))
    return json.load(open(wj, encoding='utf-8'))
def write_wav(path, a, sr=16000):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(np.clip(a, -32768, 32767).astype(np.int16).tobytes())

# ---------- main ----------
def main():
    global FF
    if not JOB or not os.path.exists(JOB): raise PrepError('не найден файл задания: ' + str(JOB))
    job = json.load(open(JOB, encoding='utf-8-sig'))
    name = job.get('name'); folder = job.get('folder'); pieces = job.get('pieces') or []
    if not name or not folder or not pieces: raise PrepError('в задании нужны поля name, folder и pieces')
    for n, p in enumerate(pieces, 1):
        if 'in' not in p or 'out' not in p: raise PrepError(f'кусок {n}: нужны поля in и out')
        try: tc(p['in']); tc(p['out'])
        except ValueError: raise PrepError(f'кусок {n}: не понимаю таймкод {p["in"]} / {p["out"]} (нужно Ч:ММ:СС)')
    fdir = os.path.join(SHORTS, folder)
    if not os.path.isdir(fdir): raise PrepError(f'нет папки Shorts\\{folder}')
    FF = find_ffmpeg()
    if job.get('source'): src = os.path.join(fdir, job['source'])
    else:
        mp4 = [f for f in glob.glob(os.path.join(fdir, '*.mp4')) if os.path.getsize(f) > 300e6] or glob.glob(os.path.join(fdir, '*.mp4'))
        if not mp4: raise PrepError(f'в папке {folder} нет исходника mp4')
        src = max(mp4, key=os.path.getsize)
    if not os.path.exists(src): raise PrepError('нет исходника ' + src)
    log('исходник:', os.path.basename(src))
    tmp = os.path.join(WORK, 'prep_' + name); os.makedirs(tmp, exist_ok=True)
    warns = []

    # 1. words -> piece boundaries
    full = [f for f in glob.glob(os.path.join(fdir, '*.words.json')) if 'полный' in os.path.basename(f).lower()]
    if full:
        W = json.load(open(full[0], encoding='utf-8')); log('полная расшифровка:', os.path.basename(full[0]), len(W), 'слов')
    else:
        if NO_ASR: raise PrepError('нет полной расшифровки, а распознавание отключено')
        log('полной расшифровки нет — распознаю только нужные участки')
        mer = []
        for a, b in sorted([tc(p['in']) - 25, tc(p['out']) + 25] for p in pieces):
            if mer and a <= mer[-1][1]: mer[-1][1] = max(mer[-1][1], b)
            else: mer.append([max(0.0, a), b])
        W = []
        for k, (a, b) in enumerate(mer):
            wav = os.path.join(tmp, f'slice{k}.wav'); write_wav(wav, pcm(src, a, b - a))
            for w in python_asr(wav, os.path.join(tmp, f'slice{k}.srt'), True): W.append(dict(w=w['w'], s=w['s'] + a, e=w['e'] + a))
    W = [w for w in W if w['w'].strip()]; W.sort(key=lambda w: w['s'])
    NW = [norm(w['w']) for w in W]

    P = []
    for n, p in enumerate(pieces, 1):
        tin, tout = tc(p['in']), tc(p['out']); hs, he = toks(p.get('hint_start')), toks(p.get('hint_end'))
        best = None
        for i, w in enumerate(W):
            if abs(w['s'] - tin) > 20: continue
            sc = (seq_sim(hs, NW[i:i + len(hs)]) if hs else 0) - 0.004 * abs(w['s'] - tin)
            if best is None or sc > best[0]: best = (sc, i)
        if best is None: raise PrepError(f'кусок {n}: в расшифровке нет слов около {p["in"]}')
        si, i = best; best = None
        for j in range(i, len(W)):
            if W[j]['e'] - tout > 20: break
            if abs(W[j]['e'] - tout) > 20: continue
            sc = (seq_sim(he, NW[max(i, j - len(he) + 1):j + 1]) if he else 0) - 0.004 * abs(W[j]['e'] - tout)
            if best is None or sc > best[0]: best = (sc, j)
        if best is None: raise PrepError(f'кусок {n}: не найден конец около {p["out"]}')
        se, j = best
        txt = ' '.join(w['w'] for w in W[i:j + 1])
        log(f'кусок {n}: слова {W[i]["s"]:.2f}-{W[j]["e"]:.2f} (совпадение {si:.2f}/{se:.2f}) «{txt[:80]}»')
        if hs and si < 0.6: warns.append(f'Кусок {n}: начало «{p.get("hint_start")}» найдено неуверенно (взял «{" ".join(w["w"] for w in W[i:i + 4])}»)')
        if he and se < 0.6: warns.append(f'Кусок {n}: конец «{p.get("hint_end")}» найден неуверенно (взял «{" ".join(w["w"] for w in W[max(i, j - 3):j + 1])}»)')
        st, ton = refine_start(src, W, i); en, toff, tnx = refine_end(src, W, j)
        P.append(dict(n=n, hint=p, i=i, j=j, ws=W[i]['s'], we=W[j]['e'], onset=round(ton, 3), offset=round(toff, 3),
                      next_onset=round(tnx, 3), start=st, end=en, text=txt))

    # 2-3. shots & framing
    for p in P:
        t0 = fr_floor(p['start'] - 1.0); t1 = p['end'] + 1.0
        px = os.path.join(tmp, f'p{p["n"]}.mp4'); make_proxy(src, t0, t1, px)
        cuts = scene_cuts(px, t0)
        st, en = p['start'], p['end']
        for c in cuts:
            if st < c <= st + 0.3 and c < p['onset'] + 0.12: log(f'кусок {p["n"]}: начало {st:.2f} -> склейка {c:.2f}'); st = c
        for c in cuts:
            if en - 0.3 <= c < en and c >= p['offset'] - 0.04: log(f'кусок {p["n"]}: конец {en:.2f} -> склейка {c:.2f}'); en = c; break
        p['start'], p['end'] = r2(st), r2(en)
        inner = [c for c in cuts if st + 0.2 < c < en - 0.2]
        b = [st] + inner + [en]; shots = []
        for a, z in zip(b[:-1], b[1:]):
            shots.append(dict(src_in=r2(a), src_out=r2(z), **framing(px, t0, a, z)))
        p['cuts'] = cuts; p['shots'] = shots
        log(f'кусок {p["n"]}: {p["start"]:.2f}-{p["end"]:.2f}, планов {len(shots)}: ' +
            ', '.join(f'{s["src_in"]:.2f}' + (' карточка' if s['card'] else f' x={s["pos_x"]:.3f}') + f' (лица {s["cover"]}, ш {s["face_w"]}, дв {s.get("motion")})' for s in shots))
        if p['end'] - p['start'] < 0.5: warns.append(f'Кусок {p["n"]}: слишком короткий ({p["end"] - p["start"]:.2f} с)')

    tl = 0.0; rows = []
    for p in P:
        p['tl'] = r2(tl)
        for s in p['shots']:
            rows.append(dict(start=r2(tl + s['src_in'] - p['start']), src_in=s['src_in'], src_out=s['src_out'], scale=s['scale'],
                             pos_x=s['pos_x'], card=s['card'], note=s.get('note', ''), piece=p['n']))
        tl = r2(tl + p['end'] - p['start'])
    total = tl

    # 5. timeline audio + verification
    tlwav = os.path.join(WORK, name + '_tl.wav'); chunks = []
    for p in P:
        a = pcm(src, p['start'], p['end'] - p['start']); need = int(round((p['end'] - p['start']) * 16000))
        chunks.append(np.pad(a, (0, max(0, need - len(a))))[:need])
    write_wav(tlwav, np.concatenate(chunks))
    TW = None
    if not NO_ASR:
        log('распознаю собранный звук (novad)…')
        try: TW = python_asr(tlwav, os.path.join(tmp, name + '_tl.raw.srt'), False)
        except PrepError as ex: warns.append('Проверка распознаванием не удалась: ' + str(ex))
    if TW is None:
        warns.append('Титры и затворы посчитаны по полной расшифровке (без распознавания собранного звука) — проверить тайминг')
        TW = []
        for p in P:
            for w in W[p['i']:p['j'] + 1]:
                TW.append(dict(w=w['w'], s=max(p['tl'], w['s'] - p['start'] + p['tl']), e=min(p['tl'] + p['end'] - p['start'], w['e'] - p['start'] + p['tl'])))
    TW = [w for w in TW if w['w'].strip()]
    for p in P:
        a, z = p['tl'], p['tl'] + p['end'] - p['start']
        # whisper word starts drift early at splices -> a word belongs to the piece where it ENDS
        p['words'] = [dict(w, s=max(w['s'], a + 0.02)) for w in TW if a <= w['e'] - 0.05 < z or (p is P[-1] and w['e'] - 0.05 >= z)]
        p['heard'] = ' '.join(w['w'] for w in p['words'])
        hs, he = toks(p['hint'].get('hint_start')), toks(p['hint'].get('hint_end'))
        nw = [norm(w['w']) for w in p['words']]
        if hs and seq_sim(hs, nw[:len(hs)]) < 0.6:
            warns.append(f'Кусок {p["n"]}: в собранном звуке начинается с «{" ".join(w["w"] for w in p["words"][:4])}», ожидалось «{p["hint"].get("hint_start")}»')
        if he and seq_sim(he, nw[-len(he):] if len(nw) >= len(he) else []) < 0.6:
            warns.append(f'Кусок {p["n"]}: в собранном звуке кончается на «{" ".join(w["w"] for w in p["words"][-4:])}», ожидалось «{p["hint"].get("hint_end")}»')
    shutters = [r2(w['s']) for w in TW if is_mat(w['w'])]
    end_words = r2(max(w['e'] for w in TW)) if TW else total

    # 4. subtitles (make_srt2 house style)
    sys.path.insert(0, ROOT); import make_srt2
    spieces = []
    for p in P:
        f = os.path.join(tmp, f'w{p["n"]}.json')
        json.dump([dict(w=censor(w['w']), s=round(w['s'] - p['tl'], 3), e=round(w['e'] - p['tl'], 3)) for w in p['words']],
                  open(f, 'w', encoding='utf-8'), ensure_ascii=False)
        spieces.append((p['tl'], f))
    srt = os.path.join(fdir, name + '.corrected.srt')
    cues = make_srt2.build(spieces, srt, job.get('fixes', []), job.get('maxlen', 22))
    long = [c.split('\n')[2] for c in cues if len(c.split('\n')[2]) > 26]
    if long: warns.append('Длинные титры (>26 знаков), поправить вручную: ' + ' | '.join(long))

    # 6. output
    prj = os.path.join(fdir, folder + '.prproj')
    L = [f'# {name} ({folder}) — план сборки, сделан автоматически (prep). Пересчитывать НИЧЕГО не надо.',
         f'Проект: Shorts\\{folder}\\{folder}.prproj{"" if os.path.exists(prj) else " (ещё не создан)"} ; исходник = {os.path.basename(src)}, 25fps',
         f'Секвенция: import_sequences из шаблона Shorts Varlamov Template.prproj (секв. «название ролика») -> переименовать «{name}».',
         'Вставка: open_in_source -> set_source_in_out(in+0.02, out=след_in+0.02) -> set_playhead(старт) -> overwrite_from_source(video 1, audio 0), по очереди.',
         'start | src_in | src_out | scale | pos_x']
    for r in rows:
        L.append(f'{r["start"]:.2f} | {r["src_in"]:.2f} | {r["src_out"]:.2f} | {r["scale"]} | {("%.4f" % r["pos_x"]).lstrip("0")}' + (f'   ({r["note"]})' if r['note'] else ''))
    L.append(f'конец {total:.2f}')
    L.append(('Затвор (мат) на A2: ' + ' и '.join(f'{t:.2f}' for t in shutters) + ', обрезать до 0.8 с.' if shutters else 'Мата нет — затвор не нужен.') +
             ' Файл: 1. Оформление\\1. Общее\\7. Звук затвора (для мата)\\Звук затвора (поверх мата).mp3')
    L.append(f'Концовка MOGRT: с ~{end_words:.2f}; fon_full и Fade дотянуть до конца.')
    L.append(f'Титры: Shorts\\{folder}\\{name}.corrected.srt -> create_caption_track.')
    L += ['', '## Куски (исходник)']
    for p in P: L.append(f'{p["n"]}. {p["start"]:.2f}-{p["end"]:.2f} (на таймлайне с {p["tl"]:.2f}) «{p["hint"].get("hint_start", "")} … {p["hint"].get("hint_end", "")}»')
    L += ['', '## Проверка: что слышно в собранном звуке (' + ('распознавание' if not NO_ASR else 'по полной расшифровке') + ')']
    for p in P: L.append(f'{p["n"]}. {p["heard"]}')
    L += ['', '## WARNINGS'] + (['- ' + w for w in warns] or ['- нет'])
    open(os.path.join(WORK, f'ПЛАН_{name}.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    plan = dict(name=name, folder=folder, source=os.path.basename(src), fps=FPS, total=total, rows=rows, shutters=shutters, ending_start=end_words,
                srt=f'{folder}\\{name}.corrected.srt', tl_wav=f'_Робот\\work\\{name}_tl.wav', warnings=warns,
                pieces=[{k: v for k, v in p.items() if k not in ('words', 'i', 'j')} for p in P], seconds=round(time.time() - T0, 1))
    json.dump(plan, open(os.path.join(WORK, f'{name}_plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f'готово за {time.time() - T0:.0f} с, длина {total:.2f}, предупреждений {len(warns)}')
    return dict(ok=True, plan=f'_Робот\\work\\ПЛАН_{name}.md', plan_json=f'_Робот\\work\\{name}_plan.json', srt=plan['srt'],
                total=total, warnings=warns, seconds=plan['seconds'])

if __name__ == '__main__':
    try: r = main()
    except PrepError as ex: r = dict(ok=False, error=str(ex)); log('ОШИБКА:', ex)
    except Exception as ex:
        r = dict(ok=False, error='внутренняя ошибка prep.py: ' + repr(ex) + '\n' + traceback.format_exc()[-1500:]); log(r['error'])
    if RES: json.dump(r, open(RES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sys.exit(0 if r.get('ok') else 1)
