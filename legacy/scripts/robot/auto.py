#!/usr/bin/env python3
"""auto.py spec.json stage1|stage2   (запускать в песочнице на компе)
spec: {"folder","source","tag","seq_name","fps":25,"pieces":[{"a":954,"b":978,"o":950,"sw":"18 июня","ew":"везут военные","wf":"work/m2_1.raw.srt.words.json"}],
       "fixes":[["regex","repl"]], "over":{"1.3":{"scale":56.25,"x":0.5}}}
o = смещение окна расшифровки (сек исходника), a/b = таймкоды ТЗ (сек)."""
import sys, os, re, json, math, subprocess, difflib
import numpy as np
R = os.path.dirname(os.path.abspath(__file__)); os.chdir(R)
spec = json.load(open(sys.argv[1], encoding='utf-8')); stage = sys.argv[2]
FPS = spec.get('fps', 25)
S = os.path.join('..', spec['folder'], spec['source'])
tag = spec['tag']

def norm(w): return re.sub(r'[^\w]', '', w.lower().replace('ё', 'е'))
def fz(a, b): return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()

def energy(t0, t1):
    raw = subprocess.run(['ffmpeg','-v','error','-ss',f'{t0:.3f}','-t',f'{t1-t0:.3f}','-i',S,'-vn','-ac','1','-ar','16000','-f','s16le','-'],capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(float)
    n = len(a)//320
    return np.array([np.sqrt(np.mean(a[i*320:(i+1)*320]**2)) for i in range(n)])  # шаг 20 мс

def find_start(W, o, a, phrase):
    toks = phrase.split(); best = None
    for i, w in enumerate(W):
        if fz(w['w'], toks[0]) < 0.6: continue
        d = abs(o + w['s'] - a)
        if best is None or d < best[0]: best = (d, i)
    return best[1] if best and best[0] < 2.5 else min(range(len(W)), key=lambda i: abs(o + W[i]['s'] - a))

def find_end(W, o, b, phrase):
    last = phrase.split()[-1]; best = None
    for i, w in enumerate(W):
        if fz(w['w'], last) < 0.6: continue
        d = abs(o + w['e'] - b)
        if best is None or d < best[0]: best = (d, i)
    return best[1] if best and best[0] < 2.5 else min(range(len(W)), key=lambda i: abs(o + W[i]['e'] - b))

def refine_start(t):
    t0 = t - 0.45; E = energy(t0, t + 0.35)
    thr = max(np.percentile(E, 15) * 3, 300)
    # ищем последний тихий отрезок (>=80 мс) перед началом речи вблизи t; старт = конец этой тишины
    quiet = E < thr; best = None
    for i in range(len(E) - 4):
        if quiet[i:i+4].all():
            j = i + 4
            while j < len(E) and quiet[j]: j += 1
            if j < len(E):
                c = (abs(t0 + j*0.02 - t), t0 + j*0.02)
                if best is None or c[0] < best[0]: best = c
    cand = [c for c in [best] if c]
    return cand[0][1] - 0.04 if cand else t - 0.1

def refine_end(t, nxt):
    t0 = t - 0.1; E = energy(t0, t + 1.0)
    thr = max(np.percentile(E, 10) * 4, 700)
    quiet = E < thr
    for i in range(len(E) - 4):
        if quiet[i:i+4].all():
            return t0 + i*0.02 + 0.10
    return t + 0.3

if stage == 'stage1':
    plan = []
    for k, p in enumerate(spec['pieces'], 1):
        W = json.load(open(p['wf'], encoding='utf-8')); o = p['o']
        si = find_start(W, o, p['a'], p['sw']); ei = find_end(W, o, p['b'], p['ew'])
        ws = o + W[si]['s']; we = o + W[ei]['e']
        # склейки во всём окне куска (с запасом)
        sc = subprocess.run(['ffmpeg','-v','info','-ss',f'{ws-1.0:.3f}','-t',f'{we-ws+2.5:.3f}','-i',S,'-vf',"select='gt(scene,0.25)',showinfo",'-an','-f','null','-'],capture_output=True,text=True).stderr
        allc = sorted(math.ceil(round((float(x) + ws - 1.0)*FPS, 3)) for x in re.findall(r'pts_time:([0-9.]+)', sc))
        # СТАРТ (правила Артёма от 29.09): слово из расшифровки + 0.06 с; если рядом склейка — старт на 2 кадра после неё
        # (короткий кусочек прошлого плана перед склейкой не оставляем)
        if 's' in p: sf = math.floor(round(p['s']*FPS, 3))
        else:
            sf = round((ws + 0.06)*FPS)
            near = [c for c in allc if sf - 9 <= c <= sf + 4]
            if near: sf = min(near, key=lambda c: abs(c - sf)) + 2
        # КОНЕЦ: тишина после слова, но не короче слово+0.06 и не длиннее слово+0.16
        if 'e' in p: ef = math.ceil(round(p['e']*FPS, 3))
        else:
            nxt = o + W[ei + 1]['s'] if ei + 1 < len(W) else None
            e = min(max(refine_end(we, nxt), we + 0.06), we + 0.16)
            ef = math.ceil(round(e*FPS, 3))
        print(f'кусок {k}: слово-старт «{W[si]["w"]}» {ws:.2f} → старт {sf/FPS:.2f}; слово-конец «{W[ei]["w"]}» {we:.2f} → конец {ef/FPS:.2f}; длина {(ef-sf)/FPS:.2f}с')
        cf = []
        for f in allc:
            if f <= sf + 2 or f >= ef - 2: continue
            if cf and f - cf[-1] <= 3: continue
            cf.append(f)
        plan.append({'sf': sf, 'ef': ef, 'cuts': cf})
    T = 0
    for p in plan: p['T'] = T; T += p['ef'] - p['sf']
    json.dump(plan, open(f'work/{tag}_plan.json', 'w'), indent=1)
    # склеенный звук
    fl = ';'.join(f"[0:a]atrim=start={p['sf']/FPS:.3f}:end={p['ef']/FPS:.3f},asetpts=PTS-STARTPTS[a{i}]" for i, p in enumerate(plan))
    fl += ';' + ''.join(f'[a{i}]' for i in range(len(plan))) + f'concat=n={len(plan)}:v=0:a=1,aresample=16000,pan=mono|c0=c0[o]'
    subprocess.run(['ffmpeg','-y','-v','error','-i',S,'-filter_complex',fl,'-map','[o]',f'work/{tag}_final.wav'], check=True)
    json.dump({"type":"transcribe","input":f"_Робот/work/{tag}_final.wav","output":f"_Робот/work/{tag}_final.srt","offset":0,"model":"large-v3","novad":True}, open(f'queue/9{tag}_final.json','w'))
    # лица и кадры середин
    import cv2
    det = cv2.FaceDetectorYN.create('work/models/yunet.onnx','',(960,540),0.8); Wf = 1080/3413.33
    planes = []; ims = []
    for k, p in enumerate(plan, 1):
        b = [p['sf']] + p['cuts'] + [p['ef']]
        for j in range(len(b) - 1):
            a_, e_ = b[j], b[j+1]
            raw = subprocess.run(['ffmpeg','-v','error','-ss',f'{a_/FPS:.3f}','-t',f'{(e_-a_)/FPS:.3f}','-i',S,'-an','-vf','fps=5,scale=960:540','-f','rawvideo','-pix_fmt','bgr24','-'],capture_output=True).stdout
            fr = np.frombuffer(raw, np.uint8).reshape(-1, 540, 960, 3); xs = []
            for f in fr:
                _, d = det.detect(f)
                if d is None: continue
                d = [x for x in d if x[2] >= 40]
                if d: x = max(d, key=lambda x: x[2]*x[3]); xs.append((x[0]+x[2]/2)/960)
            x = 0.5; note = 'нет лица'
            if xs and len(fr):
                best = None
                for c in np.arange(min(xs), max(xs)+0.001, 0.005):
                    v = sum(1 for q in xs if abs(q-c) < Wf/2-0.04)/len(fr); sc_ = (v, -abs(c-np.median(xs)))
                    if best is None or sc_ > best[0]: best = (sc_, c)
                x = round(0.5-(best[1]-0.5)*3.1605, 4); note = f'лицо в кадре {best[0][0]:.0%}'
            planes.append({'piece': k, 'sf': a_, 'ef': e_, 'x': x, 'scale': 177.7778, 'note': note})
            mid = fr[len(fr)//2] if len(fr) else np.zeros((540,960,3),np.uint8)
            im = cv2.resize(mid, (384, 216)); cv2.putText(im, f'{len(planes)} {note}', (5,20), 0, 0.5, (0,255,255), 2); ims.append(im)
    while len(ims) % 4: ims.append(np.zeros((216,384,3), np.uint8))
    cv2.imwrite(f'work/{tag}_sheet.jpg', np.vstack([np.hstack(ims[i:i+4]) for i in range(0, len(ims), 4)]))
    json.dump(planes, open(f'work/{tag}_planes.json', 'w'), ensure_ascii=False, indent=1)
    for i, p in enumerate(planes, 1): print(i, p)

if stage == 'stage2':
    sys.path.insert(0, R); import make_srt2
    plan = json.load(open(f'work/{tag}_plan.json')); planes = json.load(open(f'work/{tag}_planes.json'))
    W = json.load(open(f'work/{tag}_final.srt.words.json', encoding='utf-8'))
    pieces = []
    for k, p in enumerate(plan):
        a = p['T']/FPS; b = a + (p['ef']-p['sf'])/FPS
        ws = [dict(w=x['w'], s=x['s']-a, e=x['e']-a) for x in W if a - 0.2 <= x['s'] < b - 0.2 and norm(x['w']) not in [norm(d) for d in spec.get('drop', [])]]
        fn = f'work/{tag}_w{k}.json'; json.dump(ws, open(fn, 'w'), ensure_ascii=False); pieces.append((a, fn))
    dst = os.path.join('..', spec['folder'], spec['seq_name'] + '.corrected.srt')
    for t in make_srt2.build(pieces, dst, [tuple(x) for x in spec.get('fixes', [])], 22): print(t.split('\n')[1], '|', t.split('\n')[2])
    over = spec.get('over', {})
    pl = []
    for i, p in enumerate(planes, 1):
        o = over.get(str(i), {})
        pl.append({'s': p['sf'] - [q for q in plan if q['sf'] <= p['sf'] < q['ef']][0]['sf'] + [q for q in plan if q['sf'] <= p['sf'] < q['ef']][0]['T'],
                   'in': p['sf'], 'x': o.get('x', p['x']), 'scale': o.get('scale', p['scale'])})
    for i, p in enumerate(pl): p['e'] = pl[i+1]['s'] if i+1 < len(pl) else plan[-1]['T'] + plan[-1]['ef'] - plan[-1]['sf']
    total = pl[-1]['e']
    auds = [{'s': q['T'], 'e': q['T'] + q['ef'] - q['sf'], 'in': q['sf']} for q in plan]
    Wn = 'C:/Users/Artem/Videos/VARLAMOV/Shorts/' + spec['folder'] + '/'
    vd = float(subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=duration','-of','csv=p=0',S],capture_output=True,text=True).stdout)
    ad = float(subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration','-of','csv=p=0',S],capture_output=True,text=True).stdout)
    job = {'seq_name': spec['seq_name'], 'out': os.path.abspath(os.path.join('..', spec['folder'], spec['seq_name'] + ' (черновик агента).prproj')),
           'source': Wn + spec['source'], 'cover': Wn + 'maxresdefault.jpg', 'srt': os.path.abspath(dst),
           'audio_in': auds[0]['in'], 'audios': auds, 'speech_end': total, 'vdur': vd, 'adur': ad, 'planes': pl}
    json.dump(job, open(f'prproj/job_{tag}.json', 'w'), ensure_ascii=False, indent=1)
    subprocess.check_call([sys.executable, 'prproj/собрать.py', f'job_{tag}.json'])
