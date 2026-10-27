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

st.set_page_config(
    page_title="Rodrigues Daytrade",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

TZ = ZoneInfo("America/Sao_Paulo")
BASE = "https://data-api.binance.vision"

# Visual inspirado na referência enviada.
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(ellipse at 80% 0%, rgba(112, 75, 12, .13), transparent 34%),
            #050505;
        color: #f4f4f4;
    }
    [data-testid="stSidebar"] {
        background: #101010;
        border-right: 1px solid #8a641b;
    }
    .block-container {
        max-width: 1200px;
        padding-top: .65rem;
        padding-bottom: .5rem;
    }
    h1, h2, h3 {
        color: #e9b949 !important;
        letter-spacing: .04em;
    }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #101010, #080808);
        border: 1px solid #6f5118;
        padding: 8px 12px;
        border-radius: 12px;
        min-height: 92px;
    }
    [data-testid="stMetricLabel"] {
        color: #c5c5c5;
        font-size: .82rem;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(1rem, 2vw, 1.45rem);
    }
    div.stButton > button, div.stDownloadButton > button {
        border: 1px solid #b88b2a;
        border-radius: 10px;
        background: #111;
        color: #f1c75b;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
        border-color: #f1c75b;
        color: #fff;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #443719;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Cabeçalho
logo_col, title_col, settings_col = st.columns([1, 4, 0.8], vertical_alignment="center")
with logo_col:
    try:
        st.image("logo_rodrigues.png", width=105)
    except Exception:
        st.markdown("## ₿")
with title_col:
    st.markdown("# RODRIGUES DAYTRADE")
    st.caption("DISCIPLINA  ·  ESTRATÉGIA  ·  RESULTADOS")
with settings_col:
    st.caption("DADOS AO VIVO")

interval_labels = {"M3": "3m", "M15": "15m", "H1": "1h"}

# Configurações editáveis
with st.sidebar:
    st.header("⚙️ Configurações")
    refresh = st.slider("Atualização (segundos)", 15, 120, 30, 15)
    tolerance = st.number_input(
        "Tolerância DIF/DEA", min_value=0.0, value=5.0, step=1.0
    )

    st.markdown("### Entrada")
    entry_dif = st.number_input("DIF de entrada", value=-1000.0, step=10.0)
    entry_dea = st.number_input("DEA de entrada", value=-800.0, step=10.0)

    st.markdown("### Saída")
    exit_dif = st.number_input("DIF de saída", value=455.0, step=10.0)
    exit_dea = st.number_input("DEA de saída", value=450.0, step=10.0)

    st.markdown("### Confirmação por médias")
    sma_fast_period = st.selectbox("SMA rápida", [9, 5, 7, 10], index=0)
    sma_slow_period = st.selectbox("SMA lenta", [12, 10, 14, 20], index=0)
    st.caption("As configurações são aplicadas ao período selecionado.")

def get_klines(symbol, interval, limit=150):
    query = urllib.parse.urlencode(
        {"symbol": symbol, "interval": interval, "limit": limit}
    )
    req = urllib.request.Request(
        f"{BASE}/api/v3/klines?{query}",
        headers={"User-Agent": "RodriguesDaytrade/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))

    now_ms = int(time.time() * 1000)
    # Exclui o candle ainda em formação.
    return [row for row in rows if int(row[6]) < now_ms]

def ema(values, period):
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1 - alpha) * out[-1])
    return out

def macd_series(values):
    fast = ema(values, 12)
    slow = ema(values, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = ema(dif, 9)
    hist = [a - b for a, b in zip(dif, dea)]
    return dif, dea, hist

def sma_series(values, period):
    result = []
    for i in range(len(values)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(values[i + 1 - period:i + 1]) / period)
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

    closes = [float(row[4]) for row in rows]
    difs, deas, _ = macd_series(closes)
    dif, dea = difs[-1], deas[-1]
    sma_fast = sum(closes[-sma_fast_period:]) / sma_fast_period
    sma_slow = sum(closes[-sma_slow_period:]) / sma_slow_period
    price = closes[-1]
    candle_time = datetime.fromtimestamp(
        int(rows[-1][6]) / 1000, timezone.utc
    ).astimezone(TZ)

    entry = (
        abs(dif - entry_dif) <= tolerance
        and abs(dea - entry_dea) <= tolerance
        and sma_fast > sma_slow
    )
    exit_signal = (
        abs(dif - exit_dif) <= tolerance
        and abs(dea - exit_dea) <= tolerance
        and sma_fast < sma_slow
    )
    signal = "ENTRADA" if entry else ("SAÍDA" if exit_signal else "Sem sinal")

    return {
        "Ativo": symbol,
        "Período": interval,
        "Sinal": signal,
        "Preço": price,
        "DIF": dif,
        "DEA": dea,
        "SMA rápida": sma_fast,
        "SMA lenta": sma_slow,
        "Tendência": "ALTA" if sma_fast > sma_slow else (
            "BAIXA" if sma_fast < sma_slow else "NEUTRA"
        ),
        "Horário do candle": candle_time.strftime("%d/%m/%Y %H:%M:%S"),
        "candle_key": f"{symbol}:{interval}:{int(rows[-1][6])}:{signal}",
    }

def build_chart(symbol, interval):
    rows = get_klines(symbol, interval, 100)
    if len(rows) < 35:
        raise RuntimeError("Histórico insuficiente para desenhar o gráfico.")

    dates = [
        datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc).astimezone(TZ)
        for row in rows
    ]
    opens = [float(row[1]) for row in rows]
    highs = [float(row[2]) for row in rows]
    lows = [float(row[3]) for row in rows]
    closes = [float(row[4]) for row in rows]

    dif, dea, hist = macd_series(closes)
    sma_fast = sma_series(closes, sma_fast_period)
    sma_slow = sma_series(closes, sma_slow_period)

    buy_x, buy_y, sell_x, sell_y = [], [], [], []
    for i in range(len(closes)):
        if sma_fast[i] is None or sma_slow[i] is None:
            continue
        if (
            abs(dif[i] - entry_dif) <= tolerance
            and abs(dea[i] - entry_dea) <= tolerance
            and sma_fast[i] > sma_slow[i]
        ):
            buy_x.append(dates[i])
            buy_y.append(lows[i] * 0.998)
        if (
            abs(dif[i] - exit_dif) <= tolerance
            and abs(dea[i] - exit_dea) <= tolerance
            and sma_fast[i] < sma_slow[i]
        ):
            sell_x.append(dates[i])
            sell_y.append(highs[i] * 1.002)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.69, 0.31],
        subplot_titles=(
            f"PREÇO · SMA {sma_fast_period}/{sma_slow_period}",
            "MACD · DIF / DEA",
        ),
    )

    fig.add_trace(
        go.Candlestick(
            x=dates, open=opens, high=highs, low=lows, close=closes,
            name="Candles",
            increasing_line_color="#16c784",
            increasing_fillcolor="#16c784",
            decreasing_line_color="#ea3943",
            decreasing_fillcolor="#ea3943",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=sma_fast, mode="lines", name=f"SMA {sma_fast_period}",
            line=dict(color="#f5b82e", width=1.6),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=sma_slow, mode="lines", name=f"SMA {sma_slow_period}",
            line=dict(color="#3478f6", width=1.6),
        ),
        row=1, col=1,
    )

    if buy_x:
        fig.add_trace(
            go.Scatter(
                x=buy_x, y=buy_y, mode="markers+text", name="ENTRADA",
                text=["B"] * len(buy_x), textposition="bottom center",
                marker=dict(symbol="circle", size=13, color="#16c784",
                            line=dict(color="white", width=1)),
                textfont=dict(color="white", size=9),
            ),
            row=1, col=1,
        )
    if sell_x:
        fig.add_trace(
            go.Scatter(
                x=sell_x, y=sell_y, mode="markers+text", name="SAÍDA",
                text=["S"] * len(sell_x), textposition="top center",
                marker=dict(symbol="circle", size=13, color="#ea3943",
                            line=dict(color="white", width=1)),
                textfont=dict(color="white", size=9),
            ),
            row=1, col=1,
        )

    colors = ["#16c784" if value >= 0 else "#ea3943" for value in hist]
    fig.add_trace(
        go.Bar(x=dates, y=hist, name="Histograma", marker_color=colors),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=dif, mode="lines", name="DIF",
            line=dict(color="#f5b82e", width=1.4),
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=dea, mode="lines", name="DEA",
            line=dict(color="#3478f6", width=1.4),
        ),
        row=2, col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080808",
        plot_bgcolor="#080808",
        height=490,
        margin=dict(l=4, r=4, t=38, b=4),
        xaxis_rangeslider_visible=False,
        hovermode=False,
        showlegend=False,
        dragmode=False,
        font=dict(color="#d8d8d8", size=10),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(180,180,180,0.12)",
        fixedrange=True,
        showspikes=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(180,180,180,0.12)",
        fixedrange=True,
    )
    return fig

