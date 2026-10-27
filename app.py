import csv
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="RODRIGUES DAYTRADE", page_icon="₿", layout="wide")
TZ = ZoneInfo("America/Sao_Paulo")
BASE = "https://data-api.binance.vision"

st.markdown("""
<style>
.stApp {background:#050505;color:#f5f5f5}
[data-testid="stSidebar"] {background:#101010;border-right:1px solid #8a641b}
.block-container {max-width:100%;padding: .45rem .65rem .6rem}
h1,h2,h3 {color:#e8b746!important}
div[data-testid="stMetric"] {background:#080808;border:1px solid #4d3b16;border-radius:9px;padding:6px 9px}
div[data-testid="stMetricLabel"] {font-size:.75rem}
div[data-testid="stMetricValue"] {font-size:1.05rem}
div[data-testid="stPlotlyChart"] {border:1px solid #3a3019;border-radius:12px;overflow:hidden}
[data-testid="stCaptionContainer"] {color:#9ca3af}
</style>
""", unsafe_allow_html=True)

# Header/logo
c_logo, c_title = st.columns([0.75, 3.25], vertical_alignment="center")
with c_logo:
    st.image("logo_rodrigues.png", width=88)
with c_title:
    st.markdown("<h2 style='margin:0;color:#e8b746'>RODRIGUES DAYTRADE</h2>", unsafe_allow_html=True)
    st.caption("DISCIPLINA · ESTRATÉGIA · RESULTADOS")

# Settings in sidebar so the main screen remains compact
intervals = {"M3": "3m", "M15": "15m", "H1": "1h"}
with st.sidebar:
    st.header("⚙️ Configurações")
    asset = st.selectbox("Ativo", ["BTCBRL", "SOLBRL"],
                         format_func=lambda x: "BTC/BRL" if x == "BTCBRL" else "SOL/BRL")
    period_label = st.radio("Tempo gráfico", list(intervals.keys()), horizontal=True, index=0)
    interval = intervals[period_label]
    refresh = st.select_slider("Atualização", options=[15, 30, 45, 60, 90, 120], value=30, format_func=lambda x: f"{x}s")
    tolerance = st.number_input("Tolerância DIF/DEA", min_value=0.0, value=5.0, step=1.0)
    st.markdown("#### Entrada")
    entry_dif = st.number_input("DIF entrada", value=-1000.0, step=10.0)
    entry_dea = st.number_input("DEA entrada", value=-800.0, step=10.0)
    st.markdown("#### Saída")
    exit_dif = st.number_input("DIF saída", value=455.0, step=10.0)
    exit_dea = st.number_input("DEA saída", value=450.0, step=10.0)
    st.markdown("#### Médias")
    sma_fast_period = st.selectbox("SMA rápida", [9, 5, 7, 10], index=0)
    sma_slow_period = st.selectbox("SMA lenta", [12, 10, 14, 20], index=0)

def get_klines(symbol, interval, limit=120):
    q = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(f"{BASE}/api/v3/klines?{q}", headers={"User-Agent": "RodriguesDaytrade/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))
    now_ms = int(time.time() * 1000)
    return [r for r in rows if int(r[6]) < now_ms]

def ema(values, period):
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1 - alpha) * out[-1])
    return out

