import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# Remove sys.path hack as it can cause issues in some environments
# sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from processor import parse_csv, calculate_portfolio
    from models import PortfolioSummary
except ImportError as e:
    st.error(f"⚠️ Error importing modules: {e}")
    st.info("Please ensure 'processor.py' and 'models.py' are in the same folder as 'app.py'.")
    st.stop()

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")

st.title("📈 Stock Portfolio Dashboard")

# Sidebar for file upload
st.sidebar.header("Upload Data")
uploaded_file = st.sidebar.file_uploader("Upload your CSV", type=["csv"])

DATA_FILE = "data.csv"

if uploaded_file is not None:
    # Save uploaded file
    with open(DATA_FILE, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success("File uploaded successfully!")

# Load data
if os.path.exists(DATA_FILE):
    try:
        df = parse_csv(DATA_FILE)
        summary = calculate_portfolio(df)
        
        # --- KPI Metrics ---
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Value", f"€{summary.total_value_eur:,.2f}")
        
        with col2:
            st.metric("Total Invested", f"€{summary.total_invested_eur:,.2f}")
            
        with col3:
            pl_color = "normal"
            if summary.total_unrealized_pl_eur > 0: pl_color = "normal" # Streamlit auto-colors delta
            st.metric("Unrealized P&L", f"€{summary.total_unrealized_pl_eur:,.2f}", 
                      delta=f"{summary.total_unrealized_pl_eur:,.2f} €")

        with col4:
            st.metric("IRR (TIR)", f"{summary.irr * 100:.2f}%")

        # --- Charts ---
        st.markdown("### 📊 Portfolio Allocation")
        
        # Prepare data for charts
        holdings_data = [
            {"Symbol": h.symbol, "Value": h.market_value, "P&L": h.unrealized_pl_percentage}
            for h in summary.holdings if h.quantity > 0
        ]
        df_holdings = pd.DataFrame(holdings_data)
        
        if not df_holdings.empty:
            c1, c2 = st.columns(2)
            
            with c1:
                fig_pie = px.pie(df_holdings, values='Value', names='Symbol', title='Allocation by Value')
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with c2:
                fig_bar = px.bar(df_holdings, x='Symbol', y='P&L', title='Unrealized P&L (%)',
                                 color='P&L', color_continuous_scale=['red', 'green'])
                st.plotly_chart(fig_bar, use_container_width=True)

        # --- Holdings Table ---
        st.markdown("### 📋 Current Holdings")
        
        # Format for display
        display_holdings = []
        for h in summary.holdings:
            if h.quantity > 0:
                display_holdings.append({
                    "Symbol": h.symbol,
                    "Qty": f"{h.quantity:.4f}",
                    "Avg Price": f"€{h.average_price:.2f}",
                    "Current Price": f"{h.currency} {h.current_price:.2f}",
                    "Market Value": f"€{h.market_value:.2f}",
                    "Unrealized P&L (€)": f"€{h.unrealized_pl:.2f}",
                    "Unrealized P&L (%)": f"{h.unrealized_pl_percentage:.2f}%"
                })
        
        st.dataframe(pd.DataFrame(display_holdings), use_container_width=True)
        
        # Debug Info
        if summary.debug_info and summary.debug_info.get("ignored_operations"):
            st.warning(f"⚠️ Some rows were ignored: {summary.debug_info['ignored_operations']}")
            st.info("Supported operations: 'Compra', 'Venta'. Check your CSV 'Operacion' column.")
        
    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
else:
    st.info("Please upload a CSV file to get started.")

