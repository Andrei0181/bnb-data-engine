import os,json,time,math,statistics
AID=int(os.environ.get("AGENT_ID",1))
PAIRS=[("BTCUSDT","ETHUSDT"),("SOLUSDT","AVAXUSDT"),("ARBUSDT","TIAUSDT"),("ATOMUSDT","OPUSDT"),("UNIUSDT","1INCHUSDT"),("ATOMUSDT","UNIUSDT")]
SA,SB=PAIRS[(AID-1)%len(PAIRS)]
W=100; KE=2.2; KX=0.5; SZ=4.5; LEG=200.0
def rd(p):
    try: return json.load(open(p))
    except Exception: return None
def calc():
    a=rd("/tmp/swarm/kl_"+SA+".json"); b=rd("/tmp/swarm/kl_"+SB+".json"); pr=rd("/tmp/swarm/prices.json")
    if not a or not b or not pr: return None
    now=int(time.time())
    if now-a["ts"]>180 or now-b["ts"]>180 or now-pr["ts"]>90: return None
    ta,ca=a.get("t"),a["c"]; tb,cb=b.get("t"),b["c"]
    if not ta or not tb: return None
    common=sorted(set(ta)&set(tb))
    if len(common)<W+1: return None
    da,db=dict(zip(ta,ca)),dict(zip(tb,cb))
    ca=[da[t] for t in common]; cb=[db[t] for t in common]
    ma,mb=statistics.mean(ca),statistics.mean(cb)
    vx=sum((x-ma)**2 for x in ca)
    if vx<=0: return None
    beta=sum((x-ma)*(y-mb) for x,y in zip(ca,cb))/vx
    ic=mb-beta*ma
    res=[y-(beta*x+ic) for x,y in zip(ca,cb)][-W:]
    sd=statistics.pstdev(res)
    if sd<=0: return None
    z=(res[-1]-statistics.mean(res))/sd
    if not math.isfinite(z) or not math.isfinite(beta): return None
    return z,beta,pr["prices"][SA],pr["prices"][SB]
pos=0; be=1.0
print("[A%02d]"%AID,SA+"/"+SB,"leg",LEG,flush=True)
while True:
    r=calc(); P={}
    if r is None:
        pos=0
    else:
        z,beta,pa,pb=r; az=abs(z)
        if pos==0:
            if KE<az<SZ: pos=-1 if z>0 else 1; be=beta
        elif az<KX or az>SZ: pos=0
        if pos!=0:
            qb=pos*LEG/pb; qa=-pos*be*qb
            P[SB]=round(qb,6); P[SA]=round(qa,8)
        else: P[SB]=0.0; P[SA]=0.0
    d={"agent_id":AID,"timestamp":int(time.time()),"pair":SA+"/"+SB,"pos":pos,"z":(round(z,3) if r is not None else None),"has_data":bool(r),"positions":P}
    t="/tmp/swarm/agent_%02d.json"%AID
    with open(t+".tmp","w") as f: json.dump(d,f)
    os.rename(t+".tmp",t)
    time.sleep(20)
