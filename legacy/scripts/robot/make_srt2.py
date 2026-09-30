# SRT for a short from per-piece whisper word files. House style: 1 line, <=30 chars,
# no hanging short words at line end (carried to next title WITH their own timing).
import json,re,sys
HANG={'–','—','-','а','в','во','и','к','ко','с','со','у','о','об','от','до','за','из','на','не','ни','по','про','для','без','над','под','при','что','как','но','же','ли','бы','это','этот','эта','эти','тот','та','те','его','её','их','мой','наш','ваш','уже','ещё','еще','очень','самый','самая','самое','чтобы','если','когда','где','куда','или','то','вот','так','там','тут','он','она','они','мы','вы','я','ты','между','через','после','перед','около','всё','все'}
def build(pieces, dst, fixes=(), maxlen=30):
    out=[]
    for pi,(tl,wf) in enumerate(pieces):
        W=json.load(open(wf,encoding='utf-8'))
        if W and W[0]['s']<0.02 and W[0]['e']-W[0]['s']<0.1: W=W[1:]   # clipped word at the cut
        for x in W:
            t=x['w'].strip()
            s,e=tl+x['s'],tl+min(x['e'],x['s']+0.25+0.09*len(t))
            if t.startswith('-') and out and out[-1][3]==pi: out[-1][2]+=t; out[-1][1]=e
            else: out.append([s,e,t,pi])
    def hangs(c): return len(c)>1 and (c[-1][2].lower().strip('«"(') in HANG or c[-1][2].isdigit()) and not re.search(r'[.,!?…:;]$',c[-1][2])
    cues=[];cur=[]
    for w in out:
        if cur and (w[3]!=cur[-1][3] or len(' '.join(x[2] for x in cur+[w]))>maxlen):
            carry=[]
            while hangs(cur) and w[3]==cur[-1][3]: carry.insert(0,cur.pop())
            cues.append(cur); cur=carry
        cur.append(w)
        if re.search(r'[.!?…]$',w[2]) or (w[2].endswith(',') and len(' '.join(x[2] for x in cur))>=14):
            cues.append(cur); cur=[]
    if cur: cues.append(cur)
    # DASH: a title must never start with a dash (reads like dialogue): glue to previous title if it fits, else dash -> comma
    i=1
    while i<len(cues):
        if cues[i][0][2] in ('–','—','-') and cues[i][0][3]==cues[i-1][-1][3]:
            rest=cues[i][1:]
            if len(' '.join(x[2] for x in cues[i-1]+cues[i]))<=maxlen+6:
                cues[i-1]+=cues[i]; del cues[i]; continue
            if not re.search(r'[.,!?…:;]$',cues[i-1][-1][2]): cues[i-1][-1][2]+=','
            cues[i]=rest
            if not rest: del cues[i]; continue
        i+=1
    def ts(x):
        ms=int(round(x*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    txt=[]
    for i,c in enumerate(cues):
        line=' '.join(x[2] for x in c)
        line=re.sub(r'(^|\s)[–-](\s|$)',r'\1—\2',line)
        for a,b in fixes: line=re.sub(a,b,line)
        line=line[:1].upper()+line[1:] if i==0 or re.search(r'[.!?…]$',cues[i-1][-1][2]) else line
        end=c[-1][1]
        if i+1<len(cues): end=min(end,cues[i+1][0][0])
        txt.append(f"{i+1}\n{ts(c[0][0])} --> {ts(end)}\n{line}\n")
    open(dst,'w',encoding='utf-8').write('\n'.join(txt)); return txt
if __name__=='__main__':
    j=json.load(open(sys.argv[1],encoding='utf-8'))
    for t in build(j['pieces'],j['dst'],j.get('fixes',[]),j.get('maxlen',30)): print(t.split('\n')[1],'|',t.split('\n')[2])
