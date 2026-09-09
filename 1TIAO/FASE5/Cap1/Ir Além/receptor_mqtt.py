# Para rodar: python receptor_mqtt.py

import paho.mqtt.client as mqtt
from datetime import datetime
import sqlite3
import random
import os


if os.path.exists("dados_farmtech_historico.csv"):
    os.remove("dados_farmtech_historico.csv")
    print("🧹 Arquivo CSV antigo detectado e eliminado permanentemente!")


# Configurações do Broker MQTT (exatamente o mesmo usado no ESP32)
BROKER = "broker.hivemq.com"
PORT = 1883
TOPICOS = [
    ("farmtech/solutions/temperatura", 0),
    ("farmtech/solutions/umidade", 0),
    ("farmtech/solutions/chuva", 0)
]

# Nome do arquivo do Banco de Dados SQLite
DB_NAME = "farmtech.db"


def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leituras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            topico TEXT,
            valor TEXT
        )
    ''')
    conn.commit()
    conn.close()


# Função chamada automaticamente quando o ESP32 publica alguma mensagem de 4 em 4s
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        topico = msg.topic
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"[{timestamp}] SALVANDO NO SQLITE -> Tópico: {topico} | Valor: {payload}")
        
        # Insere diretamente no banco de dados relacional SQLite
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO leituras (timestamp, topico, valor) VALUES (?, ?, ?)", 
                       (timestamp, topico, payload))
        conn.commit()
        conn.close()
            
    except Exception as e:
        print(f"Erro ao processar mensagem: {e}")

# Callback de conexão atualizado para a versão moderna da API (VERSION2)
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Conectado com sucesso ao Broker MQTT!")
        print("Escutando os dados da FarmTech Solutions...")
        client.subscribe(TOPICOS)
    else:
        print(f"Falha na conexão. Código: {rc}")

# Inicialização do Banco
inicializar_banco()

# Cliente MQTT com ID único
client_id = f"FarmTech_SQLite_{random.randint(1000, 9999)}"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message

print(f"Conectando ao broker MQTT ({BROKER}:{PORT})...")
client.connect(BROKER, PORT, 60)

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\nEncerrando receptor...")
    client.disconnect()