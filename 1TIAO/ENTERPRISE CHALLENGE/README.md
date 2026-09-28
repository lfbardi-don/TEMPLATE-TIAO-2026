# Enterprise Challenge — Sompo Seguros

<p align="center">
<a href="https://www.fiap.com.br/">
  <img src="../../assets/logo-fiap.png"
       alt="FIAP - Faculdade de Informática e Administração Paulista"
       width="40%">
</a>
</p>

## SEIVA — Inspeção preventiva Fendt 314

O SEIVA usa telemetria para orientar a vistoria preventiva de máquinas. O
especialista cadastra a frota e a máquina, importa um CSV e consulta os episódios
sinalizados. O vistoriador segue uma pauta por componente, consulta os gráficos e
registra os achados. Novos dados permitem acompanhar a operação após a vistoria.

O modelo treinado combina **K-Means**, **Isolation Forest por regime** e **regras
físicas** em janelas causais de 60 segundos. A referência foi construída com dados
observados de uma única Fendt 314. Os CSVs simulados demonstram novas frotas e
máquinas; não validam o modelo em outras unidades reais. O resultado apoia a
inspeção, sem diagnosticar dano, mau uso ou probabilidade de sinistro.

## Entrega da Fase 6 — Sprint 4

O código e a documentação estão em
[`1TIAO/FASE6/enterprise-challenge-sprint-4-sompo`](../FASE6/enterprise-challenge-sprint-4-sompo/).

- **[Guia do projeto](../FASE6/enterprise-challenge-sprint-4-sompo/README.md):**
  instalação, execução, login, permissões e testes.
- **[Fluxo do produto](../FASE6/enterprise-challenge-sprint-4-sompo/README.md#como-funciona):**
  entrada de dados, inferência, gráficos, vistoria e acompanhamento.
- **[Vídeo com narração em português](https://youtu.be/ZLmSHQjQImI)**.
- **[Relatório em Markdown](../FASE6/enterprise-challenge-sprint-4-sompo/docs/FENDT314_SEIVA.md)**
  · **[PDF](../FASE6/enterprise-challenge-sprint-4-sompo/docs/FENDT314_SEIVA.pdf)**.
- **[Evolução até a Sprint 4](../FASE6/enterprise-challenge-sprint-4-sompo/docs/FENDT314_SEIVA.md#11-evolução-até-a-sprint-4):**
  decisões e mudanças de escopo documentadas.
- **[Model card](../FASE6/enterprise-challenge-sprint-4-sompo/docs/modeling/fendt314-hybrid-v2-model-card.md):**
  método, avaliação e limites da referência.

## Entrega anterior — Fase 5, Sprint 3

A **[Sprint 3](../FASE5/enterprise-challenge-sprint-3-sompo/README.md)** permanece
na Fase 5, com seu código e documentação preservados.

## Equipe — Grupo SEIVA

| Integrante | RM |
|---|---:|
| Karina Queiroz de Gennaro | 570928 |
| Luis Felipe Bardi | 569479 |
| Beatriz de Oliveira Ossola Ribeiro | 570190 |

**Instituição:** Faculdade de Informática e Administração Paulista (FIAP)

**Parceiro corporativo:** Sompo Seguros

---

## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/SabrinaOtoni/TEMPLATE-FIAP-GRAD-ON-IA">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">FIAP</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
