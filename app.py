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
.stApp { background: #080808; color: #f5f5f5; }
[data-testid="stSidebar"] { background: #111111; border-right: 1px solid #8a641b; }
h1, h2, h3 { color: #e9b949 !important; }
.block-container { padding-top: .55rem; padding-bottom: .5rem; max-width: 100%; }
div[data-testid="stMetric"] { background: #121212; border: 1px solid #6f5118; padding: 6px 9px; border-radius: 8px; }
div[data-testid="stMetricLabel"] { font-size: .78rem; }
div[data-testid="stMetricValue"] { font-size: 1.05rem; }
</style>
""", unsafe_allow_html=True)

logo_col, title_col = st.columns([1, 3])
with logo_col:
    try:
        st.image("logo_rodrigues.png", width=82)
    except Exception:
        st.markdown("## 🟡")
with title_col:
    st.markdown("### 🟡 RODRIGUES DAYTRADE")
    st.caption("BTC/BRL · SOL/BRL | Somente alertas")

interval_labels = {"3 minutos": "3m", "15 minutos": "15m", "1 hora": "1h"}
with st.sidebar:
    st.header("Configurações")
    selected_label = st.selectbox("Tempo gráfico", list(interval_labels.keys()), index=0)
    interval = interval_labels[selected_label]
    refresh = st.slider("Atualização (segundos)", 15, 120, 30, 15)
    tolerance = st.number_input("Tolerância DIF/DEA", min_value=0.0, value=5.0, step=1.0)
    st.markdown("### Entrada")
    entry_dif = st.number_input("DIF de entrada", value=-1000.0, step=10.0)
    entry_dea = st.number_input("DEA de entrada", value=-800.0, step=10.0)
    st.markdown("### Saída")
    exit_dif = st.number_input("DIF de saída", value=455.0, step=10.0)
    exit_dea = st.number_input("DEA de saída", value=450.0, step=10.0)
    st.markdown("### Confirmação por médias")
    sma_fast_period = st.selectbox("SMA rápida", [9, 5, 7, 10], index=0)
    sma_slow_period = st.selectbox("SMA lenta", [12, 10, 14, 20], index=0)
    st.info("Os indicadores e sinais usam o período selecionado. Ajuste os níveis DIF/DEA conforme o ativo.")

def get_klines(symbol, interval, limit=150):
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(
        f"{BASE}/api/v3/klines?{query}",
        headers={"User-Agent": "RodriguesDaytrade/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))
    now_ms = int(time.time() * 1000)
    return [r for r in rows if int(r[6]) < now_ms]

def ema(values, period):
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for x in values[1:]:
        out.append(alpha * float(x) + (1 - alpha) * out[-1])
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
        raise RuntimeError(f"Dados históricos insuficientes para {symbol} em {interval}.")
    closes = [float(r[4]) for r in rows]
    difs, deas, _ = macd_series(closes)
    dif, dea = difs[-1], deas[-1]
    sma_fast = sum(closes[-sma_fast_period:]) / sma_fast_period
    sma_slow = sum(closes[-sma_slow_period:]) / sma_slow_period
    price = closes[-1]
    candle_time = datetime.fromtimestamp(int(rows[-1][6]) / 1000, timezone.utc).astimezone(TZ)
    entry = abs(dif - entry_dif) <= tolerance and abs(dea - entry_dea) <= tolerance and sma_fast > sma_slow
    exit_signal = abs(dif - exit_dif) <= tolerance and abs(dea - exit_dea) <= tolerance and sma_fast < sma_slow
    signal = "ENTRADA" if entry else ("SAÍDA" if exit_signal else "Sem sinal")
    return {
        "Ativo": symbol, "Período": interval, "Sinal": signal, "Preço": price,
        "DIF": dif, "DEA": dea, "SMA rápida": sma_fast, "SMA lenta": sma_slow,
        "Tendência": "ALTA" if sma_fast > sma_slow else ("BAIXA" if sma_fast < sma_slow else "NEUTRA"),
        "Horário do candle": candle_time.strftime("%d/%m/%Y %H:%M:%S"),
        "candle_key": f"{symbol}:{interval}:{int(rows[-1][6])}:{signal}",
    }

def build_chart(symbol, interval):
    rows = get_klines(symbol, interval, 150)
    if len(rows) < 35:
        raise RuntimeError("Histórico insuficiente para desenhar o gráfico.")
    dates = [datetime.fromtimestamp(int(r[0]) / 1000, timezone.utc).astimezone(TZ) for r in rows]
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
        if abs(dif[i] - entry_dif) <= tolerance and abs(dea[i] - entry_dea) <= tolerance and sma_fast[i] > sma_slow[i]:
            buy_x.append(dates[i]); buy_y.append(lows[i] * 0.998)
        if abs(dif[i] - exit_dif) <= tolerance and abs(dea[i] - exit_dea) <= tolerance and sma_fast[i] < sma_slow[i]:
            sell_x.append(dates[i]); sell_y.append(highs[i] * 1.002)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.045,
                        row_heights=[0.68, 0.32],
                        subplot_titles=(f"Candles {interval} + SMA {sma_fast_period}/{sma_slow_period}",
                                        f"MACD {interval} — DIF, DEA e histograma"))
    fig.add_trace(go.Candlestick(x=dates, open=opens, high=highs, low=lows, close=closes,
        name="Candles", increasing_line_color="#16c784", increasing_fillcolor="#16c784",
        decreasing_line_color="#ea3943", decreasing_fillcolor="#ea3943"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_fast, mode="lines", name=f"SMA {sma_fast_period}",
        line=dict(color="#f5b82e", width=1.8)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=sma_slow, mode="lines", name=f"SMA {sma_slow_period}",
        line=dict(color="#536dfe", width=1.8)), row=1, col=1)
    if buy_x:
        fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode="markers+text", name="ENTRADA",
            text=["B"] * len(buy_x), textposition="bottom center",
            marker=dict(symbol="circle", size=15, color="#16c784", line=dict(color="white", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)
    if sell_x:
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode="markers+text", name="SAÍDA",
            text=["S"] * len(sell_x), textposition="top center",
            marker=dict(symbol="circle", size=15, color="#ea3943", line=dict(color="white", width=1)),
            textfont=dict(color="white", size=10)), row=1, col=1)
    colors = ["#16c784" if value >= 0 else "#ea3943" for value in hist]
    fig.add_trace(go.Bar(x=dates, y=hist, name="Histograma", marker_color=colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dif, mode="lines", name="DIF",
        line=dict(color="#f5b82e", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dea, mode="lines", name="DEA",
        line=dict(color="#536dfe", width=1.5)), row=2, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#080808", plot_bgcolor="#080808",
        height=660, margin=dict(l=5, r=5, t=50, b=5), xaxis_rangeslider_visible=False,
        hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(180,180,180,0.15)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(180,180,180,0.15)")
    return fig

get_state()
st.caption(f"Atualizado: {datetime.now(TZ).strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")
top_a, top_b, top_c = st.columns([1.2, 1.2, 1.0])
with top_a:
    chart_asset = st.selectbox("Ativo", ["BTCBRL", "SOLBRL"],
        format_func=lambda v: "BTC/BRL" if v == "BTCBRL" else "SOL/BRL")
with top_b:
    chosen_period = st.selectbox("Período", list(interval_labels.keys()), index=0)
    chosen_interval = interval_labels[chosen_period]
with top_c:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.rerun()

try:
    result = analyze(chart_asset, chosen_interval)
    a, b, c = st.columns(3)
    a.metric("Preço (BRL)", f'{result["Preço"]:,.2f}')
    b.metric("Sinal", result["Sinal"])
    c.metric("Tendência", result["Tendência"])
    st.caption(f'DIF {result["DIF"]:.2f} · DEA {result["DEA"]:.2f} · SMA rápida {result["SMA rápida"]:.2f} · SMA lenta {result["SMA lenta"]:.2f}')
    st.caption(f'Candle fechado: {result["Horário do candle"]}')
    if result["Sinal"] != "Sem sinal":
        key = result["candle_key"]
        if key not in st.session_state.seen:
            st.session_state.seen.add(key)
            record = {k: v for k, v in result.items() if k != "candle_key"}
            record["Registrado em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            st.session_state.signals.insert(0, record)
            st.toast(f'{result["Ativo"]}: {result["Sinal"]}', icon="🔔")
    st.plotly_chart(build_chart(chart_asset, chosen_interval), use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": False})
except Exception as e:
    st.error(f"Não foi possível consultar a Binance: {e}")
    st.caption("Verifique a conexão com a internet e tente novamente.")

with st.expander("📋 Histórico de sinais"):
    if st.session_state.signals:
        st.dataframe(st.session_state.signals, use_container_width=True, hide_index=True)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(st.session_state.signals[0].keys()))
        writer.writeheader()
        writer.writerows(st.session_state.signals)
        st.download_button("Baixar histórico CSV", buffer.getvalue(), "sinais_binance.csv",
            "text/csv", use_container_width=True)
    else:
        st.info("Nenhum sinal detectado nesta sessão.")

st.caption("Dados públicos da Binance · Não envia ordens · Sinais informativos, sem garantia de resultado.")
time.sleep(refresh)
st.rerun()