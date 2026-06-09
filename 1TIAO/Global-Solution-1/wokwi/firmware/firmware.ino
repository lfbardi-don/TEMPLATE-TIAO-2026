// No de borda (ESP32) no Wokwi.
//
// O ESP32 e um no fino; a fisica roda no backend:
//   - le o POTENCIOMETRO -> irradiance_frac (0..1) = entrada solar (baixe = eclipse)
//   - le o BOTAO         -> force_eclipse (eclipse forcado)
//   - faz POST /telemetry e recebe o comando na resposta
//   - aplica o comando no LED via PWM (brilho = carga; escurece = throttle)
//
// Rede: no Wokwi o ESP32 conecta no WiFi virtual "Wokwi-GUEST". Aponte BACKEND_HOST para
// o seu backend (ver wokwi/README.md): VS Code Wokwi Gateway (host.wokwi.internal) ou um
// tunel cloudflared publico.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---- configuracao ----
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const char* BACKEND_HOST = "host.wokwi.internal";  // VS Code gateway; ou "<seu-subdominio>.trycloudflare.com"
const int   BACKEND_PORT = 8000;                   // para https/cloudflared use 443 + WiFiClientSecure
const char* NODE_ID = "wokwi-0";
const int   LOOKAHEAD = 3;                          // 0 = modo burro; >0 = MPC preditivo

// ---- pinos ----
const int PIN_POT = 34;   // ADC1 (entrada solar / gatilho)
const int PIN_BTN = 27;   // botao -> force_eclipse
const int PIN_LED = 25;   // LED PWM (carga visivel)

// ---- estado ----
int   currentPwm = 0;        // ultimo comando aplicado (0..255)
float currentLoad = 0.0;     // currentPwm/255 (reportado como load_frac)
String nodeState = "idle";
unsigned long lastOkMs = 0;  // ultimo POST bem-sucedido (failsafe de timeout)

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(PIN_POT, INPUT);
  analogWrite(PIN_LED, 0);     // LEDC via analogWrite (robusto entre versoes do core ESP32)

  Serial.print("Conectando WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  Serial.printf("\nWiFi OK, IP: %s\n", WiFi.localIP().toString().c_str());
  lastOkMs = millis();
}

void loop() {
  // --- le sensores ---
  float irradiance = analogRead(PIN_POT) / 4095.0;       // 0..1 (potenciometro)
  bool forceEclipse = (digitalRead(PIN_BTN) == LOW);     // botao pressionado

  // --- monta telemetria ---
  StaticJsonDocument<256> body;
  body["node_id"] = NODE_ID;
  body["ts"] = millis();
  body["irradiance_frac"] = irradiance;
  body["force_eclipse"] = forceEclipse;
  body["load_frac"] = currentLoad;
  body["state"] = nodeState;
  body["lookahead"] = LOOKAHEAD;
  String payload;
  serializeJson(body, payload);

  // --- POST /telemetry, comando volta na resposta ---
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + BACKEND_PORT + "/telemetry";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(4000);
  int code = http.POST(payload);

  if (code == 200) {
    StaticJsonDocument<256> resp;
    if (deserializeJson(resp, http.getString()) == DeserializationError::Ok) {
      const char* action = resp["action"] | "run";
      int pwm = resp["target_pwm"] | 0;
      applyCommand(action, pwm);
      Serial.printf("irr=%.2f ecl=%d -> %s pwm=%d (%s)\n",
                    irradiance, forceEclipse, action, pwm, (const char*)(resp["reason"] | ""));
      lastOkMs = millis();
    }
  } else {
    Serial.printf("POST falhou (%d)\n", code);
  }
  http.end();

  // --- failsafe: sem comando ha muito tempo -> carga segura (desliga) ---
  if (millis() - lastOkMs > 10000) {
    applyCommand("defer", 0);
    Serial.println("FAILSAFE: sem backend, carga em 0");
  }

  delay(2000);  // ~1 telemetria a cada 2 s
}

void applyCommand(const char* action, int pwm) {
  pwm = constrain(pwm, 0, 255);
  currentPwm = pwm;
  currentLoad = pwm / 255.0;
  analogWrite(PIN_LED, pwm);   // brilho = carga; escurece = throttle
  if      (strcmp(action, "run") == 0)          nodeState = "running";
  else if (strcmp(action, "throttle") == 0)     nodeState = "throttled";
  else if (strcmp(action, "checkpoint") == 0)   nodeState = "checkpointing";
  else                                          nodeState = "idle";  // defer
}