def macd_series(values):
    fast, slow = ema(values, 12), ema(values, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = ema(dif, 9)
    hist = [a - b for a, b in zip(dif, dea)]
    return dif, dea, hist

def sma_series(values, period):
    result = []
    for i in range(len(values)):
        result.append(None if i + 1 < period else sum(values[i + 1 - period:i + 1]) / period)
    return result

def get_state():
    if "signals" not in st.session_state:
        st.session_state.signals = []
    if "seen" not in st.session_state:
        st.session_state.seen = set()

def analyze(symbol, interval):
    rows = get_klines(symbol, interval, 150)
    if len(rows) < 40:
        raise RuntimeError(f"Histórico insuficiente para {symbol} em {interval}.")
    close = [float(r[4]) for r in rows]
    difs, deas, _ = macd_series(close)
    dif, dea = difs[-1], deas[-1]
    sma_fast = sum(close[-sma_fast_period:]) / sma_fast_period
    sma_slow = sum(close[-sma_slow_period:]) / sma_slow_period
    candle_time = datetime.fromtimestamp(int(rows[-1][6]) / 1000, timezone.utc).astimezone(TZ)
    entry = abs(dif-entry_dif) <= tolerance and abs(dea-entry_dea) <= tolerance and sma_fast > sma_slow
    exit_signal = abs(dif-exit_dif) <= tolerance and abs(dea-exit_dea) <= tolerance and sma_fast < sma_slow
    signal = "ENTRADA" if entry else ("SAÍDA" if exit_signal else "AGUARDANDO")
    return {
        "Ativo": symbol, "Período": interval, "Sinal": signal, "Preço": close[-1],
        "DIF": dif, "DEA": dea, "Histograma": dif-dea,
        "SMA rápida": sma_fast, "SMA lenta": sma_slow,
        "Tendência": "ALTA" if sma_fast > sma_slow else ("BAIXA" if sma_fast < sma_slow else "NEUTRA"),
        "Horário": candle_time.strftime("%d/%m/%Y %H:%M:%S"),
        "key": f"{symbol}:{interval}:{int(rows[-1][6])}:{signal}"
    }

def build_chart(symbol, interval, latest_price):
    rows = get_klines(symbol, interval, 120)
    dates = [datetime.fromtimestamp(int(r[0])/1000, timezone.utc).astimezone(TZ) for r in rows]
    opens = [float(r[1]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    dif, dea, hist = macd_series(closes)
    sma_fast = sma_series(closes, sma_fast_period)
    sma_slow = sma_series(closes, sma_slow_period)

    buy_x, buy_y, sell_x, sell_y = [], [], [], []
    for i in range(len(closes)):
        if sma_fast[i] is None or sma_slow[i] is None:
            continue
        if abs(dif[i]-entry_dif) <= tolerance and abs(dea[i]-entry_dea) <= tolerance and sma_fast[i] > sma_slow[i]:
            buy_x.append(dates[i]); buy_y.append(lows[i] * 0.997)
        if abs(dif[i]-exit_dif) <= tolerance and abs(dea[i]-exit_dea) <= tolerance and sma_fast[i] < sma_slow[i]:
            sell_x.append(dates[i]); sell_y.append(highs[i] * 1.003)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.025,
        row_heights=[0.70, 0.30], subplot_titles=(f"{symbol} · Candles + SMA", "MACD"))
    fig.add_trace(go.Candlestick(x=dates, open=opens, high=highs, low=lows, close=closes,
        name="Preço", increasing_line_color="#00d879", increasing_fillcolor="#00d879",
        decreasing_line_color="#ff3548", decreasing_fillcolor="#ff3548"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_fast, mode="lines", name=f"SMA {sma_fast_period}",
        line=dict(color="#ffbd2e", width=1.8)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_slow, mode="lines", name=f"SMA {sma_slow_period}",
        line=dict(color="#286bff", width=1.8)), row=1, col=1)
    if buy_x:
        fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode="markers+text", name="ENTRADA",
            text=["B"]*len(buy_x), textposition="bottom center",
            marker=dict(size=14, color="#00bd72", symbol="circle", line=dict(color="#ffffff", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)
    if sell_x:
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode="markers+text", name="SAÍDA",
            text=["S"]*len(sell_x), textposition="top center",
            marker=dict(size=14, color="#ff3548", symbol="circle", line=dict(color="#ffffff", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)

    # Price line and label are drawn inside the main chart, not in a separate metric column.
    fig.add_hline(y=latest_price, line_dash="dot", line_color="#00d879", line_width=1, row=1, col=1)
    fig.add_annotation(xref="paper", yref="y", x=0.985, y=latest_price, text=f"{latest_price:,.2f}",
        showarrow=False, xanchor="right", bgcolor="#00a95f", bordercolor="#00d879",
        font=dict(color="white", size=11), borderpad=4, row=1, col=1)

    hist_colors = ["#00c978" if v >= 0 else "#ff3548" for v in hist]
    fig.add_trace(go.Bar(x=dates, y=hist, name="Histograma", marker_color=hist_colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dif, mode="lines", name="DIF",
        line=dict(color="#ffbd2e", width=1.6)), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dea, mode="lines", name="DEA",
        line=dict(color="#286bff", width=1.6)), row=2, col=1)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#050505", plot_bgcolor="#050505",
        height=510, margin=dict(l=4, r=4, t=34, b=4), hovermode=False,
        showlegend=False, xaxis_rangeslider_visible=False,
        dragmode=False, clickmode="none",
        font=dict(color="#cbd5e1", size=10)
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(160,160,160,.12)", fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(160,160,160,.12)", fixedrange=True)
    return fig

get_state()
head_a, head_b, head_c = st.columns([1.15, 1.1, 0.65])
with head_a:
    asset = st.selectbox("Ativo", ["BTCBRL", "SOLBRL"], format_func=lambda x: "₿ BTC/BRL" if x=="BTCBRL" else "◎ SOL/BRL")
with head_b:
    period_label = st.radio("Tempo", list(intervals.keys()), horizontal=True, index=0, label_visibility="collapsed")
    interval = intervals[period_label]
with head_c:
    if st.button("↻", use_container_width=True):
        st.rerun()

try:
    result = analyze(asset, interval)
    # Summary is compact and directly above the chart.
    x2, x3 = st.columns([1, 1])
    x2.metric("SINAL", result["Sinal"])
    x3.metric("TENDÊNCIA", result["Tendência"])
    st.caption(f'SMA {sma_fast_period}: {result["SMA rápida"]:,.2f}   ·   SMA {sma_slow_period}: {result["SMA lenta"]:,.2f}')
    st.plotly_chart(build_chart(asset, interval, result["Preço"]), use_container_width=True,
        config={"staticPlot": True, "displayModeBar": False, "scrollZoom": False, "doubleClick": False,
                "responsive": True})
    st.caption(f'MACD · DIF: {result["DIF"]:.3f}  DEA: {result["DEA"]:.3f}  Histograma: {result["Histograma"]:.3f} · Candle fechado: {result["Horário"]}')
    if result["Sinal"] in ("ENTRADA", "SAÍDA") and result["key"] not in st.session_state.seen:
        st.session_state.seen.add(result["key"])
        st.session_state.signals.insert(0, {k:v for k,v in result.items() if k != "key"})
        st.toast(f'{asset}: {result["Sinal"]}', icon="🔔")
except Exception as e:
    st.error(f"Não foi possível consultar a Binance: {e}")
    st.caption("Verifique a conexão e tente novamente.")

with st.expander("📋 Histórico de sinais"):
    if st.session_state.signals:
        st.dataframe(st.session_state.signals, use_container_width=True, hide_index=True)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(st.session_state.signals[0].keys()))
        writer.writeheader()
        writer.writerows(st.session_state.signals)
        st.download_button("Baixar histórico CSV", buf.getvalue(), "sinais_binance.csv", "text/csv", use_container_width=True)
    else:
        st.info("Nenhum sinal detectado nesta sessão.")

st.caption("Dados públicos · Sem envio de ordens · Sinais informativos, não garantem resultados.")
time.sleep(refresh)
st.rerun()