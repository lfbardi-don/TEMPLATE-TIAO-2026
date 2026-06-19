# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/">
  <img src="../../../../assets/logo-fiap.png"
       alt="FIAP - Faculdade de Informática e Administração Paulista"
       width="40%">
</a>
</p>

<br>

# Da Terra ao Código — Classificação de Grãos de Trigo com Machine Learning (Fase 4 · Cap 3)

## 👨‍🎓 Integrantes
- `Luis Felipe Bardi - RM569479`
- `Karina Queiroz de Gennaro - RM570928`
- `Beatriz de Oliveira Ossola Ribeiro - RM570190`

## 👩‍🏫 Professores
### Tutor(a)
- `<preencher>`
### Coordenador(a)
- André Godoi Chiovato

---

## 📜 Descrição

Atividade **"Ir Além"** que automatiza a **classificação de variedades de grãos de
trigo** (**Kama**, **Rosa** e **Canadian**) a partir de suas características físicas,
aplicando a metodologia **CRISP-DM**.

Em cooperativas agrícolas de pequeno porte a triagem dos grãos é feita manualmente
por especialistas — um processo **lento e sujeito a erro humano**. Este projeto
mostra que um modelo de aprendizado de máquina classifica as três variedades com
**F1-macro de ~0,90–0,96** (validação cruzada), decidindo em milissegundos.

> **Entregável principal:** o notebook [`src/seeds_classification.ipynb`](src/seeds_classification.ipynb),
> que percorre todas as etapas do CRISP-DM. As figuras geradas ficam em
> [`docs/figures/`](docs/figures) e os artefatos do modelo em `src/models/`.

### Conjunto de dados
**Seeds Dataset** — [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/236/seeds):
210 amostras (70 por variedade), **7 atributos contínuos** medidos por imagem de
raios-X dos grãos, sem valores ausentes e perfeitamente balanceado.

| # | Atributo (código) | Atributo (pt) | Descrição |
|---|---|---|---|
| 1 | `area` | Área | Área *A* do grão |
| 2 | `perimeter` | Perímetro | Perímetro *P* do contorno |
| 3 | `compactness` | Compacidade | *C = 4·π·A / P²* |
| 4 | `kernel_length` | Comprimento do núcleo | Eixo principal da elipse equivalente |
| 5 | `kernel_width` | Largura do núcleo | Eixo secundário da elipse |
| 6 | `asymmetry` | Coef. de assimetria | Assimetria do grão |
| 7 | `groove_length` | Comprimento do sulco | Comprimento do sulco central |
| — | `variety` | Variedade | Classe: 1=Kama, 2=Rosa, 3=Canadian |

---

## 🧠 Metodologia (CRISP-DM)

1. **Entendimento do Negócio** — automatizar a triagem das variedades, reduzindo
   tempo e erro humano.
2. **Entendimento dos Dados** — estatísticas descritivas (média, mediana, desvio),
   histogramas, boxplots, matriz de correlação e matriz de dispersão; verificação de
   valores ausentes e balanceamento das classes.
3. **Preparação dos Dados** — sem imputação (não há ausentes); **padronização**
   (`StandardScaler`) encapsulada em `Pipeline` para evitar **vazamento de dados**;
   *split* **70/30 estratificado** (`random_state=42`).
4. **Modelagem** — **cinco** algoritmos: KNN, SVM, Random Forest, Naive Bayes e
   Regressão Logística.
5. **Avaliação** — acurácia, precisão, recall, F1 (macro) e matrizes de confusão,
   com **validação cruzada (5 folds)** como critério estável de comparação.
6. **Otimização** — **`GridSearchCV`** de hiperparâmetros e re-avaliação.
7. **Interpretação** — importância de atributos, PCA 2D, curva de aprendizado e
   recomendações para a cooperativa.

> **Convenção:** todo o **código está em inglês**; toda a **documentação e as
> figuras estão em português** (público-alvo brasileiro).

---

## 📊 Resultados

### Modelos com hiperparâmetros padrão (baseline) — conjunto de teste

| Modelo | Acurácia | Precisão | Recall | F1 (macro) | F1 CV (média ± desvio) |
|---|---|---|---|---|---|
| KNN | 0,873 | 0,872 | 0,873 | 0,871 | 0,918 ± 0,027 |
| SVM | 0,873 | 0,872 | 0,873 | 0,871 | 0,939 ± 0,040 |
| **Random Forest** | **0,921** | 0,924 | 0,921 | **0,919** | 0,903 ± 0,080 |
| Naive Bayes | 0,825 | 0,834 | 0,825 | 0,825 | 0,923 ± 0,048 |
| Regressão Logística | 0,857 | 0,857 | 0,857 | 0,854 | 0,945 ± 0,042 |

### Modelos otimizados (Grid Search) — conjunto de teste

| Modelo | Acurácia | F1 (macro) | **F1 CV (melhor)** | Melhores hiperparâmetros |
|---|---|---|---|---|
| KNN | 0,889 | 0,888 | 0,946 | `n_neighbors=3, p=1 (Manhattan), weights=uniform` |
| **SVM** | 0,857 | 0,854 | **0,959** | `C=10, gamma=scale, kernel=rbf` |
| Random Forest | 0,905 | 0,902 | 0,910 | `n_estimators=200, max_depth=4, max_features=sqrt, min_samples_leaf=1` |
| Naive Bayes | 0,825 | 0,825 | 0,923 | `var_smoothing=1e-09` |
| Regressão Logística | 0,889 | 0,888 | 0,951 | `C=10` |

