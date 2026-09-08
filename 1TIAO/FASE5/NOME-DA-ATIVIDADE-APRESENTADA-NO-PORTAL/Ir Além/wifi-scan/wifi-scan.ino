#include <WiFi.h>
#include <DHT.h>
#include <PubSubClient.h> // Biblioteca para comunicação MQTT (Porta 1883)

// Definição de Pinos conforme a montagem
#define DHTPIN 2          // DHT22 conectado ao GPIO 2
#define DHTTYPE DHT22     // Tipo do sensor DHT
#define RAIN_PIN 23       // Botão (Chuva) conectado ao GPIO 23

// Credenciais de Wi-Fi do Wokwi
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Configurações do Broker MQTT (Nuvem)
const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;

// Tópicos onde o ESP32 vai publicar os dados para o Python/Streamlit
const char* topic_temp = "farmtech/solutions/temperatura";
const char* topic_umid = "farmtech/solutions/umidade";
const char* topic_chuva = "farmtech/solutions/chuva";

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);

// Variável volátil obrigatória para a interrupção (ISR) do sensor de chuva
volatile bool chuvaDetectada = false;
unsigned long ultimaLeitura = 0;
const long intervaloEnvio = 4000; // Intervalo de envio a cada 4 segundos

// Função de Tratamento de Interrupção (ISR) para o Botão/Chuva
void IRAM_ATTR detectaChuva() {
    chuvaDetectada = true;
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    // Inicialização dos Sensores
    dht.begin();
    pinMode(RAIN_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(RAIN_PIN), detectaChuva, FALLING);

    // Conexão Wi-Fi
    Serial.print("Conectando ao Wi-Fi");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWi-Fi conectado com sucesso!");

    // Configurando o Servidor MQTT
    client.setServer(mqtt_server, mqtt_port);
    Serial.println("Sistema FarmTech IoT pronto e operando com MQTT.\n");
}

void loop() {
    // Garante que o ESP32 permaneça conectado ao Broker MQTT
    if (!client.connected()) {
        while (!client.connected()) {
            Serial.print("Conectando ao Broker MQTT...");
            if (client.connect("ESP32_FarmTech_Client")) {
                Serial.println(" Conectado!");
            } else {
                Serial.print(" Falha, rc=");
                Serial.print(client.state());
                Serial.println(" Tentando novamente em 5 segundos...");
                delay(5000);
            }
        }
    }
    client.loop();

    unsigned long tempoAtual = millis();

    // Tarefa periódica controlada por millis() (Evita travamentos)
    if (tempoAtual - ultimaLeitura >= intervaloEnvio) {
        ultimaLeitura = tempoAtual;

        // Leitura do DHT22
        float umidadeAr = dht.readHumidity();
        float temperatura = dht.readTemperature();

        // Validação se a leitura falhou
        if (isnan(umidadeAr) || isnan(temperatura)) {
            Serial.println("Erro ao ler o sensor DHT22!");
            return;
        }

        bool statusChuva = chuvaDetectada;
        chuvaDetectada = false; // Reseta a flag após capturar o evento

        // Convertendo os valores para string para envio MQTT
        char tempStr[8], umidStr[8];
        dtostrf(temperatura, 1, 2, tempStr);
        dtostrf(umidadeAr, 1, 2, umidStr);

        // Publicando os dados reais para a nuvem (Broker MQTT)
        client.publish(topic_temp, tempStr);
        client.publish(topic_umid, umidStr);
        client.publish(topic_chuva, statusChuva ? "1" : "0");

        // Exibindo no Monitor Serial do Wokwi
        Serial.println("=========================================");
        Serial.println("      FARMTECH SOLUTIONS - TELEMETRIA    ");
        Serial.println("=========================================");
        Serial.printf("Temperatura (2m)       : %.2f °C (Enviado MQTT)\n", temperatura);
        Serial.printf("Umidade Relativa (2m)  : %.2f %% (Enviado MQTT)\n", umidadeAr);
        
        if (statusChuva) {
            Serial.println("Precipitação (Chuva)   : DETECTADA! (Enviado MQTT)");
        } else {
            Serial.println("Precipitação (Chuva)   : Sem chuva no momento");
        }
        Serial.println("-----------------------------------------\n");
    }
}