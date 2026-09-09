# FarmTech Solutions — Fase 5, Capítulo 1

Este projeto analisa dados de quatro culturas agrícolas para investigar a relação
entre condições climáticas e rendimento da safra. O trabalho compara cinco modelos
de regressão e utiliza técnicas de clusterização para identificar grupos de cenários
climáticos e observações atípicas (outliers).

## Integrantes

- Luis Felipe Bardi — RM569479
- Karina Queiroz de Gennaro — RM570928
- Beatriz de Oliveira Ossola Ribeiro — RM570190

## Entregas

- **Entrega 1 — Machine Learning:** análise de rendimento agrícola no notebook abaixo.
- **[Entrega 2 — Computação em nuvem (AWS)](docs/entrega2_aws.md):** comparação entre
  São Paulo e Virgínia do Norte, com estimativa, gráfico e justificativa da região.

## Ir Além

O [projeto de telemetria com ESP32 e Wi-Fi](Ir%20Al%C3%A9m/README.md) reúne o firmware,
o receptor MQTT, o banco SQLite e o dashboard.

## Notebook da Entrega 1

Abra o **[notebook executado](src/LuisFelipeBardi_rm569479_pbl_fase4.ipynb)**.
Ele contém o código comentado, gráficos, resultados, decisões metodológicas e
conclusões. O sufixo `pbl_fase4.ipynb` segue o nome solicitado no enunciado da Fase 5.

## Dados

A base [crop_yield.csv](data/crop_yield.csv) contém 156 registros, quatro culturas e
39 cenários climáticos distintos. O arquivo foi preservado como recebido.

## Metodologia

A análise explora a distribuição dos dados e utiliza K-Means e DBSCAN para agrupar
cenários climáticos e identificar observações atípicas.

Para prever o rendimento, são comparados Regressão Linear, KNN, SVR, Árvore de Decisão
e Random Forest. A separação entre treino e teste e a validação cruzada mantêm juntos
os registros de cada cenário climático, evitando que o mesmo cenário apareça nos dois
lados da avaliação. A média de rendimento por cultura, calculada no treino, serve
como referência para comparar os modelos.

## Principais resultados

Random Forest apresentou o menor erro na validação cruzada e foi selecionado por
esse critério. No teste, porém, seu RMSE foi de **10.001,66**, acima dos **9.244,69**
da referência baseada na média por cultura. Assim, o modelo selecionado não superou
essa referência em cenários climáticos reservados para teste.

KNN obteve o menor RMSE no teste (**7.781,54**), mas esse resultado não foi usado
para alterar a seleção feita na validação cruzada. As métricas completas estão no
notebook e em [docs/results/](docs/results/).

## Limitações dos dados

O enunciado informa rendimento em t/ha, mas a escala dos valores de `Yield` precisa
ser confirmada na fonte. Por isso, os resultados permanecem na escala original do
CSV, sem conversão para toneladas. A unidade e o período de agregação da precipitação
também precisam de confirmação para uma interpretação física dos resultados.

## Executar

Ambiente validado com Python 3.13.11. Na pasta deste README:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m jupyter lab src/LuisFelipeBardi_rm569479_pbl_fase4.ipynb
```

No Jupyter, selecione **Python 3 (ipykernel)** e **Restart Kernel and Run All Cells**.
Não há dependência de credenciais, downloads ou caminhos pessoais no notebook.
Mantenha `src/` e `data/` na mesma estrutura ao clonar ou baixar o repositório.

Para executar todas as células pelo terminal e salvar as saídas no próprio arquivo:

```bash
python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=240 \
  src/LuisFelipeBardi_rm569479_pbl_fase4.ipynb
```

## Arquivos

```text
Cap1/
├── README.md
├── requirements.txt
├── .gitignore
├── Ir Além/                    # Telemetria com ESP32, MQTT e dashboard
├── data/crop_yield.csv
├── src/LuisFelipeBardi_rm569479_pbl_fase4.ipynb
└── docs/
    ├── entrega2_aws.md          # Comparação de regiões AWS
    ├── aws_estimate.png         # Evidência da calculadora
    ├── roteiro_video.md
    ├── figures/                 # Gráficos do notebook e da comparação AWS
    └── results/                 # Métricas, previsões, clusters e outliers em CSV
```

## Publicação da entrega

- **[Vídeo da Entrega 1 — Machine Learning](https://youtu.be/fjhWUvlUb_M):**
  demonstração da análise e dos resultados do notebook.
- **[Vídeo da Entrega 2 — AWS](https://www.youtube.com/watch?v=CHrZ8GJ93vY):**
  demonstração da comparação de custos.
- **[Roteiro da Entrega 1](docs/roteiro_video.md):** sequência prevista de 4min40s.

Antes de enviar, confira o acesso público ao repositório, a visualização do notebook
com saídas e o acesso ao vídeo por link. Conforme o enunciado, o grupo não deve fazer
novos commits após a data da entrega.
