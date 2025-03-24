# app.py
import streamlit as st
import vectorbt as vbt
import yfinance as yf
import pandas as pd
import plotly.express as px
import re

# Initialize session state
if 'ticker_data' not in st.session_state:
    st.session_state.ticker_data = {}
if 'weights' not in st.session_state:
    st.session_state.weights = {}
if 'valid_tickers' not in st.session_state:
    st.session_state.valid_tickers = []

# Custom CSS for improved layout
st.markdown("""
<style>
.ticker-row {
    border: 1px solid #e0e0e0;
    border-radius: 5px;
    padding: 10px;
    margin-bottom: 10px;
    background: #f8f9fa;
}
.ticker-row:hover {
    background: #f1f3f5;
}
.weight-input {
    max-width: 100px;
}
.st-emotion-cache-1n5z4mc {
    gap: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

def validate_ticker(ticker):
    """Validate stock ticker format"""
    return re.match(r'^[A-Z]{1,5}$', ticker)

def normalize_weights():
    """Ensure weights sum to 100% with proportional adjustment"""
    total = sum(st.session_state.weights.values())
    if total == 0:
        equal_weight = 100 / len(st.session_state.valid_tickers) if st.session_state.valid_tickers else 0
        st.session_state.weights = {t: equal_weight for t in st.session_state.valid_tickers}
    else:
        for ticker in st.session_state.weights:
            st.session_state.weights[ticker] = (st.session_state.weights[ticker] / total) * 100

def handle_ticker_change(index):
    """Handle ticker input changes and validation"""
    ticker = st.session_state[f'ticker_{index}'].strip().upper()
    enabled = st.session_state[f'enable_{index}']
    
    # Clear invalid data when ticker changes
    if ticker != st.session_state.ticker_data.get(index, {}).get('value', ''):
        if ticker in st.session_state.valid_tickers:
            st.session_state.valid_tickers.remove(ticker)
        if ticker in st.session_state.weights:
            del st.session_state.weights[ticker]
    
    # Validate new ticker
    if enabled and ticker:
        if validate_ticker(ticker):
            if ticker not in st.session_state.valid_tickers:
                st.session_state.valid_tickers.append(ticker)
            if ticker not in st.session_state.weights:
                st.session_state.weights[ticker] = 0
        else:
            st.error(f"Invalid ticker format: {ticker}")
    
    # Store ticker state
    st.session_state.ticker_data[index] = {
        'enabled': enabled,
        'value': ticker,
        'valid': validate_ticker(ticker) if enabled else False
    }
    
    normalize_weights()

# Portfolio Configuration
st.sidebar.header("Portfolio Setup")

# Create 5 ticker input rows
for i in range(5):
    with st.sidebar.container():
        cols = st.columns([1, 4, 3])
        with cols[0]:
            enabled = st.checkbox(
                "", 
                key=f"enable_{i}",
                value=st.session_state.ticker_data.get(i, {}).get('enabled', False),
                on_change=handle_ticker_change,
                args=(i,)
            )
        with cols[1]:
            ticker = st.text_input(
                "Ticker",
                value=st.session_state.ticker_data.get(i, {}).get('value', ''),
                key=f"ticker_{i}",
                disabled=not enabled,
                placeholder="Enter symbol...",
                label_visibility="collapsed",
                on_change=handle_ticker_change,
                args=(i,)
            )
        with cols[2]:
            if enabled and ticker and validate_ticker(ticker):
                weight = st.number_input(
                    "Weight %",
                    min_value=0.0,
                    max_value=100.0,
                    value=st.session_state.weights.get(ticker, 0.0),
                    key=f"weight_{ticker}",
                    step=0.1,
                    format="%.1f",
                    on_change=normalize_weights,
                    label_visibility="collapsed"
                )
                st.session_state.weights[ticker] = weight

# Date and capital inputs
st.sidebar.header("Backtest Parameters")
start_date = st.sidebar.date_input('Start Date', pd.to_datetime('2020-01-01'))
end_date = st.sidebar.date_input('End Date', pd.to_datetime('today'))
initial_capital = st.sidebar.number_input("Initial Capital ($)", 10000, 1000000, 100000)

# Main display area
st.title("Portfolio Backtester")

if st.session_state.valid_tickers:
    # Normalize weights and show allocation
    normalize_weights()
    valid_weights = {k: v/100 for k, v in st.session_state.weights.items() if k in st.session_state.valid_tickers}
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.header("Allocation")
        fig = px.pie(
            names=list(valid_weights.keys()),
            values=list(valid_weights.values()),
            hole=0.3
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Data loading with validation
    @st.cache_data(show_spinner="Loading market data...")
    def load_data(tickers):
        try:
            df = yf.download(tickers, start=start_date, end=end_date)['Close']
            return df.dropna(axis=1, how='all')
        except Exception as e:
            st.error(f"Data loading failed: {str(e)}")
            return None

    if st.button("Run Backtest") or 'price_data' in st.session_state:
        price_data = load_data(st.session_state.valid_tickers)
        
        if price_data is not None and not price_data.empty:
            # Portfolio construction
            portfolio = vbt.Portfolio.from_orders(
                close=price_data,
                size=list(valid_weights.values()),
                size_type='targetpercent',
                cash_sharing=True,
                group_by=True,
                freq='D',
                init_cash=initial_capital
            )
            
            # Performance metrics
            with col2:
                st.header("Performance Analysis")
                st.metric("Total Return", f"{portfolio.stats()['Total Return [%]']:.2f}%")
                st.metric("Sharpe Ratio", f"{portfolio.stats()['Sharpe Ratio']:.2f}")
                st.metric("Max Drawdown", f"{portfolio.stats()['Max Drawdown [%]']:.2f}%")
                
                st.subheader("Equity Curve")
                st.plotly_chart(portfolio.plot(subplots=['orders', 'cum_returns']))
            
            # Individual asset analysis
            st.header("Asset Details")
            tabs = st.tabs(st.session_state.valid_tickers)
            for i, ticker in enumerate(st.session_state.valid_tickers):
                with tabs[i]:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Price History")
                        st.line_chart(price_data[ticker])
                    with col2:
                        st.subheader("Statistics")
                        returns = price_data[ticker].pct_change().dropna()
                        st.metric("Annualized Return", f"{(returns.mean() * 252):.2%}")
                        st.metric("Volatility", f"{(returns.std() * np.sqrt(252)):.2%}")
                        st.metric("Max Drawdown", f"{(returns.cumsum().expanding().max() - returns.cumsum()).max():.2%}")
else:
    st.warning("Please enable and enter valid tickers to begin analysis")

# Validation summary
if 'price_data' in locals() and price_data is not None:
    missing = set(st.session_state.valid_tickers) - set(price_data.columns)
    if missing:
        st.error(f"Failed to load data for: {', '.join(missing)}")
