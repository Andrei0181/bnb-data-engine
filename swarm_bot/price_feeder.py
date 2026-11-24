import requests,json,time,os
B="https://api-demo.bybit.com"
S=["BTCUSDT","ETHUSDT","SOLUSDT","AVAXUSDT","ARBUSDT","TIAUSDT","ATOMUSDT","OPUSDT","UNIUSDT","1INCHUSDT"]
os.makedirs("/tmp/swarm",exist_ok=True)
def wr(p,d):
    with open(p+".tmp","w") as f: json.dump(d,f)
    os.rename(p+".tmp",p)
print("[FEED] tickers + 1m klines",flush=True)
while True:
    pr={};fu={}
    for s in S:
        try:
            r=requests.get(B+"/v5/market/tickers",params={"category":"linear","symbol":s},timeout=6).json()
            it=r["result"]["list"][0]; pr[s]=float(it["lastPrice"]); fu[s]=float(it["fundingRate"])
        except Exception as e: print("tick",s,e,flush=True)
    if len(pr)==len(S): wr("/tmp/swarm/prices.json",{"ts":int(time.time()),"prices":pr,"funding":fu})
    for s in S:
        try:
            r=requests.get(B+"/v5/market/kline",params={"category":"linear","symbol":s,"interval":"1","limit":200},timeout=8).json()
            rows=list(reversed(r["result"]["list"]))[:-1]
            wr("/tmp/swarm/kl_"+s+".json",{"ts":int(time.time()),"t":[int(x[0]) for x in rows],"c":[float(x[4]) for x in rows]})
        except Exception as e: print("kl",s,e,flush=True)
    print("[FEED]",len(pr),"tickers | BTC",pr.get("BTCUSDT"),"ETH",pr.get("ETHUSDT"),flush=True)
    time.sleep(30)
