import cv2,numpy as np,subprocess,sys,json
F=sys.argv[1]
cap=cv2.VideoCapture(F)
frames=[]
while True:
    ok,f=cap.read()
    if not ok: break
    frames.append(cv2.cvtColor(f,cv2.COLOR_BGR2GRAY))
print(len(frames))
ref=frames[int(6.5*30)]
tpl=ref[518:574,88:144]  # checkbox
segs={1:(4.8,8.0),2:(8.4,11.6),3:(12.0,15.2),4:(15.6,18.8),5:(19.2,22.4),6:(22.8,26.0)}
out={}
for k,(a,b) in segs.items():
    rows=[]
    for i in range(int(a*30)-6,int(b*30)+6):
        r=cv2.matchTemplate(frames[i],tpl,cv2.TM_CCOEFF_NORMED)
        _,mx,_,loc=cv2.minMaxLoc(r)
        rows.append((i,round(mx,3),loc))
    out[k]=rows
    for i,mx,loc in rows[::6]: print(k,i,mx,loc)
json.dump({k:[(i,m,list(l)) for i,m,l in v] for k,v in out.items()},open(sys.argv[2],'w'))
