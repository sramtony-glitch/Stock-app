from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# ----------------------------------------------------
# ⚙️ 頁面設定
# ----------------------------------------------------
st.set_page_config(
    page_title="散戶 vs 法人 價量加權持股成本分析系統 (規格書 v1.0)",
    page_icon="📈",
    layout="wide",
)


# ----------------------------------------------------
# 🏷️ 股票中文名稱查詢
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
# 📊 抓取 FinMind 籌碼數據 (三大法人、融資、當沖)
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def fetch_chip_data(stock_code, s_date, e_date):
    # 1. 三大法人買賣超 (T86)
    inst_url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={stock_code}&start_date={s_date}&end_date={e_date}"
    resp_inst = requests.get(inst_url, timeout=15).json()

    # 2. 融資融券 (MI_MARGN)
    margin_url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMarginPurchaseShortSale&data_id={stock_code}&start_date={s_date}&end_date={e_date}"
    resp_margin = requests.get(margin_url, timeout=15).json()

    # 3. 當沖統計
    daytrade_url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockDayTrading&data_id={stock_code}&start_date={s_date}&end_date={e_date}"
    resp_dt = requests.get(daytrade_url, timeout=15).json()

    # 整理三大法人 (張數)
    inst_df = pd.DataFrame(resp_inst.get("data", []))
    if not inst_df.empty:
        inst_df["buy"] = (
            pd.to_numeric(inst_df["buy"], errors="coerce").fillna(0) / 1000.0
        )
        inst_df["sell"] = (
            pd.to_numeric(inst_df["sell"], errors="coerce").fillna(0) / 1000.0
        )
        inst_df["net"] = inst_df["buy"] - inst_df["sell"]

        foreign_df = (
            inst_df[inst_df["name"].str.contains("Foreign|外資", na=False)]
            .groupby("date")["buy"]
            .sum()
            .reset_index(name="foreign_buy")
        )
        inst_total_buy = (
            inst_df.groupby("date")["buy"]
            .sum()
            .reset_index(name="inst_total_buy")
        )
    else:
        foreign_df = pd.DataFrame(columns=["date", "foreign_buy"])
        inst_total_buy = pd.DataFrame(columns=["date", "inst_total_buy"])

    # 整理融資 (張數)
    margin_df = pd.DataFrame(resp_margin.get("data", []))
    if not margin_df.empty:
        margin_df["MarginPurchase"] = pd.to_numeric(
            margin_df["MarginPurchase"], errors="coerce"
        ).fillna(0)
        margin_df["MarginPurchaseTodayBalance"] = pd.to_numeric(
            margin_df["MarginPurchaseTodayBalance"], errors="coerce"
        ).fillna(0)
        margin_clean = margin_df[
            ["date", "MarginPurchase", "MarginPurchaseTodayBalance"]
        ].rename(
            columns={
                "MarginPurchase": "margin_delta",
                "MarginPurchaseTodayBalance": "margin_balance",
            }
        )
    else:
        margin_clean = pd.DataFrame(
            columns=["date", "margin_delta", "margin_balance"]
        )

    # 整理當沖 (股數 -> 張數，雙邊合計除以 2000)
    dt_df = pd.DataFrame(resp_dt.get("data", []))
    if not dt_df.empty and "BuyVolume" in dt_df.columns:
        dt_df["daytrade_vol"] = pd.to_numeric(
            dt_df["BuyVolume"], errors="coerce"
        ).fillna(0)
        dt_clean = dt_df[["date", "daytrade_vol"]]
    else:
        dt_clean = pd.DataFrame(columns=["date", "daytrade_vol"])

    return inst_total_buy, foreign_df, margin_clean, dt_clean


# ----------------------------------------------------
# 🚀 主程式介面
# ----------------------------------------------------
st.title("📈 散戶 vs 法人 價量加權持股成本分析系統")
st.caption(
    "遵循計算規格書 v1.0：VWAP加權、除權息還原、當沖剔除、存貨加權沖銷、融資純度驗證"
)

col1, col2, col3 = st.columns(3)
with col1:
    stock_id = st.text_input("【股票代號】", value="2330").strip()
