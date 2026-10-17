import csv
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

st.set_page_config(page_title="Monitor MACD Binance", page_icon="📈", layout="centered")
TZ = ZoneInfo("America/Sao_Paulo")
BASE = "https://data-api.binance.vision"

st.title("📈 Monitor MACD — Binance Spot")
st.caption("BTC/BRL e SOL/BRL · M3 + confirmação SMA 9/12 no M15 · Somente alertas")

with st.sidebar:
    st.header("Configurações")
    tolerance = st.number_input("Tolerância DIF/DEA", min_value=0.0, value=5.0, step=1.0)
    refresh = st.slider("Atualização (segundos)", min_value=15, max_value=120, value=30, step=15)
    st.markdown("### Entrada")
    entry_dif = st.number_input("DIF de entrada", value=-280.0, step=1.0)
    entry_dea = st.number_input("DEA de entrada", value=-285.0, step=1.0)
    st.markdown("### Saída")
    exit_dif = st.number_input("DIF de saída", value=455.0, step=1.0)
    exit_dea = st.number_input("DEA de saída", value=450.0, step=1.0)
    st.info("M3: sinal pelo MACD. M15: SMA 9 > SMA 12 confirma entrada; SMA 9 < SMA 12 confirma saída.")

def get_klines(symbol, interval, limit=120):
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(f"{BASE}/api/v3/klines?{query}", headers={"User-Agent": "MobileMACDMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))
    now_ms = int(time.time() * 1000)
    return [r for r in rows if int(r[6]) < now_ms]

def ema(values, period):
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for x in values[1:]:
        out.append(alpha * float(x) + (1-alpha) * out[-1])
    return out

def macd(values):
    fast, slow = ema(values, 12), ema(values, 26)
    dif = [a-b for a,b in zip(fast, slow)]
    dea = ema(dif, 9)
    return dif[-1], dea[-1]

def get_state():
    if "signals" not in st.session_state:
        st.session_state.signals = []
    if "seen" not in st.session_state:
        st.session_state.seen = set()

def analyze(symbol):
    m3 = get_klines(symbol, "3m")
    m15 = get_klines(symbol, "15m")
    if len(m3) < 40 or len(m15) < 15:
        raise RuntimeError("Dados históricos insuficientes")
    close3 = [float(x[4]) for x in m3]
    close15 = [float(x[4]) for x in m15]
    dif, dea = macd(close3)
    sma9 = sum(close15[-9:])/9
    sma12 = sum(close15[-12:])/12
    price = close3[-1]
    candle_time = datetime.fromtimestamp(int(m3[-1][6])/1000, timezone.utc).astimezone(TZ)
    entry = abs(dif-entry_dif) <= tolerance and abs(dea-entry_dea) <= tolerance and sma9 > sma12
    exit_ = abs(dif-exit_dif) <= tolerance and abs(dea-exit_dea) <= tolerance and sma9 < sma12
    signal = "ENTRADA" if entry else ("SAÍDA" if exit_ else "Sem sinal")
    return {
        "Ativo": symbol, "Sinal": signal, "Preço": price, "DIF (M3)": dif,
        "DEA (M3)": dea, "SMA 9 (M15)": sma9, "SMA 12 (M15)": sma12,
        "Confirmação M15": "ALTA" if sma9 > sma12 else ("BAIXA" if sma9 < sma12 else "NEUTRA"),
        "Horário do candle": candle_time.strftime("%d/%m/%Y %H:%M:%S"),
        "candle_key": f"{symbol}:{int(m3[-1][6])}:{signal}",
    }

get_state()
st.write(f"**Última atualização:** {datetime.now(TZ).strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")

if st.button("🔄 Atualizar agora", use_container_width=True):
    st.rerun()

try:
    results = [analyze(sym) for sym in ("BTCBRL", "SOLBRL")]
    for result in results:
        st.subheader("₿ " + result["Ativo"] if result["Ativo"] == "BTCBRL" else "◎ " + result["Ativo"])
        a, b = st.columns(2)
        a.metric("Preço", f'{result["Preço"]:,.2f} BRL')
        b.metric("Sinal", result["Sinal"])
        c, d = st.columns(2)
        c.metric("DIF (M3)", f'{result["DIF (M3)"]:.4f}')
        d.metric("DEA (M3)", f'{result["DEA (M3)"]:.4f}')
        st.caption(f'SMA9 M15: {result["SMA 9 (M15)"]:.4f} · SMA12 M15: {result["SMA 12 (M15)"]:.4f} · Tendência: {result["Confirmação M15"]}')
        st.caption(f'Candle fechado: {result["Horário do candle"]}')
        if result["Sinal"] != "Sem sinal":
            key = result["candle_key"]
            if key not in st.session_state.seen:
                st.session_state.seen.add(key)
                record = {k: v for k, v in result.items() if k != "candle_key"}
                record["Registrado em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
                st.session_state.signals.insert(0, record)
                st.toast(f'{result["Ativo"]}: {result["Sinal"]}', icon="🔔")
        st.divider()
except Exception as e:
    st.error(f"Não foi possível consultar a Binance: {e}")
    st.caption("Verifique a conexão com a internet e tente novamente.")

st.subheader("📋 Histórico de sinais nesta sessão")
if st.session_state.signals:
    st.dataframe(st.session_state.signals, use_container_width=True, hide_index=True)
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=list(st.session_state.signals[0].keys()))
    writer.writeheader()
    writer.writerows(st.session_state.signals)
    st.download_button("Baixar histórico CSV", csv_buffer.getvalue(), "sinais_binance.csv", "text/csv", use_container_width=True)
else:
    st.info("Nenhum sinal detectado nesta sessão.")

st.caption("O painel consulta dados públicos. Não envia ordens. Mantenha o painel aberto para atualizar; a sessão e o histórico local podem ser perdidos ao reiniciar.")
time.sleep(refresh)
st.rerun()
