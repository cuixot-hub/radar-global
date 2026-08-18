import json, csv, io, urllib.request, urllib.parse, datetime as dt, math, statistics, os, time

START_MONTH="1998-01"
CUTOFF_MONTH="2026-07"
BASE=100.0

FRED_IDS=["FEDFUNDS","M2SL","T10Y2Y","CPIAUCSL","DGS10","DCOILWTICO","PPIACO","VIXCLS","BAMLH0A0HYM2","DFII10","NFCI"]

def req_text(url, timeout=60):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 SemaforoMacroBacktest/1.0"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8-sig")

def month_add(m,n):
    y,mo=map(int,m.split("-"))
    k=y*12+(mo-1)+n
    return f"{k//12:04d}-{k%12+1:02d}"

def month_diff(a,b):
    ya,ma=map(int,a.split("-")); yb,mb=map(int,b.split("-"))
    return (yb*12+mb)-(ya*12+ma)

def months_between(a,b):
    out=[]; m=a
    while m<=b:
        out.append(m); m=month_add(m,1)
    return out

def fetch_sp500():
    start_ts=int(dt.datetime(1995,1,1,tzinfo=dt.timezone.utc).timestamp())
    end_ts=int(dt.datetime(2026,8,2,tzinfo=dt.timezone.utc).timestamp())
    hosts=["query1.finance.yahoo.com","query2.finance.yahoo.com"]
    last_err=None
    for host in hosts:
        try:
            url=f"https://{host}/v8/finance/chart/%5EGSPC?period1={start_ts}&period2={end_ts}&interval=1mo&includeAdjustedClose=true&events=div%2Csplits"
            raw=json.loads(req_text(url))
            res=raw["chart"]["result"][0]
            ts=res["timestamp"]
            closes=res["indicators"]["quote"][0]["close"]
            out={}
            for t,v in zip(ts,closes):
                if v is None: continue
                d=dt.datetime.fromtimestamp(t,dt.timezone.utc)
                m=d.strftime("%Y-%m")
                if m<=CUTOFF_MONTH:
                    out[m]=float(v)
            if len(out)>300:
                return out, "Yahoo Finance ^GSPC monthly"
        except Exception as e:
            last_err=e
    raise RuntimeError("No se pudo descargar S&P 500: "+repr(last_err))

def fetch_fred(sid):
    url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(sid)}&cosd=1995-01-01&coed=2026-07-31"
    txt=req_text(url)
    arr=[]
    for r in csv.DictReader(io.StringIO(txt)):
        d=r.get("observation_date") or r.get("DATE")
        val=r.get(sid)
        if not d or val in (None,"","."): continue
        try: v=float(val)
        except: continue
        arr.append((d,v))
    if not arr: raise RuntimeError("Sin datos FRED "+sid)
    return arr

def monthly_last(arr):
    out={}
    for d,v in arr:
        m=d[:7]
        if m<=CUTOFF_MONTH:
            out[m]=v
    return out

def yoy(series,m):
    p=month_add(m,-12)
    if m not in series or p not in series or not series[p]: return None
    return (series[m]/series[p]-1)*100

def mean_available(vals):
    v=[x for x in vals if x is not None and math.isfinite(x)]
    return sum(v)/len(v) if v else None, len(v)

