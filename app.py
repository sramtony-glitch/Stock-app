from datetime import datetime, timedelta
import io
import pandas as pd
import plotly.graph_objects as io_plotly
from plotly.subplots import make_subplots
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

# 設定網頁標題與響應式滿版版面
st.set_page_config(
    page_title="台股籌碼與股價對照系統", page_icon="📈", layout="wide"
)

# 注入 CSS
st.markdown(
    """
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    </head>
    <style>
    .stTextInput label, .stDateInput label { font-size: 18px !important; font-weight: bold !important; }
    .stTextInput input, .stDateInput input { font-size: 18px !important; font-weight: bold !important; }
    h1 { font-size: 28px !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: auto !important; }
    </style>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------
# 🔐 1. 欄位一：每月密碼驗證 (30天記憶)
# ----------------------------------------------------
current_time = datetime.now()
year_month_key = current_time.strftime("%Y_%m")

YEARLY_PASSWORDS = {
    "2026_07": "stock777",
    "2026_08": "august888",
    "2026_09": "september999",
    "2026_10": "october168",
    "2026_11": "november520",
    "2026_12": "december999",
    "2027_01": "happy2027",
    "2027_02": "cny2027",
}

CORRECT_PASSWORD = YEARLY_PASSWORDS.get(year_month_key, "stock2026")

if "authenticated" not in st.session_state:
  st.session_state["authenticated"] = False

query_params = st.query_params
if (
    not st.session_state["authenticated"]
    and query_params.get("auth_token") == CORRECT_PASSWORD
):
  st.session_state["authenticated"] = True


def check_password():
  if st.session_state["authenticated"]:
    return True

  st.title("🔒 系統授權鎖定")
  st.caption("請輸入每月授權密碼以存取圖表分析（輸入一次可維持 30 天登入狀態）。")

  user_pwd = st.text_input("【欄位一】請輸入授權密碼：", type="password")

  if st.button("解鎖並進入系統", type="primary"):
    if user_pwd == CORRECT_PASSWORD:
      st.session_state["authenticated"] = True
      st.query_params["auth_token"] = CORRECT_PASSWORD
      st.success("驗證成功！已自動記住認證狀態。")
      st.rerun()
    else:
      st.error("❌ 密碼錯誤，請向管理者索取當月密碼！")

  components.html(
      f"""
        <script>
            const savedToken = localStorage.getItem('stock_app_auth_token');
            const tokenTime = localStorage.getItem('stock_app_auth_time');
            const now = new Date().getTime();
            
            if (savedToken === '{CORRECT_PASSWORD}' && tokenTime && (now - parseInt(tokenTime) < 2592000000)) {{
                const url = new URL(window.location.href);
                if (!url.searchParams.has('auth_token')) {{
                    url.searchParams.set('auth_token', '{CORRECT_PASSWORD}');
                    window.location.href = url.href;
                }}
            }}
        </script>
    """,
      height=0,
  )

  return False


if st.session_state["authenticated"]:
  components.html(
      f"""
        <script>
            localStorage.setItem('stock_app_auth_token', '{CORRECT_PASSWORD}');
            localStorage.setItem('stock_app_auth_time', new Date().getTime().toString());
        </script>
    """,
      height=0,
  )


# ----------------------------------------------------
# 🏷️ 台股繁體中文名稱查詢器
# ----------------------------------------------------
@st.cache_data(ttl=86400)
def get_tw_stock_name(stock_code):
  try:
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
      data = resp.json()
      for item in data:
        if item.get("Code") == stock_code:
          return item.get("Name")
  except Exception:
    pass

  fallback_names = {
      "2330": "台積電",
      "2317": "鴻海",
      "2454": "聯發科",
      "2618": "長榮航",
      "2603": "長榮",
      "2609": "陽明",
      "2615": "萬海",
      "2646": "星宇航空",
      "2316": "楠梓電",
      "2308": "台達電",
      "2382": "廣達",
      "3231": "緯創",
      "2356": "英業達",
  }
  if stock_code in fallback_names:
    return fallback_names[stock_code]

  try:
    fm_url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo&data_id={stock_code}"
    res = requests.get(fm_url, timeout=5).json()
    if res.get("data"):
      return res["data"][0]["stock_name"]
  except Exception:
    pass

  return stock_code


# ----------------------------------------------------
# 🚀 2. 主程式
# ----------------------------------------------------
if check_password():
  st.title("📈 台股每日 K 線 vs 20日外資與散戶成本對照圖")

  col1, col2, col3 = st.columns([2, 1.5, 1.5])

  with col1:
    stock_id = st.text_input(
        "【欄位二】股票代號（範例: 2618）", value="2618"
    ).strip()

  default_start = datetime.now().date() - timedelta(days=120)
  default_end = datetime.now().date()

  with col2:
    start_date = st.date_input("【欄位三】起始日期", value=default_start)

  with col3:
    end_date = st.date_input("【欄位四】結束日期", value=default_end)

  # ----------------------------------------------------
  # 📊 外資與散戶籌碼數據
  # ----------------------------------------------------
  @st.cache_data(ttl=1800)
  def fetch_institutional_data(stock_code, s_date, e_date):
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": stock_code,
        "start_date": s_date.strftime("%Y-%m-%d"),
        "end_date": e_date.strftime("%Y-%m-%d"),
    }
    try:
      resp = requests.get(url, params=params, timeout=15)
      data = resp.json()
      if data.get("msg") == "success" and data.get("data"):
        df = pd.DataFrame(data["data"])
        df["buy"] = pd.to_numeric(df["buy"], errors="coerce") / 1000.0

        foreign_df = df[df["name"].str.contains("Foreign|外資", na=False)]
        foreign_buy = (
            foreign_df.groupby("date")["buy"].sum().reset_index()
            if not foreign_df.empty
            else df.groupby("date")["buy"].sum().reset_index()
        )
        foreign_buy.columns = ["Date", "Foreign_Buy_Qty"]

        inst_buy = df.groupby("date")["buy"].sum().reset_index()
        inst_buy.columns = ["Date", "Inst_Buy_Qty"]

        res_df = pd.merge(foreign_buy, inst_buy, on="Date", how="outer")
        res_df["Date"] = pd.to_datetime(res_df["Date"])
        return res_df.sort_values("Date")
    except Exception:
      pass
    return pd.DataFrame()

  try:
    with st.spinner("正在計算 20 日外資成本與散戶成本數據..."):
      stock_name = get_tw_stock_name(stock_id)

      ticker = f"{stock_id}.TW"
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )
      if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

      inst_df = fetch_institutional_data(stock_id, start_date, end_date)

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 繪製圖表 (關閉底部 rangeslider)
  # ----------------------------------------------------
  if price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】的股價資料！")
  else:
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

    plot_df = pd.DataFrame({
        "Open": open_s,
        "High": high_s,
        "Low": low_s,
        "Close": close_s,
        "Total_Volume": vol_s,
    })
    plot_df.index = pd.to_datetime(plot_df.index)

    if not inst_df.empty:
      inst_df = inst_df.set_index("Date")
      plot_df = plot_df.join(inst_df, how="left")

    plot_df["Foreign_Buy_Qty"] = plot_df["Foreign_Buy_Qty"].fillna(0)
    plot_df["Inst_Buy_Qty"] = plot_df["Inst_Buy_Qty"].fillna(0)

    plot_df["Retail_Volume"] = (
        plot_df["Total_Volume"] - plot_df["Inst_Buy_Qty"]
    ).apply(lambda x: max(x, 0))

    plot_df["Foreign_Amt"] = plot_df["Foreign_Buy_Qty"] * plot_df["Close"]
    plot_df["Retail_Amt"] = plot_df["Retail_Volume"] * plot_df["Close"]

    plot_df["Foreign_20D_Cost"] = (
        plot_df["Foreign_Amt"].rolling(window=20).sum()
        / plot_df["Foreign_Buy_Qty"].rolling(window=20).sum()
    )
    plot_df["Retail_20D_Cost"] = (
        plot_df["Retail_Amt"].rolling(window=20).sum()
        / plot_df["Retail_Volume"].rolling(window=20).sum()
    )

    plot_df["MA20"] = plot_df["Close"].rolling(window=20).mean()
    plot_df["Foreign_20D_Cost"] = plot_df["Foreign_20D_Cost"].fillna(
        plot_df["MA20"]
    )
    plot_df["Retail_20D_Cost"] = plot_df["Retail_20D_Cost"].fillna(
        plot_df["MA20"]
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. 繪製台股標準日 K 線圖
    fig.add_trace(
        io_plotly.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="日 K 線",
            increasing_line_color="#FF3333",
            increasing_fillcolor="#FF3333",
            decreasing_line_color="#00B359",
            decreasing_fillcolor="#00B359",
        ),
        secondary_y=False,
    )

    # 2. 外資20日成本線
    fig.add_trace(
        io_plotly.Scatter(
            x=plot_df.index,
            y=plot_df["Foreign_20D_Cost"],
            name="外資20日成本線",
            mode="lines",
            line=dict(color="#0066FF", width=2.5, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>外資20日成本: $%{y:.2f}",
        ),
        secondary_y=False,
    )

    # 3. 散戶20日成本線
    fig.add_trace(
        io_plotly.Scatter(
            x=plot_df.index,
            y=plot_df["Retail_20D_Cost"],
            name="散戶20日成本線",
            mode="lines",
            line=dict(color="#FF8C00", width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>散戶20日成本: $%{y:.2f}",
        ),
        secondary_y=False,
    )

    display_title = (
        f"{stock_name} ({stock_id})" if stock_name != stock_id else stock_id
    )

    fig.update_layout(
        title={
            "text": (
                f"<b>【{display_title}】 日 K 線 vs 外資成本線 vs 散戶成本線</b>"
            ),
            "x": 0.5,
            "xanchor": "center",
            "y": 0.96,
            "yanchor": "top",
            "font": {"size": 19},
        },
        hovermode="x unified",
        autosize=True,
        margin=dict(l=15, r=15, t=90, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=15),
        ),
        hoverlabel=dict(font_size=15),
        # 關鍵精髓：徹底隱藏底部的 rangeslider
        xaxis=dict(
            fixedrange=True,
            type="date",
            rangebreaks=[dict(bounds=["sat", "mon"])],
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(fixedrange=True),
    )

    fig.update_yaxes(
        title_text="<b>股票價格 / 成本 (元)</b>",
        title_font=dict(size=18),
        tickfont=dict(size=14),
        secondary_y=False,
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    fig.update_xaxes(
        title_text=f"<b>日期期間：{start_date} ～ {end_date}</b>",
        title_font=dict(size=16),
        tickfont=dict(size=14),
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": False, "displayModeBar": False},
    )
