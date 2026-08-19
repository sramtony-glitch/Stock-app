from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as io_plotly
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# ----------------------------------------------------
# ⚙️ 頁面設定
# ----------------------------------------------------
st.set_page_config(
    page_title="外資 vs 散戶 價量加權持股成本分析系統",
    page_icon="📈",
    layout="wide",
)


# ----------------------------------------------------
# 🏷️ 股票名稱查詢
# ----------------------------------------------------
@st.cache_data(ttl=86400)
def get_tw_stock_name(stock_code):
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, timeout=10)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        for val in df["有價證券代號及名稱"]:
            if str(stock_code) in str(val):
                return str(val).split("\u3000")[-1].strip()
    except Exception:
        pass
    return ""


# ----------------------------------------------------
# 📊 抓取外資買賣超
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_foreign_data(stock_code, s_date, e_date):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={stock_code}&start_date={s_date}&end_date={e_date}"
    resp = requests.get(url, timeout=15)
    data = resp.json()
    if data.get("msg") == "success" and data.get("data"):
        df = pd.DataFrame(data["data"])
        df["buy"] = pd.to_numeric(df["buy"], errors="coerce") / 1000.0  # 張數

        # 篩選外資
        foreign_df = df[df["name"].str.contains("Foreign|外資", na=False)]
        if not foreign_df.empty:
            f_buy = foreign_df.groupby("date")["buy"].sum().reset_index()
            f_buy.rename(columns={"buy": "Foreign_Buy"}, inplace=True)
            return f_buy
    return pd.DataFrame(columns=["date", "Foreign_Buy"])


# ----------------------------------------------------
# 🚀 主程式
# ----------------------------------------------------
st.title("📈 外資 vs 散戶 價量加權持股成本分析系統")

col1, col2, col3 = st.columns(3)
with col1:
    stock_id = st.text_input("【股票代號】", value="2330").strip()
with col2:
    default_start = datetime.today() - timedelta(days=90)
    start_date = st.date_input("【開始日期】", value=default_start)
with col3:
    default_end = datetime.today()
    end_date = st.date_input("【結束日期】", value=default_end)

if stock_id:
    stock_name = get_tw_stock_name(stock_id)
    title_text = f"{stock_id} {stock_name}" if stock_name else stock_id
    st.subheader(f"📊 分析標的：{title_text}")

    s_str = start_date.strftime("%Y-%m-%d")
    e_str = end_date.strftime("%Y-%m-%d")

    # 抓取外資資料
    foreign_df = fetch_foreign_data(stock_id, s_str, e_str)

    # 抓取 K 線行情
    ticker = f"{stock_id}.TW"
    price_df = yf.download(
        ticker,
        start=s_str,
        end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
    )

    if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker,
            start=s_str,
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
        )

    if not price_df.empty:
        if isinstance(price_df.columns, pd.MultiIndex):
            open_s = price_df["Open"][ticker]
            high_s = price_df["High"][ticker]
            low_s = price_df["Low"][ticker]
            close_s = price_df["Close"][ticker]
            vol_s = price_df["Volume"][ticker] / 1000.0  # 張數
        else:
            open_s = price_df["Open"]
            high_s = price_df["High"]
            low_s = price_df["Low"]
            close_s = price_df["Close"]
            vol_s = price_df["Volume"] / 1000.0

        plot_df = pd.DataFrame(
            {
                "Open": open_s,
                "High": high_s,
                "Low": low_s,
                "Close": close_s,
                "Total_Vol": vol_s,
            }
        )
        plot_df.index = pd.to_datetime(plot_df.index).strftime("%Y-%m-%d")

        if not foreign_df.empty:
            foreign_df.set_index("date", inplace=True)
            plot_df = plot_df.join(foreign_df, how="left")
        else:
            plot_df["Foreign_Buy"] = 0

        plot_df["Foreign_Buy"] = plot_df["Foreign_Buy"].fillna(0)

        # 散戶張數 = 總量 - 外資
        plot_df["Retail_Buy"] = (
            plot_df["Total_Vol"] - plot_df["Foreign_Buy"]
        ).apply(lambda x: max(x, 1))

        # 每日成交金額估算
        plot_df["Foreign_Amt"] = plot_df["Foreign_Buy"] * plot_df["Close"]
        plot_df["Retail_Amt"] = plot_df["Retail_Buy"] * plot_df["Close"]

        # 20日滾動價量加權成本
        plot_df["Foreign_20D_Cost"] = (
            plot_df["Foreign_Amt"].rolling(20).sum()
            / plot_df["Foreign_Buy"].rolling(20).sum()
        )
        plot_df["Retail_20D_Cost"] = (
            plot_df["Retail_Amt"].rolling(20).sum()
            / plot_df["Retail_Buy"].rolling(20).sum()
        )

        # 若無外資買盤則用 20日均價補充
        plot_df["MA20"] = plot_df["Close"].rolling(20).mean()
        plot_df["Foreign_20D_Cost"] = plot_df["Foreign_20D_Cost"].fillna(
            plot_df["MA20"]
        )
        plot_df["Retail_20D_Cost"] = plot_df["Retail_20D_Cost"].fillna(
            plot_df["MA20"]
        )

        # 繪製圖表
        fig = make_subplots(specs=[[{"secondary_y": False}]])

        fig.add_trace(
            io_plotly.Candlestick(
                x=plot_df.index,
                open=plot_df["Open"],
                high=plot_df["High"],
                low=plot_df["Low"],
                close=plot_df["Close"],
                name="K線",
            )
        )

        # 外資價量加權成本線
        fig.add_trace(
            io_plotly.Scatter(
                x=plot_df.index,
                y=plot_df["Foreign_20D_Cost"],
                name="外資成本 (20D)",
                line=dict(color="#1f77b4", width=2),
            )
        )

        # 散戶價量加權成本線
        fig.add_trace(
            io_plotly.Scatter(
                x=plot_df.index,
                y=plot_df["Retail_20D_Cost"],
                name="散戶成本 (20D)",
                line=dict(color="#ff7f0e", width=2),
            )
        )

        fig.update_layout(
            title=dict(
                text=f"{title_text} 價量加權持股成本走勢",
                x=0.5,
                font=dict(size=14),
            ),
            xaxis=dict(
                fixedrange=True,
                type="date",
                rangebreaks=[dict(bounds=["sat", "mon"])],
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(fixedrange=True, side="right"),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"scrollZoom": False, "displayModeBar": False},
        )

        # 數據統計整理
        total_foreign_amt = plot_df["Foreign_Amt"].sum()
        total_foreign_qty = plot_df["Foreign_Buy"].sum()
        overall_foreign_cost = (
            total_foreign_amt / total_foreign_qty
            if total_foreign_qty > 0
            else 0
        )

        total_retail_amt = plot_df["Retail_Amt"].sum()
        total_retail_qty = plot_df["Retail_Buy"].sum()
        overall_retail_cost = (
            total_retail_amt / total_retail_qty if total_retail_qty > 0 else 0
        )

        st.markdown("### 📋 區間籌碼成本總結")
        m1, m2 = st.columns(2)
        m1.metric("外資全區間平均成本", f"{overall_foreign_cost:.2f} 元")
        m2.metric("散戶全區間平均成本", f"{overall_retail_cost:.2f} 元")
    else:
        st.warning("⚠️ 查無此股票行情資料，請確認股票代號是否正確。")
