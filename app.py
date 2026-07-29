from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as io_plotly
from plotly.subplots import make_subplots
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

# 設定網頁標題與響應式滿版版面
st.set_page_config(
    page_title="外資 vs 散戶籌碼價量成本分析", page_icon="📈", layout="wide"
)

st.markdown(
    """
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    </head>
    <style>
    .stTextInput label, .stDateInput label { font-size: 18px !important; font-weight: bold !important; }
    .stTextInput input, .stDateInput input { font-size: 18px !important; font-weight: bold !important; }
    h1 { font-size: 26px !important; }
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
  st.caption("請輸入每月授權密碼以存取籌碼分析圖。")

  user_pwd = st.text_input("【授權密碼】請輸入當月密碼：", type="password")

  if st.button("解鎖並進入系統", type="primary"):
    if user_pwd == CORRECT_PASSWORD:
      st.session_state["authenticated"] = True
      st.query_params["auth_token"] = CORRECT_PASSWORD
      st.success("驗證成功！")
      st.rerun()
    else:
      st.error("❌ 密碼錯誤！")

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
# 🏷️ 股票中文名稱查詢器
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
      "6683": "雍智科技",
  }
  return fallback_names.get(stock_code, stock_code)


# ----------------------------------------------------
# 🚀 2. 主程式：Eve 價量加權籌碼模型
# ----------------------------------------------------
if check_password():
  st.title("📈 外資 vs 散戶 價量加權持股成本分析系統")

  col1, col2, col3 = st.columns([2, 1.5, 1.5])

  with col1:
    stock_id = st.text_input(
        "【股票代號】 (例如 6683 或 2618)", value="6683"
    ).strip()

  default_start = datetime.now().date() - timedelta(days=90)
  default_end = datetime.now().date()

  with col2:
    start_date = st.date_input("【起始日期】", value=default_start)

  with col3:
    end_date = st.date_input("【結束日期】", value=default_end)

  # ----------------------------------------------------
  # 📊 FinMind 抓取外資買賣超張數
  # ----------------------------------------------------
  @st.cache_data(ttl=1800)
  def fetch_foreign_data(stock_code, s_date, e_date):
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
        df["buy"] = pd.to_numeric(df["buy"], errors="coerce") / 1000.0  # 張數

        # 篩選外資
        foreign_df = df[df["name"].str.contains("Foreign|外資", na=False)]
        if not foreign_df.empty:
          f_buy = foreign_df.groupby("date")["buy"].sum().reset_index()
          f_buy.columns = ["Date", "Foreign_Buy"]
          f_buy["Date"] = pd.to_datetime(f_buy["Date"])
          return f_buy
    except Exception:
      pass
    return pd.DataFrame()

  try:
    with st.spinner("正在計算外資與散戶價量加權成本..."):
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

      foreign_df = fetch_foreign_data(stock_id, start_date, end_date)

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  if price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】的行情資料！")
  else:
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

    plot_df = pd.DataFrame({
        "Open": open_s,
        "High": high_s,
        "Low": low_s,
        "Close": close_s,
        "Total_Vol": vol_s,
    })
    plot_df.index = pd.to_datetime(plot_df.index)

    if not foreign_df.empty:
      foreign_df = foreign_df.set_index("Date")
      plot_df = plot_df.join(foreign_df, how="left")

    plot_df["Foreign_Buy"] = plot_df["Foreign_Buy"].fillna(0)

    # ✨ Eve 算式一：散戶張數 = 每日總成交量 - 外資買進張數
    plot_df["Retail_Buy"] = (
        plot_df["Total_Vol"] - plot_df["Foreign_Buy"]
    ).apply(lambda x: max(x, 1))

    # 每日成交金額估算 (金額 = 張數 * 當日收盤價)
    plot_df["Foreign_Amt"] = plot_df["Foreign_Buy"] * plot_df["Close"]
    plot_df["Retail_Amt"] = plot_df["Retail_Buy"] * plot_df["Close"]

    # ✨ Eve 算式二：20日滾動價量加權平均成本
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

    # ----------------------------------------------------
    # 📈 畫 K 線圖與雙成本線
    # ----------------------------------------------------
    fig = make_subplots(specs=[[{"secondary_y": False}]])

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
        )
    )

    # 🔵 外資價量加權成本線
    fig.add_trace(
        io_plotly.Scatter(
            x=plot_df.index,
            y=plot_df["Foreign_20D_Cost"],
            name="外資20日加權成本",
            line=dict(color="#0066FF", width=2.5, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>外資加權成本: $%{y:.1f}",
        )
    )

    # 🟠 散戶價量加權成本線
    fig.add_trace(
        io_plotly.Scatter(
            x=plot_df.index,
            y=plot_df["Retail_20D_Cost"],
            name="散戶20日加權成本",
            line=dict(color="#FF8C00", width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>散戶加權成本: $%{y:.1f}",
        )
    )

    display_title = (
        f"{stock_name} ({stock_id})" if stock_name != stock_id else stock_id
    )

    fig.update_layout(
        title={
            "text": (
                f"<b>【{display_title}】 日K線 vs 外資成本線 vs 散戶成本線</b>"
            ),
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 19},
        },
        hovermode="x unified",
        margin=dict(l=15, r=15, t=80, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=14),
        ),
        xaxis=dict(
            fixedrange=True,
            type="date",
            rangebreaks=[dict(bounds=["sat", "mon"])],
        ),
        yaxis=dict(fixedrange=True, side="right"),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": False, "displayModeBar": False},
    )

    # ----------------------------------------------------
    # 📋 Eve 專屬：全區間價量數據 summary（方便直接複製丟 AI）
    # ----------------------------------------------------
    total_foreign_amt = plot_df["Foreign_Amt"].sum()
    total_foreign_qty = plot_df["Foreign_Buy"].sum()
    overall_foreign_cost = (
        (total_foreign_amt / total_foreign_qty)
        if total_foreign_qty > 0
        else plot_df["Close"].iloc[-1]
    )

    total_retail_amt = plot_df["Retail_Amt"].sum()
    total_retail_qty = plot_df["Retail_Buy"].sum()
    overall_retail_cost = (
        (total_retail_amt / total_retail_qty)
        if total_retail_qty > 0
        else plot_df["Close"].iloc[-1]
    )

    latest_close = plot_df["Close"].iloc[-1]

    ai_text = f"""【{display_title} 籌碼價量加權分析】
分析時間範圍：{start_date} ~ {end_date}
最新收盤價：{latest_close:,.1f} 元

1. 外資區間加權平均成本：{overall_foreign_cost:,.1f} 元 （目前狀態：{'獲利中' if latest_close > overall_foreign_cost else '套牢中'}）
2. 散戶區間加權平均成本：{overall_retail_cost:,.1f} 元 （目前狀態：{'獲利中' if latest_close > overall_retail_cost else '套牢中'}）
3. 外資20日滾動均價成本：{plot_df['Foreign_20D_Cost'].iloc[-1]:,.1f} 元
4. 散戶20日滾動均價成本：{plot_df['Retail_20D_Cost'].iloc[-1]:,.1f} 元
"""

    st.markdown("### 🤖 丟給 AI 分析的整理文字（可直接複製）：")
    st.code(ai_text, language="text")
