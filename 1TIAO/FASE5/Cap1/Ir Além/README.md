# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/">
  <img src="../../../../assets/logo-fiap.png"
       alt="FIAP - Faculdade de Informática e Administração Paulista"
       width="40%">
</a>
</p>

<br>


# 🌱 Ir Além — Sistema de Coleta e Comunicação de Dados via ESP32 e Wi-Fi
FarmTech Solutions — Projeto de extensão Ir Além 1

## 👨‍🎓 Integrantes

- Karina Queiroz de Gennaro — RM570928
- Luis Felipe Bardi — RM569479
- Beatriz de Oliveira Ossola Ribeiro — RM570190

## 👩‍🏫 Professores:
### Tutor(a)
- <a href="https://www.linkedin.com/in/sabrina-otoni-22525519b/">Sabrina Otoni</a>
### Coordenador(a)
- <a href="https://www.linkedin.com/in/andregodoichiovato/">André Godoi</a>


## 📜 Descrição

Este projeto implementa um sistema de telemetria agrícola em tempo real utilizando um ESP32 integrado via Wi-Fi, coletando dados de dois sensores distintos e publicando-os em um broker MQTT para armazenamento em banco de dados SQLite e visualização em um dashboard interativo (Streamlit).

O objetivo é monitorar, de forma remota e contínua, as condições ambientais de uma área de cultivo — temperatura, umidade relativa do ar e ocorrência de chuva — permitindo à FarmTech Solutions apoiar decisões de manejo agrícola (irrigação, plantio, colheita) com base em dados reais e históricos.


## 🧠 Justificativa da Escolha dos Sensores
### DHT22 — Temperatura do Ar e Umidade Relativa

O DHT22 é um sensor digital combinado que mede simultaneamente temperatura e umidade relativa do ar, duas das variáveis climáticas mais críticas para o manejo agrícola:
 Temperatura do ar influencia diretamente a taxa de evapotranspiração das plantas, o ritmo de desenvolvimento das culturas e o risco de estresse térmico em períodos de calor extremo ou geadas.

 Umidade relativa do ar está diretamente ligada à necessidade hídrica das plantas (quanto menor a umidade, maior a perda de água por transpiração) e é também um dos principais fatores de risco para proliferação de fungos e doenças na lavoura em ambientes muito úmidos.


- Por que o DHT22 e não o DHT11: ambos os sensores medem as mesmas duas grandezas, mas o DHT22 foi escolhido por oferecer:

| Característica | DHT11 | DHT22 |
| :--- | :--- | :--- |
| Faixa de temperatura | 0–50 °C | -40–80 °C |
| Faixa de umidade | 20–90% | 0–100% |
| Precisão de temperatura | ±2 °C | ±0.5 °C |
| Precisão de umidade | ±5% | ±2–5% |

Para um cenário agrícola real, onde variações de temperatura podem ser mais extremas (geadas noturnas, calor intenso durante o dia) e a precisão da leitura impacta diretamente a qualidade da decisão de manejo (por exemplo, decidir se é necessário irrigar), a faixa mais ampla e a maior precisão do DHT22 o tornam a escolha mais adequada ao contexto da FarmTech Solutions.

### Botão Digital — Simulação de Sensor de Chuva

Para representar a ocorrência de precipitação, foi utilizado um botão digital com leitura por interrupção, simulando o comportamento de um sensor de chuva real.

Por que essa escolha: sensores de chuva físicos mais comuns no mercado (como o módulo FC-37 / YL-83) funcionam, em sua essência, como uma chave digital: uma placa com trilhas condutoras fecha o circuito quando entra em contato com água, gerando um sinal digital (HIGH/LOW) equivalente ao de um botão pressionado. Como o Wokwi (ambiente de simulação utilizado neste projeto) não disponibiliza um componente nativo de sensor de chuva, o botão digital foi adotado como substituto funcionalmente equivalente:

Do ponto de vista do hardware simulado, ambos os componentes geram o mesmo tipo de sinal (digital, binário).
Do ponto de vista do firmware, a leitura é feita da mesma forma: um pino digital configurado com INPUT_PULLUP, tratado por uma interrupção de hardware (attachInterrupt) que dispara na borda de descida (FALLING) — exatamente a lógica que seria usada com o sensor real.
Isso significa que a migração para o sensor físico, em uma implementação com hardware real, não exigiria nenhuma alteração de arquitetura ou de lógica de software — apenas a troca do componente conectado ao mesmo GPIO.

A variável "ocorrência de chuva" é relevante para a FarmTech Solutions porque impacta diretamente decisões como suspensão temporária de irrigação automatizada, previsão de risco de encharcamento do solo e planejamento de janelas de pulverização ou colheita.

