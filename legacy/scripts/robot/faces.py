# faces.py <source> <ranges.json>  -> prints best fixed pos_x for each [a,b]
import sys, json, subprocess, numpy as np, cv2, os
src=sys.argv[1]; rs=json.load(open(sys.argv[2]))
det = cv2.FaceDetectorYN.create(os.path.join(os.path.dirname(os.path.abspath(__file__)),'work','models','yunet.onnx'),'',(960,540),0.8)
W=1080/3413.33
for a,b in rs:
    raw=subprocess.run(['ffmpeg','-v','error','-ss',f'{a:.3f}','-t',f'{b-a:.3f}','-i',src,'-an','-vf','fps=5,scale=960:540','-f','rawvideo','-pix_fmt','bgr24','-'],capture_output=True).stdout
    fr=np.frombuffer(raw,np.uint8).reshape(-1,540,960,3); xs=[]
    for f in fr:
        _,d=det.detect(f)
        if d is None: continue
        d=[x for x in d if x[2]>=40]
        if d: x=max(d,key=lambda x:x[2]*x[3]); xs.append((x[0]+x[2]/2)/960)
    if not xs: print(a,b,'no face'); continue
    best=None
    for c in np.arange(min(xs),max(xs)+0.001,0.005):
        v=sum(1 for x in xs if abs(x-c)<W/2-0.04)/len(fr); s=(v,-abs(c-np.median(xs)))
        if best is None or s>best[0]: best=(s,c)
    c=best[1]; print(a,b,f'cover={len(xs)/len(fr):.2f} vis={best[0][0]:.2f} x_range={min(xs):.3f}-{max(xs):.3f} pos_x={0.5-(c-0.5)*3.1605:.4f}')
