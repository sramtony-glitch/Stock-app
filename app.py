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
  # 📊 多源可靠籌碼擷取器 (多重備用)
  # ----------------------------------------------------
  @st.cache_data(ttl=3600)
  def fetch_robust_chip_data(stock_code, s_date, e_date):
    # 管道 A: FinMind API
    try:
      url = "https://api.finmindtrade.com/api/v4/data"
      params = {
          "dataset": "TaiwanStockHoldingSharesPer",
          "data_id": stock_code,
          "start_date": s_date.strftime("%Y-%m-%d"),
          "end_date": e_date.strftime("%Y-%m-%d"),
      }
      resp = requests.get(url, params=params, timeout=10)
      data = resp.json()
      if data.get("msg") == "success" and data.get("data"):
        df = pd.DataFrame(data["data"])
        level_col = (
            "HoldingSharesLevel"
            if "HoldingSharesLevel" in df.columns
            else "holding_shares_level"
        )
        percent_col = "percent" if "percent" in df.columns else "Percent"

        df[level_col] = pd.to_numeric(df[level_col], errors="coerce")
        df[percent_col] = pd.to_numeric(df[percent_col], errors="coerce")

        retail_df = df[df[level_col].between(1, 9)]
        summary = (
            retail_df.groupby("date")[percent_col].sum().reset_index()
        )
        summary.columns = ["Date", "Retail_Ratio"]
        summary["Date"] = pd.to_datetime(summary["Date"])
        res_df = summary.sort_values("Date")
        if not res_df.empty and len(res_df) > 1:
          return res_df
    except Exception:
      pass

    # 管道 B: TDCC 集保開放資料
    try:
      url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
      headers = {
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          )
      }
      res = requests.get(url, headers=headers, verify=False, timeout=10)
      res.encoding = "utf-8"
      df_tdcc = pd.read_csv(io.StringIO(res.text), dtype=str)

      date_col, code_col, level_col, shares_col = (
          df_tdcc.columns[0],
          df_tdcc.columns[1],
          df_tdcc.columns[2],
          df_tdcc.columns[4],
      )
      df_tdcc[code_col] = df_tdcc[code_col].str.strip()
      df_tdcc[level_col] = pd.to_numeric(df_tdcc[level_col], errors="coerce")
      df_tdcc[shares_col] = pd.to_numeric(df_tdcc[shares_col], errors="coerce")

      stock_tdcc = df_tdcc[df_tdcc[code_col] == stock_code].copy()
      stock_tdcc["Date_Obj"] = pd.to_datetime(
          stock_tdcc[date_col], format="%Y%m%d", errors="coerce"
      )

      chip_summary = []
      for d, group in stock_tdcc.groupby("Date_Obj"):
        total_row = group[group[level_col] == 17]
        tot_shares = (
            total_row[shares_col].values[0]
            if not total_row.empty
            else group[shares_col].sum()
        )
        retail_shares = group[group[level_col].between(1, 9)][shares_col].sum()
        retail_ratio = (
            (retail_shares / tot_shares) * 100 if tot_shares > 0 else 0
        )
        chip_summary.append(
            {"Date": d, "Retail_Ratio": round(retail_ratio, 2)}
        )

      tdcc_res = pd.DataFrame(chip_summary)
      if not tdcc_res.empty:
        return tdcc_res
    except Exception:
      pass

    return pd.DataFrame()

  try:
    with st.spinner("正在讀取歷史股價與散戶籌碼資料..."):
      # 1. 股價資料
      ticker = f"{stock_id}.TW"
      price_df = yf.download(
          ticker, start=start_date, end=end_date + timedelta(days=1)
      )
      if price_df.empty:
        ticker = f"{stock_id}.TWO"
        price_df = yf.download(
            ticker, start=start_date, end=end_date + timedelta(days=1)
        )

      # 2. 籌碼資料
      chip_df = fetch_robust_chip_data(stock_id, start_date, end_date)

  except Exception as e:
    st.error(f"資料讀取失敗：{e}")
    st.stop()

  # ----------------------------------------------------
  # 📈 繪製雙 Y 軸 疊加折線圖
  # ----------------------------------------------------
  if price_df.empty:
    st.warning(f"❌ 查無股票代號【{stock_id}】的股價資料！")
  else:
    # 提取股價收盤價
    if isinstance(price_df.columns, pd.MultiIndex):
      price_series = price_df["Close"][ticker]
    else:
      price_series = price_df["Close"]

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

    # 折線二：橘紅色 散戶持倉% (右 Y 軸)
    if not chip_df.empty:
      fig.add_trace(
          io_plotly.Scatter(
              x=chip_df["Date"],
              y=chip_df["Retail_Ratio"],
              name="散戶持倉比(%)",
              mode="lines+markers",
              line=dict(color="#FF4D4D", width=3),
              marker=dict(size=7, color="#FF4D4D"),
              connectgaps=True,
              hovertemplate="%{x|%Y-%m-%d}<br>散戶持倉: %{y:.2f}%",
          ),
          secondary_y=True,
      )
    else:
      st.info(
          "💡 提示：第三方籌碼資料庫暫時連線繁忙，已自動為您優先呈現在地股價趨勢。"
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
