"""Dashboard ephemnous (Streamlit)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent))
import queries

ROOT = Path(__file__).resolve().parent.parent

st.set_page_config(page_title="ephemnous", layout="wide")
st.title("ephemnous - escalonador de IA para data center em órbita")


@st.cache_resource
def get_conn():
    return queries.connect()


conn = get_conn()
nodes = queries.list_nodes(conn)
if not nodes:
    st.warning("Sem nós no banco ainda. Rode o backend + um nó/sim "
               "(`python scripts/run_node_sim.py 60 sim-1` ou o Wokwi).")
    st.stop()

names = {f"{n[1]} ({n[2]})": n[0] for n in nodes}
sel = st.sidebar.selectbox("Nó", list(names.keys()))
node_id = names[sel]
st.sidebar.caption("Aba Ao Vivo atualiza sozinha a cada 3 s.")

tab_live, tab_sci = st.tabs(["Ao Vivo", "Ciência"])


@st.fragment(run_every="3s")
def live_view():
    df = queries.node_state_df(conn, node_id)
    if df.empty:
        st.info("Aguardando telemetria deste nó...")
        return
    last = df.iloc[-1]
    tel = queries.latest_telemetry(conn, node_id) or {}
    dec = queries.decisions_df(conn, node_id)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Potência solar", f"{last['power_w']:.0f} W")
    c2.metric("Temperatura", f"{last['temp_c']:.1f} °C", f"folga {last['margin_k']:.1f} K")
    c3.metric("Bateria (SoC)", f"{last['soc'] * 100:.0f} %")
    c4.metric("Regime", "eclipse" if last["eclipse"] else "sol")
    if not dec.empty:
        c5.metric("Última decisão IA", dec.iloc[0]["ação"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    x = list(range(len(df)))
    fig.add_trace(go.Scatter(x=x, y=df["power_w"], name="potência (W)", line=dict(color="#f5a623")),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=df["temp_c"], name="temp (°C)", line=dict(color="#d0021b")),
                  secondary_y=True)

    fc = queries.latest_forecast(conn, node_id)
    if fc and fc["pred_power_w"]:
        xf = list(range(len(df) - 1, len(df) - 1 + len(fc["pred_power_w"]) + 1))
        yf = [df["power_w"].iloc[-1]] + list(fc["pred_power_w"])
        fig.add_trace(go.Scatter(x=xf, y=yf, name=f"previsão IA ({fc['model']})",
                                 line=dict(color="#4a90e2", dash="dash")), secondary_y=False)
    for i, ecl in enumerate(df["eclipse"]):
        if ecl:
            fig.add_vrect(x0=i - 0.5, x1=i + 0.5, fillcolor="#222", opacity=0.08, line_width=0)
    fig.update_yaxes(title_text="potência (W)", secondary_y=False)
    fig.update_yaxes(title_text="temperatura (°C)", secondary_y=True)
    fig.update_layout(height=360, margin=dict(t=30, b=10), legend=dict(orientation="h"),
                      title="Telemetria + previsão da IA (linha tracejada = futuro previsto)")
    st.plotly_chart(fig, width="stretch")

    ca, cb = st.columns([1, 1])
    with ca:
        figs = go.Figure()
        figs.add_trace(go.Scatter(x=x, y=df["soc"] * 100, fill="tozeroy", line=dict(color="#7ed321")))
        figs.update_layout(height=240, margin=dict(t=30, b=10), title="Bateria SoC (%)",
                           yaxis=dict(range=[0, 100]))
        st.plotly_chart(figs, width="stretch")
    with cb:
        st.caption("Decisões recentes da IA")
        st.dataframe(dec[["ação", "pwm", "modo", "motivo"]], hide_index=True,
                     width="stretch", height=240)


with tab_live:
    live_view()

with tab_sci:
    st.subheader("A previsão ganha onde importa, e a gente mede onde")
    png = ROOT / "data" / "regime_curve.png"
    mcol, tcol = st.columns([3, 2])
    with mcol:
        if png.exists():
            st.image(str(png), width="stretch")
        else:
            st.info("Gere a curva: `python scripts/compare_jobs.py plot`")
    with tcol:
        st.markdown(
            "Resultado (jobs não-interrompíveis):\n"
            "- Regime energia-crítico (bateria 6-12 Wh): a IA conclui ~20-25% mais "
            "jobs e perde ~65-75% menos, delta score +3.3 a +4.9 com IC 95% > 0 em 3 blocos.\n"
            "- Regime folgado (>=16 Wh): empate, e a gente diz isso.\n"
            "- Comparação justa: mesma regra de admissão, só muda a qualidade da previsão.\n\n"
            "Por que é ML de verdade (sem leakage):\n"
            "- skill vs persistência inteligente: 0.64-0.68 (energia), 0.62-0.89 (folga térmica)\n"
            "- skill vs efeméride (física pura): 0.60-0.78, o ML prevê a incerteza "
            "(apontamento/atitude), não o eclipse determinístico."
        )

    metrics_path = ROOT / "ephemnous" / "ml" / "models" / "metrics.json"
    if metrics_path.exists():
        st.caption("Skill do forecaster por alvo/horizonte (validação por episódio)")
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        st.dataframe(data, hide_index=True, width="stretch")
