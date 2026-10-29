"""Vietnam Money Flow | Private Streamlit dashboard (OIDC login)."""
from pathlib import Path
import json
import os
import pandas as pd
import streamlit as st
import plotly.express as px

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
st.set_page_config(page_title='Vietnam Money Flow',page_icon='📈',layout='wide')

# Temporary deployment test
# No user authentication in this version.
email = "pilot"
admin_set = set()
page = st.sidebar.radio(
    "Chọn trang",
    ["Stock Screener", "Sector Rotation"]
)
@st.cache_data(ttl=300)
def load_data():
    required=['stock_screener.csv','sector_rotation.csv']
    missing=[x for x in required if not (OUT/x).exists()]
    if missing: return None,None,None,missing
    stocks=pd.read_csv(OUT/required[0]); sectors=pd.read_csv(OUT/required[1]); status={}
    if (OUT/'refresh_status.json').exists():
        status=json.loads((OUT/'refresh_status.json').read_text(encoding='utf-8'))
    return stocks,sectors,status,[]


    st.title('Vietnam Money Flow')
    st.caption(email)
    page=st.radio('Trang', ['Stock Screener','Sector Rotation'])
    if st.button('Làm mới màn hình'):
        load_data.clear();st.rerun()
    if st.button('Đăng xuất'): st.logout()
    st.caption('Nguồn: Finwise REST API · Dữ liệu cập nhật bởi job Python')

stocks,sectors,status,missing=load_data()
if missing:
    st.warning('Chưa có dữ liệu xử lý. Chạy `python pipeline.py` trên máy chủ đã cấu hình FINWISE_API_KEY.')
    st.code('python pipeline.py',language='powershell')
    st.info('Tệp universe.csv hiện chỉ có 4 mã thử nghiệm. Chưa có dữ liệu toàn bộ 3 sàn.')
    st.stop()

st.title('Stock Screener' if page=='Stock Screener' else 'Sector Rotation')
last=status.get('last_settled_session','chưa rõ')
st.caption(f'Phiên dữ liệu: {last} · {status.get("symbols_loaded","?")} mã đã tải · {status.get("failures","?")} lỗi · Giá gốc/điều chỉnh: {status.get("adjustments","?")}')

with st.sidebar:
    exchanges=sorted(stocks.exchange.dropna().unique().tolist())
    ex=st.multiselect('Sàn',exchanges,default=exchanges)
    industries=sorted(stocks.sector.dropna().unique().tolist())
    selected=st.multiselect('Ngành',industries,default=industries)
    adv=st.number_input('GTGD bình quân 20 phiên tối thiểu (tỷ VND)',min_value=0.0,max_value=500.0,value=5.0,step=1.0)
    min_score=st.slider('Điểm dòng tiền tối thiểu',0,100,0)
    phase=st.multiselect('Trạng thái dòng tiền',sorted(stocks.market_phase.dropna().unique().tolist()))

s=stocks[stocks.exchange.isin(ex)&stocks.sector.isin(selected)&(stocks.adv20_vnd>=adv*1e9)&(stocks.flow_score_prelim>=min_score)].copy()
if phase: s=s[s.market_phase.isin(phase)]
if page=='Stock Screener':
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Cổ phiếu đạt lọc',len(s))
    c2.metric('CMF20 dương',f'{(s.cmf20.gt(0).mean()*100):.1f}%' if len(s) else '—')
    c3.metric('RVOL ≥ 1,5',int(s.rvol20.ge(1.5).sum()))
    c4.metric('Tích lũy Watch',int(s.market_phase.eq('Accumulation Watch').sum()))
    cols=['ticker','exchange','sector','close','adv20_vnd','ret20','cmf20','obv_change20','rvol20','vsa_signal','market_phase','flow_score_prelim']
    st.dataframe(s[cols].sort_values('flow_score_prelim',ascending=False),hide_index=True,use_container_width=True)
    st.download_button('Xuất danh sách CSV',s[cols].to_csv(index=False).encode('utf-8-sig'),'stock_screener.csv','text/csv')
    if not s.empty:
        chart=px.scatter(s,x='cmf20',y='rvol20',size='adv20_vnd',color='sector',hover_name='ticker',title='Dòng tiền: CMF20 vs RVOL20',size_max=35)
        st.plotly_chart(chart,use_container_width=True)
else:
    if s.empty:
        st.info('Không có cổ phiếu đáp ứng bộ lọc.')
    else:
        grouped=s.groupby('sector').agg(stock_count=('ticker','nunique'),avg_score=('flow_score_prelim','mean'),cmf_positive_pct=('cmf20',lambda x:100*x.gt(0).mean()),obv_rising_pct=('obv_up20',lambda x:100*x.gt(0).mean()),high_rvol_pct=('rvol20',lambda x:100*x.ge(1.5).mean()),accumulation_pct=('market_phase',lambda x:100*x.eq('Accumulation Watch').mean()),distribution_pct=('market_phase',lambda x:100*x.eq('Distribution Watch').mean()),total_adv_vnd=('adv20_vnd','sum')).reset_index()
        grouped['sector_rank']=grouped.avg_score.rank(ascending=False,method='min').astype(int)
        grouped=grouped.sort_values('sector_rank')
        st.caption('Xếp hạng ngành được tính lại trên chính các cổ phiếu đáp ứng bộ lọc; không phải xếp hạng toàn thị trường khi có bộ lọc.')
        st.plotly_chart(px.bar(grouped.head(25),x='avg_score',y='sector',orientation='h',color='cmf_positive_pct',title='Xếp hạng dòng tiền theo ngành').update_layout(yaxis={'categoryorder':'total ascending'}),use_container_width=True)
        st.dataframe(grouped,hide_index=True,use_container_width=True)
        st.download_button('Xuất bảng ngành CSV',grouped.to_csv(index=False).encode('utf-8-sig'),'sector_rotation.csv','text/csv')

st.divider()
st.caption('Flow Score là chỉ báo nghiên cứu chưa backtest; VSA là quy tắc nhận dạng heuristic, không xác nhận giao dịch của tổ chức. Không sử dụng làm khuyến nghị mua/bán độc lập.')
if email in admin_set:
    with st.expander('Quản trị · Trạng thái tải dữ liệu'):
        st.json(status)
        if (OUT/'load_errors.csv').exists():
            st.dataframe(pd.read_csv(OUT/'load_errors.csv'),hide_index=True)