def score_fed(x): return None if x is None else (0 if x<1 else 1 if x<3 else 2 if x<5 else 3)
def score_m2(x): return None if x is None else (0 if x>10 else 1 if x>5 else 2 if x>0 else 3)
def score_curve(x): return None if x is None else (0 if x>1 else 1 if x>=0 else 2 if x>=-0.5 else 3)
def score_cpi(x): return None if x is None else (0 if x<2.5 else 1 if x<3.5 else 2 if x<5 else 3)
def score_g10(x): return None if x is None else (0 if x<3 else 1 if x<4 else 2 if x<5 else 3)
def score_wti(x): return None if x is None else (0 if x<70 else 1 if x<90 else 2 if x<110 else 3)
def score_ppi(x): return None if x is None else (0 if x<3 else 1 if x<5 else 2 if x<8 else 3)
def score_vix(x): return None if x is None else (0 if x<15 else 1 if x<25 else 2 if x<35 else 3)
def score_hy(x): return None if x is None else (0 if x<3.5 else 1 if x<5 else 2 if x<6 else 3)
def score_real(x): return None if x is None else (0 if x<0.75 else 1 if x<2 else 2 if x<2.5 else 3)
def score_nfci(x): return None if x is None else (0 if x<-0.5 else 1 if x<0 else 2 if x<0.1 else 3)

sp, sp_source = fetch_sp500()
fred_raw={sid:fetch_fred(sid) for sid in FRED_IDS}
F={sid:monthly_last(fred_raw[sid]) for sid in FRED_IDS}

months=[m for m in months_between(START_MONTH,CUTOFF_MONTH) if m in sp]
records={}
for i,m in enumerate(months):
    prices=[sp[x] for x in months[max(0,i-9):i+1] if x in sp]
    ma10=sum(prices)/len(prices) if len(prices)==10 else None
    pct=(sp[m]/ma10-1)*100 if ma10 else None
    b3=None if pct is None else (0 if pct>5 else 1 if pct>=0 else 2 if pct>=-5 else 3)

    fed=F["FEDFUNDS"].get(m)
    m2y=yoy(F["M2SL"],m)
    curve=F["T10Y2Y"].get(m)
    b1,n1=mean_available([score_fed(fed),score_m2(m2y),score_curve(curve)])

    cpiy=yoy(F["CPIAUCSL"],m)
    g10=F["DGS10"].get(m)
    wti=F["DCOILWTICO"].get(m)
    ppiy=yoy(F["PPIACO"],m)
    sw=score_wti(wti); sp_p=score_ppi(ppiy)
    cost,_=mean_available([sw,sp_p])
    b2,n2=mean_available([score_cpi(cpiy),score_g10(g10),cost])

    vix=F["VIXCLS"].get(m); hy=F["BAMLH0A0HYM2"].get(m); real=F["DFII10"].get(m); nfci=F["NFCI"].get(m)
    b5,n5=mean_available([score_vix(vix),score_hy(hy),score_real(real),score_nfci(nfci)])

    records[m]={
      "m":m,"sp":sp[m],"ma10":ma10,"pct_ma10":pct,"b3":b3,
      "b1":b1,"b1_complete":n1==3,
      "b2":b2,"b2_complete":n2==3,
      "b5":b5,"b5_complete":n5==4,"b5_n":n5,
      "raw":{"fed":fed,"m2_yoy":m2y,"curve":curve,"cpi_yoy":cpiy,"g10":g10,"wti":wti,"ppi_yoy":ppiy,"vix":vix,"hy":hy,"real10":real,"nfci":nfci}
    }

# Valid episodes: only a bull market turning down.
episodes=[]
active=None
for i,m in enumerate(months):
    r=records[m]; b3=r["b3"]
    if active is None and b3 in (2,3) and i>=13:
        pm=months[i-1]
        prev=records[pm]
        m12=months[i-13]
        trailing=(sp[pm]/sp[m12]-1) if m12 in sp else None
        if prev["b3"] is not None and prev["b3"]<=1 and trailing is not None and trailing>0:
            active={"start":m,"signals":[]}
    if active is not None:
        if b3 in (2,3):
            # confirmation: at least one of B1/B2/B5 worsens vs 3m ago or is stressed >=1.5
            conf=[]
            prev3=month_add(m,-3)
            for b in ("b1","b2","b5"):
                now=r[b]; old=records.get(prev3,{}).get(b)
                if now is not None and ((old is not None and now>old+1e-9) or now>=1.5):
                    conf.append(b.upper())
            active["signals"].append({"m":m,"b3":b3,"price":sp[m],"confirm":conf,"confirm_n":len(conf),
                                      "b1":r["b1"],"b2":r["b2"],"b5":r["b5"],"b5_complete":r["b5_complete"]})
        else:
            active["end"]=active["signals"][-1]["m"]
            episodes.append(active); active=None
