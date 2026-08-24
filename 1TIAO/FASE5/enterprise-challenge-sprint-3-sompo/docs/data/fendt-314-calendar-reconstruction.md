# Reconstrução temporal do Fendt 314

Status: `CONFIRMADO`

## Objetivo

Recuperar o instante UTC de cada registro do CSV consolidado sem criar datas
sintéticas nem remover intervalos sem telemetria.

## Fontes e método

O arquivo `Fendt 314 - Kopie/Fendt 314.csv` contém `Time_(s)` como duração
global, mas não possui timestamp absoluto. Três arquivos de transporte mantêm
timestamps UTC e foram usados como âncoras independentes:

| Âncora | UTC conhecido | `Time_(s)` correspondente | Origem calculada |
|---|---:|---:|---:|
| `Transport/Field_1.csv` | `2024-09-23T07:40:36.000Z` | `12.939.490,9` | `2024-04-26T13:22:25.100Z` |
| `Transport/Field_2.csv` | `2024-09-30T09:16:39.200Z` | `13.550.054,1` | `2024-04-26T13:22:25.100Z` |
| `Transport/Field_3.csv` | `2024-10-08T01:37:37.000Z` | `14.213.711,9` | `2024-04-26T13:22:25.100Z` |

Cada âncora foi localizada por uma sequência multivariada de posição, RPM,
torque, velocidade e tipo de trabalho. A origem resulta de:

```text
epoch_utc = timestamp_ancora - Time_(s)_ancora
observed_at_utc = 2024-04-26T13:22:25.100Z + Time_(s)
```

As três estimativas coincidem na resolução original de 0,1 s. A coluna de
tempo decorrido permanece preservada para auditoria.

## Cobertura recuperada

| Medida | Resultado aproximado |
|---|---:|
| Período civil | 26/04 a 04/12/2024 (223 dias) |
| Dias com telemetria | 80 |
| Tempo observado | 226 h |
| Missões | 555 |
| Blocos civis não sobrepostos | 31 de 7 dias; 14 de 15 dias; 7 de 30 dias |

Janelas móveis de 7, 15 e 30 dias são possíveis, mas se sobrepõem e não devem
ser tratadas como observações independentes.

## Regras analíticas

- UTC é o tempo canônico.
- Ausência de leitura é `NO_DATA`, não evidência de inatividade.
- Agregados devem informar horas observadas e cobertura civil.
- Janelas usam apenas informações disponíveis até o próprio fechamento.
- Treino, validação e teste seguem a ordem temporal; não há sorteio de janelas.
- `Time_(s)` inválido ou não monotônico deve ser rejeitado.

## Limitação

A reconstrução estabelece quando a telemetria foi observada. Ela não fornece
rótulos de dano, manutenção, sinistro ou mau uso.
