from datetime import datetime, timedelta
import io
import pandas as pd
import plotly.graph_objects as io_plotly
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# 設定網頁標題、圖示與響應式版面 (自動滿版)
st.set_page_config(
    page_title="台股籌碼與股價對照系統", page_icon="📈", layout="wide"
)

# ----------------------------------------------------
# 🔐 1. 欄位一：每月密碼驗證 (自動對照一整年)
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
# 🚀 2. 主程式 (密碼通過後顯示)
# ----------------------------------------------------
if check_password():
  st.title("📈 台股股價 vs 散戶持股比例對照圖")

  # ----------------------------------------------------
  # 📥 介面輸入欄位 (欄位二、三、四)
  # ----------------------------------------------------
  col1, col2, col3 = st.columns([2, 1.5, 1.5])

  with col1:
    stock_id = st.text_input(
        "【欄位二】股票代號（範例: 2330）", value="2330"
    ).strip()

  # 預設時間範圍為過去兩個月
  default_start = datetime.now().date() - timedelta(days=60)
  default_end = datetime.now().date()

  with col2:
    start_date = st.date_input("【欄位三】起始日期", value=default_start)

  with col3:
    end_date = st.date_input("【欄位四】結束日期", value=default_end)

  # ----------------------------------------------------
  # 📊 資料抓取與處理解析
  # ----------------------------------------------------
  # A. 下載集保籌碼資料 (散戶持股)
  @st.cache_data(ttl=3600)
  def fetch_tdcc_data():
    url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    res = requests.get(url, headers=headers, verify=False, timeout=30)
    res.encoding = "utf-8"
    df = pd.read_csv(io.StringIO(res.text), dtype=str)

    date_col, code_col, level_col, shares_col = (
        df.columns[0],
        df.columns[1],
        df.columns[2],
        df.columns[4],
    )
    df[code_col] = df[code_col].str.strip()
    df[level_col] = pd.to_numeric(df[level_col], errors="coerce")
    df[shares_col] = pd.to_numeric(df[shares_col], errors="coerce")
    return df, date_col, code_col, level_col, shares_col

  try:
    with st.spinner("讀取籌碼與股價資料中..."):
      tdcc_df, date_col, code_col, level_col, shares_col = fetch_tdcc_data()

      # B. 下載 Yahoo Finance 歷史股價資料
      ticker = (
          f"{stock_id}.TW"  # 預設上市股票格式，若是上櫃可自動備用修正
      )
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )

      if price_df.empty:  # 嘗試上櫃 .TWO 格式
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

  except Exception as e:
    st.error(f"資料讀取失敗，請確認網路或股票代號：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 運算籌碼比例與繪製雙 Y 軸圖表
  # ----------------------------------------------------
  stock_chips = tdcc_df[tdcc_df[code_col] == stock_id]

  if stock_chips.empty or price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】在此區間的完整資料！")
  else:
    # 算散戶持股% (1-9分級為 <=50張散戶)
    # 集保資料為每週更新，做日期篩選與處理
    stock_chips["Date_Obj"] = pd.to_datetime(
        stock_chips[date_col], format="%Y%m%d", errors="coerce"
    )
    mask = (stock_chips["Date_Obj"].dt.date >= start_date) & (
        stock_chips["Date_Obj"].dt.date <= end_date
    )
    filtered_chips = stock_chips[mask]

    chip_summary = []
    for d, group in filtered_chips.groupby("Date_Obj"):
      total_row = group[group[level_col] == 17]
      tot_shares = (
          total_row[shares_col].values[0]
          if not total_row.empty
          else group[shares_col].sum()
      )

      # 散戶 <= 50張 (級別 1-9)
      retail_shares = group[group[level_col].between(1, 9)][shares_col].sum()
      # 大戶 >= 200張 (級別 12-15)
      big_shares = group[group[level_col] >= 12][shares_col].sum()

      retail_ratio = (
          (retail_shares / tot_shares) * 100 if tot_shares > 0 else 0
      )
      big_ratio = (big_shares / tot_shares) * 100 if tot_shares > 0 else 0

      chip_summary.append({
          "Date": d,
          "Retail_Ratio": round(retail_ratio, 2),
          "Big_Ratio": round(big_ratio, 2),
      })

    chip_df = pd.DataFrame(chip_summary)

    # 處理股價 Close 欄位
    if isinstance(price_df.columns, pd.MultiIndex):
      price_series = price_df["Close"][ticker]
    else:
      price_series = price_df["Close"]

    # ----------------------------------------------------
    # 🎨 建立手繪圖要求的 雙 Y 軸 疊加折線圖
    # ----------------------------------------------------
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 折線一：淺藍色 股票價格 (左邊 Y 軸)
    fig.add_trace(
        io_plotly.Scatter(
            x=price_series.index,
            y=price_series.values,
            name="股票價格",
            line=dict(color="#3399FF", width=3),  # 淺藍色
            hovertemplate="%{x|%Y-%m-%d}<br>股價: $%{y:.2f}",
        ),
        secondary_y=False,
    )

    # 折線二：橘紅色 散戶持倉% (右邊 Y 軸)
    if not chip_df.empty:
      fig.add_trace(
          io_plotly.Scatter(
              x=chip_df["Date"],
              y=chip_df["Retail_Ratio"],
              name="散戶持倉比(%)",
              line=dict(color="#FF4D4D", width=3),  # 橘紅色
              hovertemplate="%{x|%Y-%m-%d}<br>散戶持倉: %{y:.2f}%",
          ),
          secondary_y=True,
      )

    # 設定 Y 軸標題與色彩風格 (如手繪稿的要求)
    fig.update_layout(
        title=f"<b>股票代號：{stock_id} 股價 vs 散戶持倉比</b>",
        title_x=0.4,
        hovermode="x unified",
        autosize=True,  # 跨裝置自動滿版適應
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )

    # 左側 Y 軸：淺藍色 {股票價格}
    fig.update_yaxes(
        title_text="<b style='color:#3399FF;'>股票價格 (元)</b>",
        secondary_y=False,
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    # 右側 Y 軸：橘紅色 {散戶持倉比}
    fig.update_yaxes(
        title_text="<b style='color:#FF4D4D;'>散戶持倉比 (%)</b>",
        secondary_y=True,
        showgrid=False,
    )

    # 下方 X 軸：日期期間
    fig.update_xaxes(
        title_text=f"<b>日期期間：{start_date} ～ {end_date}</b>",
        showgrid=True,
        gridcolor="#E2E2E2",
    )

    # 渲染至全螢幕滿版 (Responsive)
    st.plotly_chart(fig, use_container_width=True)
