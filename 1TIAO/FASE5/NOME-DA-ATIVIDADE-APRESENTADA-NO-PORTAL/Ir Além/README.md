# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/">
  <img src="../../../assets/logo-fiap.png" 
       alt="FIAP - Faculdade de Informática e Administração Paulista" 
       width="40%">
</a>
</p>

<br>


# 🌱 Ir Além — Sistema de Coleta e Comunicação de Dados via ESP32 e Wi-Fi
FarmTech Solutions — Projeto de extensão Ir Além 1

## 👨‍🎓 Integrantes: 
- <a href="https://www.linkedin.com/in/sabrina-otoni-22525519b/">Karina Queiroz de Gennaro | 570928 1</a>
- <a href="https://www.linkedin.com/in/sabrina-otoni-22525519b/">Luis Felipe Bardi | 569479</a>
- <a href="https://www.linkedin.com/in/sabrina-otoni-22525519b/">Beatriz de Oliveira Ossola Ribeiro | 570190</a> 


## 👩‍🏫 Professores:
### Tutor(a) 
- <a href="https://www.linkedin.com/in/sabrina-otoni-22525519b/">Sabrina Otoni</a>
### Coordenador(a)
- <a href="https://www.linkedin.com/in/andregodoichiovato/">André Godoi</a>


## 📜 Descrição

Este projeto implementa um sistema de telemetria agrícola em tempo real utilizando um ESP32 integrado via Wi-Fi, coletando dados de dois sensores distintos e publicando-os em um broker MQTT para armazenamento em banco de dados SQLite e visualização em um dashboard interativo (Streamlit).

O objetivo é monitorar, de forma remota e contínua, as condições ambientais de uma área de cultivo — temperatura, umidade relativa do ar e ocorrência de chuva — permitindo à FarmTech Solutions apoiar decisões de manejo agrícola (irrigação, plantio, colheita) com base em dados reais e históricos.

## 🧠 Justificativa da Escolha dos Sensores
Sensor	Variável medida	Motivo da escolha
DHT22	Temperatura do ar e umidade relativa	São as duas variáveis climáticas mais diretamente relacionadas à necessidade hídrica das plantas e ao risco de estresse térmico ou proliferação de fungos. O DHT22 foi escolhido em vez do DHT11 por ter maior precisão e faixa de leitura mais ampla, relevante para monitoramento agrícola.
Botão (simulando sensor de chuva)	Ocorrência de precipitação	No ambiente de simulação Wokwi não há um componente nativo de sensor de chuva; um botão digital com interrupção foi usado para representar fielmente o comportamento binário de um sensor de chuva real (tipo FC-37/YL-83: contato fecha na presença de água). A lógica de software (leitura via interrupção, GPIO digital) é idêntica à que seria usada com o sensor físico — a troca do componente não exige nenhuma mudança na arquitetura do sistema.

Isso satisfaz o requisito de pelo menos dois sensores distintos, ambos alinhados ao contexto de monitoramento agrícola da FarmTech Solutions.


## 📁 Estrutura de pastas

<pre>
📁 ir-alem/
├── 📁 docs/
│   ├── 🖼️ circuito_wokwi.png  # Diagrama do circuito (ESP32 + DHT22 + sensor de chuva)
│   └── 📄 decisoes_tecnicas.md # Justificativas e decisões de arquitetura
├── 📁 src/
│   ├── 💻 esp32_firmware.ino    # Código-fonte do ESP32 (C/C++)
│   ├── 🐍 receptor_mqtt.py      # Script Python: subscriber MQTT → SQLite
│   └── 📊 app.py                # Dashboard Streamlit
├── 📁 data/
│   └── 🗄️ farmtech.db           # Banco de dados SQLite gerado pela coleta
├── 📁 entregas/
│   └── 🔗 video_demonstracao.txt # Link não listado do YouTube
├── 📁 prints/                   # Capturas de tela do dashboard funcionando
└── 📄 README.md
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

- Vídeo de demonstração (não listado, YouTube): (inserir link)
- Simulação no Wokwi: (inserir link do projeto no Wokwi, se público)

## ⚡ Explicação de Decisões Técnicas
Optou-se por SQLite em vez de CSV para o armazenamento histórico, por ser um banco de dados relacional real (permitido explicitamente pelo enunciado), mais robusto contra concorrência de escrita e mais alinhado a boas práticas de persistência de dados IoT.
Optou-se por um broker MQTT público (HiveMQ) em vez de um broker local, para simplificar a entrega acadêmica e evitar dependência de infraestrutura própria — ciente do trade-off de não haver autenticação/isolamento dos tópicos.
O sensor de chuva foi simulado por um botão digital no Wokwi, dado que o simulador não oferece um componente nativo equivalente; a lógica de leitura (GPIO digital + interrupção) é idêntica à que seria usada com um sensor físico real.
9.3 Observações Ger

## 🔍 Estrutura do Código
- Firmware do ESP32 (src/esp32_firmware.ino)
Leitura periódica (a cada 4 segundos) do DHT22, controlada por millis() para evitar bloqueios (delay()).
Leitura do sensor de chuva via interrupção por hardware (attachInterrupt), garantindo que nenhum evento de chuva seja perdido mesmo entre ciclos de leitura do DHT22.
Validação de leitura (isnan()) antes de qualquer publicação, evitando envio de dados inválidos ao broker.
Reconexão automática ao broker MQTT em caso de queda de conexão.

- src/receptor_mqtt.py
Inscreve-se nos três tópicos publicados pelo ESP32.
A cada mensagem recebida, insere um registro na tabela leituras do banco data/farmtech.db, com timestamp de recebimento, tópico de origem e valor.
Usa client_id único gerado aleatoriamente para evitar conflito de identificação no broker público.

- src/app.py (Dashboard)
Lê os dados diretamente do SQLite via pandas.read_sql_query.
Exibe métricas atuais (temperatura, umidade, status de chuva) em cartões (KPIs).
Gráficos históricos de temperatura e umidade em abas separadas.
Tabela com os últimos 10 registros brutos do banco.
Opção de auto-atualização a cada 5 segundos.


## 🔧 Como executar o código

# Pré-requisitos
Conta gratuita em Wokwi.com para simular o circuito ESP32.
Python 3.10+ instalado na máquina local.
Conexão com a internet (necessária para o Wokwi acessar o broker MQTT público e para o script Python receber as mensagens).

# Clonar o repositório
git clone <link-do-repositorio>
cd ir-alem

# Instalar as dependências Python
pip install paho-mqtt pandas streamlit

# Execução
Abra o projeto no Wokwi.com e inicie a simulação do circuito ESP32 + DHT22 + botão (arquivo src/esp32_firmware.ino).
Em um terminal local, execute o receptor MQTT (mantenha rodando durante toda a demonstração):
   python src/receptor_mqtt.py
   streamlit run src/app.py
Acesse o dashboard em http://localhost:8501
   
## 🗃 Histórico de lançamentos

* 0.5.0 - XX/XX/2024
    * 
* 0.4.0 - XX/XX/2024
    * 
* 0.3.0 - XX/XX/2024
    * 
* 0.2.0 - XX/XX/2024
    * 
* 0.1.0 - XX/XX/2024
    *

---


## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/SabrinaOtoni/TEMPLATE-FIAP-GRAD-ON-IA">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">FIAP</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
