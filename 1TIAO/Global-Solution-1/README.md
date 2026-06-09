# ephemnous

Escalonador preditivo para um data center em órbita baixa (LEO), usando telemetria de um nó de borda ESP32, simulação física orbital/térmica, aprendizado de máquina e um controlador que decide quando executar, adiar, reduzir carga ou fazer checkpoint.

## Proposta

No espaço, a energia solar não é constante: em órbita baixa, o satélite entra na sombra da Terra a cada aproximadamente 95 minutos. Ao mesmo tempo, o calor gerado pela computação só pode sair por radiação, porque no vácuo não há convecção.

O ephemnous resolve esse problema como um laço fechado:

1. O nó de borda envia telemetria para o backend.
2. O backend atualiza o estado físico do satélite simulado.
3. Um modelo de ML prevê energia disponível e folga térmica nos próximos passos.
4. O controlador decide a ação: `run`, `defer`, `checkpoint` ou `throttle`.
5. O comando volta para o nó, que aplica a carga via PWM no LED.

A ideia central não é "usar IA por usar". A previsão só agrega valor quando o erro é caro: no regime energia-crítico, a IA conclui cerca de 20% a 25% mais jobs e perde 65% a 75% menos jobs do que uma política reativa. Quando a bateria está folgada, o resultado empata, e isso é reportado no relatório.

## Integrantes

- Karina Queiroz de Gennaro - RM570928
- Luis Felipe Bardi - RM569479
- Beatriz de Oliveira Ossola Ribeiro - RM570190

## Links

- Vídeo de demonstração: <https://www.youtube.com/watch?v=GAs3oIsI3PU>
- Repositório: <https://github.com/lfbardi-don/TEMPLATE-TIAO-2026/tree/main/1TIAO/Global-Solution-1>
- Relatório final: [`report/relatorio.pdf`](report/relatorio.pdf)

## Como a solução funciona

```text
ESP32/Wokwi
  potenciômetro + botão
  POST /telemetry
       |
       v
FastAPI
  atualiza física orbital/térmica
  consulta forecaster de ML
  roda controlador MPC
       |
       v
PostgreSQL + Dashboard
  telemetria, previsões, decisões e estados
```

O ESP32 simulado no Wokwi é propositalmente simples: ele lê sensores, envia telemetria e aplica o comando recebido no LED. A física, a previsão e a decisão ficam no backend Python, para evitar duplicar regra entre firmware e servidor.

Componentes principais:

- `POST /telemetry`: recebe telemetria do nó e devolve a decisão do controlador.
- `GET /healthz`: verifica se a API e o banco estão disponíveis.
- `POST /admin/inject_eclipse`: força eclipse em uma demo sem depender do Wokwi.
- Dashboard Streamlit: mostra telemetria, previsões e decisões em tempo quase real.
- Scripts de simulação: treinam o modelo, rodam comparativos e populam o banco.

## Tecnologias utilizadas

- Python 3.11+
- FastAPI
- PostgreSQL 16 via Docker Compose
- scikit-learn (`HistGradientBoostingRegressor`)
- Streamlit e Plotly
- ESP32 simulado no Wokwi
- Arduino C++ no firmware
- LaTeX/Tectonic para o relatório

## Execução básica

Pré-requisitos:

- Python 3.11 ou superior
- Docker
- Make

Instale as dependências:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[ml,dashboard]'
cp .env.example .env
```

Suba o banco e aplique o schema:

```bash
make up
make migrate
```

Treine o forecaster:

```bash
OMP_NUM_THREADS=1 python scripts/train.py
```

Rode a API, o dashboard e a simulação em três terminais:

```bash
make api
```

```bash
make dash
```

```bash
make sim
```

Depois disso:

- API: <http://localhost:8000/healthz>
- Dashboard: <http://localhost:8501>

## Experimentos e validação

```bash
OMP_NUM_THREADS=1 python scripts/compare_jobs.py
OMP_NUM_THREADS=1 python scripts/compare_jobs.py plot
OMP_NUM_THREADS=1 python scripts/demo.py
```

Esses comandos executam a comparação entre a política preditiva e a política reativa, geram a curva de regime em `data/regime_curve.png` e oferecem uma demonstração textual para apresentação.

## Wokwi

Os arquivos do nó de borda estão em `wokwi/`.

- `wokwi/diagram.json`: circuito do ESP32.
- `wokwi/firmware/firmware.ino`: firmware Arduino.
- `wokwi/wokwi.toml`: configuração local da simulação.
- `wokwi/README.md`: instruções detalhadas para rodar no Wokwi.

Na demo, o potenciômetro altera a irradiância e o botão força eclipse. O backend responde com uma decisão, e o LED representa a carga de computação aplicada pelo controlador.

## Organização dos arquivos

```text
.
├── dashboard/              # Dashboard Streamlit e consultas read-only
├── data/                   # Artefatos de resultado, como a curva de regime
├── db/                     # Schema SQL do PostgreSQL
├── ephemnous/
│   ├── core/               # Modelos de domínio, física, forecaster e MPC
│   ├── infra/              # FastAPI, banco, repositório e adaptador de ML
│   ├── ml/                 # Dataset, features e modelos treinados
│   └── services/           # Orquestração do laço de controle
├── report/                 # Relatório final em LaTeX e PDF
├── scripts/                # Treino, simulação, migração e comparativos
├── wokwi/                  # Simulação ESP32 e firmware
├── docker-compose.yml      # PostgreSQL local
├── Makefile                # Comandos principais do projeto
└── pyproject.toml          # Dependências Python
```

Arquivos locais como `.env`, `.venv/`, `__pycache__/`, `.DS_Store` e `*.egg-info/` não fazem parte da entrega versionada.
