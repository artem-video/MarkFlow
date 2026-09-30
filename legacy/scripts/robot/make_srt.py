# build short-relative SRT from whisper words + cut list; house style: 1 line, <=30 chars
import json,re,sys
def build(words_json, off, segs, dst, fixes=()):
    W=json.load(open(words_json,encoding='utf-8'))
    out=[]
    for si,(tl,a,b) in enumerate(segs):
        for x in W:
            s,e=off+x['s'],off+x['e']
            if a<=(s+e)/2<=b:
                t=x['w'].strip()
                e=min(e, s+0.25+0.09*len(t))
                w=[tl+max(s,a)-a, tl+min(e,b)-a, t, si]
                if t.startswith('-') and out and out[-1][3]==si: out[-1][2]+=t; out[-1][1]=w[1]
                else: out.append(w)
    HANG={'–','—','-','а','в','во','и','к','ко','с','со','у','о','об','от','до','за','из','на','не','ни','по','про','для','без','над','под','при','что','как','но','же','ли','бы','это','этот','эта','эти','тот','та','те','его','её','их','мой','наш','ваш','уже','ещё','еще','очень','самый','самая','самое','чтобы','если','когда','где','куда','или','то','вот','так','там','тут','он','она','они','мы','вы','я','ты','между','через','после','перед','около'}
    def hangs(c): return len(c)>1 and c[-1][2].lower().strip('«"(') in HANG and not re.search(r'[.,!?…:;]$',c[-1][2])
    cues=[];cur=[]
    for w in out:
        if cur and (w[3]!=cur[-1][3] or len(' '.join(x[2] for x in cur+[w]))>30):
            carry=[]
            while hangs(cur) and w[3]==cur[-1][3]: carry.insert(0,cur.pop())
            cues.append(cur);cur=carry
        cur.append(w)
        if re.search(r'[.!?…]$',w[2]) or (w[2].endswith(',') and len(' '.join(x[2] for x in cur))>=14): cues.append(cur);cur=[]
    if cur: cues.append(cur)
    def ts(x):
        ms=int(round(x*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    txt=[]
    for i,c in enumerate(cues):
        line=' '.join(x[2] for x in c)
        line=re.sub(r'(^|\s)[–-](\s)',r'\1—\2',line)
        for a_,b_ in fixes: line=line.replace(a_,b_)
        if i==0 or not re.search(r'[.!?…]$',cues[i-1][-1][2]): pass
        line=line[0].upper()+line[1:] if i==0 else line
        end=c[-1][1]
        if i+1<len(cues): end=min(max(end, c[-1][1]), cues[i+1][0][0])
        txt.append(f"{i+1}\n{ts(c[0][0])} --> {ts(end)}\n{line}\n")
    open(dst,'w',encoding='utf-8').write('\n'.join(txt)); return '\n'.join(txt)
if __name__=='__main__':
    j=json.load(open(sys.argv[1],encoding='utf-8'))
    print(build(j['words'],j['offset'],j['segs'],j['dst'],j.get('fixes',[])))
