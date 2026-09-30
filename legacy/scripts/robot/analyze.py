# analyze.py <source> <pieces.json> <out.json>
# pieces.json: [[word_start, word_end], ...]  (seconds in source)
import sys, json, subprocess, numpy as np, cv2, math, os
src, pj, outp = sys.argv[1:4]
pieces = json.load(open(pj))
FPS = 30.0
def audio(t0, dur):
    raw = subprocess.run(['ffmpeg','-v','error','-ss',f'{t0:.3f}','-t',f'{dur:.3f}','-i',src,'-vn','-ac','1','-ar','16000','-f','s16le','-'],capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32)
def quiet(t, lo, hi):
    a = audio(t+lo, hi-lo); n = 160
    best, bt = 1e18, t
    for i in range(0, len(a)-n, 16):
        r = float(np.sqrt(np.mean(a[i:i+n]**2)))
        if r < best: best, bt = r, t+lo+(i+n/2)/16000
    return bt
def scenes(t0, t1):
    p = subprocess.run(['ffmpeg','-v','info','-ss',f'{t0:.3f}','-t',f'{t1-t0:.3f}','-i',src,'-an','-vf',"select='gt(scene,0.3)',showinfo",'-f','null','-'],capture_output=True,text=True).stderr
    out=[]
    for line in p.splitlines():
        if 'pts_time:' in line:
            out.append(t0+float(line.split('pts_time:')[1].split()[0]))
    return out
det = cv2.FaceDetectorYN.create(os.path.join(os.path.dirname(__file__),'work','models','yunet.onnx'),'',(960,540),0.8)
def faces(t0, t1):
    raw = subprocess.run(['ffmpeg','-v','error','-ss',f'{t0:.3f}','-t',f'{t1-t0:.3f}','-i',src,'-an','-vf','fps=5,scale=960:540','-f','rawvideo','-pix_fmt','bgr24','-'],capture_output=True).stdout
    fr = np.frombuffer(raw,np.uint8).reshape(-1,540,960,3)
    res=[]
    for f in fr:
        _, d = det.detect(f)
        if d is None: res.append(None); continue
        d = [x for x in d if x[2] >= 40]
        if not d: res.append(None); continue
        x = max(d, key=lambda x: x[2]*x[3])
        res.append(((x[0]+x[2]/2)/960, x[2]))
    return res
W = 1080/3413.33  # visible width in source units at scale 177.78
out=[]; tl=0.0
for (ws, we) in pieces:
    i0 = quiet(ws, -0.08, 0.02); o0 = quiet(we, -0.02, 0.08)
    i0 = round(i0*FPS)/FPS
    nfr = round((o0-i0)*FPS); o0 = i0 + nfr/FPS
    cuts = [c for c in scenes(i0, o0) if c-i0 > 0.05 and o0-c > 0.05]
    bounds=[i0]+cuts+[o0]
    plans=[]
    for a,b in zip(bounds[:-1],bounds[1:]):
        ka = 0 if a==i0 else math.ceil(round((a-i0)*FPS,3))
        kb = nfr if b==o0 else math.ceil(round((b-i0)*FPS,3))
        if kb<=ka: continue
        fs = faces(a, b)
        xs = [f[0] for f in fs if f]
        cover = len(xs)/max(1,len(fs))
        pos = None; vis = 0
        if xs and cover >= 0.4 and (b-a) > 0.6:
            best=None
            for c in np.arange(min(xs), max(xs)+0.001, 0.005):
                v = sum(1 for x in xs if abs(x-c) < W/2-0.03)/len(fs)
                score=(v, -abs(c-np.median(xs)))
                if best is None or score>best[0]: best=(score,c)
            c=best[1]; vis=best[0][0]
            pos = 0.5-(c-0.5)*3.1605
            pos = max(1-1.58, min(1.58, pos))
        plans.append(dict(src_in=i0+ka/FPS, tl_start=tl+ka/FPS, tl_end=tl+kb/FPS, cut=a, face_cover=round(cover,2), face_vis=round(vis,2), pos_x=None if pos is None else round(pos,4)))
    out.append(dict(word_start=ws, word_end=we, src_in=i0, src_out=o0, tl_start=tl, tl_end=tl+nfr/FPS, plans=plans))
    tl += nfr/FPS
json.dump(out, open(outp,'w'), ensure_ascii=False, indent=1)
for p in out:
    print(f"piece src {p['src_in']:.3f}-{p['src_out']:.3f} tl {p['tl_start']:.3f}-{p['tl_end']:.3f}")
    for q in p['plans']: print('   ', q)
