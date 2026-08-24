# Contract Path: avaliação de telemetria do Fendt 314

Status: `IMPLEMENTED`

## Objetivo e limite científico

O projeto demonstra uma avaliação de telemetria construída a partir do histórico
observado de uma unidade Fendt 314 no dataset público Zenodo. A abordagem pode
receber telemetria de outras unidades Fendt 314 com o mesmo contrato, inclusive
em uma frota homogênea, mas comparação e generalização entre tratores exigem
novos dados e validação futura.

O artefato principal é o modelo congelado `fendt314-hybrid-v2.0.1`. PostgreSQL,
API e frontend demonstram que esse modelo foi colocado em funcionamento ponta a
ponta. O resultado representa exposição operacional contextual para prevenção;
não é diagnóstico nem probabilidade de dano, falha, mau uso ou sinistro.

## Entradas

- `data/fendt314-validation/fendt314-validation-observed.csv.gz`: recorte
  observado de validação com 152.561 amostras em 105 missões;
- DOI `10.5281/zenodo.14619787`, licença CC BY 4.0;
- `models/fendt314-hybrid-v2.0.1/bundle.joblib` e `manifest.json`;
- janela causal de inferência: 60 segundos.

Não existe entrada sintética no MVP.

## Caminho de criação do modelo

| Etapa | Arquivo e símbolo | Regra |
|---|---|---|
| divisão temporal | `experiments/selection.py::selection_splits()` | treino e validação selecionam; teste fica fechado |
| features | `features/schema.py::model_feature_columns()` | fecha as 43 variáveis e exclui identidade, regras físicas e leakage |
| regimes | `modeling/regimes.py::evaluate_regime_candidates()` | seleciona K-Means com três regimes |
| raridade | `modeling/hybrid.py::evaluate_hybrid_candidates()` | ajusta uma Isolation Forest por regime com limiar no quantil 0,97 do treino |
| alerta | `HybridUsageModel.score()` | exige regra física por pelo menos 5 s e raridade acima do limiar do regime |
| longitudinal | `modeling/longitudinal.py::fit_longitudinal_baseline()` | cria referências empíricas de 7, 15 e 30 dias somente com treino |
| experimento | `scripts/run_model_selection.py` | teste só pode ser aberto por autorização explícita |
| congelamento | `scripts/freeze_approved_bundle.py` | grava bundle e manifesto sem usar teste no ajuste |
| runtime | `modeling/artifact.py::load_frozen_bundle()` | valida versão, tamanho, hash, contrato e estado do artefato |

“Eficácia” significa aprovação nos critérios operacionais predefinidos e
generalização temporal no histórico estudado. Não significa acurácia para dano
ou sinistro, porque esses rótulos não existem no dataset.

## Execução local aprovada

O caminho público é `make demo-real`. O Compose possui uma única
responsabilidade: iniciar a imagem oficial `postgres:16`, com credenciais
locais, volume persistente, porta loopback e healthcheck. Não existe
`Dockerfile` próprio para o banco porque o projeto não customiza a imagem.

Depois que o PostgreSQL fica saudável, o Makefile executa
`uv run python scripts/demo_real.py` no host. O script valida dataset, bundle,
dependências e portas; recria somente `tractor_usage_demo_real`; aplica as
migrations; importa as amostras; inicia API e frontend; executa o replay pela
API; e verifica o resultado persistido. O progresso permanece em memória no
mesmo processo da demonstração.

| Parte | Execução | Responsabilidade | Estado final |
|---|---|---|---|
| PostgreSQL | `docker compose up -d --wait postgres` | persistir importação, amostras, decisões e casos no banco isolado | permanece saudável até `docker compose down` |
| Orquestrador | `scripts/demo_real.py` | validar, migrar, importar, iniciar processos e verificar o replay | permanece ativo após o replay |
| API | Uvicorn em `127.0.0.1:8010` | carregar o bundle e atender os contratos HTTP | encerra com `Ctrl+C` |
| Replay | chamada interna do orquestrador | ler o PostgreSQL e enviar cada janela uma vez à API | termina após a verificação integral |
| Frontend | Vite em `127.0.0.1:5174` | servir o dashboard e encaminhar `/api` para a API | encerra com `Ctrl+C` |

### Escopo exato de implementação

