# Ir Além — FarmTech Solutions (Fase 4 / CAP 1)

Os dois itens "Ir Além" foram **integrados ao projeto principal** (não há código
separado nesta pasta — apenas a documentação abaixo). Tudo roda com o mesmo
pipeline descrito no [README principal](../README.md).

---

## Ir Além 1 — Integração dos dados IoT com banco de dados (PostgreSQL)

Modelo relacional simples (capítulos de *Cognitive Data Science*) capaz de
armazenar os dados dos sensores (reais ou simulados no Wokwi) e as previsões da IA.

- **Schema:** [`src/schema.sql`](../src/schema.sql)
  - `devices` — nós IoT cadastrados (setor, modelo do sensor, data).
  - `sensor_readings` — leituras dos sensores + previsões (produtividade,
    irrigação, fertilizante) + recomendações em texto.
  - `history_view` — **VIEW com JOIN** entre leituras e dispositivos.
- **Infra:** [`docker-compose.yml`](../docker-compose.yml) sobe um `postgres:16`
  e aplica o schema automaticamente na primeira criação do volume.
- **Acesso:** [`src/database.py`](../src/database.py) (SQLAlchemy + psycopg2) —
  conecta, migra (idempotente), insere leituras e consulta o histórico.

```bash
cp .env.example .env
docker compose up -d
make db-test          # testa conexão + insere uma leitura de exemplo
```

Cada previsão feita no **Simulador** do dashboard é gravada automaticamente
nessa base, alimentando a aba de histórico.

---

## Ir Além 2 — Dashboard analítico com previsões (interativo e online)

Implementado em [`src/dashboard.py`](../src/dashboard.py) (Streamlit), com quatro abas:

1. **📍 Panorama** — KPIs do campo + **matriz de correlação** + produtividade por faixa.
2. **🤖 Desempenho dos Modelos** — métricas reais (MAE/MSE/RMSE/R²), comparação
   **Linear × Random Forest**, gráficos *Real × Previsto* e importância de atributos.
3. **🔮 Simulador de Manejo** — **resultados de previsão em tempo real** a partir
   das leituras simuladas, com recomendações automáticas de irrigação/fertilização.
4. **🗄️ Histórico (DB)** — **tendências de produtividade**, irrigação e fertilização
   ao longo das leituras persistidas no PostgreSQL.

```bash
make run              # http://localhost:8501
```
