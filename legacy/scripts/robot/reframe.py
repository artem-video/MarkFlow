# per-shot static reframe for 9:16 from 16:9: find the host's face, return Premiere Position X
import cv2, subprocess, numpy as np, json, sys, os
K = 1920*1.77777786/1080   # scaled source width / sequence width
def frames(src, t0, t1, n=7):
    out=[]
    for i in range(n):
        t = t0 + (t1-t0)*(i+0.5)/n
        p = subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-ss',f'{t:.3f}','-i',src,'-frames:v','1','-f','rawvideo','-pix_fmt','bgr24','-s','960x540','-'],capture_output=True).stdout
        if len(p)==960*540*3: out.append(np.frombuffer(p,np.uint8).reshape(540,960,3))
    return out
det = cv2.FaceDetectorYN.create(os.path.expanduser('~/yunet.onnx'), '', (960,540), 0.7)
def shot_x(src,t0,t1):
    xs=[];ws=[]
    for f in frames(src,t0,t1):
        _, faces = det.detect(f)
        if faces is None: continue
        big = max(faces, key=lambda r: r[2]*r[3])
        if big[2] < 40: continue            # tiny faces = background people
        xs.append((big[0]+big[2]/2)/960); ws.append(big[2]/960)
    if len(xs) < 2: return None
    return float(np.median(xs)), float(np.median(ws)), len(xs)
if __name__=='__main__':
    j=json.load(open(sys.argv[1],encoding='utf-8'))
    res=[]
    for c in j['clips']:
        r=shot_x(j['src'],c['in'],c['out'])
        if r:
            f,w,n=r; pos=0.5-(f-0.5)*K
            pos=max(0.5-1.08,min(0.5+1.08,pos))
            res.append({**c,'face_x':round(f,3),'n':n,'pos':round(pos,3)})
        else: res.append({**c,'face_x':None,'pos':None})
    print(json.dumps(res,ensure_ascii=False,indent=0))
