# SEIVA — Inspeção preventiva Fendt 314

**Da telemetria à vistoria: selecionar trechos, consultar evidências e registrar
os achados de uma inspeção preventiva.**

> Grupo SEIVA · Enterprise Challenge FIAP × Sompo Seguros

**Fase 6 · Sprint 4.** Continuação do projeto da
[Sprint 3, preservada na Fase 5](../../FASE5/enterprise-challenge-sprint-3-sompo/README.md).

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

- [Vídeo demonstrativo no YouTube](https://youtu.be/ZLmSHQjQImI)

> **Limite científico:** o resultado apoia prevenção e priorização de inspeções.
> Não representa diagnóstico de falha, previsão de dano ou sinistro, culpa, mau
> uso ou probabilidade de indenização.


## Valor entregue

| Para quem | Valor |
|---|---|
| **Especialista da seguradora** | cadastrar máquinas, importar dados, comparar medidas com a referência e decidir se abre uma vistoria |
| **Vistoriador** | consultar a evidência de cada componente, salvar achados e concluir a vistoria |
| **Gestor da frota** | acompanhar a exposição semana a semana e conversar com o operador sobre trechos concretos |
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
  API --> UI["Dashboard React<br/>máquina + episódio + vistoria"]

  classDef data fill:#EAF1F9,stroke:#2E74B5,color:#1F4D78,stroke-width:2px;
  classDef model fill:#DCECE2,stroke:#2E7D52,color:#1A2230,stroke-width:2px;
  classDef db fill:#D9E6F2,stroke:#1F4D78,color:#1A2230,stroke-width:2px;
  classDef output fill:#1F4D78,stroke:#1F4D78,color:#FFFFFF,stroke-width:2px;
  class DATA,REPLAY data;
  class MODEL model;
  class PG1,PG2 db;
  class API,UI output;
```

1. O especialista seleciona ou cadastra uma frota e uma máquina.
2. Importa um CSV, confere a prévia e confirma o processamento. O replay observado
   incluído continua disponível pelo comando de demonstração.
3. O servidor valida as amostras, forma janelas causais e executa o bundle treinado.
4. A máquina apresenta gráficos, episódios, cobertura e três medidas comparadas
   com a referência Fendt 314 do modelo.
5. O especialista abre uma vistoria com a evidência nova. O vistoriador consulta
   os gráficos, salva achados e conclui com um resultado.
6. A próxima importação atualiza a análise. A conclusão anterior e sua evidência
   permanecem preservadas, e os novos episódios ficam identificados.

Importar dados **não treina novamente o modelo**. Os contratos estão na seção
[API e arquitetura](#api-e-arquitetura).

## O que a aplicação mostra

| Tela | Uso |
|---|---|
| **Máquinas** (`/`) | Escolher frota e máquina; cadastrar como especialista; ver origem e última importação. |
| **Máquina** (`/tratores/{id}`) | Comparar três medidas com a referência, explorar semanas e episódios por condição e acompanhar a situação da vistoria. |
| **Telemetria** (`/tratores/{id}/telemetria`) | Explorar gráficos dos dados importados, escolhendo missão. A visão geral usa amostragem; os episódios preservam 1 Hz. |
| **Importações** (`/tratores/{id}/importacoes`) | Consultar arquivos, origem e períodos processados; o especialista pode enviar outro CSV. |
| **Episódio** | Consultar sinais a 1 Hz, limites físicos e pistas de contexto. A partir da vistoria, usa a data congelada do caso. |
| **Vistorias** (`/vistorias`) | Encontrar casos abertos, em andamento e concluídos; trabalhar no checklist com a evidência ao lado. |
| **Administração** (`/admin`) | Gerenciar contas e consultar históricos de alterações. |

Origem e períodos ficam nas importações da máquina; cobertura aparece na análise,
e os sinais ficam em Telemetria e nos episódios. Método e validação permanecem na
documentação técnica. O histórico de quem fez cada ação é exclusivo do administrador.

A pauta `inspection-checklist-v1` associa condições a componentes e permanece
uma hipótese de engenharia a confirmar em campo. Cada item concluído recebe um
achado: sem anomalia, atenção, problema ou não verificado. Atenção e problema
exigem nota. O vistoriador pode salvar os achados parciais; conclusão e resultado
são a etapa final. O responsável é opcional e vem dos vistoriadores ativos.

### Demonstrar novas frotas com CSVs simulados

A interface oferece quatro CSVs reproduzíveis para duas frotas e três máquinas:

| Arquivo | Máquina | Etapa |
|---|---|---|
| `aurora-01-simulado.csv` | Aurora 01 | operação regular e gráficos |
| `aurora-02-simulado.csv` | Aurora 02 | carga variável, episódios e abertura de vistoria |
| `horizonte-01-inicial-simulado.csv` | Horizonte 01 | primeira vistoria com achados de teste |
| `horizonte-01-novo-periodo-simulado.csv` | Horizonte 01 | novos episódios após a conclusão |

Os arquivos contêm sensores, não escores ou alertas prontos. O modelo congelado
processa todos eles. As máquinas, a evidência e os casos mantêm a marcação
**Dados simulados**, com comparação demonstrativa à referência Fendt 314. Os
achados simulados não validam a precisão do modelo.

Os CSVs operacionais reais são aceitos somente na unidade que já tem a origem
observada da referência. Uma nova unidade real exige validação de identidade,
sinais e referência antes de habilitar a interpretação; outro modelo de trator
continua fora do escopo. Períodos simulados e reais usam máquinas separadas.

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

## Executar localmente

### Pré-requisitos e instalação

- Docker com Docker Compose para a instalação padrão do PostgreSQL;
- Python 3.11 ou 3.12 com [`uv`](https://docs.astral.sh/uv/);
- Node.js 22 com npm;
- Make.

```bash
git clone https://github.com/lfbardi-don/TEMPLATE-TIAO-2026.git
cd TEMPLATE-TIAO-2026/1TIAO/FASE6/enterprise-challenge-sprint-4-sompo
uv sync --frozen
npm --prefix frontend ci
```

O recorte observado e o bundle necessários já estão no repositório. Execute os
comandos seguintes a partir da pasta do projeto Sompo.

### Criar uma demonstração do zero

**`make demo-real` recria o banco `tractor_usage_demo_real` a cada execução.**
As contas, importações e vistorias anteriores desse banco são apagadas. Para
continuar usando uma base existente, siga a seção seguinte.

Com as portas `5432`, `8010` e `5174` livres:

```bash
make demo-real
```

O Compose inicia somente o PostgreSQL oficial (`postgres:16`). O script
`scripts/demo_real.py` aplica as migrations, importa o recorte observado, inicia
a API e o frontend e executa o replay causal por HTTP. O banco `tractor_usage`
é preservado. O resultado esperado do replay é:

```text
Replay vivo concluído: 2522 janelas novas e 74 alertas.
```

Acesse [`http://127.0.0.1:5174`](http://127.0.0.1:5174). O terminal apresenta os
números `1000`, `1001`, `1002` e `1003`, com senhas aleatórias, para administrador,
especialista, vistoriador e gestor. O gestor fica limitado à frota da demo.

API e frontend continuam disponíveis até `Ctrl+C`. Para parar também o banco
iniciado pelo Compose deste projeto, execute `docker compose down` na mesma
pasta. Isso não remove seu volume.

**Nesta máquina, a porta `5432` pertence a outro projeto.** Não pare nem substitua
esse serviço. O ambiente local Sompo foi configurado em `55432`; confirme o banco
e as portas antes de usar os comandos de retomada abaixo. As portas, os processos e
outros detalhes dessa instalação ficam em `.demo-real/local-runtime.json`, quando
essa configuração local estiver presente; eles não fazem parte da instalação padrão.

Para uma demonstração descartável em outra porta, `scripts/demo_real.py` aceita
`DEMO_POSTGRES_PORT` e `DEMO_POSTGRES_DATA_DIR`. O PostgreSQL precisa estar em
execução, e o diretório de dados deve estar sob `/tmp`. O script compara esse
caminho com `SHOW data_directory` antes de recriar o banco. Definir somente
`DATABASE_URL` **não altera** o destino de `make demo-real`.

### Retomar uma base existente

Não execute `make demo-real` para retomar o trabalho. Com o PostgreSQL já em
execução, aponte para a base que contém as contas e vistorias. O exemplo abaixo
usa a configuração local Sompo (`55432`); em outra instalação, ajuste a URL.
Se API e frontend já estiverem abertos, basta acessar a interface.

Terminal da API:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:55432/tractor_usage_demo_real"
export AUTH_COOKIE_SECURE=0
uv run uvicorn tractor_usage.api.app:create_app --factory --host 127.0.0.1 --port 8010
```

Outro terminal, na mesma pasta:

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8010 \
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Esses comandos somente iniciam os servidores; não recriam o banco, as contas ou o
replay. As credenciais existentes continuam válidas. Após atualizar o código,
confira `uv run alembic current` e `uv run alembic heads` com a mesma
`DATABASE_URL`; se houver migrations pendentes, faça backup da base antes de
aplicar `uv run alembic upgrade head`.

### Desenvolvimento em uma base nova

Para desenvolver em `tractor_usage`, com PostgreSQL na porta livre `5432`:

```bash
docker compose up -d --wait postgres
cp .env.example .env
set -a
. ./.env
set +a
uv run alembic upgrade head
uv run python scripts/manage_users.py create --worker-id 1000 --role ADMIN
uv run python scripts/run_api.py
```

O `.env` é local e ignorado pelo Git. Edite sua URL antes de carregá-lo caso use
outro banco. A API lê variáveis de ambiente; copiar o arquivo sozinho não o
carrega. O comando de criação de conta solicita a senha sem eco. Na tela
Administração, crie as contas operacionais para cadastrar máquinas e importar CSVs.

Em outro terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Nesse modo, a API fica em `8000` e a interface em `5173`. O proxy `/api` usa a
porta `8000` por padrão; `VITE_API_PROXY_TARGET` permite apontar para outra API.
O token `INGEST_TOKEN` é necessário somente para ingestão de janelas pelo replay
HTTP. Login e importação de CSV pela interface usam a sessão do usuário.

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

Se o banco já existir, pule o `createdb`. Sem `TEST_DATABASE_URL`, os testes que
exigem PostgreSQL são pulados.

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
| `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout` | criar, consultar e encerrar a sessão do usuário |
| `GET/POST /v1/admin/users`, `PATCH /v1/admin/users/{id}`, `POST /v1/admin/users/{id}/reset-password` | administrar contas com senha temporária entregue uma vez |
| `GET /v1/admin/user-events` | consultar o histórico de alterações de contas |
| `GET /v1/inspectors` | listar vistoriadores ativos para atribuição opcional de casos |
| `GET /v1/catalog`, `POST /v1/fleets`, `POST /v1/fleets/{id}/tractors` | consultar o catálogo e cadastrar frotas e máquinas |
| `POST /v1/tractors/{id}/imports/preview`, `POST /v1/tractors/{id}/imports` | validar CSV e confirmar a importação com inferência atômica |
| `GET /v1/tractors/{id}/imports`, `GET /v1/tractors/{id}/telemetry-chart` | consultar processamentos e pontos dos gráficos |
| `GET /v1/demo/csv-scenarios` | listar os quatro arquivos simulados disponíveis para download |
| `POST /v1/tractors/{id}/windows` | reconstruir, pontuar e persistir uma janela observada |
| `GET /v1/tractors/{id}/overview` | scores 7/15/30, cobertura anterior, medianas de referência, episódios, pauta e situação da vistoria |
| `GET /v1/tractors/{id}/exposure-timeline` | exposição física por semana, com `NO_DATA` nas semanas sem operação |
| `GET /v1/tractors/{id}/episodes/{episode_id}` | sinais a 1 Hz e segundos de cada regra, recalculados das amostras gravadas |
| `POST /v1/tractors/{id}/inspection-cases` | abrir um caso e congelar evidência e pauta (`inspection-evidence-v2`) |
| `GET /v1/inspection-cases`, `GET /v1/inspection-cases/{id}` | listar vistorias e abrir o workspace do caso |
| `PATCH /v1/inspection-cases/{id}` | atualizar, iniciar, salvar achados, cancelar ou concluir; concluir exige um achado por item |
| `GET /v1/inspection-cases/{id}/episodes/{episode_id}` | consultar um episódio na data da evidência congelada |
| `GET /v1/inspection-cases/{id}/events` | consultar como administrador quem abriu ou alterou o caso, a ação e o horário UTC |
| `GET /v1/portfolio/inspection-priorities` | listar as máquinas com dados pontuados |
| `GET /v1/demo/replay-progress` | acompanhar a demonstração atual; retorna `204` quando não há replay |

### Acesso local

O login usa um número de identificação do trabalhador e uma senha em contas
locais no PostgreSQL, com sessões revogáveis em cookie
`HttpOnly` e `SameSite=Lax`. Não há cadastro público de usuários. Depois de
aplicar as migrations no banco escolhido, o primeiro administrador é criado
no terminal; a senha é solicitada sem eco. Depois disso, a tela `/admin` é o
caminho normal para gerir contas. O comando local fica para bootstrap e
recuperação:

```bash
# Use a DATABASE_URL do banco escolhido, já com as migrations aplicadas.
uv run python scripts/manage_users.py create --worker-id 1000 --role ADMIN
```

O identificador aceita de 1 a 20 dígitos, é único neste banco e preserva zeros
à esquerda. É um identificador local de acesso; a POC não o confere com um
cadastro de RH. Na demo, os números são recriados junto com o banco.
Para o gestor, use `--role FLEET_MANAGER --fleet-id UUID_DA_FROTA`. O comando
também oferece `set-role`, `reset-password` e `disable`; execute `--help` para
os argumentos. O backend verifica as permissões em cada requisição:

| Papel | Acesso |
|---|---|
| Administrador (`ADMIN`) | Lê todas as máquinas, importações, casos e históricos; cria e gerencia contas. Não executa ações de vistoria em nome de outros papéis |
| Especialista (`INSURER`) | Cadastra frotas e máquinas, importa CSVs, consulta evidências; abre, atualiza e cancela casos; escolhe um vistoriador ativo opcional |
| Vistoriador (`INSPECTOR`) | Consulta máquinas, gráficos e casos; inicia, salva achados parciais e conclui vistorias |
| Gestor (`FLEET_MANAGER`) | Consulta máquinas e gráficos somente de sua frota; não acessa casos, importações ou históricos de ações |

O vínculo do vistoriador a um caso usa seu número cadastrado, mas ainda não é uma
regra de autorização por pessoa. O especialista e o vistoriador têm visibilidade global
das máquinas nesta POC. Uma requisição sem sessão recebe `401`; papel sem
permissão recebe `403`; recursos de outra frota não são revelados ao gestor.

Cada abertura ou alteração de caso feita pela API autenticada registra, na
mesma transação, o número do trabalhador e o papel no momento da ação, o
horário UTC, a ação e a mudança de estado. Somente o administrador pode consultar
esse histórico no próprio caso. A página de importações da máquina mostra os
períodos e a origem dos registros. Importações pela interface registram o
número do trabalhador, data UTC e origem declarada; imports observados feitos
por scripts podem não ter autor de sessão. Mudanças de
contas feitas na interface do administrador também ganham autor, horário e
ação. Nesta POC, leituras, logins e comandos locais de administração de
usuários não têm trilha individual de eventos.

A ingestão de janelas exige um token de serviço separado das sessões de usuário.
Ao executar a API e `scripts/run_api_replay.py` manualmente, defina o mesmo
`INGEST_TOKEN` aleatório em ambos os processos. `make demo-real` gera esse token
somente para sua execução. Em uma implantação com HTTPS, configure
`AUTH_COOKIE_SECURE=1`; integração com provedor de identidade, gestão de segredos
e operação externa ainda exigem trabalho próprio.

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
  api/               adaptador FastAPI e composição
frontend/             dashboard React
```

### Scripts disponíveis

`run_api.py` inicia diretamente a API local na porta 8000. Os demais scripts
aceitam `--help` para consultar os argumentos. O treinamento usa a base completa
preparada; a aplicação carrega o bundle já incluído.

| Script | Uso |
|---|---|
| `demo_real.py` | Executar a demonstração observada completa, também chamada por `make demo-real` |
| `run_api.py` | Iniciar a API sobre o banco configurado |
| `manage_users.py` | Criar o primeiro administrador e recuperar contas |
| `import_telemetry.py` | Importar manualmente telemetria observada de treino ou validação para uma máquina cadastrada |
| `run_api_replay.py` | Reproduzir amostras persistidas enviando janelas à API |
| `run_model_selection.py` | Reproduzir a seleção científica de regimes e detector |
| `freeze_approved_bundle.py` | Gerar e verificar o bundle aprovado em um novo diretório |
| `verify_replay_equivalence.py` | Comparar o replay causal com o processamento em lote |

Todos os processos da demo escutam apenas em loopback (`127.0.0.1`). As contas
locais e o RBAC apoiam a POC; a API não deve ser exposta diretamente na internet.

## Documentação técnica

- [Evolução até a Sprint 4](docs/FENDT314_SEIVA.md#11-evolução-até-a-sprint-4),
  com as mudanças de escopo e a passagem para o fluxo de inspeção preventiva.
- [Relatório acadêmico em Markdown](docs/FENDT314_SEIVA.md), com diagramas
  Mermaid para leitura direta no GitHub.
- [Relatório acadêmico em PDF](docs/FENDT314_SEIVA.pdf), versão diagramada
  para apresentação e entrega.
- [Model card](docs/modeling/fendt314-hybrid-v2-model-card.md), com método,
  avaliação, resultados e limitações.
- [Reconstrução do calendário](docs/data/fendt-314-calendar-reconstruction.md),
  com a recuperação temporal do dataset.
- [Proveniência do recorte](data/fendt314-validation/README.md), com fonte,
  licença e significado dos arquivos incluídos.

## Limitações e próximos passos

- A referência científica atual vem de uma única unidade Fendt 314.
- O dataset de treinamento não tem rótulos de dano, falha, manutenção ou sinistro.
  Achados cadastrados são evidência humana; os de máquinas simuladas são testes.
- Achados ainda não são usados para medir precisão nem para treinar o modelo.
- As regras físicas são hipóteses de engenharia, não diagnóstico do fabricante.
- Reproduzir o treinamento exige o dataset integral; executar o bundle e a demo
  não exige.
- Validação entre tratores, integração com identidade corporativa e
  infraestrutura cloud permanecem como próximos passos.

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
