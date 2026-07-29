import pandas as pd
import streamlit as st


# 設定網頁標題與圖示
st.set_page_config(page_title="台股籌碼大戶散戶查詢", page_icon="📈")

st.title("📈 台股大戶 vs 散戶持股查詢")
st.caption("資料來源：臺灣集中保管結算所 (TDCC) 每週每人股權分散表")

# 1. 載入資料（使用快取機制）
@st.cache_data(ttl=3600)
def load_data():
    url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    df = pd.read_csv(url, dtype=str)
    
    date_col, code_col, level_col, shares_col = df.columns[0], df.columns[1], df.columns[2], df.columns[4]
    df[code_col] = df[code_col].str.strip()
    df[level_col] = pd.to_numeric(df[level_col], errors='coerce')
    df[shares_col] = pd.to_numeric(df[shares_col], errors='coerce')
    return df, date_col, code_col, level_col, shares_col

try:
    with st.spinner("正在讀取最新集保資料..."):
        df, date_col, code_col, level_col, shares_col = load_data()
    st.success("資料載入成功！")
except Exception as e:
    st.error(f"資料讀取失敗，請稍後再試：{e}")
    st.stop()

# 2. 介面輸入框
stock_id = st.text_input("請輸入股票代號（例如：2330, 2317）", value="2330").strip()

# 3. 查詢與顯示結果
if st.button("開始查詢", type="primary"):
    stock_df = df[df[code_col] == stock_id]
    
    if not stock_df.empty:
        date_val = stock_df[date_col].iloc[0]
        total_row = stock_df[stock_df[level_col] == 17]
        total_shares = total_row[shares_col].values[0] if not total_row.empty else stock_df[shares_col].sum()
        
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
        st.warning(f"❌ 找不到股票代碼【{stock_id}】的資料，請確認後重新輸入！")