| Arquivo | Símbolo ou responsabilidade |
|---|---|
| `compose.yaml` | PostgreSQL oficial, healthcheck, porta loopback e `postgres_data` |
| `Makefile` | `demo-real` inicia o banco e chama o orquestrador local |
| `scripts/demo_real.py` | preflight, banco isolado, importação, API, frontend, replay e verificação |
| `README.md`, este Contract Path e `docs/FENDT314_SEIVA.md/.pdf` | pré-requisitos, comando, arquitetura e limites reproduzíveis |

Não há imagem customizada da aplicação nem mudança em algoritmo, bundle,
features, contratos de janela, schema PostgreSQL, regras físicas, idempotência
ou API pública.

## Caminho runtime

| Etapa | Arquivo e símbolo | Decisão ou efeito |
|---|---|---|
| comando | `Makefile::demo-real` | espera o PostgreSQL saudável e inicia a demonstração local |
| preflight | `scripts/demo_real.py::_preflight()` | verifica dataset, hashes, bundle, dependências e portas |
| isolamento | `_recreate_demo_database()` | recria somente `tractor_usage_demo_real` |
| cadastro | `_initialize_demo()` | cria uma frota demonstrativa com uma unidade Fendt 314 |
| importação | `ImportTelemetryUseCase.execute()` | persiste atomicamente importação, missões e amostras observadas |
| replay | `PostgresTelemetryReplay.iter_samples()` | lê do PostgreSQL em ordem causal; não reabre o CSV |
| janela | `CausalWindowAggregator.ingest()` | produz `READY` ou `NO_DATA` |
| transporte | `HttpWindowIngestClient.ingest()` | envia cada janela pronta por POST HTTP loopback, sem retry |
| reconstrução | `PostgresInspectionRepository.resolve_observed_window()` | reconstrói a janela a partir das amostras persistidas e confere integralmente a alegação HTTP |
| validação | `IngestWindowUseCase.execute()` | usa somente a janela autoritativa reconstruída, com idempotência e ordem |
| inferência | `FrozenBundleUsageModel.score()` | executa o bundle `v2.0.1` |
| persistência | `PostgresInspectionRepository.insert_window()` | grava janela, decisão e explicação na mesma transação |
| progresso | `InMemoryReplayProgress.observe()` | publica apenas recibos posteriores ao commit no processo da demonstração |
| consulta | `GetTractorOverviewUseCase.execute()` | agrega episódios e escores de 7, 15 e 30 dias |
| frontend | `DemonstrationDashboardPage` | distingue método, evidência experimental e resultado da execução atual |

## Contrato HTTP observado

`POST /v1/tractors/{tractor_id}/windows` aceita somente:

- `telemetry_import_id: UUID` obrigatório;
- `provenance.source_kind = observed_dataset_replay`;
- `provenance.dataset_split = train | validation`;
- `provenance.source_reference` não vazio.

A aplicação sempre confere trator, importação, missão, instante, split e origem
antes de pontuar. As 43 features, durações físicas e metadados enviados são uma
alegação do cliente: o servidor reconstrói a janela causal de 60 segundos a
partir de `telemetry_samples`, compara o conteúdo completo e usa somente o
objeto autoritativo reconstruído na inferência e na persistência. Divergência de
qualquer valor retorna `409`; payload estruturalmente inválido retorna `422`;
criação retorna `201`; repetição idêntica, `200`.

A identidade de uma missão no histórico inclui `telemetry_import_id`, além de
trator e `mission_index`. Assim, imports observados distintos podem reutilizar
índices locais de missão sem colidir.

A migration `0003_observed_only_window_lineage.py` não apaga nem converte dados.
Como versões anteriores não provavam o conteúdo integral contra as amostras,
ela falha explicitamente se encontrar qualquer janela já pontuada e orienta
recriá-la por replay. Em banco vazio, torna `telemetry_import_id` obrigatório e
restringe a proveniência.

## Transações e operação

- importação: uma transação por arquivo;
- inferência: uma transação por janela;
- ordem: timestamp crescente e índice crescente dentro da missão;
- concorrência: lock do trator por `SELECT ... FOR UPDATE`;
- idempotência: identidade da janela e fingerprint do conteúdo;
- retry e paralelismo do replay: nenhum;
- correlação: `telemetry_import_id`, `tractor_id` e `idempotency_key`;
- recuperação: interromper e executar `make demo-real` novamente; o script
  recria somente o banco demo;
