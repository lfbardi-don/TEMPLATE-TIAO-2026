"""
FarmTech Solutions — Dashboard (Streamlit)  •  FASE 4 / CAP 1

Interactive panel for farm managers integrating:
  • PARTE 1 — ML pipeline (Scikit-Learn) + real metrics;
  • PARTE 2 — management predictions (irrigation, fertilization, yield);
  • Ir Além 1 — PostgreSQL persistence;
  • Ir Além 2 — correlation, prediction and trend charts.

Code/identifiers are in English; on-screen text stays in Portuguese (the
audience is Brazilian farm managers).

Run (from the CAP1 folder):
    streamlit run src/dashboard.py
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

import database as db
import recommendation
from config import (
    TARGETS, FEATURES, DATASET_PATH, METRICS_PATH, MODELS_DIR, FIGURES_DIR,
)

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FarmTech Solutions — Agricultura Cognitiva",
    page_icon="🌾",
    layout="wide",
)

st.markdown("""
    <style>
    .main-title { font-size: 38px; font-weight: 800; color: #005088; margin-bottom: 2px; }
    .subtitle  { font-size: 18px; color: #64748b; margin-bottom: 18px; }
    .kpi-box   { background:#f8fafc; padding:18px; border-radius:10px; border-left:5px solid #11CAA0; }
    </style>
""", unsafe_allow_html=True)

DEFAULT_DEVICE_ID = 101

# Portuguese labels for the history table columns (keeps the UI in Portuguese).
HISTORY_LABELS = {
    "id_reading": "ID", "plantation_sector": "Setor", "sensor_model": "Sensor",
    "reading_ts": "Data/Hora", "temperature": "Temp (°C)", "ph": "pH",
    "soil_humidity": "Umidade (%)", "n": "N", "p": "P", "k": "K", "pump": "Bomba",
    "yield_ton_ha": "Produtividade (ton/ha)",
    "irrigation_volume_l_m2": "Irrigação (L/m²)",
    "fertilizer_kg_ha": "Fertilizante (kg/ha)",
    "recommendation_irrigation": "Rec. Irrigação",
    "recommendation_fertilization": "Rec. Fertilização",
    "recommendation_yield": "Rec. Produtividade",
}


# ── Cached loaders ───────────────────────────────────────────────────────────
@st.cache_data
def load_data() -> pd.DataFrame | None:
    if not DATASET_PATH.exists():
        return None
    df = pd.read_csv(DATASET_PATH)
    df["total_nutrients"] = df["n"] + df["p"] + df["k"]
    df["temp_ph_interaction"] = df["temperature"] * df["ph"]
    return df


@st.cache_resource
def load_models() -> dict:
    models = {}
    for target in TARGETS:
        path = MODELS_DIR / f"model_{target}.pkl"
        if path.exists():
            models[target] = joblib.load(path)
    return models


@st.cache_data
def load_metrics() -> pd.DataFrame | None:
    return pd.read_csv(METRICS_PATH) if METRICS_PATH.exists() else None


def build_input(n, p, k, ph, humidity, temperature, pump) -> pd.DataFrame:
    """Build the input row in the EXACT FEATURES order (prevents misalignment)."""
    values = {
        "n": n, "p": p, "k": k, "ph": ph, "humidity": humidity,
        "temperature": temperature, "pump": pump,
        "total_nutrients": n + p + k, "temp_ph_interaction": temperature * ph,
    }
    return pd.DataFrame([[values[c] for c in FEATURES]], columns=FEATURES)


df = load_data()
models = load_models()
metrics = load_metrics()

# ── Sidebar: project and database status ─────────────────────────────────────
with st.sidebar:
    st.header("🌱 FarmTech Solutions")
    st.caption("FASE 4 · CAP 1 — Agricultura Cognitiva")

    st.subheader("Status do pipeline")
    st.write("📊 Dataset:", "✅" if df is not None else "❌ ausente")
    st.write(f"🤖 Modelos carregados: {len(models)}/{len(TARGETS)}")

    db_ok, db_msg = db.test_connection()
    if db_ok:
        try:
            db.init_db()  # ensure schema/seed (idempotent)
        except Exception as exc:  # noqa: BLE001
            db_ok, db_msg = False, f"Schema: {exc}"
    st.write("🗄️ PostgreSQL:", "✅ conectado" if db_ok else "⚠️ offline")
    if not db_ok:
        st.caption("Suba o banco com `docker compose up -d`. "
                   "A IA funciona offline; o histórico fica indisponível.")

    st.divider()
    st.caption("Pipeline: `generate_dataset → eda → train → dashboard`")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">🌾 FarmTech Solutions — Agricultura Cognitiva</p>',
            unsafe_allow_html=True)
st.markdown('<p class="subtitle">Do sensor à decisão: previsão de produtividade, '
            'irrigação e fertilização da soja com Machine Learning</p>',
            unsafe_allow_html=True)

if df is None or not models:
    st.error("❌ Dataset ou modelos ausentes. Rode o pipeline antes:\n\n"
             "```\npython src/generate_dataset.py\npython src/eda.py\npython src/train.py\n```")
    st.stop()

tab_overview, tab_models, tab_simulator, tab_history = st.tabs(
    ["📍 Panorama", "🤖 Desempenho dos Modelos", "🔮 Simulador de Manejo", "🗄️ Histórico (DB)"]
)


# =============================================================================
# TAB 1 — FIELD OVERVIEW
# =============================================================================
with tab_overview:
    st.subheader("Diagnóstico geral da base de sensores")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Umidade média", f"{df['humidity'].mean():.1f}%")
    c2.metric("Temperatura média", f"{df['temperature'].mean():.1f} °C")
    c3.metric("pH médio", f"{df['ph'].mean():.2f}")
    c4.metric("Uso da bomba", f"{df['pump'].mean() * 100:.1f}%")

    st.markdown("Produtividade prevista média e amplitude observada nos dados:")
    p1, p2, p3 = st.columns(3)
    p1.metric("Produtividade média", f"{df['yield_ton_ha'].mean():.2f} ton/ha")
    p2.metric("Produtividade máxima", f"{df['yield_ton_ha'].max():.2f} ton/ha")
    p3.metric("Irrigação média", f"{df['irrigation_volume_l_m2'].mean():.2f} L/m²")

    st.divider()
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### 📈 Matriz de correlação")
        img = FIGURES_DIR / "correlation.png"
        if img.exists():
            st.image(str(img), width="stretch")
        st.caption("Diferente da base original (grade fatorial sem sinal), aqui os alvos "
                   "correlacionam-se de forma agronomicamente coerente com os sensores.")
    with g2:
        st.markdown("#### 🌾 Produtividade por faixa")
        img2 = FIGURES_DIR / "yield_by_range.png"
        if img2.exists():
            st.image(str(img2), width="stretch")
        st.caption("A produtividade é máxima nas faixas ideais de umidade, pH e temperatura.")


# =============================================================================
# TAB 2 — MODEL PERFORMANCE (real metrics)
# =============================================================================
with tab_models:
    st.subheader("Métricas reais de validação — Regressão Linear × Random Forest")
    st.caption("Conjunto de teste (split 80/20, sem vazamento de alvo). "
               "Métricas calculadas em `src/train.py` e salvas em `src/models/metrics.csv`.")

    if metrics is not None:
        st.dataframe(metrics, width="stretch", hide_index=True)

        # R² comparison per target (Linear vs RF)
        pivot = metrics.pivot(index="label", columns="model", values="R2")
        fig, ax = plt.subplots(figsize=(9, 4))
        pivot.plot.bar(ax=ax, color={"Regressão Linear": "#94a3b8", "Random Forest": "#11CAA0"})
        ax.set_ylabel("R² (quanto maior, melhor)")
        ax.set_xlabel("")
        ax.set_title("Comparação de R² — Linear × Random Forest")
        ax.tick_params(axis="x", rotation=12)
        ax.legend(title="")
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.info(
            "**Leitura dos resultados:** a **produtividade** é fortemente NÃO-LINEAR "
            "(resposta gaussiana em torno dos ótimos), então a Regressão Linear vai mal "
            "(R²≈0,14) enquanto o **Random Forest** captura bem o padrão (R²≈0,92). "
            "Para irrigação e fertilização o modelo linear já é razoável, mas o Random "
            "Forest continua superior — por isso ele é o modelo de produção dos três alvos."
        )

    st.divider()
    st.markdown("#### Real × Previsto e importância de atributos (modelo de produção)")
    for target, label in TARGETS.items():
        st.markdown(f"**{label}**")
        col_a, col_b = st.columns(2)
        avp = FIGURES_DIR / f"actual_vs_predicted_{target}.png"
        imp = FIGURES_DIR / f"importance_{target}.png"
        if avp.exists():
            col_a.image(str(avp), width="stretch")
        if imp.exists():
            col_b.image(str(imp), width="stretch")


# =============================================================================
# TAB 3 — MANAGEMENT SIMULATOR (real-time predictions + recommendations)
# =============================================================================
with tab_simulator:
    st.subheader("Simule as leituras do sensor e obtenha previsões + recomendações")

    col_soil, col_climate, col_nutri = st.columns(3)
    with col_soil:
        st.markdown("**Solo**")
        in_humidity = st.slider("Umidade do solo (%)", 10.0, 95.0, 45.0, step=1.0)
        in_ph = st.slider("pH do solo", 4.5, 8.0, 6.4, step=0.1)
    with col_climate:
        st.markdown("**Clima & Bomba**")
        in_temp = st.slider("Temperatura (°C)", 10.0, 45.0, 30.0, step=0.5)
        in_pump = st.radio("Bomba de irrigação", [0, 1],
                           format_func=lambda x: "Desligada" if x == 0 else "Ligada")
    with col_nutri:
        st.markdown("**Nutrientes (presença)**")
        in_n = st.radio("Nitrogênio (N)", [0, 1],
                        format_func=lambda x: "Ausente" if x == 0 else "Presente")
        in_p = st.radio("Fósforo (P)", [0, 1],
                        format_func=lambda x: "Ausente" if x == 0 else "Presente")
        in_k = st.radio("Potássio (K)", [0, 1],
                        format_func=lambda x: "Ausente" if x == 0 else "Presente")

    if st.button("🌾 Gerar previsões e recomendações", type="primary"):
        x = build_input(in_n, in_p, in_k, in_ph, in_humidity, in_temp, in_pump)
        pred_yield = max(float(models["yield_ton_ha"]["model"].predict(x)[0]), 0.0)
        pred_irrig = max(float(models["irrigation_volume_l_m2"]["model"].predict(x)[0]), 0.0)
        pred_fert = max(float(models["fertilizer_kg_ha"]["model"].predict(x)[0]), 0.0)

        r1, r2, r3 = st.columns(3)
        r1.metric("🌾 Produtividade estimada", f"{pred_yield:.2f} ton/ha")
        r2.metric("💧 Volume de irrigação", f"{pred_irrig:.2f} L/m²")
        r3.metric("🌱 Fertilizante recomendado", f"{pred_fert:.1f} kg/ha")

        st.markdown("#### 📋 Recomendações automáticas de manejo")
        emit = {"ok": st.success, "warning": st.warning, "critical": st.error}

        lvl_i, txt_i = recommendation.recommend_irrigation(pred_irrig, in_humidity, in_temp)
        emit[lvl_i](f"💧 **Irrigação:** {txt_i}")

        lvl_f, txt_f = recommendation.recommend_fertilization(pred_fert, in_n, in_p, in_k, in_ph)
        emit[lvl_f](f"🌱 **Fertilização:** {txt_f}")

        lvl_y, txt_y = recommendation.recommend_yield(pred_yield)
        emit[lvl_y](f"🌾 **Produtividade:** {txt_y}")

        factors = recommendation.limiting_factors(in_humidity, in_ph, in_n + in_p + in_k, in_temp)
        if factors:
            st.info("🔍 **Fatores limitantes:** " + "; ".join(factors) +
                    ". Corrigi-los tende a elevar a produtividade estimada.")
        else:
            st.info("✅ Nenhum fator limitante crítico — condições próximas do ótimo da soja.")

        # ── Persist to PostgreSQL ────────────────────────────────────────────
        if db_ok:
            try:
                new_id = db.insert_reading(
                    id_device=DEFAULT_DEVICE_ID,
                    temperature=in_temp, ph=in_ph, soil_humidity=in_humidity,
                    n=in_n, p=in_p, k=in_k, pump=in_pump,
                    yield_ton_ha=pred_yield,
                    irrigation_volume_l_m2=pred_irrig,
                    fertilizer_kg_ha=pred_fert,
                    recommendation_irrigation=txt_i,
                    recommendation_fertilization=txt_f,
                    recommendation_yield=txt_y,
                )
                st.caption(f"✅ Leitura registrada no PostgreSQL (id_reading = {new_id}).")
            except Exception as exc:  # noqa: BLE001
                st.caption(f"⚠️ Não foi possível salvar no banco: {exc}")
        else:
            st.caption("ℹ️ PostgreSQL offline — previsão não persistida. "
                       "Suba o banco com `docker compose up -d` para registrar o histórico.")


# =============================================================================
# TAB 4 — DATABASE HISTORY (PostgreSQL)
# =============================================================================
with tab_history:
    st.subheader("Histórico de leituras e previsões — PostgreSQL")
    if not db_ok:
        st.warning("⚠️ PostgreSQL offline. Suba o banco com `docker compose up -d` "
                   "e gere previsões no Simulador para popular o histórico.")
    else:
        hist = db.load_history(limit=200)
        if hist.empty:
            st.info("Nenhuma leitura registrada ainda. Use o **Simulador de Manejo** "
                    "para gerar e salvar previsões.")
        else:
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Leituras salvas", len(hist))
            h2.metric("Irrigação média", f"{hist['irrigation_volume_l_m2'].mean():.2f} L/m²")
            h3.metric("Fertilizante médio", f"{hist['fertilizer_kg_ha'].mean():.1f} kg/ha")
            h4.metric("Produtividade média", f"{hist['yield_ton_ha'].mean():.2f} ton/ha")

            st.markdown("#### 📋 Tabela (JOIN sensores + setor da fazenda)")
            st.dataframe(hist.rename(columns=HISTORY_LABELS), width="stretch", hide_index=True)

            if len(hist) >= 2:
                st.markdown("#### 📈 Tendências ao longo das leituras")
                d = hist.sort_values("id_reading")
                fig, axes = plt.subplots(1, 3, figsize=(14, 4))
                for ax, col, title, color, marker in [
                    (axes[0], "irrigation_volume_l_m2", "Irrigação (L/m²)", "#005088", "o"),
                    (axes[1], "fertilizer_kg_ha", "Fertilizante (kg/ha)", "#11CAA0", "s"),
                    (axes[2], "yield_ton_ha", "Produtividade (ton/ha)", "#f59e0b", "^"),
                ]:
                    ax.plot(d["id_reading"], d[col], marker=marker, color=color, linewidth=2)
                    ax.set_title(title)
                    ax.set_xlabel("id_reading")
                    ax.grid(True, alpha=0.3)
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)

            with st.expander("🔍 Ver a consulta SQL (view history_view)"):
                st.code(
                    "SELECT\n"
                    "    r.id_reading, d.plantation_sector, d.sensor_model, r.reading_ts,\n"
                    "    r.temperature, r.ph, r.soil_humidity, r.n, r.p, r.k, r.pump,\n"
                    "    r.yield_ton_ha, r.irrigation_volume_l_m2, r.fertilizer_kg_ha,\n"
                    "    r.recommendation_irrigation, r.recommendation_fertilization,\n"
                    "    r.recommendation_yield\n"
                    "FROM sensor_readings r\n"
                    "INNER JOIN devices d ON r.id_device = d.id_device\n"
                    "ORDER BY r.id_reading DESC;",
                    language="sql",
                )