with col2:
    default_start = datetime.today() - timedelta(days=180)
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

    # 抓取行情 (自動除權息還原)
    ticker = f"{stock_id}.TW"
    price_df = yf.download(
        ticker,
        start=s_str,
        end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker,
            start=s_str,
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )

    if not price_df.empty:
        if isinstance(price_df.columns, pd.MultiIndex):
            open_s = price_df["Open"][ticker]
            high_s = price_df["High"][ticker]
            low_s = price_df["Low"][ticker]
            close_s = price_df["Close"][ticker]
            vol_s = price_df["Volume"][ticker] / 1000.0
        else:
            open_s = price_df["Open"]
            high_s = price_df["High"]
            low_s = price_df["Low"]
            close_s = price_df["Close"]
            vol_s = price_df["Volume"] / 1000.0

        df = pd.DataFrame(
            {
                "Open": open_s,
                "High": high_s,
                "Low": low_s,
                "Close": close_s,
                "Total_Vol": vol_s,
            }
        )
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")

        # Step 0: 當日均價 (VWAP 逼近值)
        df["adj_vwap"] = (df["High"] + df["Low"] + df["Close"]) / 3.0

        # 合併籌碼資料
        inst_buy, foreign_buy, margin, dt = fetch_chip_data(
            stock_id, s_str, e_str
        )

        for sub_df in [inst_buy, foreign_buy, margin, dt]:
            if not sub_df.empty:
                sub_df.set_index("date", inplace=True)
                df = df.join(sub_df, how="left")

        df.fillna(0, inplace=True)

        # Step 1: 殘差散戶量 = 總成交量 - 三大法人買進
        df["raw_retail_vol"] = df["Total_Vol"] - df["inst_total_buy"]

        # Step 2: 剔除當沖量 (當沖成交量 / 2000)
        df["daytrade_est"] = df["daytrade_vol"] / 2000.0
        df["eff_retail_vol"] = (
            df["raw_retail_vol"] - df["daytrade_est"]
        ).apply(lambda x: max(x, 0))

        # Step 3: 純度指標與品質標記 (purity = margin_delta / eff_retail_vol)
        def calc_quality(row):
            if row["eff_retail_vol"] <= 0:
                return "NA"
            p = row["margin_delta"] / row["eff_retail_vol"]
            if p >= 0.30:
                return "HIGH"
            elif p >= 0.10:
                return "MEDIUM"
            else:
                return "LOW"

        df["quality_flag"] = df.apply(calc_quality, axis=1)

        # Step 4: 斷頭日偵測 (margin_delta / margin_balance[t-1] <= -3%)
        df["margin_shift"] = df["margin_balance"].shift(1)
        df["blowout_day"] = (
            df["margin_delta"] / df["margin_shift"].replace(0, np.nan)
        ) <= -0.03

        # Step 6: 存貨加權平均成本計算 (賣超以現行成本沖銷，成本不變部位減少)
        cum_cost_list = []
        cum_qty = 0.0
        cum_amt = 0.0
        current_avg = df["adj_vwap"].iloc[0]

        for idx, row in df.iterrows():
            # 斷頭日重置起算點
            if row["blowout_day"]:
                cum_qty = 0.0
                cum_amt = 0.0

            q = row["eff_retail_vol"]
            p = row["adj_vwap"]

            if q > 0:
                cum_amt += q * p
                cum_qty += q
                current_avg = cum_amt / cum_qty if cum_qty > 0 else current_avg
            elif q < 0:
                sell_q = abs(q)
                cum_amt -= sell_q * current_avg
                cum_qty -= sell_q
                if cum_qty <= 0:
                    cum_qty = 0.0
                    cum_amt = 0.0

            cum_cost_list.append(current_avg)

        df["retail_cost_range"] = cum_cost_list

        # Step 7: 向量化滾動成本線 (N=5, 20, 60)
        retail_amt = df["eff_retail_vol"] * df["adj_vwap"]
        df["retail_cost_ma5"] = (
            retail_amt.rolling(5).sum() / df["eff_retail_vol"].rolling(5).sum()
        ).fillna(df["Close"])
        df["retail_cost_ma20"] = (
            retail_amt.rolling(20).sum()
            / df["eff_retail_vol"].rolling(20).sum()
        ).fillna(df["Close"])
        df["retail_cost_ma60"] = (
            retail_amt.rolling(60).sum()
            / df["eff_retail_vol"].rolling(60).sum()
        ).fillna(df["Close"])

        # 外資 20 日滾動成本
        f_amt = df["foreign_buy"] * df["adj_vwap"]
        df["foreign_cost_ma20"] = (
            f_amt.rolling(20).sum() / df["foreign_buy"].rolling(20).sum()
        ).fillna(df["Close"])

        # 狀態指標顯示
        latest_close = float(df["Close"].iloc[-1])
        latest_retail_cost = float(df["retail_cost_ma20"].iloc[-1])
        latest_foreign_cost = float(df["foreign_cost_ma20"].iloc[-1])
        dev_pct = (
            (latest_close - latest_retail_cost) / latest_retail_cost
        ) * 100

        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("最新還原收盤價", f"{latest_close:.2f} 元")
        c2.metric("散戶20D洗淨成本", f"{latest_retail_cost:.2f} 元")
        c3.metric("外資20D預估成本", f"{latest_foreign_cost:.2f} 元")
        c4.metric(
            "散戶狀態",
            "🟢 獲利中" if latest_close >= latest_retail_cost else "⚠️ 散戶套牢中",
            f"{dev_pct:+.2f}%",
        )

        # 💡 限制與定義說明
        st.info(
            """
            **📋 系統計算規格與限制說明：**
            1. **散戶成本為推估殘差值**：已剔除三大法人及當沖量，僅供相對支撐/壓力參考。
            2. **均線標示**：🟣 **紫色實線**為【散戶洗淨成本 (20D)】；🔵 **藍色虛線**為【外資預估成本 (20D)】。
            3. **賣超處理**：固定採「**存貨加權平均法**」沖銷，賣超期間均價不變僅部位減少。
            4. **綠色垂直線**：代表偵測到融資單日大減之【斷頭重置日 (Blowout Day)】。
            """
        )

        # 繪製圖表
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.75, 0.25],
        )

        # K線
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="K線",
            ),
            row=1,
            col=1,
        )

        # 散戶成本線 (紫色實線)
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["retail_cost_ma20"],
                name="🟣 散戶洗淨成本 (20D)",
                line=dict(color="#ab63fa", width=2.5),
            ),
            row=1,
            col=1,
        )

        # 外資成本線 (藍色虛線)
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["foreign_cost_ma20"],
                name="🔵 外資預估成本 (20D)",
                line=dict(color="#00cc96", width=2, dash="dot"),
            ),
            row=1,
            col=1,
        )

        # 標記斷頭日
        blowout_dates = df[df["blowout_day"]].index
        for b_date in blowout_dates:
            fig.add_vline(
                x=b_date,
                line_width=1.5,
                line_dash="dash",
                line_color="#00FF7F",
                annotation_text=f"斷頭重置 ({b_date})",
                annotation_position="top left",
                row=1,
                col=1,
            )

        # 成交量柱狀圖
        colors = [
            "#ef553b" if c >= o else "#00cc96"
            for c, o in zip(df["Close"], df["Open"])
        ]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Total_Vol"],
                name="成交量 (張)",
                marker_color=colors,
            ),
            row=2,
            col=1,
        )

        fig.update_layout(
            title=dict(
                text=f"{title_text} 散戶 vs 法人籌碼成本走勢圖",
                x=0.5,
                font=dict(size=16),
            ),
            xaxis=dict(
                fixedrange=True,
                type="date",
                rangebreaks=[dict(bounds=["sat", "mon"])],
                rangeslider=dict(visible=False),
            ),
            xaxis2=dict(
                type="date",
                rangebreaks=[dict(bounds=["sat", "mon"])],
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(fixedrange=True, side="right"),
            yaxis2=dict(fixedrange=True, side="right", title="成交量 (張)"),
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
    else:
        st.warning("⚠️ 查無行情資料，請確認股票代號。")
