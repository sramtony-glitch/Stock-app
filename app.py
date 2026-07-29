from datetime import datetime, timedelta
import io
from FinMind.data import DataLoader
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

    user_pwd = st.text_input(
        "【欄位一】請輸入授權密碼：", type="password"
    )

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
  st.title("📈 台股股價 vs 散戶持股比例對照圖")

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
  # 📊 抓取歷史籌碼資料 (使用 FinMind API)
  # ----------------------------------------------------
  @st.cache_data(ttl=3600)
  def fetch_chip_history(stock_code, s_date, e_date):
    dl = DataLoader()
    # 抓取股權分散表歷史資料
    df_chip = dl.taiwan_stock_holding_shares_per(
        stock_id=stock_code,
        start_date=s_date.strftime("%Y-%m-%d"),
        end_date=e_date.strftime("%Y-%m-%d"),
    )
    return df_chip

  try:
    with st.spinner("正在抓取歷史籌碼與股價資料..."):
      # 1. 抓取股價 (Yahoo Finance)
      ticker = f"{stock_id}.TW"
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )

      if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

      # 2. 抓取籌碼歷史 (FinMind)
      chip_raw = fetch_chip_history(stock_id, start_date, end_date)

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 計算散戶持股比例歷史折線
  # ----------------------------------------------------
  if price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】的股價資料！")
  else:
    # 處理 FinMind 籌碼數據
    chip_df = pd.DataFrame()
    if not chip_raw.empty:
      # holding_shares_level 1~9 代表 <= 50張的散戶
      # 計算每週散戶持股比例總和
      chip_raw["percent"] = pd.to_numeric(
          chip_raw["percent"], errors="coerce"
      )
      chip_raw["holding_shares_level"] = pd.to_numeric(
          chip_raw["holding_shares_level"], errors="coerce"
      )

      retail_df = chip_raw[chip_raw["holding_shares_level"].between(1, 9)]
      chip_summary = (
          retail_df.groupby("date")["percent"].sum().reset_index()
      )
      chip_summary.columns = ["Date", "Retail_Ratio"]
      chip_summary["Date"] = pd.to_datetime(chip_summary["Date"])
      chip_df = chip_summary.sort_values("Date")

    # 處理股價 Close 欄位
    if isinstance(price_df.columns, pd.MultiIndex):
      price_series = price_df["Close"][ticker]
    else:
      price_series = price_df["Close"]

    # ----------------------------------------------------
    # 🎨 繪製雙 Y 軸 疊加折線圖
    # ----------------------------------------------------
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 折線一：淺藍色 股票價格 (左 Y 軸)
    fig.add_trace(
        io_plotly.Scatter(
            x=price_series.index,
            y=price_series.values,
            name="股票價格",
            mode="lines",
            line=dict(color="#3399FF", width=3),
            hovertemplate="%{x|%Y-%m-%d}<br>股價: $%{y:.2f}",
        ),
        secondary_y=False,
    )

    # 折線二：橘紅色 散戶持倉% (右 Y 軸) - 完整歷史連線！
    if not chip_df.empty:
      fig.add_trace(
          io_plotly.Scatter(
              x=chip_df["Date"],
              y=chip_df["Retail_Ratio"],
              name="散戶持倉比(%)",
              mode="lines+markers",
              line=dict(color="#FF4D4D", width=3),
              marker=dict(size=6, color="#FF4D4D"),
              connectgaps=True,  # 自動跨週連接成滑順折線
              hovertemplate="%{x|%Y-%m-%d}<br>散戶持倉: %{y:.2f}%",
          ),
          secondary_y=True,
      )

    # 圖表佈局設定
    fig.update_layout(
        title=f"<b>股票代號：{stock_id} 股價 vs 散戶持倉比</b>",
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

    # 右 Y 軸：橘紅色 {散戶持倉比}
    fig.update_yaxes(
        title_text="<b style='color:#FF4D4D;'>散戶持倉比 (%)</b>",
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
