# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/">
  <img src="../../../assets/logo-fiap.png"
       alt="FIAP - Faculdade de Informática e Administração Paulista"
       width="40%">
</a>
</p>

<br>

# FarmTech Solutions — Assistente Agrícola Inteligente (Fase 4)

## 👨‍🎓 Integrantes
- `Luis Felipe Bardi - RM569479`
- `Karina Queiroz de Gennaro - RM570928`
- `Beatriz de Oliveira Ossola Ribeiro - RM570190`

## 👩‍🏫 Professores
### Tutor(a)
- Sabrina Otoni
### Coordenador(a)
- André Godoi Chiovato

---

## 📜 Descrição

Protótipo de **Assistente Agrícola Inteligente** para a cultura da **soja**, que
aplica **aprendizado de máquina supervisionado (regressão)** sobre dados de
sensores (umidade, pH, temperatura, presença de N/P/K e estado da bomba) para
**prever** três variáveis críticas de manejo e **recomendar ações**:

| Alvo previsto | Uso na decisão |
|---|---|
| **Produtividade estimada (ton/ha)** | Estimativa de rendimento da safra (PARTE 1) |
| **Volume de irrigação (L/m²)** | Quanto irrigar agora (PARTE 2) |
| **Fertilizante recomendado (kg/ha)** | Quanto/quais nutrientes aplicar (PARTE 2) |

O resultado é apresentado em um **dashboard Streamlit** interativo (métricas,
correlações, previsões em tempo real e tendências) e cada previsão gerada é
**persistida em PostgreSQL** (Ir Além 1), formando o histórico do campo.

> **Agricultura Cognitiva:** sensores IoT → banco de dados → modelos de ML →
> recomendação automática de manejo.

---

## 🧠 Por que o dataset foi (re)modelado — decisão técnica importante

A base original do capítulo (preservada em `../legado_cap1_original/`) é uma
**grade fatorial completa**: todas as combinações de `n, p, k, ph, umidade,
temperatura` aparecem exatamente uma vez, **sem ruído**. Nessa construção as
variáveis são *independentes entre si* — a correlação entre `umidade` e qualquer
feature é ≈ 0,00 (confirmado na própria matriz de correlação da base original).

**Consequência:** qualquer regressão tentando prever `umidade` a partir das
demais colunas resulta em **R² negativo** (pior que prever a média), porque não
existe sinal a ser aprendido. Não é um problema do modelo, e sim da base.

**Solução adotada (honesta e reprodutível):** geramos um dataset
agronomicamente coerente (`src/generate_dataset.py`) em que os **alvos são funções
documentadas** das condições de solo/clima/nutrientes, somadas a **ruído
gaussiano**. Assim a regressão aprende uma superfície de resposta real e as
métricas (MAE, MSE, RMSE, R²) passam a ser **verdadeiras e interpretáveis**.

### Relações modeladas (resumo)
- **Produtividade** = `MAX_YIELD · f(umidade) · f(pH) · f(temperatura) · f(N,P,K) + ruído`,
  onde cada `f(·)` é uma resposta **gaussiana** centrada no ótimo agronômico da
  soja (umidade ≈ 65%, pH ≈ 6,4, temperatura ≈ 27 °C). É **fortemente não-linear**.
- **Volume de irrigação** = déficit de umidade + demanda evapotranspirativa
  (cresce com a temperatura; diminui se a bomba já está ligada) + ruído.
- **Fertilizante** = nutrientes ausentes (3 − N+P+K) + desvio de pH do ótimo + ruído.

Todas as constantes ficam em `src/config.py` e podem ser auditadas/ajustadas.

---

## 🤖 Pipeline de Machine Learning (Scikit-Learn)

`generate_dataset → eda → train → dashboard`

1. **Tratamento / engenharia de atributos:** features de sensores + `total_nutrients`
   (N+P+K) e `temp_ph_interaction` (temperatura × pH).
2. **Treino e validação:** split **80/20** (`train_test_split`, `random_state=42`),
   **sem vazamento de alvo**. Para cada alvo treina-se **Regressão Linear** (baseline)
   e **Random Forest** (não-linear); o melhor por R² vira o modelo de produção.
3. **Métricas reais** (conjunto de teste), salvas em `src/models/metrics.csv`:

| Alvo | Modelo | MAE | MSE | RMSE | R² |
|---|---|---|---|---|---|
| Produtividade (ton/ha) | Regressão Linear | 0,66 | 0,82 | 0,91 | **0,14** |
| Produtividade (ton/ha) | **Random Forest** | 0,22 | 0,08 | 0,28 | **0,92** |
| Irrigação (L/m²) | Regressão Linear | 0,79 | 0,97 | 0,99 | 0,86 |
| Irrigação (L/m²) | **Random Forest** | 0,31 | 0,15 | 0,39 | **0,98** |
| Fertilizante (kg/ha) | Regressão Linear | 10,83 | 168,75 | 12,99 | 0,81 |
| Fertilizante (kg/ha) | **Random Forest** | 4,14 | 27,07 | 5,20 | **0,97** |

> *Os valores acima são gerados pelo pipeline; rode `make pipeline` para reproduzi-los.*

**Interpretação:** a produtividade é fortemente não-linear → a Regressão Linear
falha (R² ≈ 0,14) e o Random Forest acerta (R² ≈ 0,92). Para irrigação e
fertilização o modelo linear já é razoável, mas o Random Forest continua melhor.

4. **Recomendações** (`src/recommendation.py`): regras em Python convertem as
   previsões em ações de irrigação, fertilização e leitura de produtividade.

---

## 📁 Estrutura de pastas

> Conforme o template FIAP, só existem as pastas **data**, **docs**, **src** e
> **Ir Além** (mais os arquivos de configuração na raiz).

```
CAP1/
├── README.md               # Este guia
├── requirements.txt        # Dependências
├── docker-compose.yml      # PostgreSQL (Ir Além 1)
├── .env.example            # Variáveis de ambiente (copie para .env)
├── Makefile                # Atalhos (make pipeline, make run, ...)
├── src/                    # Todo o código-fonte (Python + SQL)
│   ├── config.py           # Fonte única: features, alvos, ótimos, conexão DB
│   ├── generate_dataset.py # Geração do dataset sintético agronômico
│   ├── eda.py              # Análise exploratória + figuras
│   ├── train.py            # Treino/validação (Linear × Random Forest)
│   ├── recommendation.py   # Motor de recomendações de manejo
│   ├── database.py         # Camada de persistência PostgreSQL
│   ├── dashboard.py        # Dashboard Streamlit (entrypoint)
│   ├── schema.sql          # Schema relacional (tabelas + view + seed)
│   └── models/             # Modelos treinados (.pkl) + metrics.csv
├── data/                   # Dataset gerado (CSV)
├── docs/                   # Documentação
│   └── figures/            # Figuras (correlação, real×previsto, importâncias)
└── Ir Além/                # Documentação dos itens "Ir Além"
```

> A versão original do grupo foi preservada **fora** do entregável, em
> `FASE4/legado_cap1_original/` (não faz parte da estrutura acima).

---

## 🔧 Como executar

**Pré-requisitos:** Python 3.13, [uv](https://docs.astral.sh/uv/) e Docker.

```bash
# 1) Ambiente + dependências
make setup            # ou: uv venv --python 3.13 .venv && uv pip install -r requirements.txt

# 2) Pipeline de ML (gera dataset, EDA e treina os modelos)
make pipeline

# 3) Banco de dados PostgreSQL (Ir Além 1)
cp .env.example .env
make db-up            # docker compose up -d
make db-test          # testa conexão + insere uma leitura de exemplo

# 4) Dashboard
make run              # streamlit run src/dashboard.py  →  http://localhost:8501
```

> O dashboard funciona mesmo **sem** o banco (a IA roda offline); nesse caso
> apenas o histórico (aba "Histórico") fica indisponível.

---

## 🚀 Itens "Ir Além"

- **Ir Além 1 — Banco de dados (PostgreSQL):** modelo relacional em
  `src/schema.sql` (`devices`, `sensor_readings`, view `history_view` com JOIN).
  Sobe via `docker-compose.yml`; acesso em `src/database.py` (SQLAlchemy).
- **Ir Além 2 — Dashboard analítico interativo:** abas de **correlação**,
  **desempenho dos modelos**, **simulador de previsões em tempo real** e
  **tendências de produtividade** a partir do histórico do banco.

---

## 📎 Links e Observações

- **Vídeo (até 5 min):** `<[(https://www.youtube.com/watch?v=NwIQvVF_ASg)]>`
- **Decisões técnicas:** ver seção *"Por que o dataset foi (re)modelado"*.
- A versão original do grupo está preservada em `FASE4/legado_cap1_original/`.

## 🗃 Histórico de lançamentos

* 1.0.0 - 19/06/2026
    * Pipeline de ML reescrito com alvos aprendíveis e métricas reais.
    * Dashboard único (Streamlit) integrando PARTE 1, PARTE 2 e Ir Além.
    * Persistência migrada de SQLite para **PostgreSQL** (Ir Além 1).

---

## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/SabrinaOtoni/TEMPLATE-FIAP-GRAD-ON-IA">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">FIAP</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
