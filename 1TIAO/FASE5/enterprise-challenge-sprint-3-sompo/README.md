# Avaliação de Telemetria Fendt 314

**IA auditável para identificar exposição operacional contextual e apoiar
inspeções preventivas no seguro de máquinas agrícolas.**

> Grupo SEIVA · Enterprise Challenge FIAP × Sompo Seguros

---

## Sobre o projeto

Este projeto transforma telemetria observada de um trator **Fendt 314** em
evidência explicável para gestores de frota e especialistas de uma seguradora.
O objetivo não é prever uma quebra inexistente no dataset, mas responder a uma
pergunta defensável: **quando uma condição física sustentada também é rara para
o contexto operacional da máquina?**

O núcleo de IA combina três elementos:

- **K-Means** para separar três regimes operacionais;
- **Isolation Forest por regime** para medir raridade contextual;
- **regras físicas versionadas** para exigir relevância operacional.

Um alerta só é emitido quando há, simultaneamente, exposição física sustentada
e raridade dentro do regime atual. PostgreSQL, API FastAPI e dashboard React
demonstram esse modelo funcionando de ponta a ponta com replay causal de dados
reais.

> **Limite científico:** o resultado apoia prevenção e priorização de inspeções.
> Não representa diagnóstico de falha, previsão de dano ou sinistro, culpa, mau
> uso ou probabilidade de indenização.
> 
> Vídeo Demonstrativo do Projeto: [link](https://youtu.be/oCJZlmFzLKY)

## Valor entregue

| Para quem | Valor |
|---|---|
| **Especialista da seguradora** | priorizar inspeções usando episódios, explicações e proveniência rastreável |
| **Gestor da frota** | identificar exposição recorrente em 7, 15 e 30 dias e investigar a operação da máquina |
| **Equipe técnica** | executar um modelo congelado sobre dados persistidos, com contratos e testes reproduzíveis |

O sistema mantém a decisão humana no processo. O alerta indica onde investigar;
ele não conclui que houve dano ou conduta inadequada.

## Como funciona

```mermaid
flowchart LR
  DATA["Recorte observado<br/>Fendt 314 · 1 Hz"] --> PG1["PostgreSQL<br/>missões + amostras"]
  PG1 --> REPLAY["Replay causal<br/>janelas de 60 s"]
  REPLAY --> MODEL["Modelo híbrido<br/>regime + raridade + regra"]
  MODEL --> PG2["PostgreSQL<br/>decisão + explicação"]
  PG2 --> API["API FastAPI"]
  API --> UI["Dashboard React<br/>prioridade + inspeção"]

  classDef data fill:#EAF1F9,stroke:#2E74B5,color:#1F4D78,stroke-width:2px;
  classDef model fill:#DCECE2,stroke:#2E7D52,color:#1A2230,stroke-width:2px;
  classDef db fill:#D9E6F2,stroke:#1F4D78,color:#1A2230,stroke-width:2px;
  classDef output fill:#1F4D78,stroke:#1F4D78,color:#FFFFFF,stroke-width:2px;
  class DATA,REPLAY data;
  class MODEL model;
  class PG1,PG2 db;
  class API,UI output;
```

1. O recorte observado é importado para o PostgreSQL.
2. O replay lê apenas o banco e forma janelas causais de 60 segundos.
3. A API reconstrói e confere as 43 features antes de executar o modelo.
4. Alerta, regime, raridade, regras, explicação e versão são persistidos.
5. O dashboard apresenta episódios, scores longitudinais e casos de inspeção.

Não existe geração sintética no fluxo principal, e a demonstração não precisa
baixar o dataset original de aproximadamente 1 GB.

## Dados, modelo e evidência

| Item | Evidência atual |
|---|---|
| Fonte | dataset público Zenodo, DOI [`10.5281/zenodo.14619787`](https://doi.org/10.5281/zenodo.14619787) |
| Equipamento de referência | uma unidade física Fendt 314 |
| Licença dos dados | CC BY 4.0 |
| Demo incluída | 152.561 amostras observadas em 105 missões |
| Unidade de inferência | janela causal de 60 segundos com 43 features |
| Artefato executado | `fendt314-hybrid-v2.0.1` |
| Alerta híbrido | condição física sustentada **e** raridade contextual |
| Horizontes longitudinais | 7, 15 e 30 dias |

### Avaliação temporal

| Divisão | Finalidade | Janelas | Resultado |
|---|---|---:|---:|
| Treino | ajustar a referência | 7.317 | modelo e baselines aprendidos |
| Validação | selecionar pelos gates | 2.522 | 74 alertas (2,93%) |
| Teste posterior | avaliação final, aberta uma vez | 3.617 | 95 alertas (2,63%) |

Esses resultados medem estabilidade temporal sob critérios predefinidos. Eles
**não são acurácia, precision ou recall para dano**, pois o dataset não contém
rótulos de falha, manutenção, sinistro ou indenização.

## Executar a demonstração

### Pré-requisitos

- Docker com Docker Compose;
- Python 3.11 ou 3.12 com [`uv`](https://docs.astral.sh/uv/);
- Node.js 22 com npm;
- Make;
- portas `5432`, `8010` e `5174` disponíveis.

### Instalação e execução

```bash
git clone <URL-DO-REPOSITORIO>
cd challenge_sompo
uv sync --frozen
npm --prefix frontend ci
make demo-real
```

O repositório já contém o recorte observado e o bundle necessários. O Compose
inicia somente o PostgreSQL oficial; `scripts/demo_real.py` executa localmente
as migrations, a API, o replay e o frontend. Não há `Dockerfile` próprio para o
banco porque a imagem oficial `postgres:16` não precisa de customização.

### Replay real com dashboard

Acesse [`http://127.0.0.1:5174`](http://127.0.0.1:5174). O comando espera o
PostgreSQL ficar saudável, cria o banco isolado da demonstração e inicia os
processos locais:

```text
Compose: PostgreSQL
             ↓
demo_real.py: importação → API → replay observado
                         └────→ frontend
```

O replay lê as amostras do PostgreSQL e envia cada janela por HTTP para a API.
Ao terminar, API e frontend continuam disponíveis para exploração até
`Ctrl+C`. O resultado esperado é:

```text
Replay vivo concluído: 2522 janelas novas e 74 alertas.
```

Use `Ctrl+C` para encerrar API e frontend. Para parar também o PostgreSQL:

```bash
docker compose down
```

O Compose existe apenas para tornar o banco reproduzível. API, modelo, replay e
dashboard permanecem visíveis como processos locais, o que reduz a cerimônia e
facilita a leitura acadêmica do projeto.

## Testes

Testes sem PostgreSQL externo:

```bash
uv sync --frozen
uv run pytest
```

Suíte completa com banco isolado:

```bash
docker compose up -d --wait postgres
docker compose exec -T postgres createdb -U postgres tractor_usage_test

TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/tractor_usage_test" \
uv run pytest
```

Se o banco já existir, pule o `createdb`. Sem `TEST_DATABASE_URL`, a suíte
termina com `113 passed` e `1 skipped`. Com o banco de teste configurado como
acima, o resultado vigente é `116 passed`.

Frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## API e arquitetura

Durante a demo, o contrato OpenAPI fica disponível em
[`http://127.0.0.1:8010/docs`](http://127.0.0.1:8010/docs).

| Rota principal | Finalidade |
|---|---|
| `POST /v1/tractors/{id}/windows` | reconstruir, pontuar e persistir uma janela observada |
| `GET /v1/portfolio/inspection-priorities` | ordenar prioridades de inspeção |
| `GET /v1/tractors/{id}/overview` | consultar alertas, episódios e scores 7/15/30 |
| `POST /v1/tractors/{id}/inspection-cases` | abrir um caso persistido de inspeção |
| `GET /v1/demo/replay-progress` | acompanhar a demonstração atual |

O código usa uma *clean architecture* pragmática:

```text
compose.yaml           configura somente o PostgreSQL oficial
Makefile               inicia o banco e a demonstração local
scripts/demo_real.py   orquestra importação, API, replay e frontend
src/tractor_usage/
  application/       contratos, ports e casos de uso
  infrastructure/    PostgreSQL, modelo congelado, replay e HTTP
  modeling/          treinamento e avaliação científica
  streaming/         formação causal das janelas
api/                  adaptador FastAPI e composição
frontend/             dashboard React
```

Todos os processos escutam apenas em loopback (`127.0.0.1`). A API do MVP não
possui autenticação e não deve ser exposta diretamente na internet.

## Documentação técnica

- [Relatório acadêmico em Markdown](docs/FENDT314_SEIVA.md), com diagramas
  Mermaid para leitura direta no GitHub.
- [Relatório acadêmico em PDF](docs/FENDT314_SEIVA.pdf), versão diagramada
  para apresentação e entrega.
- [Model card](docs/modeling/fendt314-hybrid-v2-model-card.md), com método,
  avaliação, resultados e limitações.
- [Contract Path](docs/design/real-validation-demo/contract-path.md), com o
  comportamento ponta a ponta e critérios de aceitação.
- [Reconstrução do calendário](docs/data/fendt-314-calendar-reconstruction.md),
  com a recuperação temporal do dataset.
- [Proveniência do recorte](data/fendt314-validation/README.md), com fonte,
  licença e significado dos arquivos incluídos.

## Limitações e próximos passos

- A referência científica atual vem de uma única unidade Fendt 314.
- Não existem rótulos observados de dano, falha, manutenção ou sinistro.
- As regras físicas são hipóteses de engenharia, não diagnóstico do fabricante.
- Reproduzir o treinamento exige o dataset integral; executar o bundle e a demo
  não exige.
- Validação entre tratores, autenticação e infraestrutura cloud permanecem como
  próximos passos.

O escopo é deliberadamente honesto: demonstrar que um modelo de IA foi
construído, avaliado, congelado e integrado a dados persistidos, API e frontend
sem transformar raridade operacional em uma alegação de dano.

## Equipe

| Integrante | RM |
|---|---:|
| Karina Queiroz de Gennaro | 570928 |
| Luis Felipe Bardi | 569479 |
| Beatriz de Oliveira Ossola Ribeiro | 570190 |

**Instituição:** Faculdade de Informática e Administração Paulista (FIAP)  
**Parceiro corporativo:** Sompo Seguros
