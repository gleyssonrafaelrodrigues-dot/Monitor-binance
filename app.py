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

# -------------------- Visual --------------------
st.markdown("""
<style>
.stApp { background: #080808; color: #f5f5f5; }
[data-testid="stSidebar"] { background: #111111; border-right: 1px solid #8a641b; }
h1, h2, h3 { color: #e9b949 !important; }
.block-container { padding-top: .45rem; padding-bottom: .35rem; max-width: 100%; }
div[data-testid="stMetric"] { background: #121212; border: 1px solid #6f5118; padding: 5px 7px; border-radius: 8px; }
div[data-testid="stMetricLabel"] { font-size: .75rem; }
div[data-testid="stMetricValue"] { font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

logo_col, title_col = st.columns([1, 3])
with logo_col:
    try:
        st.image("logo_rodrigues.png", width=76)
    except Exception:
        st.markdown("## 🟡")
with title_col:
    st.markdown("### 🟡 RODRIGUES DAYTRADE")
    st.caption("BTC/BRL · SOL/BRL | Somente alertas")

# -------------------- Settings --------------------
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
    st.info("Os indicadores e sinais usam o período selecionado. Valores MACD dependem do ativo; ajuste DIF/DEA para cada ativo se necessário.")

def get_klines(symbol, interval, limit=150):
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(
        f"{BASE}/api/v3/klines?{query}",
        headers={"User-Agent": "RodriguesDaytrade/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))
    now_ms = int(time.time() * 1000)
    # Binance kline field 6 is close time. Ignore the still-open candle.
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
    out = []
    for i in range(len(values)):
        out.append(None if i + 1 < period else sum(values[i + 1 - period:i + 1]) / period)
    return out

def get_state()
col_asset, col_period, col_refresh = st.columns([1.2, 1.2, 1])
with col_asset:
    chart_asset = st.selectbox("Ativo", ["BTCBRL", "SOLBRL"], format_func=lambda v: "BTC/BRL" if v == "BTCBRL" else "SOL/BRL")
with col_period:
    selected_label = st.selectbox("Tempo gráfico", list(interval_labels.keys()), index=list(interval_labels.values()).index(interval))
    interval = interval_labels[selected_label]
with col_refresh:
    st.write("")
    if st.button("🔄", use_container_width=True): st.rerun()

try:
    result = analyze(chart_asset)
    a, b, c = st.columns(3)
    a.metric("Preço (BRL)", f'{result["Preço"]:,.2f}')
    b.metric("Sinal", result["Sinal"])
    c.metric("Tendência", result["Tendência"])
    st.caption(f'DIF {result["DIF"]:.2f} · DEA {result["DEA"]:.2f} · SMA rápida {result["SMA rápida"]:.2f} · SMA lenta {result["SMA lenta"]:.2f}')
    st.plotly_chart(build_chart(chart_asset), use_container_width=True, config={"scrollZoom": True, "displayModeBar": False})
    st.caption(f'Candle fechado: {result["Horário do candle"]} · Atualizado {datetime.now(TZ).strftime("%H:%M:%S")}')
    if result["Sinal"] != "Sem sinal":
        key = result["candle_key"]
        if key not in st.session_state.seen:
            st.session_state.seen.add(key)
            record = {k: v for k, v in result.items() if k != "candle_key"}
            record["Registrado em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            st.session_state.signals.insert(0, record)
            st.toast(f'{result["Ativo"]}: {result["Sinal"]}', icon="🔔")
except Exception as e:
    st.error(f"Não foi possível consultar a Binance: {e}")
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

st.caption("Dados públicos da Binance · Não envia ordens · Atualização automática")
time.sleep(refresh)
st.rerun()