# Model card: Fendt 314 Hybrid v2.0.1

## Finalidade e escopo

`fendt314-hybrid-v2.0.1` é um modelo congelado para contextualizar exposição
operacional em janelas causais de 60 s. Ele foi calibrado e validado
temporalmente no histórico observado de uma unidade Fendt 314 do dataset
Zenodo `10.5281/zenodo.14619787` (CC BY 4.0). PostgreSQL, API e frontend são a
demonstração de implantação desse núcleo; não são uma nova fonte de evidência
científica.

O resultado é um alerta explicável para prevenção e priorização de inspeção.
Não é diagnóstico, nem probabilidade de dano, falha, sinistro, culpa ou mau
uso. O dataset não possui tais rótulos. Uma futura frota homogênea Fendt 314
ainda exige telemetria observada própria por unidade e validação entre tratores.

## Dados e divisão temporal

O relógio UTC foi reconstruído a partir de três âncoras independentes; o
método e as limitações estão em
[reconstrução do calendário](../data/fendt-314-calendar-reconstruction.md).
As missões foram divididas cronologicamente, sem sorteio de janelas:

| Conjunto | Intervalo | Janelas | Papel |
|---|---|---:|---|
| Treino | 26/04–30/08/2024 | 7.317 | ajuste de pré-processamento, regimes, detectores e referências longitudinais |
| Validação | 07/09–19/10/2024 | 2.522 | seleção contra critérios pré-definidos |
| Teste | 21/10–04/12/2024 | 3.617 | avaliação temporal final, consumida |

O recorte versionado da demonstração contém 152.561 amostras em 105 missões e
é somente a partição de validação. O teste não entra no runtime e não foi
usado durante o congelamento do artefato.

## Entradas e pré-processamento

As 43 features fechadas são formadas pela média e pelo desvio-padrão de 17
sinais de estado (34 colunas) e por média, desvio-padrão e máximo de três
sinais transitórios (9 colunas):

| Grupo | Sinais |
|---|---|
| Motor e comando | RPM do motor, torque atual, carga, acelerador |
| Velocidade e implemento | velocidade do eixo dianteiro, velocidade sobre o solo, velocidade do implemento no solo, velocidade da roda, PTO traseira |
| Engate e esforço | posição e estado do engate traseiro, força do elo traseiro, draft traseiro |
| Velocidades da máquina | velocidades ground, selecionada e da roda da máquina |
| Dinâmica | patinagem, subida de torque em 1 s, mudança de RPM em 1 s e mudança de velocidade em 1 s |

Os campos transitórios são `torque_rise_1s`, `rpm_change_1s` e
`speed_change_1s`; eles acrescentam o máximo, totalizando 43. Valores ausentes
são imputados pela mediana de treino e as features são escaladas com
`RobustScaler`. Identidade, tempo, split, tipo de trabalho, dados de saúde e
as durações das regras físicas são excluídos do modelo aprendido para evitar
leakage.

## Método congelado

1. K-Means separa três regimes operacionais a partir das 43 features
   pré-processadas.
2. Uma Isolation Forest por regime mede raridade contextual.
3. O limiar de cada detector é o quantil 0,97 dos escores de treino daquele
   regime.
4. Um alerta exige, simultaneamente, raridade acima do limiar e ao menos 5 s
   observáveis em uma regra física versionada: baixa RPM sob carga, torque e
   carga elevados, patinagem sob carga, temperatura sob carga ou subida brusca
   de torque.
5. Os escores de 7, 15 e 30 dias comparam exposição física/h, alertas/h e
   episódios/h com distribuições empíricas apenas do treino.

As regras são hipóteses de engenharia auditáveis; não são features e não
convertem o alerta em rótulo de falha.

## Resultados

“Eficácia” neste projeto significa atender aos critérios operacionais e de
explicabilidade pré-definidos, além de manter comportamento no corte temporal
posterior. Não significa acurácia para dano ou sinistro.

| Avaliação | Alertas | Episódios | Episódios/h | Decisão |
|---|---:|---:|---:|---|
| Validação | 74/2.522 (2,93%) | 68 | 1,618 | GO |
| Teste temporal consumido | 95/3.617 (2,63%) | 79 | 1,311 | GO final |

Na validação, 40,40% das janelas foram fisicamente elegíveis e 7,26% delas
foram retidas pela raridade contextual; três famílias físicas foram
representadas. No teste, a taxa de elegibilidade foi 22,59%, a retenção
contextual 11,63% e também houve três famílias representadas. São resultados
de estabilidade operacional no histórico estudado, não métricas de risco
segurável.

## Integridade e runtime

O runtime só aceita o manifest e o bundle locais atuais:

| Item | Valor |
|---|---|
| Modelo | `fendt314-hybrid-v2.0.1` |
| Contrato | `window-inference-v1.1` |
| Bundle | `models/fendt314-hybrid-v2.0.1/bundle.joblib` |
| SHA-256 do bundle | `24b39996b3d0016f2bb29c6d722a24c46ac90576aab3da78cf44acdbad9cf5a4` |
| Tamanho | 2.921.962 bytes |
| SHA-256 das janelas de origem | `db6156e0f86c1bda5f155cca2649ea14c9991eb53e388500fdee0db41beb1c1e` |

O carregamento verifica versão, hash, tamanho, contrato, esquema de features,
estado do modelo, três regimes, detectores por regime, quantil 0,97, regra de
5 s e ausência de uso do teste no ajuste. Joblib só deve ser carregado de um
caminho local confiável: hash detecta alteração, mas não torna seguro um
artefato desconhecido.

## Limitações e uso responsável

- A evidência vem de uma única unidade Fendt 314; não há validação entre
  tratores, implementos, operadores ou propriedades.
- Há telemetria operacional, mas não há manutenção, DTC confirmado, dano,
  sinistro ou desfecho financeiro ligado no tempo.
- Cobertura ausente é `NO_DATA`, não inatividade ou operação segura.
- O teste temporal foi consumido; reproduções futuras verificam software, não
  criam evidência inédita de generalização.
- Produção atuarial exigiria múltiplas unidades, desfechos confirmados,
  governança de identidade e uma validação externa prospectiva.

## Reconstrução científica

A demonstração não precisa do dataset integral. Para refazer seleção,
congelamento ou auditoria, é necessário obter externamente as janelas e as
amostras completas publicadas pela fonte:

```bash
uv run python scripts/run_model_selection.py \
  --windows /caminho/fendt314-model-windows-60s.csv.gz \
  --report /tmp/fendt314-selection.json

uv run python scripts/freeze_approved_bundle.py \
  --windows /caminho/fendt314-model-windows-60s.csv.gz \
  --output-dir /tmp/fendt314-model

uv run python scripts/verify_replay_equivalence.py \
  --samples /caminho/fendt314-stress-1s.csv.gz \
  --windows /caminho/fendt314-model-windows-60s.csv.gz \
  --model-dir models/fendt314-hybrid-v2.0.1 \
  --mission-index 277 \
  --split validation
```

O teste temporal já foi consumido. Reexecutá-lo verifica software, mas não
constitui nova evidência de generalização.
