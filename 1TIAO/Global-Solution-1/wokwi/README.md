# No de borda no Wokwi (ESP32)

O ESP32 simulado e um no fino: le o potenciometro (entrada solar / gatilho ao vivo) e o botao (eclipse forcado), faz `POST /telemetry` e aplica o comando do backend no LED (PWM = carga). A fisica orbital/termica e a IA (forecaster + MPC) ficam no backend.

## Circuito (`diagram.json`)

- Potenciometro (SIG): GPIO34 (ADC). Irradiancia solar 0..1. Gire para baixo para simular eclipse.
- Botao: GPIO27. `force_eclipse` enquanto pressionado.
- LED (via resistor 220 ohm): GPIO25 (PWM). Carga de computacao. Escurece quando a IA da throttle.

Os nomes de pino no `diagram.json` (ex.: `esp:D34`) seguem o ESP32 DevKit V1 do Wokwi. Se algum fio nao casar ao abrir, religue no editor do Wokwi. O que importa sao os GPIOs no firmware (34/27/25).

## Rodar

### Opcao A: VS Code + Wokwi (gateway local p/ localhost)

1. Instale a extensao Wokwi for VS Code e faca login (licenca gratis).
2. Compile o sketch (arduino-cli ou PlatformIO) para `firmware/build/firmware.ino.bin` + `.elf` (alvo: ESP32 Dev Module). Ajuste os caminhos em `wokwi.toml` se preciso.
3. Suba o backend local: `make up && make migrate && make api` (porta 8000).
4. Abra `diagram.json` no VS Code e inicie a simulacao. Com `gateway = true`, o firmware alcanca o backend em `http://host.wokwi.internal:8000`.

### Opcao B: Wokwi online (wokwi.com) + cloudflared

1. Exponha o backend: `cloudflared tunnel --url http://localhost:8000`. Copie a URL `https://<sub>.trycloudflare.com`.
2. No `firmware.ino`, troque `BACKEND_HOST` por `<sub>.trycloudflare.com` e use HTTPS (porta 443; trocar `HTTPClient` por `WiFiClientSecure` + `client.setInsecure()`).
3. Em wokwi.com crie um projeto ESP32, cole `diagram.json`, `firmware.ino` e `libraries.txt` (ArduinoJson) e rode.

## Gatilho ao vivo (demo)

- Gire o potenciometro para baixo (setas do teclado sobre o pot). `irradiance_frac` cai, o forecaster preve queda, o MPC manda `throttle`/`checkpoint` e o LED escurece.
- Ou segure o botao (Cmd-clique trava) para `force_eclipse`.
- Fallback (sem mexer no Wokwi): `curl -X POST "localhost:8000/admin/inject_eclipse?node_id=wokwi-0&on=true"`.

## Verificacao rapida (lado backend, sem Wokwi)

`python scripts/run_node_sim.py 30 wokwi-0 3` simula o payload do firmware e mostra o backend respondendo comandos e gravando em `telemetry`/`decisions`.
