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


# Demo mode is limited to public pilot data. Configure OIDC before sharing private research.
email = "pilot"
admin_set = set()

@st.cache_data(ttl=300)
def load_data():
    p=OUT/'stock_screener.csv'
    if not p.exists(): return None, {}
    df=pd.read_csv(p)
    status={}
    q=OUT/'refresh_status.json'
    if q.exists():
        status=json.loads(q.read_text(encoding='utf-8-sig'))
    return df,status

stocks,status=load_data()
st.sidebar.title("Vietnam Money Flow")
page=st.sidebar.radio("Chọn trang",["Stock Screener","Sector Rotation"])
if st.sidebar.button("Làm mới dữ liệu"):
    load_data.clear()
    st.rerun()

if stocks is None:
    st.warning("Chưa có output/stock_screener.csv. Hãy tải dữ liệu thử nghiệm lên GitHub.")
    st.stop()

st.caption("Dữ liệu pilot · không tự cập nhật · chưa có xác thực người dùng · không dùng cho dữ liệu nội bộ")
st.caption(f"Phiên dữ liệu: {status.get('last_settled_session', stocks['date'].max() if 'date' in stocks else 'không rõ')}")
with st.sidebar:
    ex=st.multiselect("Sàn",sorted(stocks.exchange.dropna().unique()),default=sorted(stocks.exchange.dropna().unique()))
    inds=st.multiselect("Ngành",sorted(stocks.sector.dropna().unique()),default=sorted(stocks.sector.dropna().unique()))
    adv=st.number_input("GTGD bình quân 20 phiên tối thiểu (tỷ VND)",0.0,500.0,5.0,1.0)
    min_score=st.slider("Flow Score tối thiểu",0,100,0)
    phases=st.multiselect("Trạng thái dòng tiền",sorted(stocks.market_phase.dropna().unique()))
s=stocks[stocks.exchange.isin(ex)&stocks.sector.isin(inds)&stocks.adv20_vnd.ge(adv*1e9)&stocks.flow_score_prelim.ge(min_score)].copy()
if phases: s=s[s.market_phase.isin(phases)]
if page=="Stock Screener":
    st.title("Stock Screener")
    a,b,c=st.columns(3)
    a.metric("Cổ phiếu đạt lọc",len(s))
    b.metric("CMF20 dương",f"{s.cmf20.gt(0).mean()*100:.1f}%" if len(s) else "—")
    c.metric("RVOL ≥ 1,5",int(s.rvol20.ge(1.5).sum()))
    st.dataframe(s.sort_values("flow_score_prelim",ascending=False),hide_index=True,use_container_width=True)
    st.download_button("Xuất danh sách CSV",s.to_csv(index=False).encode("utf-8-sig"),"stock_screener.csv","text/csv")
    if len(s):
        st.plotly_chart(px.scatter(s,x="cmf20",y="rvol20",size="adv20_vnd",color="sector",hover_name="ticker",size_max=38),use_container_width=True)
