# app.py
import streamlit as st
import vectorbt as vbt
import yfinance as yf
import pandas as pd
import plotly.express as px

# Initialize session state
if 'weights' not in st.session_state:
    st.session_state.weights = {}

if 'tickers' not in st.session_state:
    st.session_state.tickers = ['' for _ in range(5)]

# Custom CSS for layout
st.markdown("""
<style>
div.row-widget.stRadio > div {
    flex-direction: row;
}
div.stSlider > div[data-baseweb="slider"] {
    margin: 0.5rem 0;
}
.ticker-box {
    border: 1px solid #ccc;
    padding: 10px;
    border-radius: 5px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

# Portfolio Configuration Section
st.sidebar.header("Portfolio Configuration")

# Ticker input section
st.sidebar.subheader("Ticker Selection")
ticker_boxes = []
selected_tickers = []

# Create 5 ticker input boxes with checkboxes
for i in range(5):
    col1, col2 = st.sidebar.columns([1, 5])
    with col1:
        enabled = st.checkbox("", key=f"enable_{i}", value=bool(st.session_state.tickers[i]))
    with col2:
        if enabled:
            ticker = st.text_input(
                f"Ticker {i+1}",
                value=st.session_state.tickers[i],
                key=f"ticker_{i}",
                placeholder="Enter symbol...",
                label_visibility="collapsed"
            ).strip().upper()
            if ticker:
                selected_tickers.append(ticker)
            st.session_state.tickers[i] = ticker if enabled else ''
        else:
            st.text_input(
                f"Ticker {i+1}",
                value="",
                key=f"ticker_{i}",
                disabled=True,
                placeholder="(Disabled)",
                label_visibility="collapsed"
            )

# Weight allocation section
st.sidebar.subheader("Portfolio Weights")

# Initialize or reset weights when tickers change
current_tickers = tuple(selected_tickers)
if 'prev_tickers' not in st.session_state or st.session_state.prev_tickers != current_tickers:
    num_selected = len(selected_tickers)
    if num_selected > 0:
        equal_weight = 100 / num_selected
        st.session_state.weights = {ticker: equal_weight for ticker in selected_tickers}
    else:
        st.session_state.weights = {}
    st.session_state.prev_tickers = current_tickers

# Weight adjustment functions
def update_weight_from_slider(ticker):
    st.session_state[f"text_{ticker}"] = st.session_state[f"slider_{ticker}"]

def update_weight_from_text(ticker):
    try:
        value = float(st.session_state[f"text_{ticker}"])
        if value < 0:
            value = 0.0
        elif value > 100:
            value = 100.0
        st.session_state.weights[ticker] = value
        st.session_state[f"slider_{ticker}"] = value
    except:
        st.session_state[f"text_{ticker}"] = st.session_state.weights.get(ticker, 0)

# Create weight controls for each selected ticker
if selected_tickers:
    total_weight = sum(st.session_state.weights.values())
    remaining_weight = 100 - total_weight
    
    for ticker in selected_tickers:
        col1, col2, col3 = st.sidebar.columns([2, 6, 2])
        with col1:
            st.text_input(
                "%",
                value=f"{st.session_state.weights.get(ticker, 0):.1f}",
                key=f"text_{ticker}",
                on_change=update_weight_from_text,
                args=(ticker,)
            )
        with col2:
            st.slider(
                ticker,
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.weights.get(ticker, 0)),
                step=0.1,
                key=f"slider_{ticker}",
                on_change=update_weight_from_slider,
                args=(ticker,),
                label_visibility="collapsed"
            )
        with col3:
            st.write("")

    # Auto-balance weights
    total_weight = sum(st.session_state.weights.values())
    if abs(total_weight - 100) > 0.1:
        st.sidebar.warning(f"Total weight: {total_weight:.1f}% - Adjusting to 100%")
        for ticker in selected_tickers:
            st.session_state.weights[ticker] = (st.session_state.weights[ticker] / total_weight) * 100
            st.session_state[f"text_{ticker}"] = f"{st.session_state.weights[ticker]:.1f}"
            st.session_state[f"slider_{ticker}"] = st.session_state.weights[ticker]
    
    st.sidebar.metric("Total Weight", f"{sum(st.session_state.weights.values()):.1f}%")

# Date range selection
st.sidebar.subheader("Backtest Parameters")
start_date = st.sidebar.date_input('Start Date', pd.to_datetime('2020-01-01'))
end_date = st.sidebar.date_input('End Date', pd.to_datetime('today'))
initial_capital = st.sidebar.number_input("Initial Capital ($)", 10000, 1000000, 100000)

# Main content area
st.title("Portfolio Backtester")

if selected_tickers:
    # Display portfolio composition
    st.header("Portfolio Allocation")
    weights = {k: v/100 for k, v in st.session_state.weights.items()}
    fig = px.pie(
        names=list(weights.keys()),
        values=list(weights.values()),
        hole=0.3,
        title="Portfolio Weight Distribution"
    )
    st.plotly_chart(fig)

    # Fetch data
    @st.cache_data
    def load_data(tickers):
        try:
            df = yf.download(tickers, start=start_date, end=end_date)['Close']
            return df.dropna(axis=1, how='all')
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            return None

    price_data = load_data(selected_tickers)
    
    if price_data is not None and not price_data.empty:
        # Create portfolio
        portfolio = vbt.Portfolio.from_orders(
            close=price_data,
            size=list(weights.values()),
            size_type='targetpercent',
            cash_sharing=True,
            group_by=True,
            freq='D',
            init_cash=initial_capital,
            call_seq='auto'
        )

        # Performance metrics
        st.header("Performance Analysis")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Key Statistics")
            stats = portfolio.stats()
            st.metric("Total Return", f"{stats['Total Return [%]']:.2f}%")
            st.metric("Sharpe Ratio", f"{stats['Sharpe Ratio']:.2f}")
            st.metric("Max Drawdown", f"{stats['Max Drawdown [%]']:.2f}%")
        
        with col2:
            st.subheader("Equity Curve")
            fig = portfolio.plot(subplots=['orders', 'trade_pnl', 'cum_returns'])
            st.plotly_chart(fig)

        # Individual asset analysis
        st.header("Individual Asset Performance")
        for ticker in selected_tickers:
            with st.expander(f"{ticker} Analysis"):
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Price History")
                    st.line_chart(price_data[ticker])
                with col2:
                    st.subheader("Metrics")
                    returns = price_data[ticker].pct_change().dropna()
                    ann_return = (1 + returns.mean())**252 - 1
                    ann_vol = returns.std() * np.sqrt(252)
                    sharpe = ann_return / ann_vol if ann_vol > 0 else 0
                    
                    st.metric("Annualized Return", f"{ann_return:.2%}")
                    st.metric("Annualized Volatility", f"{ann_vol:.2%}")
                    st.metric("Sharpe Ratio", f"{sharpe:.2f}")

else:
    st.warning("Please enable and enter at least one ticker to begin analysis")

# Error handling section
if 'price_data' in locals() and price_data is not None:
    if len(price_data.columns) < len(selected_tickers):
        missing = set(selected_tickers) - set(price_data.columns)
        st.error(f"Failed to load data for: {', '.join(missing)}")