get_state()

st.caption(
    f"Atualizado: {datetime.now(TZ).strftime('%d/%m/%Y %H:%M:%S')} (Brasília)"
)

control_a, control_b, control_c = st.columns([1.5, 1.2, 1])
with control_a:
    chart_asset = st.selectbox(
        "Ativo",
        ["BTCBRL", "SOLBRL"],
        format_func=lambda value: "BTC/BRL" if value == "BTCBRL" else "SOL/BRL",
    )
with control_b:
    chosen_period = st.segmented_control(
        "Período",
        options=list(interval_labels.keys()),
        default="M3",
        selection_mode="single",
    )
    if chosen_period is None:
        chosen_period = "M3"
    chosen_interval = interval_labels[chosen_period]
with control_c:
    if st.button("↻ Atualizar", use_container_width=True):
        st.rerun()

try:
    result = analyze(chart_asset, chosen_interval)

    # Preço, sinal e tendência permanecem juntos na mesma linha.
    metric_a, metric_b, metric_c = st.columns([1.25, 1, 1])
    metric_a.metric("Preço (BRL)", f'R$ {result["Preço"]:,.2f}')
    metric_b.metric("Sinal", result["Sinal"])
    metric_c.metric("Tendência", result["Tendência"])

    st.caption(
        f'DIF: {result["DIF"]:.2f}  ·  DEA: {result["DEA"]:.2f}  ·  '
        f'SMA {sma_fast_period}: {result["SMA rápida"]:.2f}  ·  '
        f'SMA {sma_slow_period}: {result["SMA lenta"]:.2f}'
    )
    st.plotly_chart(
        build_chart(chart_asset, chosen_interval),
        use_container_width=True,
        config={
            "staticPlot": True,
            "scrollZoom": False,
            "displayModeBar": False,
            "doubleClick": False,
            "responsive": True,
        },
    )
    st.caption(f'Candle fechado: {result["Horário do candle"]}')

    if result["Sinal"] != "Sem sinal":
        key = result["candle_key"]
        if key not in st.session_state.seen:
            st.session_state.seen.add(key)
            record = {key: value for key, value in result.items() if key != "candle_key"}
            record["Registrado em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            st.session_state.signals.insert(0, record)
            st.toast(f'{result["Ativo"]}: {result["Sinal"]}', icon="🔔")

except Exception as exc:
    st.error(f"Não foi possível consultar a Binance: {exc}")
    st.caption("Verifique a conexão com a internet e tente novamente.")

with st.expander("📋 Histórico de sinais"):
    if st.session_state.signals:
        st.dataframe(
            st.session_state.signals,
            use_container_width=True,
            hide_index=True,
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=list(st.session_state.signals[0].keys())
        )
        writer.writeheader()
        writer.writerows(st.session_state.signals)
        st.download_button(
            "Baixar histórico CSV",
            buffer.getvalue(),
            "sinais_binance.csv",
            "text/csv",
            use_container_width=True,
        )
    else:
        st.info("Nenhum sinal detectado nesta sessão.")

st.caption(
    "Dados públicos da Binance · Não envia ordens · "
    "Sinais informativos, sem garantia de resultado."
)

# Atualização automática sem manter a tela bloqueada por longos períodos.
time.sleep(refresh)
st.rerun()
