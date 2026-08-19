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
    page_title="三大法人 vs 散戶 價量加權持股成本分析系統",
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
# 📊 抓取三大法人買賣超 (外資 + 投信 + 自營商)
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_institutional_data(stock_code, s_date, e_date):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={stock_code}&start_date={s_date}&end_date={e_date}"
    resp = requests.get(url, timeout=15)
    data = resp.json()

    if data.get("msg") == "success" and data.get("data"):
        df = pd.DataFrame(data["data"])
        df["buy"] = pd.to_numeric(df["buy"], errors="coerce") / 1000.0  # 轉為張數

        # 彙總三大法人（外資、投信、自營商）每日總買進張數
        inst_buy = df.groupby("date")["buy"].sum().reset_index()
        inst_buy.rename(columns={"buy": "Inst_Buy"}, inplace=True)
        return inst_buy

    return pd.DataFrame(columns=["date", "Inst_Buy"])


# ----------------------------------------------------
# 🚀 主程式
# ----------------------------------------------------
st.title("📈 三大法人 vs 純散戶 價量加權持股成本分析系統")

col1, col2, col3 = st.columns(3)
with col1:
    stock_id = st.text_input("【股票代號】", value="2330").strip()
with col2:
    default_start = datetime.today() - timedelta(days=120)
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

    # 抓取三大法人資料
    inst_df = fetch_institutional_data(stock_id, s_str, e_str)

    # 抓取行情 (K線)
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

        # 合併法人買盤
        if not inst_df.empty:
            inst_df.set_index("date", inplace=True)
            plot_df = plot_df.join(inst_df, how="left")
        else:
            plot_df["Inst_Buy"] = 0

        plot_df["Inst_Buy"] = plot_df["Inst_Buy"].fillna(0)

        # 💡 精化計算 1：計算當日典型均價 (Typical Price)，比單純用收盤價更貼近全日買進均價
        plot_df["Typical_Price"] = (
            plot_df["High"] + plot_df["Low"] + plot_df["Close"]
        ) / 3.0

        # 💡 精化計算 2：扣除三大法人（外資+投信+自營商）取得純散戶張數
        plot_df["Retail_Buy"] = (
            plot_df["Total_Vol"] - plot_df["Inst_Buy"]
        ).apply(lambda x: max(x, 1))

        # 每日成交金額估算
        plot_df["Inst_Amt"] = plot_df["Inst_Buy"] * plot_df["Typical_Price"]
        plot_df["Retail_Amt"] = (
            plot_df["Retail_Buy"] * plot_df["Typical_Price"]
        )

        # 20日滾動價量加權成本 (VWAP)
        plot_df["Inst_20D_Cost"] = (
            plot_df["Inst_Amt"].rolling(20).sum()
            / plot_df["Inst_Buy"].rolling(20).sum()
        )
        plot_df["Retail_20D_Cost"] = (
            plot_df["Retail_Amt"].rolling(20).sum()
            / plot_df["Retail_Buy"].rolling(20).sum()
        )

        # 若缺乏法人買盤則以 20日均價填補
        plot_df["MA20"] = plot_df["Close"].rolling(20).mean()
        plot_df["Inst_20D_Cost"] = plot_df["Inst_20D_Cost"].fillna(
            plot_df["MA20"]
        )
        plot_df["Retail_20D_Cost"] = plot_df["Retail_20D_Cost"].fillna(
            plot_df["MA20"]
        )

        # 最新損益狀態判定
        latest_close = float(plot_df["Close"].iloc[-1])
        latest_retail_cost = float(plot_df["Retail_20D_Cost"].iloc[-1])
        latest_inst_cost = float(plot_df["Inst_20D_Cost"].iloc[-1])

        retail_pnl_pct = (
            (latest_close - latest_retail_cost) / latest_retail_cost
        ) * 100
        inst_pnl_pct = (
            (latest_close - latest_inst_cost) / latest_inst_cost
        ) * 100

        st.markdown("---")
        st_col1, st_col2 = st.columns(2)
        with st_col1:
            st.markdown("#### 🔵 三大法人（大戶）狀態")
            if latest_close >= latest_inst_cost:
                st.success(
                    f"🟢 **法人獲利中** (現價高於法人成本 {inst_pnl_pct:+.2f}%)"
                )
            else:
                st.warning(
                    f"⚠️ **法人套牢中** (現價低於法人成本 {inst_pnl_pct:+.2f}%)"
                )

        with st_col2:
            st.markdown("#### 🟠 純散戶狀態")
            if latest_close >= latest_retail_cost:
                st.success(
                    f"🟢 **散戶獲利中** (現價高於散戶成本 {retail_pnl_pct:+.2f}%)"
                )
            else:
                st.warning(
                    f"⚠️ **散戶套牢中** (現價低於散戶成本 {retail_pnl_pct:+.2f}%)"
                )

        # 💡 指標說明卡片
        st.info(
            """
            **📊 成本均線與模型說明：**
            * 🔵 **藍色線【三大法人加權成本 (20D)】**：外資、投信、自營商在近 20 日內的典型成交加權平均成本。當股價高於此線，代表三大法人處於獲利控盤狀態。
            * 🟠 **橘色線【純散戶加權成本 (20D)】**：總成交量完整扣除三大法人買盤後的散戶 20 日加權平均成本。
            * 💡 **算法特點**：改採當日典型價格 $(High + Low + Close) / 3$ 結合價量加權（VWAP），有效降低單一收盤價的失真率。
            """
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

        # 三大法人價量加權成本線 (藍色)
        fig.add_trace(
            io_plotly.Scatter(
                x=plot_df.index,
                y=plot_df["Inst_20D_Cost"],
                name="🔵 三大法人成本 (20D)",
                line=dict(color="#1f77b4", width=2.5),
            )
        )

        # 純散戶價量加權成本線 (橘色)
        fig.add_trace(
            io_plotly.Scatter(
                x=plot_df.index,
                y=plot_df["Retail_20D_Cost"],
                name="🟠 純散戶成本 (20D)",
                line=dict(color="#ff7f0e", width=2.5),
            )
        )

        fig.update_layout(
            title=dict(
                text=f"{title_text} 三大法人 vs 散戶持股成本走勢圖",
                x=0.5,
                font=dict(size=15),
            ),
            xaxis=dict(
                fixedrange=True,
                type="date",
                rangebreaks=[dict(bounds=["sat", "mon"])],
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(fixedrange=True, side="right"),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"scrollZoom": False, "displayModeBar": False},
        )

        # 數據統計整理
        total_inst_amt = plot_df["Inst_Amt"].sum()
        total_inst_qty = plot_df["Inst_Buy"].sum()
        overall_inst_cost = (
            total_inst_amt / total_inst_qty if total_inst_qty > 0 else 0
        )

        total_retail_amt = plot_df["Retail_Amt"].sum()
        total_retail_qty = plot_df["Retail_Buy"].sum()
        overall_retail_cost = (
            total_retail_amt / total_retail_qty if total_retail_qty > 0 else 0
        )

        st.markdown("### 📋 區間籌碼成本總結")
        m1, m2 = st.columns(2)
        m1.metric(
            "🔵 三大法人全區間平均成本", f"{overall_inst_cost:.2f} 元"
        )
        m2.metric(
            "🟠 純散戶全區間平均成本", f"{overall_retail_cost:.2f} 元"
        )
    else:
        st.warning("⚠️ 查無此股票行情資料，請確認股票代號是否正確。")
