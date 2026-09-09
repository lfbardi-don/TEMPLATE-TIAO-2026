import streamlit as st
import sqlite3
import pandas as pd
import time
import os


# Configuração da página do Dashboard
st.set_page_config(
    page_title="FarmTech Solutions - Dashboard IoT",
    page_icon="🌱",
    layout="wide"
)

DB_NAME = "farmtech.db"

# Cabeçalho Principal
st.title("🌱 FarmTech Solutions - Monitoramento Agrícola")
st.markdown("Painel avançado de telemetria em tempo real integrando **ESP32**, **MQTT**, **SQLite** e **Streamlit**.")
st.markdown("---")

# Função para carregar os dados do SQLite 
def carregar_dados():
    if sqlite3.connect(DB_NAME):
        try:
            conn = sqlite3.connect(DB_NAME)
            df = pd.read_sql_query("SELECT timestamp, topico, valor FROM leituras ORDER BY id ASC", conn)
            conn.close()
            return df
        except Exception as e:
            st.error(f"Erro ao ler o banco de dados: {e}")
            return pd.DataFrame(columns=["timestamp", "topico", "valor"])
    return pd.DataFrame(columns=["timestamp", "topico", "valor"])

# Carrega os dados
df_dados = carregar_dados()

# Barra lateral para controles
st.sidebar.header("⚙️ Configurações do Painel")
auto_refresh = st.sidebar.checkbox("🔄 Auto-atualizar a cada 5s", value=False)
st.sidebar.markdown("---")
st.sidebar.info("Projeto desenvolvido para automação e monitoramento agrícola de alta precisão.")

if not df_dados.empty:
    # Separação por tópicos
    df_temp = df_dados[df_dados["topico"] == "farmtech/solutions/temperatura"].copy()
    df_umid = df_dados[df_dados["topico"] == "farmtech/solutions/umidade"].copy()
    df_chuva = df_dados[df_dados["topico"] == "farmtech/solutions/chuva"].copy()

    # Últimos valores capturados
    ultima_temp = float(df_temp["valor"].iloc[-1]) if not df_temp.empty else 0.0
    ultima_umid = float(df_umid["valor"].iloc[-1]) if not df_umid.empty else 0.0
    ultimo_chuva = df_chuva["valor"].iloc[-1] if not df_chuva.empty else "0"

    # Seção de Métricas em Cartões (KPIs)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="🌡️ Temperatura do Ar (2m)", value=f"{ultima_temp:.2f} °C", delta=f"{ultima_temp - 25:.1f} °C ref. ideal")
    with col2:
        st.metric(label="💧 Umidade Relativa (2m)", value=f"{ultima_umid:.2f} %")
    with col3:
        status_chuva_txt = "DETECTADA 🌧️" if str(ultimo_chuva).strip() != "0" else "Sem Chuva ☀️"
        st.metric(label="☔ Status de Precipitação", value=status_chuva_txt)

    st.markdown("---")

    # Seção de Gráficos 
    st.subheader("📈 Histórico de Telemetria dos Sensores")
    
    aba1, aba2 = st.tabs(["📊 Gráfico de Temperatura", "💧 Gráfico de Umidade"])
    
    with aba1:
        if not df_temp.empty:
            df_temp["timestamp"] = pd.to_datetime(df_temp["timestamp"])
            df_temp["valor"] = df_temp["valor"].astype(float)
            df_chart_temp = df_temp.set_index("timestamp")[["valor"]]
            st.line_chart(df_chart_temp, color="#FF4B4B")
        else:
            st.info("Aguardando dados de temperatura...")

    with aba2:
        if not df_umid.empty:
            df_umid["timestamp"] = pd.to_datetime(df_umid["timestamp"])
            df_umid["valor"] = df_umid["valor"].astype(float)
            df_chart_umid = df_umid.set_index("timestamp")[["valor"]]
            st.line_chart(df_chart_umid, color="#0068C9")
        else:
            st.info("Aguardando dados de umidade...")

    # Seção com Tabela de Dados Brutos Recentes
    st.markdown("---")
    st.subheader("📋 Registros Recentes no Banco de Dados (SQLite)")
    st.dataframe(df_dados.tail(10).iloc[::-1], use_container_width=True)

else:
    st.warning("⚠️ O banco de dados `farmtech.db` está vazio ou aguardando o receptor MQTT.")

# Botão manual de atualização
if st.button("🔄 Atualizar Dados Agora"):
    st.rerun()

# Lógica de auto-refresh se habilitada na barra lateral
if auto_refresh:
    time.sleep(5)
    st.rerun()