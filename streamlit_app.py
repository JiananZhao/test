import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- 1. Data Fetching Function (Cached) ---
@st.cache_data(ttl=3600)
def get_valuation_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    if not info or 'marketCap' not in info:
        raise ValueError("无法获取股票数据，请检查代码是否正确。")
    
    cash_flow = ticker.cashflow
    income_stmt = ticker.financials
    
    # Risk-free rate
    tnx = yf.Ticker("^TNX")
    rf_rate = tnx.fast_info['last_price'] / 100 if 'last_price' in tnx.fast_info else 0.042
    
    beta = info.get('beta', 1.2)
    mkt_cap = info.get('marketCap', 0)
    total_debt = info.get('totalDebt', 0)
    
    # Tax Rate
    tax_rate = income_stmt.loc["Tax Rate For Calcs"].iloc[0] if "Tax Rate For Calcs" in income_stmt.index else 0.21
    
    # Cost of Debt (Rd)
    try:
        interest_expense = abs(income_stmt.loc['Interest Expense'].iloc[0])
        rd = interest_expense / total_debt if total_debt > 0 else 0.05
    except:
        rd = 0.05
        
    # FCF & SBC
    sbc = cash_flow.loc["Stock Based Compensation"].iloc[0] if "Stock Based Compensation" in cash_flow.index else 0
    if "Free Cash Flow" in cash_flow.index:
        fcf_raw = cash_flow.loc["Free Cash Flow"].iloc[0]
    else:
        fcf_raw = (cash_flow.loc["Operating Cash Flow"].iloc[0] + cash_flow.loc["Capital Expenditures"].iloc[0])

    # Dilution Rate
    shares_history = ticker.get_shares_full(start="2021-01-01")
    if not shares_history.empty:
        years = (shares_history.index[-1] - shares_history.index[0]).days / 365.25
        hist_dilution = (shares_history.iloc[-1] / shares_history.iloc[0]) ** (1/years) - 1 if years > 0 else 0.0
    else:
        hist_dilution = 0.0

    return {
        "rf_rate": rf_rate, "beta": beta, "mkt_cap": mkt_cap, "total_debt": total_debt,
        "rd": rd, "fcf_raw": fcf_raw, "sbc": sbc, "hist_dilution": float(hist_dilution),
        "current_price": info.get("currentPrice"), "shares": info.get("sharesOutstanding"),
        "net_debt": (total_debt - info.get("totalCash", 0)), "tax_rate": float(tax_rate),
        "q_income": ticker.quarterly_financials, "q_balance": ticker.quarterly_balance_sheet, "q_cash": ticker.quarterly_cashflow,
        "a_income": ticker.financials, "a_balance": ticker.balance_sheet, "a_cash": ticker.cashflow
    }

# --- 2. UI Layout ---
st.set_page_config(page_title="自动化硬核估值台", layout="wide")
st.title("⚖️ 自动化 WACC & 动态股本 DCF 模型")

# Step 1: Get Ticker First
with st.sidebar:
    st.header("1. 目标选择")
    ticker_input = st.text_input("股票代码", value="TEAM").upper()

# Step 2: Fetch Data
try:
    data = get_valuation_data(ticker_input)

    # Step 3: Use Data to populate other Sidebar inputs
    with st.sidebar:
        st.divider()
        st.header("2. WACC 自动计算器")
        erp = st.number_input("股权风险溢价 (ERP %)", value=5.5, step=0.1) / 100
        tax_rate_input = st.number_input("企业所得税率 (%)", value=data['tax_rate']*100, step=1.0) / 100
        
        # Calculate Re (CAPM)
        re = data['rf_rate'] + data['beta'] * erp
        # Weights
        v = data['mkt_cap'] + data['total_debt']
        w_e = data['mkt_cap'] / v if v > 0 else 1
        w_d = data['total_debt'] / v if v > 0 else 0
        # Calc WACC
        calculated_wacc = (w_e * re) + (w_d * data['rd'] * (1 - tax_rate_input))
        
        final_wacc = st.number_input("最终折现率 (WACC)", value=float(calculated_wacc), step=0.001, format="%.3f")
        net_rate = st.number_input("预期年化股本变动率", value=data["hist_dilution"], step=0.001, format="%.3f")

        st.divider()
        st.header("3. 估值核心假设")
        deduct_sbc = st.checkbox("扣除 SBC 影响", value=True)
        g_base = st.number_input("中性增长率 (g)", value=0.200, step=0.005, format="%.3f")
        terminal_g = st.number_input("永续增长率 (tg)", value=0.030, step=0.001, format="%.3f")

    # --- 3. Dashboard Display ---
    st.subheader(f"📊 {ticker_input} 自动化参数审计")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("无风险利率 (10Y)", f"{data['rf_rate']*100:.2f}%")
    a2.metric("Beta 系数", f"{data['beta']:.2f}")
    a3.metric("股权成本 (Re)", f"{re*100:.2f}%")
    a4.metric("计算所得 WACC", f"{calculated_wacc*100:.2f}%", border=True)

    # Calculation logic
    fcf_calc = (data['fcf_raw'] - data['sbc']) / 1e6 if deduct_sbc else data['fcf_raw'] / 1e6
    shares_m = data['shares'] / 1e6
    net_debt_m = data['net_debt'] / 1e6
    
    def run_dcf(fcf, g, wacc, tg, nd, sh, dr):
        # 5 Year Projection
        pvs = [ (fcf * (1 + g)**t) / (1 + wacc)**t for t in range(1, 6) ]
        tv = (fcf * (1 + g)**5 * (1 + tg)) / (wacc - tg)
        pv_tv = tv / (1 + wacc)**5
        eq_val = (sum(pvs) + pv_tv) - nd
        proj_sh = sh * ((1 + dr) ** 5) # Dilution over 5 years
        return eq_val / proj_sh

    # Scenarios
    st.divider()
    scenarios = {"悲观 (g-5%)": g_base - 0.05, "中性": g_base, "乐观 (g+5%)": g_base + 0.05}
    res = []
    for name, g in scenarios.items():
        price = run_dcf(fcf_calc, g, final_wacc, terminal_g, net_debt_m, shares_m, net_rate)
        res.append({
            "情景": name, 
            "增速假设": f"{g*100:.1f}%", 
            "内在价值": f"${price:.2f}", 
            "潜力": f"{(price/data['current_price']-1)*100:.1f}%"
        })
        
    st.table(pd.DataFrame(res))
    
    with st.expander("🔍 深度财务审计"):
        # 修改点：不再调用不存在的 ticker 对象，而是使用 data 字典中存好的数据
        time_frame = st.radio("选择报告频率", ["年度 (Annual)", "季度 (Quarterly)"], horizontal=True)
        
        if "年度" in time_frame:
            # 这些 key 对应你 get_valuation_data 函数中 return 的值
            inc = data['a_income']
            bal = data['a_balance']
            cf = data['a_cash']
        else:
            inc = data['q_income']
            bal = data['q_balance']
            cf = data['q_cash']
        
        t1, t2, t3 = st.tabs(["利润表", "资产负债表", "现金流表"])
        
        # 这里的 .T 转置可以让年份变成行，指标变成列，更易读
        t1.dataframe(inc.T.rename(index=lambda x: x.strftime('%Y-%m-%d')))
        t2.dataframe(bal.T.rename(index=lambda x: x.strftime('%Y-%m-%d')))
        t3.dataframe(cf.T.rename(index=lambda x: x.strftime('%Y-%m-%d')))

except Exception as e:
    st.error(f"分析出错：{e}")
    st.info("提示：请检查网络连接或股票代码是否在 Yahoo Finance 上存在。")