else:
    st.title("Sector Rotation | Dòng tiền theo ngành")
    st.warning("PILOT: Mỗi ngành hiện chỉ có 1 mã. Điểm ngành không đại diện cho toàn ngành. Không thể suy ra luân chuyển dòng tiền qua thời gian từ một phiên dữ liệu.")
    if s.empty:
        st.info("Không có cổ phiếu phù hợp bộ lọc.")
        st.stop()
    g=s.groupby("sector",as_index=False).agg(
        stock_count=("ticker","nunique"),
        avg_score=("flow_score_prelim","mean"),
        cmf_positive_pct=("cmf20",lambda x:100*x.gt(0).mean()),
        obv_rising_pct=("obv_change20",lambda x:100*x.gt(0).mean()),
        high_rvol_pct=("rvol20",lambda x:100*x.ge(1.5).mean()),
        avg_cmf20=("cmf20","mean"),
        avg_rvol20=("rvol20","mean"),
        total_adv_vnd=("adv20_vnd","sum"),
        ret20_mean=("ret20","mean")
    )
    g["liquidity_share_pct"]=100*g.total_adv_vnd/g.total_adv_vnd.sum()
    g["sector_rank"]=g.avg_score.rank(ascending=False,method="min").astype(int)
    g=g.sort_values("sector_rank")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Ngành được lọc",len(g))
    c2.metric("Số cổ phiếu",len(s))
    c3.metric("CMF20 dương",f"{s.cmf20.gt(0).mean()*100:.1f}%")
    c4.metric("Thanh khoản bình quân",f"{s.adv20_vnd.sum()/1e9:,.1f} tỷ/ngày")
    tab0,tab1,tab2,tab3=st.tabs(["Ma trận luân chuyển","Sức mạnh dòng tiền","Độ rộng & thanh khoản","Chi tiết & xuất dữ liệu"])
    with tab0:
        history_path=OUT/"sector_history.csv"
        if not history_path.exists():
            st.info("Chưa có dữ liệu lịch sử ngành. Ma trận sẽ hoạt động khi có output/sector_history.csv được tính từ OHLCV thực tế.")
        else:
            hist=pd.read_csv(history_path,parse_dates=["date"])
            horizon=st.radio("Thay đổi trong số phiên",[5,10,20],index=1,horizontal=True)
            pivot=hist.pivot_table(index="date",columns="sector",values="avg_score",aggfunc="last").sort_index()
            if len(pivot)<=horizon:
                st.warning(f"Cần tối thiểu {horizon+1} phiên dữ liệu ngành; hiện có {len(pivot)}.")
            else:
                current=pivot.iloc[-1]; past=pivot.iloc[-1-horizon]; delta=current-past
                matrix=pd.DataFrame({"sector":current.index,"score":current.values,"delta":delta.values}).dropna()
                matrix=matrix[matrix.sector.isin(g.sector)]
                matrix=matrix.merge(g[["sector","stock_count","total_adv_vnd"]],on="sector",how="left")
                threshold=50
                matrix["quadrant"]=matrix.apply(lambda r:("Dẫn dắt" if r.score>=threshold else "Phục hồi") if r.delta>=0 else ("Hạ nhiệt" if r.score>=threshold else "Suy yếu"),axis=1)
                if matrix.empty: st.info("Không có ngành đủ dữ liệu để vẽ ma trận.")
                else:
                    fig=px.scatter(matrix,x="score",y="delta",size="total_adv_vnd",color="quadrant",text="sector",hover_data=["stock_count"],size_max=55,labels={"score":"Flow Score hiện tại","delta":f"Thay đổi Flow Score {horizon} phiên (điểm)"})
                    fig.add_vline(x=threshold,line_dash="dash",line_color="gray")
                    fig.add_hline(y=0,line_dash="dash",line_color="gray")
                    fig.update_traces(textposition="top center")
                    st.plotly_chart(fig,use_container_width=True)
                    st.dataframe(matrix.sort_values("delta",ascending=False),hide_index=True,use_container_width=True)
                    st.download_button("Xuất dữ liệu ma trận",matrix.to_csv(index=False).encode("utf-8-sig"),"rotation_matrix.csv","text/csv")
                st.caption("Chênh lệch điểm phản ánh thay đổi chỉ báo, không chứng minh dòng vốn dịch chuyển trực tiếp giữa hai ngành. Ngưỡng 50 là quy ước pilot.")
    with tab1:
        fig=px.bar(g,x="avg_score",y="sector",orientation="h",color="cmf_positive_pct",
                   hover_data=["stock_count","avg_cmf20","avg_rvol20"],
                   labels={"avg_score":"Flow Score (pilot)","sector":"Ngành","cmf_positive_pct":"% CMF20 dương"})
        fig.update_layout(yaxis={"categoryorder":"total ascending"},height=max(360,70*len(g)))
        st.plotly_chart(fig,use_container_width=True)
        st.caption("Điểm trung bình các cổ phiếu đạt lọc, không phải điểm ngành chính thức. Ngành ít mã có độ tin cậy thấp.")
    with tab2:
        fig=px.scatter(g,x="cmf_positive_pct",y="obv_rising_pct",size="total_adv_vnd",
                       color="avg_score",hover_name="sector",hover_data=["stock_count","liquidity_share_pct"],
                       labels={"cmf_positive_pct":"% cổ phiếu CMF20 dương","obv_rising_pct":"% cổ phiếu OBV tăng","avg_score":"Flow Score"},
                       size_max=55)
        fig.update_xaxes(range=[-5,105])
        fig.update_yaxes(range=[-5,105])
        st.plotly_chart(fig,use_container_width=True)
        fig2=px.bar(g,x="sector",y="liquidity_share_pct",color="sector",
                    labels={"liquidity_share_pct":"Tỷ trọng GTGD bình quân (%)","sector":"Ngành"})
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2,use_container_width=True)
        st.caption("Tỷ trọng chỉ tính trong tập cổ phiếu đang được lọc, không phải tỷ trọng dòng tiền toàn thị trường.")
    with tab3:
        st.dataframe(g.style.format({"avg_score":"{:.1f}","cmf_positive_pct":"{:.1f}%","obv_rising_pct":"{:.1f}%","high_rvol_pct":"{:.1f}%","avg_cmf20":"{:.3f}","avg_rvol20":"{:.2f}","liquidity_share_pct":"{:.1f}%","ret20_mean":"{:.1%}","total_adv_vnd":"{:,.0f}"}),hide_index=True,use_container_width=True)
        sector=st.selectbox("Xem cổ phiếu trong ngành",g.sector.tolist())
        st.dataframe(s.loc[s.sector.eq(sector),["ticker","close","cmf20","rvol20","ret20","flow_score_prelim","vsa_signal"]],hide_index=True,use_container_width=True)
        st.download_button("Xuất Sector Rotation CSV",g.to_csv(index=False).encode("utf-8-sig"),"sector_rotation_improved.csv","text/csv")
    st.info("Tính năng so sánh 5/10/20 phiên sẽ được kích hoạt khi có dữ liệu lịch sử theo ngày. Không dùng dữ liệu giả để tạo xu hướng.")
