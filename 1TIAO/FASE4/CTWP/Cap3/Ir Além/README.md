# Ir Além — Classificação de Grãos (Fase 4 / CAP 3)

As análises "Ir Além" foram **integradas ao notebook principal**
([`src/seeds_classification.ipynb`](../src/seeds_classification.ipynb)) — não há
código separado nesta pasta, apenas a documentação abaixo. Tudo é regenerado com
`make pipeline`.

Elas vão **além das quatro tarefas exigidas** (EDA, comparação de modelos,
otimização e interpretação), elevando o rigor metodológico e a leitura de negócio.

---

## Ir Além 1 — Validação cruzada como critério de seleção

O conjunto de teste tem apenas **63 amostras**, então a métrica em uma única
partição é **ruidosa** (cada amostra vale ~1,6 p.p. de acurácia). Por isso o projeto
usa **validação cruzada estratificada (5 folds)** sobre o treino como critério
**principal** de comparação e de escolha do modelo final.

- **Boxplot de estabilidade** (`docs/figures/cv_stability.png`): mostra a dispersão
  do F1-macro por *fold*, revelando modelos bons **e** estáveis (caixa alta e estreita).
- **Seleção do modelo final** pelo maior **F1-macro em validação cruzada**, não pela
  acurácia de teste — decisão metodologicamente mais defensável.

## Ir Além 2 — Importância por permutação (agnóstica ao modelo)

O modelo final (**SVM com kernel RBF**) não expõe `feature_importances_`. Para
interpretá-lo mesmo assim, usamos **`permutation_importance`** sobre o conjunto de
teste: embaralha-se cada atributo e mede-se a **queda no F1-macro**.

- Figura: `docs/figures/feature_importance.png` (lado a lado com a importância nativa
  da Random Forest).
- Resultado: ambas as visões concordam — **comprimento do sulco**, **área** e
  **perímetro** são os atributos mais informativos.

## Ir Além 3 — Projeção PCA 2D (visualização da separabilidade)

Projeção dos dados padronizados em 2 componentes principais
(`docs/figures/pca_2d.png`): **~89% da variância** em 2 eixos, evidenciando os três
agrupamentos e a posição **intermediária da Kama** — a origem geométrica dos erros.

## Ir Além 4 — Curva de aprendizado

`docs/figures/learning_curve.png`: compara o desempenho em treino e validação à
medida que o tamanho do treino cresce, indicando se **coletar mais grãos** traria
ganho marginal — informação útil para a cooperativa priorizar a coleta de dados.

## Ir Além 5 — Persistência do modelo final

O modelo final é serializado em `src/models/model_best.pkl` (via `joblib`), junto dos
seus metadados (nome, atributos, hiperparâmetros e mapa de classes). Isso permite
**reusar o classificador** em um serviço/dashboard futuro sem re-treinar.

```python
import joblib
bundle = joblib.load("src/models/model_best.pkl")
model = bundle["model"]                 # Pipeline(StandardScaler + SVM) já treinado
model.predict(X_novos_graos)            # -> 1 (Kama) / 2 (Rosa) / 3 (Canadian)
```

---

> **Reprodutibilidade:** todas as figuras e artefatos acima são regenerados de forma
> determinística (`random_state=42`) ao rodar `make pipeline` a partir da raiz do CAP3.