- exposição: PostgreSQL, API e frontend escutam apenas em loopback;
- estado de progresso: memória do processo para apresentação; PostgreSQL
  continua sendo a única autoridade das decisões.

## Escopo da simplificação

Remover código desconectado ou redundante de detecção, replay direto,
atualização histórica, testes exclusivos e documentação substituída. O único
caminho de execução permanece importação observada → PostgreSQL → API → bundle
congelado → consulta.

Manter seleção, congelamento, auditoria de equivalência, demonstração
longitudinal, importação, replay pela API, frota, prioridades, detalhe,
telemetria persistida e casos de inspeção. Essas funcionalidades estão ativas;
não são código morto.

O README será a entrada curta. Uma única model card explicará dataset, 43
features agrupadas, regras físicas, métodos, divisão temporal, resultados,
integridade e limitações. Este arquivo será o único Contract Path ativo.

## Frontend

- a raiz apresenta a história
  `telemetria → 60 s → regime → raridade + regra física → alerta → 7/15/30`;
- diferencia resultados congelados do experimento dos resultados gerados na
  execução atual;
- declara que a referência vem de uma unidade Fendt 314;
- não chama alerta de falha, dano ou sinistro;
- mostra erro de atualização mesmo quando existe um valor anterior;
- cadastro não oferece reutilizar o mesmo trace para vários tratores e informa
  que cada nova unidade exige telemetria observada própria.

## Testes e aceitação

```bash
uv run pytest
uv run python -m compileall scripts src tests
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
docker compose up -d --wait postgres
uv run python scripts/demo_real.py --exit-after-replay --no-browser --window-delay-ms 0
docker compose config --quiet
```

Aceitação:

- nenhuma janela pode contornar a importação observada;
- toda decisão deve derivar de uma janela reconstruída das amostras no PostgreSQL;
- alterar qualquer feature alegada pelo cliente deve resultar em `409` sem pontuação;
- nenhuma API aceita origem diferente de replay observado;
- o bundle vigente é executado e suas decisões são persistidas;
- o frontend explica método, referência de uma unidade e limites;
- o cadastro não sugere clonar a mesma telemetria;
- não existem caminhos runtime/documentais concorrentes;
- todos os gates passam e a demonstração integral continua funcional;
- em clone limpo, Docker Compose, Python/`uv`, Node.js/npm e Make são os únicos
  pré-requisitos;
- o replay termina com verificação integral, enquanto API e frontend permanecem
  disponíveis até `Ctrl+C`;
- o progresso em memória não persiste resultados fora do PostgreSQL.

## Evidência da implementação

Verificado em 24/08/2026:

- Compose: configuração válida e somente o serviço `postgres` presente;
- Python sem banco de teste: `113 passed`, `1 skipped` por ausência de
  `TEST_DATABASE_URL`; com PostgreSQL isolado: `116 passed`; ambas as execuções
  emitiram apenas a advertência de depreciação do TestClient;
- frontend: `25 passed`, lint, typecheck e build aprovados;
- replay real: 152.561 amostras, 105 missões, 2.522 janelas novas e 74 alertas;
- PostgreSQL: as mesmas quatro contagens confirmadas diretamente no banco
  `tractor_usage_demo_real`;
- API e frontend encerraram após a validação, enquanto somente o PostgreSQL
  permaneceu saudável no Compose.

## Aprovação

Aprovado pelo usuário em 23/08/2026. A direção aprovada é: uma avaliação
acadêmica baseada nos dados observados de uma unidade Fendt 314, com o modelo
como núcleo e PostgreSQL, API e frontend como demonstração clara e concisa.

Não fazem parte desta limpeza: alteração do algoritmo ou do bundle, nova
calibração, autenticação, AWS, J1939 ao vivo, novos dados ou validação entre
tratores.

Em 24/08/2026, após avaliar a containerização completa, o usuário congelou a
alternativa mais simples: Compose somente para PostgreSQL e API, replay e
frontend executados localmente por `make demo-real`. A decisão evita imagens
customizadas sem necessidade e mantém visível a integração acadêmica do modelo.
