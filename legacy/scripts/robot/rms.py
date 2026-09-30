import subprocess,numpy as np,sys
S=sys.argv[1]
for t in map(float,sys.argv[2:]):
    raw=subprocess.run(['ffmpeg','-v','error','-ss',str(t-0.5),'-t','1.0','-i',S,'-vn','-ac','1','-ar','16000','-f','s16le','-'],capture_output=True).stdout
    a=np.frombuffer(raw,np.int16).astype(float)
    print(f'{t-0.5:.2f}:',' '.join(str(int(np.sqrt(np.mean(a[i:i+320]**2)))//100) for i in range(0,len(a),320)))
