import os,json,time,glob,hmac,hashlib,requests
B="https://api-demo.bybit.com"
K=os.getenv("API_KEY",""); S=os.getenv("API_SECRET","")
WL=["BTCUSDT","ETHUSDT","SOLUSDT","AVAXUSDT","ARBUSDT","TIAUSDT","ATOMUSDT","OPUSDT","UNIUSDT","1INCHUSDT"]
OUT="/tmp/swarm_net_delta.json"; CAP=2000.0; DB=300.0; TTL=90
def sg(p): return hmac.new(S.encode(),p.encode(),hashlib.sha256).hexdigest()
def wd(d):
    with open(OUT+".tmp","w") as f: json.dump(d,f)
    os.rename(OUT+".tmp",OUT)
def real(sym):
    ts=str(int(time.time()*1000)); q="category=linear&symbol="+sym
    r=requests.get(B+"/v5/position/list?"+q,headers={"X-BAPI-API-KEY":K,"X-BAPI-TIMESTAMP":ts,"X-BAPI-RECV-WINDOW":"5000","X-BAPI-SIGN":sg(ts+K+"5000"+q)},timeout=8).json()
    if r.get("retCode")!=0: raise RuntimeError(str(r.get("retMsg")))
    for p in r["result"]["list"]:
        if p["symbol"]==sym:
            v=float(p.get("size") or 0)
            return v if p.get("side")=="Buy" else -v
    return 0.0
def real_all():
    ts=str(int(time.time()*1000)); q="category=linear&settleCoin=USDT"
    r=requests.get(B+"/v5/position/list?"+q,headers={"X-BAPI-API-KEY":K,"X-BAPI-TIMESTAMP":ts,"X-BAPI-RECV-WINDOW":"5000","X-BAPI-SIGN":sg(ts+K+"5000"+q)},timeout=8).json()
    if r.get("retCode")!=0: raise RuntimeError(str(r.get("retMsg")))
    o={}
    for p in r["result"]["list"]:
        v=float(p.get("size") or 0)
        if v: o[p["symbol"]]=v if p.get("side")=="Buy" else -v
    return o

print("[ROUTER] 1m klines, cap",CAP,"deadband",DB,flush=True)
while True:
    try:
        pr=json.load(open("/tmp/swarm/prices.json"))
        if int(time.time())-pr["ts"]>90: raise RuntimeError("prices stale")
        P=pr["prices"]; T={s:0.0 for s in WL}; n=0; now=int(time.time())
        for f in glob.glob("/tmp/swarm/agent_*.json"):
            try: d=json.load(open(f))
            except Exception: continue
            if now-int(d.get("timestamp",0))>TTL: continue
            ps=d.get("positions")
            if not isinstance(ps,dict): continue
            n+=1
            for s in WL:
                try: T[s]+=float(ps.get(s,0.0))
                except Exception: pass
        mx=max(abs(T[s])*P[s] for s in WL)
        sc=CAP/mx if mx>CAP else 1.0
        if sc!=1.0: T={s:q*sc for s,q in T.items()}
        RA=real_all()
        need=[s for s in WL if abs(T[s])*P[s]>1.0 or abs(RA.get(s,0.0))*P[s]>1.0]
        R={s:RA.get(s,0.0) for s in need}
        D={}
        for s,rq in R.items():
            df=T[s]-rq
            if abs(df)*P[s]>=DB: D[s]=round(df,8)
        wd(D)
        act={s:round(T[s]*P[s]) for s in WL if abs(T[s])*P[s]>1.0}
        print(time.strftime("%H:%M:%S"),"agents",n,"scale",round(sc,2),"target$",act,"delta",D,flush=True)
    except Exception as e:
        wd({}); print(time.strftime("%H:%M:%S"),"SKIP",e,flush=True)
    time.sleep(15)
