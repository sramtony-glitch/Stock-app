from datetime import datetime, timedelta
import io
import pandas as pd
import plotly.graph_objects as io_plotly
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# 設定網頁標題與響應式滿版版面
st.set_page_config(
    page_title="台股籌碼與股價對照系統", page_icon="📈", layout="wide"
)

# ----------------------------------------------------
# 🔐 1. 欄位一：每月密碼驗證
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


def check_password():
  if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

  if not st.session_state["authenticated"]:
    st.title("🔒 系統授權鎖定")
    st.caption("請輸入每月授權密碼以存取圖表分析。")

    user_pwd = st.text_input("【欄位一】請輸入授權密碼：", type="password")

    if st.button("解鎖並進入系統", type="primary"):
      if user_pwd == CORRECT_PASSWORD:
        st.session_state["authenticated"] = True
        st.success("驗證成功！")
        st.rerun()
      else:
        st.error("❌ 密碼錯誤，請向管理者索取當月密碼！")

    return False
  return True


# ----------------------------------------------------
# 🚀 2. 主程式
# ----------------------------------------------------
if check_password():
  st.title("📈 台股每日股價 vs 三大法人買賣超對照圖")

  # 📥 介面輸入欄位
  col1, col2, col3 = st.columns([2, 1.5, 1.5])

  with col1:
    stock_id = st.text_input(
        "【欄位二】股票代號（範例: 2330）", value="2330"
    ).strip()

  default_start = datetime.now().date() - timedelta(days=90)
  default_end = datetime.now().date()

  with col2:
    start_date = st.date_input("【欄位三】起始日期", value=default_start)

  with col3:
    end_date = st.date_input("【欄位四】結束日期", value=default_end)

  # ----------------------------------------------------
  # 📊 每日三大法人買賣超 API 擷取器 (每日 15:30 更新)
  # ----------------------------------------------------
  @st.cache_data(ttl=1800)
  def fetch_daily_institutional_investors(stock_code, s_date, e_date):
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
        # 計算每日三大法人合計買賣超 (買進 - 賣出，單位：張)
        df["buy"] = pd.to_numeric(df["buy"], errors="coerce")
        df["sell"] = pd.to_numeric(df["sell"], errors="coerce")
        df["net"] = (df["buy"] - df["sell"]) / 1000.0  # 轉為張數

        summary = df.groupby("date")["net"].sum().reset_index()
        summary.columns = ["Date", "Institutional_Net"]
        summary["Date"] = pd.to_datetime(summary["Date"])
        return summary.sort_values("Date")
    except Exception:
      pass
    return pd.DataFrame()

  try:
    with st.spinner("正在讀取每日股價與三大法人籌碼資料..."):
      # 1. 股價資料 (Yahoo Finance)
      ticker = f"{stock_id}.TW"
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )
      if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

      # 2. 三大法人每日買賣超
      inst_df = fetch_daily_institutional_investors(
          stock_id, start_date, end_date
      )

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 繪製雙 Y 軸 疊加折線圖
  # ----------------------------------------------------
  if price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】的股價資料！")
  else:
    # 提取股價 Close 欄位
    if isinstance(price_df.columns, pd.MultiIndex):
      price_series = price_df["Close"][ticker]
    else:
      price_series = price_df["Close"]

    plot_df = pd.DataFrame({"Price": price_series})
    plot_df.index = pd.to_datetime(plot_df.index)

    if not inst_df.empty:
      inst_df = inst_df.set_index("Date")
      plot_df = plot_df.join(inst_df, how="left")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 折線一：淺藍色 股票價格 (左 Y 軸) - 每日數據
    fig.add_trace(
        io_plotly.Scatter(
            x=plot_df.index,
            y=plot_df["Price"],
            name="股票價格",
            mode="lines",
            line=dict(color="#3399FF", width=3),
            hovertemplate="%{x|%Y-%m-%d}<br>股價: $%{y:.2f}",
        ),
        secondary_y=False,
    )

    # 折線二：橘紅色 三大法人每日買賣超 (右 Y 軸) - 每日數據
    if "Institutional_Net" in plot_df.columns and not plot_df[
        "Institutional_Net"
    ].isna().all():
      fig.add_trace(
          io_plotly.Scatter(
              x=plot_df.index,
              y=plot_df["Institutional_Net"],
              name="法人買賣超(張)",
              mode="lines+markers",
              line=dict(color="#FF4D4D", width=2),
              marker=dict(size=5, color="#FF4D4D"),
              connectgaps=True,
              hovertemplate="%{x|%Y-%m-%d}<br>法人買賣超: %{y:,.0f} 張",
          ),
          secondary_y=True,
      )

    # 圖表佈局設定
    fig.update_layout(
        title=f"<b>股票代號：{stock_id} 每日股價 vs 三大法人買賣超</b>",
        title_x=0.4,
        hovermode="x unified",
        autosize=True,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )

    # 左 Y 軸：淺藍色 {股票價格}
    fig.update_yaxes(
        title_text="<b style='color:#3399FF;'>股票價格 (元)</b>",
        secondary_y=False,
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    # 右 Y 軸：橘紅色 {法人買賣超}
    fig.update_yaxes(
        title_text="<b style='color:#FF4D4D;'>三大法人買賣超 (張)</b>",
        secondary_y=True,
        showgrid=False,
    )

    # 下方 X 軸
    fig.update_xaxes(
        title_text=f"<b>日期期間：{start_date} ～ {end_date}</b>",
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    # 跨裝置滿版渲染
    st.plotly_chart(fig, use_container_width=True)