> *Tabelas reproduzidas pelo pipeline e salvas em `src/models/metrics_baseline.csv`,*
> *`src/models/metrics_tuned.csv` e `src/models/best_params.json`. Rode `make pipeline`.*

### Modelo final escolhido: **SVM (kernel RBF)**

Selecionado pelo **maior F1-macro em validação cruzada (0,959)** — critério mais
**estável** que a acurácia em uma única partição de teste. No conjunto de teste
(63 amostras) atinge **acurácia 0,857 / F1-macro 0,854**, com **todos os erros
envolvendo a variedade Kama**.

| Variedade | Precisão | Recall | F1 | Suporte |
|---|---|---|---|---|
| Kama | 0,833 | 0,714 | 0,769 | 21 |
| Rosa | 0,864 | 0,905 | 0,884 | 21 |
| Canadian | 0,870 | 0,952 | 0,909 | 21 |

---

## 🔎 Interpretação e Insights

- **Onde estão os erros:** praticamente todos **envolvem a Kama**, a variedade de
  tamanho **intermediário**, confundida ora com a Rosa, ora com a Canadian.
  **Rosa e Canadian quase nunca são confundidas entre si** (zero erros mútuos em
  todos os modelos) — são os extremos de tamanho e ficam bem separadas.
- **Atributos mais discriminantes:** **comprimento do sulco**, **área** e
  **perímetro** (concordância entre a importância nativa da Random Forest e a
  importância por permutação do SVM). O **coeficiente de assimetria** e a
  **compacidade** contribuem pouco.
- **Separabilidade:** o PCA mostra que **2 componentes** retêm ~89% da variância e já
  separam as três variedades, com a Kama no centro encostando nas outras duas.
- **Por que o Grid Search ganha pouco:** o problema é simples e os modelos já chegam
  perto do teto com configurações padrão; o ganho é real, mas modesto. A acurácia na
  partição de teste pode até oscilar para baixo após a otimização, pois o Grid Search
  otimiza o desempenho **em validação cruzada** — e o teste de 63 amostras é ruidoso.

### Recomendações para a cooperativa
1. Adotar o **modelo otimizado** como triagem automática, com inspeção humana apenas
   nos casos de **baixa confiança** (fronteira da Kama).
2. **Padronizar a captura das medidas** (mesma calibração de imagem).
3. **Ampliar a base de Kama** para reforçar a fronteira mais difícil.
4. **Reavaliar o modelo periodicamente**, reusando o pipeline reprodutível.

---

## 📁 Estrutura de pastas

> Conforme o template FIAP, só existem as pastas **data**, **docs**, **src** e
> **Ir Além** (mais os arquivos de configuração na raiz).

```
CAP3/
├── README.md                       # Este guia
├── requirements.txt                # Dependências (uv)
├── Makefile                        # Atalhos (make setup, make pipeline, ...)
├── src/
│   ├── config.py                   # Fonte única: paths, features, classes, modelos + grids
│   ├── data.py                     # Loader robusto do arquivo UCI -> CSV limpo
│   ├── seeds_classification.ipynb  # ENTREGÁVEL PRINCIPAL — notebook CRISP-DM
│   └── models/                     # metrics_*.csv, best_params.json, model_best.pkl
├── data/
│   ├── seeds_dataset.txt           # Dataset bruto (UCI, separado por espaços)
│   └── seeds_clean.csv             # CSV limpo e rotulado (gerado por src/data.py)
├── docs/
│   └── figures/                    # Figuras exportadas pelo notebook
└── Ir Além/                        # Documentação das análises "Ir Além"
```

---

## 🔧 Como executar

**Pré-requisitos:** Python 3.13 e [uv](https://docs.astral.sh/uv/).

```bash
# 1) Ambiente + dependências
make setup            # ou: uv venv --python 3.13 .venv && uv pip install -r requirements.txt

# 2) Gerar o CSV limpo a partir do arquivo bruto do UCI
make data

# 3a) Explorar o notebook interativamente
make lab              # abre o JupyterLab em src/seeds_classification.ipynb

# 3b) OU executar o pipeline completo de forma reprodutível (sem abrir o navegador)
make pipeline         # gera o CSV e executa o notebook ponta a ponta
```

> `make pipeline` re-executa o notebook e regenera **todas** as métricas
> (`src/models/*.csv`), os hiperparâmetros (`best_params.json`), o modelo final
> (`model_best.pkl`) e as figuras (`docs/figures/*.png`). Tudo é determinístico
> (`random_state=42`).

---

## 🚀 Análises "Ir Além"

Além das quatro tarefas exigidas, o notebook inclui análises extras — documentadas em
[`Ir Além/README.md`](Ir%20Além/README.md): **validação cruzada de estabilidade**,
**importância por permutação** (agnóstica ao modelo), **projeção PCA 2D**,
**curva de aprendizado** e **persistência do modelo final** (`model_best.pkl`).

---

## 🗃 Histórico de lançamentos

* 1.0.0 - 19/06/2026
    * Pipeline de classificação CRISP-DM (5 algoritmos) com Grid Search.
    * Notebook único reprodutível + camada de dados isolada (`src/data.py`).
    * Métricas, hiperparâmetros e modelo final serializados em `src/models/`.

---

## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/SabrinaOtoni/TEMPLATE-FIAP-GRAD-ON-IA">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">FIAP</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
