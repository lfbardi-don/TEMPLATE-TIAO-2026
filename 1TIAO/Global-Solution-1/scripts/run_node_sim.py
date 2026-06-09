"""Sim de 1 no: POST /telemetry por N passos, aplica o comando e imprime o laco."""

import json
import sys
import time
import urllib.request

API = "http://localhost:8000/telemetry"

_STATE_FOR = {"run": "running", "throttle": "throttled", "checkpoint": "checkpointing", "defer": "idle"}


def post(payload: dict) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    name = sys.argv[2] if len(sys.argv) > 2 else "sim-1"
    lookahead = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    delay = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0  # segundos entre ticks (ao vivo)

    load = 0.0
    node_state = "idle"
    print(f"{'tick':>4} {'action':>11} {'pwm':>4}  reason")
    print("-" * 70)
    for i in range(n):
        cmd = post({
            "node_id": name,
            "irradiance_frac": 1.0,   # frota: deixa o relogio orbital do backend gerar o eclipse
            "load_frac": load,
            "state": node_state,
            "lookahead": lookahead,
        })
        print(f"{i:>4} {cmd['action']:>11} {cmd['target_pwm']:>4}  {cmd['reason']}", flush=True)
        load = cmd["target_pwm"] / 255.0
        node_state = _STATE_FOR.get(cmd["action"], "idle")
        if delay > 0:
            time.sleep(delay)
    print("-" * 70)
    print(f"OK: {n} passos para o no '{name}' (lookahead={lookahead})")


if __name__ == "__main__":
    main()