## 📁 Estrutura de pastas

<pre>
Ir Além/
├── wifi-scan/           # Projeto Wokwi do ESP32 (firmware, diagram.json, etc.)
├── app.py               # Dashboard Streamlit
├── receptor_mqtt.py     # Script Python: subscriber MQTT → SQLite
├── farmtech.db          # Banco de dados SQLite gerado pela coleta
└── README.md
</pre>

## 💻 Arquitetura e "API" do Sistema

O sistema não expõe uma API REST tradicional — a interface entre os componentes é o contrato de mensagens MQTT: cada tópico funciona como um "endpoint" de publicação, com um payload simples e bem definido.

<pre>
[ESP32 / Wokwi]
    │
    ├─(Wi-Fi)────────────────────────┐
    │                                ▼
    │                        [Broker HiveMQ]
    │                        (broker.hivemq.com)
    │                                │
    │(MQTT / Pub)                    │(MQTT / Sub)
    ▼                                ▼
[DHT22 & Botão]              [receptor_mqtt.py]
                                     │
                                     ▼ (INSERT SQL)
                               [farmtech.db]
                                     │
                                     ▼ (SELECT SQL)
                                 [app.py]
                               (Streamlit)
</pre>

## 📎 Links e Observações

- [Vídeo de demonstração no YouTube](https://youtu.be/M8LBDjLW25M).
- [Simulação no Wokwi](https://wokwi.com/projects/474376654703049729).

## ⚡ Explicação de Decisões Técnicas
Optou-se por SQLite em vez de CSV para o armazenamento histórico, por ser um banco de dados relacional real (permitido explicitamente pelo enunciado), mais robusto contra concorrência de escrita e mais alinhado a boas práticas de persistência de dados IoT.
Optou-se por um broker MQTT público (HiveMQ) em vez de um broker local, para simplificar a entrega acadêmica e evitar dependência de infraestrutura própria — ciente do trade-off de não haver autenticação/isolamento dos tópicos.
O sensor de chuva foi simulado por um botão digital no Wokwi, dado que o simulador não oferece um componente nativo equivalente; a lógica de leitura (GPIO digital + interrupção) é idêntica à que seria usada com um sensor físico real.

## 🔍 Estrutura do Código
- Firmware do ESP32 (wifi-scan/wifi-scan.ino)
Leitura periódica (a cada 4 segundos) do DHT22, controlada por millis() para evitar bloqueios (delay()).
Leitura do sensor de chuva via interrupção por hardware (attachInterrupt), garantindo que nenhum evento de chuva seja perdido mesmo entre ciclos de leitura do DHT22.
Validação de leitura (isnan()) antes de qualquer publicação, evitando envio de dados inválidos ao broker.
Reconexão automática ao broker MQTT em caso de queda de conexão.

- receptor_mqtt.py
Inscreve-se nos três tópicos publicados pelo ESP32.
A cada mensagem recebida, insere um registro na tabela leituras do banco farmtech.db, com timestamp de recebimento, tópico de origem e valor.
Usa client_id único gerado aleatoriamente para evitar conflito de identificação no broker público.

- app.py (Dashboard)
Lê os dados diretamente do SQLite via pandas.read_sql_query.
Exibe métricas atuais (temperatura, umidade, status de chuva) em cartões (KPIs).
Gráficos históricos de temperatura e umidade em abas separadas.
Tabela com os últimos 10 registros brutos do banco.
Opção de auto-atualização a cada 5 segundos.


## 🔧 Como executar

É necessário ter Python 3.10 ou superior, acesso ao Wokwi e conexão com a internet
para comunicação com o broker MQTT público.

Na raiz do repositório, entre na pasta do projeto e instale as dependências:

```bash
cd "1TIAO/FASE5/Cap1/Ir Além"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install paho-mqtt pandas streamlit
```

1. Abra a [simulação no Wokwi](https://wokwi.com/projects/474376654703049729) e inicie
   o circuito. O firmware está em [wifi-scan/wifi-scan.ino](wifi-scan/wifi-scan.ino).
2. No terminal com o ambiente ativado, execute o receptor e mantenha-o em execução:

   ```bash
   python receptor_mqtt.py
   ```

3. Em outro terminal, entre na mesma pasta, ative o ambiente e abra o dashboard:

   ```bash
   cd "1TIAO/FASE5/Cap1/Ir Além"
   source .venv/bin/activate
   streamlit run app.py
   ```

4. Acesse o [dashboard local](http://localhost:8501).

Execute os dois programas a partir da pasta `Ir Além` para que utilizem o mesmo
arquivo `farmtech.db`.

---

## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/SabrinaOtoni/TEMPLATE-FIAP-GRAD-ON-IA">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">FIAP</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
