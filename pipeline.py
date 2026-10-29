"""Finwise daily OHLCV -> stock screener and sector rotation CSV for Power BI.
Usage: pip install -r requirements.txt; set FINWISE_API_KEY; python pipeline.py
REST endpoints follow Finwise's published /v1/bars and /v1/reference/symbols contracts.
"""
import os, sys, time, json, logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
BASE=os.getenv('FINWISE_BASE_URL','https://api.finwise.vn/v1').rstrip('/')
KEY=os.getenv('FINWISE_API_KEY','')
ADJUST=os.getenv('FINWISE_ADJUSTMENTS','none') # raw volume for real activity; avoid adjusted volume ambiguity
START=os.getenv('FINWISE_START','2025-01-01')
END=os.getenv('FINWISE_END',datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat())
MIN_ADV=float(os.getenv('MIN_ADV_VND','1000000000'))
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

def api(path,params):
    if not KEY: raise RuntimeError('FINWISE_API_KEY missing. Set it as an environment variable; never paste it in PBIX.')
    r=requests.get(BASE+path,params=params,headers={'X-API-Key':KEY},timeout=35)
    r.raise_for_status(); return r.json()

def bars(symbol):
    raw=api('/bars',{'symbol':symbol,'interval':'1d','from':START,'to':END,'adjustments':ADJUST})
    payload=raw.get('data',raw); b=payload.get('bars',{})
    if isinstance(b,dict) and 'columns' in b: df=pd.DataFrame(b['rows'],columns=b['columns'])
    elif isinstance(b,list): df=pd.DataFrame(b)
    else: raise ValueError(f'Unexpected bars response for {symbol}: {list(payload)}')
    if df.empty: return df
    df.columns=[c.lower() for c in df.columns]
    df['date']=pd.to_datetime(df['time'],utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.date
    for c in ['open','high','low','close','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df['ticker']=symbol
    return df[['date','ticker','open','high','low','close','volume']].dropna().drop_duplicates('date').sort_values('date')

def compute(g):
    g=g.sort_values('date').copy()
    c,h,l,v=g['close'],g['high'],g['low'],g['volume']
    prev=c.shift(1); rng=h-l
    clv=pd.Series(np.where(rng>0,(2*c-h-l)/rng,0),index=g.index)
    g['clv']=clv
    g['spread_pct']=rng/c.replace(0,np.nan)
    g['ret1']=c.pct_change()
    g['ret20']=c/c.shift(20)-1
    g['volume_ma20_prev']=v.shift(1).rolling(20,min_periods=20).mean()
    g['rvol20']=v/g['volume_ma20_prev'].replace(0,np.nan)
    g['cmf20']=(clv*v).rolling(20,min_periods=20).sum()/v.rolling(20,min_periods=20).sum().replace(0,np.nan)
    g['obv']=(np.sign(c.diff()).fillna(0)*v).cumsum()
    g['obv_change20']=g['obv']-g['obv'].shift(20)
    g['obv_up20']=(g['obv_change20']>0).astype(int)
    g['obv_breakout20']=(g['obv']>g['obv'].shift(1).rolling(20,min_periods=20).max()).astype(int)
    g['close_high20_prev']=h.shift(1).rolling(20,min_periods=20).max()
    g['close_low20_prev']=l.shift(1).rolling(20,min_periods=20).min()
    g['spread_ma20_prev']=rng.shift(1).rolling(20,min_periods=20).mean()
    g['adv20_vnd']=(c*v).shift(1).rolling(20,min_periods=20).mean()
    wide=rng>g['spread_ma20_prev']*1.3
    narrow=rng<g['spread_ma20_prev']*.75
    g['vsa_sos']=((c>prev)&wide&(clv>.5)&(g['rvol20']>=1.5)&(c>g['close_high20_prev'])).astype(int)
    g['vsa_upthrust']=((h>g['close_high20_prev'])&(clv<-.5)&(g['rvol20']>=1.5)).astype(int)
    g['vsa_spring']=((l<g['close_low20_prev'])&(c>g['close_low20_prev'])&(clv>.4)).astype(int)
    g['vsa_no_supply']=((c<=prev)&narrow&(g['rvol20']<.8)).astype(int)
    g['vsa_no_demand']=((c>=prev)&narrow&(g['rvol20']<.8)).astype(int)
    g['vsa_signal']=np.select([g.vsa_upthrust.eq(1),g.vsa_spring.eq(1),g.vsa_sos.eq(1),g.vsa_no_supply.eq(1),g.vsa_no_demand.eq(1)],['Upthrust','Spring','SOS','No Supply','No Demand'],default='None')
    # Simple interpretable research score. RVOL alone is NOT automatically bullish.
    cmf_score=((g['cmf20'].clip(-.3,.3)+.3)/.6*25).fillna(12.5)
    obv_score=(g['obv_up20']*17+g['obv_breakout20']*8).astype(float)
    vsa_score=np.select([g.vsa_sos.eq(1)|g.vsa_spring.eq(1),g.vsa_upthrust.eq(1),g.vsa_no_supply.eq(1),g.vsa_no_demand.eq(1)],[25,0,18,7],default=12)
    rvol_score=np.where((g['ret1']>0)&(g['clv']>.3)&(g['rvol20']>=1.5),15,np.where((g['ret1']<0)&(g['clv']<-.3)&(g['rvol20']>=1.5),0,7))
    # RS is intentionally excluded until index data is loaded; provisional score reweights 90 pts to 100.
    g['flow_score_prelim']=((cmf_score+obv_score+vsa_score+rvol_score)/90*100).clip(0,100).round(1)
    g['market_phase']=np.select([g.vsa_upthrust.eq(1)&(g['obv_up20']==0),g.vsa_sos.eq(1),g.vsa_spring.eq(1)|((g['cmf20']>0)&(g['obv_up20']==1)&(g['ret20'].abs()<.1)),(g['cmf20']<0)&(g['obv_up20']==0)],['Distribution Watch','Markup / SOS','Accumulation Watch','Weakness'],default='Unclassified')
    g['eligible']=(g['adv20_vnd']>=MIN_ADV)&g['cmf20'].notna()&g['rvol20'].notna()
    return g

def main():
    universe=pd.read_csv(ROOT/'universe.csv',dtype=str).fillna('')
    required={'ticker','sector'}
    if not required.issubset(universe.columns): raise ValueError('universe.csv needs ticker,sector')
    if not universe['ticker'].is_unique: raise ValueError('Duplicate ticker in universe.csv')
    frames=[]; failures=[]
    for i,t in enumerate(universe['ticker'].str.upper()):
        try:
            df=bars(t)
            if len(df)<42: failures.append({'ticker':t,'reason':f'Only {len(df)} rows'}); continue
            frames.append(compute(df)); logging.info('%s: %d daily bars',t,len(df))
        except Exception as e:
            failures.append({'ticker':t,'reason':str(e)}); logging.warning('%s failed: %s',t,e)
        time.sleep(.15)
    if not frames: raise RuntimeError('No symbols loaded. Check API key, plan history, symbols and API response.')
    hist=pd.concat(frames,ignore_index=True).merge(universe[['ticker','sector','exchange']],on='ticker',how='left')
    # Only last COMPLETED common session: use most recent date among downloaded bars, excludes intraday via daily completion check.
    today=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    dates=sorted(d for d in hist['date'].unique() if d<today)
    if not dates: raise RuntimeError('No settled daily bars before today')
    last=dates[-1]; snap=hist[(hist.date==last)&hist.eligible].copy()
    snap['flow_rank']=snap['flow_score_prelim'].rank(ascending=False,method='min').astype(int)
    cols=['date','ticker','sector','exchange','close','volume','adv20_vnd','ret1','ret20','cmf20','obv','obv_change20','obv_up20','obv_breakout20','rvol20','clv','vsa_signal','market_phase','flow_score_prelim','flow_rank']
    snap[cols].sort_values('flow_rank').to_csv(OUT/'stock_screener.csv',index=False,encoding='utf-8-sig')
    sector=snap.groupby('sector',dropna=False).agg(stock_count=('ticker','nunique'),avg_score=('flow_score_prelim','mean'),cmf_positive_pct=('cmf20',lambda x:100*(x>0).mean()),obv_rising_pct=('obv_up20',lambda x:100*(x>0).mean()),high_rvol_pct=('rvol20',lambda x:100*(x>=1.5).mean()),accumulation_pct=('market_phase',lambda x:100*(x=='Accumulation Watch').mean()),distribution_pct=('market_phase',lambda x:100*(x=='Distribution Watch').mean())).reset_index()
    sector['date']=last;sector['sector_rank']=sector.avg_score.rank(ascending=False,method='min').astype(int)
    sector.sort_values('sector_rank').to_csv(OUT/'sector_rotation.csv',index=False,encoding='utf-8-sig')
    hist.to_csv(OUT/'daily_indicators.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(failures,columns=['ticker','reason']).to_csv(OUT/'load_errors.csv',index=False,encoding='utf-8-sig')
    (OUT/'refresh_status.json').write_text(json.dumps({'last_settled_session':str(last),'symbols_loaded':len(frames),'stocks_eligible':len(snap),'failures':len(failures),'adjustments':ADJUST,'min_adv_vnd':MIN_ADV,'generated_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Finished {last}: {len(snap)} eligible stocks, {len(sector)} sectors, {len(failures)} errors')
if __name__=='__main__': main()
