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

st.set_page_config(page_title="Rodrigues Daytrade", page_icon="₿", layout="centered")
TZ = ZoneInfo("America/Sao_Paulo")
BASE = "https://data-api.binance.vision"

st.markdown("""
<style>
.stApp { background:#050505; color:#f4f4f4; }
[data-testid="stSidebar"] { background:#101010; border-right:1px solid #805b17; }
h1,h2,h3 { color:#e9b949 !important; }
.block-container { padding:.45rem .55rem .7rem; max-width:100%; }
div[data-testid="stMetric"] { background:#090b0e; border:1px solid #393329; padding:6px 8px; border-radius:9px; }
div[data-testid="stMetricLabel"] { font-size:.72rem; }
div[data-testid="stMetricValue"] { font-size:1rem; }
</style>
""", unsafe_allow_html=True)

logo_col, brand_col = st.columns([1, 3])
with logo_col:
    try:
        st.image("logo_rodrigues.png", width=88)
    except Exception:
        st.markdown("## 🟡")
with brand_col:
    st.markdown("### RODRIGUES DAYTRADE")
    st.caption("DISCIPLINA · ESTRATÉGIA · RESULTADOS")

INTERVALS = {"M3": "3m", "M15": "15m", "H1": "1h"}
with st.sidebar:
    st.header("Configurações")
    st.markdown("### Sinais MACD")
    entry_dif = st.number_input("DIF de entrada", value=-1000.0, step=10.0)
    entry_dea = st.number_input("DEA de entrada", value=-800.0, step=10.0)
    exit_dif = st.number_input("DIF de saída", value=455.0, step=10.0)
    exit_dea = st.number_input("DEA de saída", value=450.0, step=10.0)
    tolerance = st.number_input("Tolerância DIF/DEA", min_value=0.0, value=5.0, step=1.0)
    st.markdown("### Médias móveis")
    sma_fast_period = st.number_input("SMA rápida", min_value=2, max_value=30, value=9, step=1)
    sma_slow_period = st.number_input("SMA lenta", min_value=3, max_value=50, value=12, step=1)
    refresh = st.slider("Atualização (segundos)", 15, 120, 30, 15)
    st.caption("Painel informativo. Não envia ordens.")

def get_klines(symbol, interval, limit=150):
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(f"{BASE}/api/v3/klines?{query}", headers={"User-Agent": "RodriguesDaytrade/1.0"})
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
    return dif, dea, [a - b for a, b in zip(dif, dea)]

def sma_series(values, period):
    return [None if i + 1 < period else sum(values[i + 1 - period:i + 1]) / period for i in range(len(values))]

def ensure_state():
    if "signals" not in st.session_state:
        st.session_state.signals = []
    if "seen" not in st.session_state:
        st.session_state.seen = set()

def analyze(symbol, interval):
    rows = get_klines(symbol, interval, 150)
    if len(rows) < max(40, int(sma_slow_period) + 2):
        raise RuntimeError(f"Histórico insuficiente para {symbol} ({interval}).")
    closes = [float(row[4]) for row in rows]
    difs, deas, _ = macd_series(closes)
    fast_n, slow_n = int(sma_fast_period), int(sma_slow_period)
    fast_sma, slow_sma = sum(closes[-fast_n:]) / fast_n, sum(closes[-slow_n:]) / slow_n
    dif, dea, price = difs[-1], deas[-1], closes[-1]
    candle_dt = datetime.fromtimestamp(int(rows[-1][6]) / 1000, timezone.utc).astimezone(TZ)
    buy = abs(dif - entry_dif) <= tolerance and abs(dea - entry_dea) <= tolerance and fast_sma > slow_sma
    sell = abs(dif - exit_dif) <= tolerance and abs(dea - exit_dea) <= tolerance and fast_sma < slow_sma
    signal = "ENTRADA" if buy else ("SAÍDA" if sell else "AGUARDANDO")
    return {"Ativo": symbol, "Período": interval, "Sinal": signal, "Preço": price, "DIF": dif, "DEA": dea,
            "SMA rápida": fast_sma, "SMA lenta": slow_sma,
            "Tendência": "ALTA" if fast_sma > slow_sma else ("BAIXA" if fast_sma < slow_sma else "NEUTRA"),
            "Horário do candle": candle_dt.strftime("%d/%m/%Y %H:%M:%S"),
            "candle_key": f"{symbol}:{interval}:{int(rows[-1][6])}:{signal}"}

