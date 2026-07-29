from datetime import datetime
import io
import pandas as pd
import requests
import streamlit as st

# 設定網頁標題與圖示
st.set_page_config(page_title="台股籌碼大戶散戶查詢", page_icon="📈")

# ----------------------------------------------------
# 🔐 自動讀取「當月預設密碼」
# ----------------------------------------------------
current_time = datetime.now()
year_month_key = current_time.strftime("%Y_%m")  # 格式例如: 2026_07

# 預先排定一整年的密碼清單（若當月未設定則使用 DEFAULT）
YEARLY_PASSWORDS = {
    "2026_07": "stock777",  # 2026年7月密碼
    "2026_08": "august888",  # 2026年8月密碼
    "2026_09": "september999",  # 2026年9月密碼
    "2026_10": "october168",  # 2026年10月密碼
    "2026_11": "november520",  # 2026年11月密碼
    "2026_12": "december999",  # 2026年12月密碼
    "2027_01": "happy2027",  # 2027年1月密碼
    "2027_02": "cny2027",  # 2027年2月密碼
    "2027_03": "spring333",  # 2027年3月密碼
    "2027_04": "april444",  # 2027年4月密碼
    "2027_05": "may555",  # 2027年5月密碼
    "2027_06": "june666",  # 2027年6月密碼
}

# 取得這個月應該使用的密碼
CORRECT_PASSWORD = YEARLY_PASSWORDS.get(
    year_month_key, "stock2026"
)  # 後方為預備備用密碼


# 檢查密碼的函式
def check_password():
  if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

  if not st.session_state["authenticated"]:
    st.title("🔒 系統已鎖定")
    st.caption("本工具需輸入授權密碼才可使用，密碼每月更新。")

    user_pwd = st.text_input("請輸入當月授權密碼：", type="password")

    if st.button("解鎖使用", type="primary"):
      if user_pwd == CORRECT_PASSWORD:
        st.session_state["authenticated"] = True
        st.success("密碼正確！解鎖成功！")
        st.rerun()
      else:
        st.error("❌ 密碼錯誤，請向管理者索取當月最新密碼！")

    return False

  return True


# ----------------------------------------------------
# 🚀 主程式 (密碼驗證通過後才執行)
# ----------------------------------------------------
if check_password():
  st.title("📈 台股大戶 vs 散戶持股查詢")
  st.caption("資料來源：臺灣集中保管結算所 (TDCC) 每週每人股權分散表")

  # 1. 載入資料
  def load_data():
    url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, verify=False, timeout=30)
    response.encoding = "utf-8"

    csv_data = io.StringIO(response.text)
    df = pd.read_csv(csv_data, dtype=str)

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
    with st.spinner("正在讀取最新集保資料..."):
      df, date_col, code_col, level_col, shares_col = load_data()
    st.success("資料載入成功！")
  except Exception as e:
    st.error(f"資料讀取失敗，請稍後再試：{e}")
    st.stop()

  # 2. 介面輸入框
  stock_id = st.text_input(
      "請輸入股票代號（例如：2330, 2317）", value="2330"
  ).strip()

  # 3. 查詢與顯示結果
  if st.button("開始查詢", type="primary"):
    stock_df = df[df[code_col] == stock_id]

    if not stock_df.empty:
      date_val = stock_df[date_col].iloc[0]
      total_row = stock_df[stock_df[level_col] == 17]
      total_shares = (
          total_row[shares_col].values[0]
          if not total_row.empty
          else stock_df[shares_col].sum()
      )

      valid_df = stock_df[stock_df[level_col].between(1, 15)]
      big_shares = valid_df[valid_df[level_col] >= 12][shares_col].sum()
      retail_shares = valid_df[valid_df[level_col] <= 9][shares_col].sum()

      big_ratio = (big_shares / total_shares) * 100
      retail_ratio = (retail_shares / total_shares) * 100

      st.markdown("---")
      st.subheader(f"股票代號：{stock_id} （資料日期：{date_val}）")

      col1, col2 = st.columns(2)
      col1.metric(label="🏛️ 大戶持股 (≥200張)", value=f"{big_ratio:.2f}%")
      col2.metric(label="🧑‍🤝‍🧑 散戶持股 (≤50張)", value=f"{retail_ratio:.2f}%")

    else:
      st.warning(
          f"❌ 找不到股票代碼【{stock_id}】的資料，請確認後重新輸入！"
      )