if active is not None:
    active["end"]=active["signals"][-1]["m"]; episodes.append(active)

# mark valid signals
valid_signal={}
for ei,e in enumerate(episodes):
    for s in e["signals"]:
        valid_signal[s["m"]]={"episode":ei,"b3":s["b3"]}

def lot_stats(m):
    p=sp[m]; idx=months.index(m)
    rec=None; minp=p
    for j in range(idx+1,len(months)):
        pj=sp[months[j]]
        minp=min(minp,pj)
        if pj>=p and rec is None:
            rec=j-idx
            break
    if rec is None:
        for j in range(idx+1,len(months)): minp=min(minp,sp[months[j]])
    dd=minp/p-1
    def fr(k):
        mm=month_add(m,k)
        return sp[mm]/p-1 if mm in sp else None
    return {"recovery_months":rec,"max_drawdown":dd,"r6":fr(6),"r12":fr(12),"r24":fr(24),"r36":fr(36)}

signal_lots=[]
for e in episodes:
    for s in e["signals"]:
        z=lot_stats(s["m"])
        signal_lots.append({**s,**z,"episode_start":e["start"],"episode_end":e["end"]})

def episode_stats(e, red_extra, purple_extra):
    invests=[]; shares=0; total=0
    for s in e["signals"]:
        extra=red_extra if s["b3"]==2 else purple_extra
        amt=BASE*(1+extra/100)
        total+=amt; shares+=amt/s["price"]
        invests.append({"m":s["m"],"b3":s["b3"],"amount":amt,"price":s["price"]})
    avg=total/shares
    start=e["start"]; end=e["end"]
    i0=months.index(start); ie=months.index(end)
    rec_after_last=None
    if sp[end]>=avg: rec_after_last=0
    else:
        for j in range(ie+1,len(months)):
            if sp[months[j]]>=avg:
                rec_after_last=j-ie; break
    rec_from_start=None if rec_after_last is None else month_diff(start,end)+rec_after_last
    end_search=(ie+rec_after_last) if rec_after_last is not None else len(months)-1
    minp=min(sp[months[j]] for j in range(i0,end_search+1))
    dd=minp/avg-1
    def ret_after_end(k):
        mm=month_add(end,k)
        return sp[mm]/avg-1 if mm in sp else None
    confirms=[s["confirm_n"] for s in e["signals"]]
    return {
      "start":start,"end":end,"months":len(e["signals"]),
      "red_n":sum(s["b3"]==2 for s in e["signals"]),"purple_n":sum(s["b3"]==3 for s in e["signals"]),
      "avg_cost":avg,"total_invested":total,"recovery_after_last":rec_after_last,"recovery_from_start":rec_from_start,
      "max_drawdown":dd,"r12":ret_after_end(12),"r24":ret_after_end(24),"r36":ret_after_end(36),
      "avg_confirmation":sum(confirms)/len(confirms) if confirms else 0,
      "high_confirmation_share":sum(c>=2 for c in confirms)/len(confirms) if confirms else 0,
      "purchases":invests
    }

def annual_irr(cashflows):
    # monthly IRR -> annual
    def npv(r):
        return sum(cf/((1+r)**i) for i,cf in enumerate(cashflows))
    lo=-0.95; hi=1.0
    flo=npv(lo); fhi=npv(hi)
    if flo*fhi>0: return None
    for _ in range(120):
        mid=(lo+hi)/2; fm=npv(mid)
        if abs(fm)<1e-8: break
        if flo*fm<=0: hi=mid; fhi=fm
        else: lo=mid; flo=fm
    return (1+mid)**12-1