def build_chart(symbol, interval):
    rows = get_klines(symbol, interval, 150)
    if len(rows) < 35:
        raise RuntimeError("Histórico insuficiente para o gráfico.")
    dates = [datetime.fromtimestamp(int(r[0]) / 1000, timezone.utc).astimezone(TZ) for r in rows]
    opens, highs, lows, closes = ([float(r[i]) for r in rows] for i in (1, 2, 3, 4))
    dif, dea, hist = macd_series(closes)
    fast_n, slow_n = int(sma_fast_period), int(sma_slow_period)
    fast_sma, slow_sma = sma_series(closes, fast_n), sma_series(closes, slow_n)
    buys_x, buys_y, sells_x, sells_y = [], [], [], []
    for i in range(len(closes)):
        if fast_sma[i] is None or slow_sma[i] is None:
            continue
        if abs(dif[i] - entry_dif) <= tolerance and abs(dea[i] - entry_dea) <= tolerance and fast_sma[i] > slow_sma[i]:
            buys_x.append(dates[i]); buys_y.append(lows[i] * .998)
        if abs(dif[i] - exit_dif) <= tolerance and abs(dea[i] - exit_dea) <= tolerance and fast_sma[i] < slow_sma[i]:
            sells_x.append(dates[i]); sells_y.append(highs[i] * 1.002)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.025, row_heights=[.70, .30],
        subplot_titles=(f"{symbol.replace('BRL','/BRL')} · {interval.upper()}",
                        f"MACD · DIF {dif[-1]:.2f} · DEA {dea[-1]:.2f} · Hist. {hist[-1]:.2f}"))
    fig.add_trace(go.Candlestick(x=dates, open=opens, high=highs, low=lows, close=closes, name="Preço",
        increasing_line_color="#00d979", increasing_fillcolor="#00d979",
        decreasing_line_color="#ff334f", decreasing_fillcolor="#ff334f"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=fast_sma, mode="lines", name=f"SMA {fast_n}", line=dict(color="#ffbd22", width=1.7)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=slow_sma, mode="lines", name=f"SMA {slow_n}", line=dict(color="#326bff", width=1.7)), row=1, col=1)
    if buys_x:
        fig.add_trace(go.Scatter(x=buys_x, y=buys_y, mode="markers+text", name="ENTRADA", text=["B"]*len(buys_x),
            textposition="bottom center", marker=dict(symbol="circle", size=14, color="#00bd70", line=dict(color="white", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)
    if sells_x:
        fig.add_trace(go.Scatter(x=sells_x, y=sells_y, mode="markers+text", name="SAÍDA", text=["S"]*len(sells_x),
            textposition="top center", marker=dict(symbol="circle", size=14, color="#ff334f", line=dict(color="white", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)
    fig.add_hline(y=closes[-1], line_dash="dash", line_color="#00d979", opacity=.75, row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=hist, name="Histograma", marker_color=["#00c878" if v >= 0 else "#ff334f" for v in hist]), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dif, mode="lines", name="DIF", line=dict(color="#ffad16", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dea, mode="lines", name="DEA", line=dict(color="#3475ff", width=1.5)), row=2, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#050505", plot_bgcolor="#05090d", height=555,
        margin=dict(l=4, r=4, t=42, b=4), xaxis_rangeslider_visible=False, hovermode=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=9)), font=dict(color="#d5dbe3", size=10))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(150,160,175,.12)", fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(150,160,175,.12)", fixedrange=True)
    return fig

ensure_state()
controls = st.columns([1.15, 1.65, .7])
with controls[0]:
    asset = st.selectbox("Ativo", ["BTCBRL", "SOLBRL"], format_func=lambda x: "BTC/BRL" if x == "BTCBRL" else "SOL/BRL")
with controls[1]:
    period_label = st.selectbox("Tempo", list(INTERVALS.keys()), index=0)
    interval = INTERVALS[period_label]
with controls[2]:
    if st.button("↻", help="Atualizar agora", use_container_width=True):
        st.rerun()
try:
    data = analyze(asset, interval)
    metrics = st.columns(3)
    metrics[0].metric("Preço", f'R$ {data["Preço"]:,.2f}')
    metrics[1].metric("Sinal", data["Sinal"])
    metrics[2].metric("Tendência", data["Tendência"])
    st.caption(f'DIF: {data["DIF"]:.2f} · DEA: {data["DEA"]:.2f} · Candle fechado: {data["Horário do candle"]}')
    if data["Sinal"] in ("ENTRADA", "SAÍDA") and data["candle_key"] not in st.session_state.seen:
        st.session_state.seen.add(data["candle_key"])
        record = {k: v for k, v in data.items() if k != "candle_key"}
        record["Registrado em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
        st.session_state.signals.insert(0, record)
        st.toast(f'{asset}: {data["Sinal"]}', icon="🔔")
    st.plotly_chart(build_chart(asset, interval), use_container_width=True,
        config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "staticPlot": True, "responsive": True})
except Exception as exc:
    st.error(f"Não foi possível consultar a Binance: {exc}")
    st.caption("Verifique a conexão com a internet e tente novamente.")
with st.expander("📋 Histórico de sinais"):
    if st.session_state.signals:
        st.dataframe(st.session_state.signals, use_container_width=True, hide_index=True)
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=list(st.session_state.signals[0].keys()))
        writer.writeheader(); writer.writerows(st.session_state.signals)
        st.download_button("Baixar histórico CSV", csv_buffer.getvalue(), "sinais_binance.csv", "text/csv", use_container_width=True)
    else:
        st.info("Nenhum sinal detectado nesta sessão.")
st.caption("Dados públicos da Binance · Sem execução de ordens · Sinais informativos, sem garantia de resultado.")
time.sleep(refresh)
st.rerun()