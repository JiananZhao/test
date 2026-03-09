import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- 1. 核心数据抓取：增加 WACC 相关指标 ---
@st.cache_data(ttl=3600)
def get_valuation_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # 基础报表
    cash_flow = ticker.cashflow
    income_stmt = ticker.financials
    
    # 1. 无风险利率 (10年美债收益率)
    tnx = yf.Ticker("^TNX")
    rf_rate = tnx.fast_info['last_price'] / 100 if 'last_price' in tnx.fast_info else 0.042
    
    # 2. 股权相关
    beta = info.get('beta', 1.2) # 若无则默认为 1.2 (科技股均值)
    mkt_cap = info.get('marketCap', 0)
    
    # 3. 债务与税率相关
    total_debt = info.get('totalDebt', 0)
    # 尝试提取利息支出计算 Rd，若无则默认为 5%
    tax_rate = income_stmt.loc["Tax Rate for Calc"].iloc[0] if "Tax Rate for Calc" in income_stmt.index else 0.21
    
    try:
        interest_expense = abs(income_stmt.loc['Interest Expense'].iloc[0])
        rd = interest_expense / total_debt if total_debt > 0 else 0.05
    except:
        rd = 0.05
        
    # 4. 现金流与 SBC
    sbc = cash_flow.loc["Stock Based Compensation"].iloc[0] if "Stock Based Compensation" in cash_flow.index else 0
    if "Free Cash Flow" in cash_flow.index:
        fcf_raw = cash_flow.loc["Free Cash Flow"].iloc[0]
    else:
        fcf_raw = (cash_flow.loc["Operating Cash Flow"] + cash_flow.loc["Capital Expenditures"]).iloc[0]

    # 5. 股本变动率 (历史 CAGR)
    shares_history = ticker.get_shares_full(start="2021-01-01")
    if not shares_history.empty:
        years = (shares_history.index[-1] - shares_history.index[0]).days / 365.25
        hist_dilution = (shares_history.iloc[-1] / shares_history.iloc[0]) ** (1/years) - 1 if years > 0 else 0
    else:
        hist_dilution = 0.0

    return {
        "rf_rate": rf_rate,
        "beta": beta,
        "mkt_cap": mkt_cap,
        "total_debt": total_debt,
        "rd": rd,
        "fcf_raw": fcf_raw,
        "sbc": sbc,
        "hist_dilution": float(hist_dilution),
        "current_price": info.get("currentPrice"),
        "shares": info.get("sharesOutstanding"),
        "net_debt": (total_debt - info.get("totalCash", 0)),
        "q_income": ticker.quarterly_financials,
        "q_balance": ticker.quarterly_balance_sheet,
        "q_cash": ticker.quarterly_cashflow,
        "tax_rate": tax_rate
    }

# --- 2. Streamlit UI ---
st.set_page_config(page_title="自动化硬核估值台", layout="wide")
st.title("⚖️ 自动化 WACC & 动态股本 DCF 模型")
try:
    data = get_valuation_data(ticker_input)
    
with st.sidebar:
    st.header("1. 目标选择")
    ticker_input = st.text_input("股票代码", value="TEAM").upper()
    
    st.divider()
    st.header("2. WACC 自动计算器")
    erp = st.number_input("股权风险溢价 (ERP %)", value=5.5, step=0.1) / 100
    # 使用抓取到的真实税率作为默认值，确保是 float 类型
    tax_rate_input = st.number_input("企业所得税率 (%)", value=float(data['tax_rate'] * 100), step=1.0) / 100
    
    st.divider()
    st.header("3. 估值核心假设")
    deduct_sbc = st.checkbox("扣除 SBC 影响", value=True)
    g_base = st.number_input("中性增长率 (g)", value=0.200, step=0.005, format="%.3f")
    terminal_g = st.number_input("永续增长率 (tg)", value=0.030, step=0.001, format="%.3f")


    
    # --- 计算 WACC ---
    # Cost of Equity (CAPM)
    re = data['rf_rate'] + data['beta'] * erp
    # Weights
    v = data['mkt_cap'] + data['total_debt']
    w_e = data['mkt_cap'] / v if v > 0 else 1
    w_d = data['total_debt'] / v if v > 0 else 0
    # Final WACC
    calculated_wacc = (w_e * re) + (w_d * data['rd'] * (1 - tax_rate))
    
    with st.sidebar:
        final_wacc = st.number_input("最终折现率 (WACC)", value=float(calculated_wacc), step=0.001, format="%.3f", help="已根据 CAPM 自动计算")
        net_rate = st.number_input("预期年化股本变动率", value=data["hist_dilution"], step=0.001, format="%.3f")

    # --- 数据面板 ---
    st.subheader("📊 自动化参数审计")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("无风险利率 (10Y)", f"{data['rf_rate']*100:.2f}%")
    a2.metric("Beta 系数", f"{data['beta']:.2f}")
    a3.metric("股权成本 (Re)", f"{re*100:.2f}%")
    a4.metric("计算所得 WACC", f"{calculated_wacc*100:.2f}%", border=True)

    # --- 估值计算 ---
    fcf_calc = (data['fcf_raw'] - data['sbc']) / 1e6 if deduct_sbc else data['fcf_raw'] / 1e6
    shares_m = data['shares'] / 1e6
    net_debt_m = data['net_debt'] / 1e6
    
    def run_dcf(fcf, g, wacc, tg, nd, sh, dr):
        pvs = [ (fcf * (1 + g)**t) / (1 + wacc)**t for t in range(1, 6) ]
        tv = (fcf * (1 + g)**5 * (1 + tg)) / (wacc - tg)
        pv_tv = tv / (1 + wacc)**5
        eq_val = (sum(pvs) + pv_tv) - nd
        proj_sh = sh * ((1 + dr) ** 5)
        return eq_val / proj_sh

    # --- 情景分析 ---
    st.divider()
    scenarios = {"悲观 (g-5%)": g_base - 0.05, "中性": g_base, "乐观 (g+5%)": g_base + 0.05}
    res = []
    for name, g in scenarios.items():
        price = run_dcf(fcf_calc, g, final_wacc, terminal_g, net_debt_m, shares_m, net_rate)
        res.append({"情景": name, "增速假设": f"{g*100:.1f}%", "内在价值": f"${price:.2f}", "潜力": f"{(price/data['current_price']-1)*100:.1f}%"})
    
    st.table(pd.DataFrame(res))

    with st.expander("🔍 查看原始财务数据"):
        tabs = st.tabs(["利润表", "资产负债表", "现金流表"])
        tabs[0].dataframe(data['q_income'])
        tabs[1].dataframe(data['q_balance'])
        tabs[2].dataframe(data['q_cash'])

except Exception as e:
    st.error(f"分析出错：{e}")