def strategy_metrics(red_extra,purple_extra, start=START_MONTH,end=CUTOFF_MONTH):
    ms=[m for m in months if start<=m<=end]
    shares=0; invested=0; cfs=[]
    extra_shares=0; extra_inv=0; extra_cfs=[]
    for m in ms:
        extra=0
        if m in valid_signal:
            extra=red_extra if valid_signal[m]["b3"]==2 else purple_extra
        amt=BASE*(1+extra/100)
        shares+=amt/sp[m]; invested+=amt; cfs.append(-amt)
        eamt=BASE*extra/100
        extra_cfs.append(-eamt)
        if eamt:
            extra_shares+=eamt/sp[m]; extra_inv+=eamt
    final=shares*sp[ms[-1]]
    cfs[-1]+=final
    extra_final=extra_shares*sp[ms[-1]]
    extra_cfs[-1]+=extra_final
    irr=annual_irr(cfs)
    exirr=annual_irr(extra_cfs) if extra_inv>0 else None
    return {"invested":invested,"final_value":final,"gain":final/invested-1,"irr":irr,
            "extra_invested":extra_inv,"extra_final":extra_final,"extra_gain":extra_final/extra_inv-1 if extra_inv else None,
            "extra_irr":exirr}

# optimization on training period only
train_eps=[e for e in episodes if e["start"]<="2016-12"]
valid_eps=[e for e in episodes if e["start"]>="2017-01"]

red_grid=[25,50,75,100,125,150]
purple_grid=[50,75,100,125,150,175,200,250]
cands=[]
baseline_train=strategy_metrics(0,0,START_MONTH,"2016-12")
for re in red_grid:
    for pe in purple_grid:
        if pe<=re: continue
        eps=[episode_stats(e,re,pe) for e in train_eps]
        r24=[x["r24"] for x in eps if x["r24"] is not None]
        rec=[x["recovery_after_last"] for x in eps if x["recovery_after_last"] is not None]
        dds=[x["max_drawdown"] for x in eps]
        sm=strategy_metrics(re,pe,START_MONTH,"2016-12")
        cands.append({"red_extra":re,"purple_extra":pe,
          "mean_r24":sum(r24)/len(r24) if r24 else None,
          "median_recovery":statistics.median(rec) if rec else 999,
          "worst_recovery":max(rec) if rec else 999,
          "worst_drawdown":min(dds) if dds else -1,
          "irr_delta":(sm["irr"]-baseline_train["irr"]) if sm["irr"] is not None and baseline_train["irr"] is not None else 0,
          "train_strategy":sm})

# normalize robust score
def norm(v,lo,hi,higher=True):
    if hi<=lo: return 0.5
    x=(v-lo)/(hi-lo)
    return x if higher else 1-x
for key in ["mean_r24","median_recovery","worst_recovery","worst_drawdown","irr_delta"]:
    vals=[c[key] for c in cands if c[key] is not None]
    lo=min(vals); hi=max(vals)
    for c in cands:
        c["_n_"+key]=norm(c[key],lo,hi,higher=key in ("mean_r24","worst_drawdown","irr_delta"))
for c in cands:
    c["score"]=0.35*c["_n_mean_r24"]+0.20*c["_n_median_recovery"]+0.15*c["_n_worst_recovery"]+0.15*c["_n_worst_drawdown"]+0.15*c["_n_irr_delta"]

best_score=max(c["score"] for c in cands)
near=[c for c in cands if c["score"]>=best_score-0.03]
# choose simpler/lower capital among near-best
selected=min(near,key=lambda c:(c["red_extra"]+c["purple_extra"],c["purple_extra"],c["red_extra"]))
RE=selected["red_extra"]; PE=selected["purple_extra"]

selected_eps=[episode_stats(e,RE,PE) for e in episodes]
full=strategy_metrics(RE,PE)
baseline=strategy_metrics(0,0)
validation=strategy_metrics(RE,PE,"2017-01",CUTOFF_MONTH)
validation_baseline=strategy_metrics(0,0,"2017-01",CUTOFF_MONTH)

