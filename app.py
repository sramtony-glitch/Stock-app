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
  # 📊 下載籌碼資料 (TDCC)
  # ----------------------------------------------------
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

      # 下載 Yahoo Finance 股價
      ticker = f"{stock_id}.TW"
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )

      if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 計算籌碼比例
  # ----------------------------------------------------
  stock_chips = tdcc_df[tdcc_df[code_col] == stock_id].copy()

  if stock_chips.empty or price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】在此區間的完整資料！")
  else:
    # 轉為日期物件
    stock_chips["Date_Obj"] = pd.to_datetime(
        stock_chips[date_col], format="%Y%m%d", errors="coerce"
    )
    stock_chips = stock_chips.dropna(subset=["Date_Obj"])

    # 篩選日期區間
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

      # 散戶持股 (1-9 級別，即 <=50張)
      retail_shares = group[group[level_col].between(1, 9)][shares_col].sum()
      retail_ratio = (
          (retail_shares / tot_shares) * 100 if tot_shares > 0 else 0
      )

      chip_summary.append({
          "Date": d,
          "Retail_Ratio": round(retail_ratio, 2),
      })

    chip_df = pd.DataFrame(chip_summary)
    if not chip_df.empty:
      chip_df = chip_df.sort_values("Date")

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

    # 折線二：橘紅色 散戶持倉% (右 Y 軸) - 加入 connectgaps=True 確保每週資料點完美連線！
    if not chip_df.empty:
      fig.add_trace(
          io_plotly.Scatter(
              x=chip_df["Date"],
              y=chip_df["Retail_Ratio"],
              name="散戶持倉比(%)",
              mode="lines+markers",  # 加上資料節點標示
              line=dict(color="#FF4D4D", width=3),
              marker=dict(size=6, color="#FF4D4D"),
              connectgaps=True,  # 跨日期自動連線
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
