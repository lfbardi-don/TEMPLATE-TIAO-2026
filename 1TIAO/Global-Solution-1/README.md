# Ephemnous

Ephemeris + Nous. Escalonador de IA para um data center em órbita baixa (LEO).

No espaço, a energia solar oscila. A cada ~95 min o satélite entra na sombra da Terra (o eclipse). O calor só sai por radiação, porque no vácuo não há convecção. O ephemnous prevê quanta energia e quanta folga térmica existirão nas próximas janelas e decide o que computar a cada instante: rodar trabalho pesado no sol, fazer checkpoint antes do eclipse e dar throttle para não superaquecer.

## Arquitetura

```
   Wokwi: ESP32 (no 0)  --WiFi HTTP POST /telemetry-->  FastAPI  -->  PostgreSQL
   pot = irradiancia/gatilho                            |  forecaster (sklearn) preve
   LED PWM = carga/throttle  <--comando na resposta-----|  MPC decide run/defer/checkpoint/throttle
                                                         |
                       frota simulada (N nos) + dataset de treino  -- MESMA fisica --   Dashboard (Streamlit)
```

A fisica orbital/termica fica so no backend Python (`ephemnous/core/physics.py`), compartilhada pela demo ao vivo, pela frota simulada e pela geracao de dados de treino. O ESP32 e um no fino: sente (pot) e atua (LED), mas nao calcula o ambiente, como um satelite real.

## Resultados

- Forecaster e ML de verdade. Skill vs persistencia inteligente 0.64-0.68 (energia) e 0.62-0.89 (folga termica). Skill vs efemeride pura 0.60-0.78. Preve a incerteza (apontamento), nao o eclipse deterministico. Sem leakage (features <= t, split por episodio, skill cai com o horizonte).
- Escalonador preditivo vs reativo (comparacao justa, mesmo codigo, lookahead 0): no regime energia-critico a IA conclui ~20-25% mais jobs e perde ~65-75% menos (delta score +3.3 a +4.9, IC 95% > 0 em 3 blocos de sementes). Com folga de bateria da empate, e isso esta reportado. Ver a curva de regime em `data/regime_curve.png`.
- RL / Deep Learning: avaliados e rejeitados com justificativa (politica otima simples; GBM no teto de Bayes). Trabalho futuro para filas combinatorias.

## Stack

FastAPI, PostgreSQL (Docker), scikit-learn, Streamlit, ESP32 simulado no Wokwi (Arduino C++), telemetria HTTP. Arquitetura limpa, sem DDD.

## Rodar

Pre-requisitos: Python 3.11+, Docker.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[ml,dashboard]'
cp .env.example .env

make up                                   # Postgres
make migrate                              # schema
OMP_NUM_THREADS=1 python scripts/train.py # treina o forecaster (+ metrics.json)

make api                                  # backend em :8000  (terminal 1)
make dash                                 # dashboard em :8501 (terminal 2)
make sim                                  # popula telemetria ao vivo (terminal 3)
```

Experimentos / artefatos:

```bash
OMP_NUM_THREADS=1 python scripts/compare_jobs.py        # ablacao 4 vias + IC pareado + curva de regime
OMP_NUM_THREADS=1 python scripts/compare_jobs.py plot   # gera data/regime_curve.png
OMP_NUM_THREADS=1 python scripts/demo.py                # narracao terminal (Plano B)
```

Wokwi: ver [wokwi/README.md](wokwi/README.md).

## Estrutura

```
ephemnous/
  core/       # entidades + regras puras (fisica, MPC, forecaster) - sem framework/IO
  services/   # orquestracao (laco de controle)
  infra/      # adapters: FastAPI (api.py), Postgres (db.py, repo.py), ML (ml_forecaster.py)
  ml/         # features.py, dataset.py (geracao + anti-leakage)
db/schema.sql # DDL do banco (fonte unica)
scripts/      # train.py, compare_jobs.py, run_node_sim.py, demo.py
dashboard/    # app.py (Streamlit), queries.py (read-only Postgres)
wokwi/        # diagram.json, wokwi.toml, firmware/firmware.ino
```