# episode labels
for x in selected_eps:
    y=int(x["start"][:4])
    if 1999<=y<=2001: x["label"]="2000 · burbuja tecnológica"
    elif 2007<=y<=2009: x["label"]="2008 · crisis financiera"
    elif 2020<=y<=2020: x["label"]="2020 · COVID"
    else: x["label"]=x["start"]

# consecutive signal stats
lengths=[len(e["signals"]) for e in episodes]
lot_red=[x for x in signal_lots if x["b3"]==2]
lot_purple=[x for x in signal_lots if x["b3"]==3]
def lot_summary(arr):
    rec=[x["recovery_months"] for x in arr if x["recovery_months"] is not None]
    dd=[x["max_drawdown"] for x in arr]
    def avg(k):
        v=[x[k] for x in arr if x[k] is not None]
        return sum(v)/len(v) if v else None
    return {"n":len(arr),"median_recovery":statistics.median(rec) if rec else None,"max_recovery":max(rec) if rec else None,
            "worst_drawdown":min(dd) if dd else None,"avg_r12":avg("r12"),"avg_r24":avg("r24"),"avg_r36":avg("r36")}

# top candidates, strip private normalization
top=sorted(cands,key=lambda c:c["score"],reverse=True)[:12]
for c in top:
    for k in list(c):
        if k.startswith("_n_"): del c[k]

# monthly timeline for visual
timeline=[]
for m in months:
    r=records[m]
    sig=valid_signal.get(m)
    timeline.append({"m":m,"sp":r["sp"],"b3":r["b3"],"signal":sig["b3"] if sig else None,
                     "confirm": next((s["confirm_n"] for e in episodes for s in e["signals"] if s["m"]==m),None)})

result={
 "meta":{"start":START_MONTH,"end":CUTOFF_MONTH,"frequency":"monthly","sp_source":sp_source,
         "fred_series":FRED_IDS,"rule":"B3 via S&P500 vs MA10; red -5%..0%; purple < -5%; only bull-to-downturn episodes",
         "base_monthly":BASE,"train":"1998-01/2016-12","validation":"2017-01/2026-07"},
 "optimization":{"selected":{"red_extra_pct":RE,"purple_extra_pct":PE,"score":selected["score"]},
                 "top_candidates":top},
 "portfolio":{"baseline_full":baseline,"optimized_full":full,"validation_baseline":validation_baseline,"validation_optimized":validation},
 "episodes":selected_eps,
 "signal_lots":{"red":lot_summary(lot_red),"purple":lot_summary(lot_purple),"all":lot_summary(signal_lots)},
 "consecutive":{"episodes":len(episodes),"max_months":max(lengths) if lengths else 0,"median_months":statistics.median(lengths) if lengths else 0,
                "lengths":lengths},
 "timeline":timeline,
 "records":records
}
os.makedirs("backtest_exhaustivo",exist_ok=True)
with open("backtest_exhaustivo/result.json","w",encoding="utf-8") as f:
    json.dump(result,f,ensure_ascii=False,separators=(",",":"))
with open("backtest_exhaustivo/signals.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["month","episode_start","b3","color","price","confirm_blocks","recovery_months","max_drawdown","r12","r24","r36"])
    for x in signal_lots:
        w.writerow([x["m"],x["episode_start"],x["b3"],"RED" if x["b3"]==2 else "PURPLE",x["price"],"|".join(x["confirm"]),
                    x["recovery_months"],x["max_drawdown"],x["r12"],x["r24"],x["r36"]])
print(json.dumps({"selected":result["optimization"]["selected"],"episodes":len(episodes),"source":sp_source,
                  "red":result["signal_lots"]["red"],"purple":result["signal_lots"]["purple"]},ensure_ascii=False,indent=2))
