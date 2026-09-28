"""Deterministic, explicitly synthetic Fendt 314 telemetry for the product journey."""
from datetime import datetime, timedelta, timezone
from io import StringIO
import csv
import math

from tractor_usage.application.operational_telemetry import CSV_COLUMNS

SCENARIOS = (
    {"id": "aurora-regular", "label": "Operação regular", "fleet_name": "Frota Aurora (simulada)", "machine_name": "Aurora 01", "file_name": "aurora-01-simulado.csv", "description": "Uma hora de deslocamento regular, para explorar dados sem alertas físicos.", "followup_for": None},
    {"id": "aurora-carga", "label": "Carga elevada", "fleet_name": "Frota Aurora (simulada)", "machine_name": "Aurora 02", "file_name": "aurora-02-simulado.csv", "description": "Uma hora com variações de carga e aderência, para analisar episódios e abrir uma vistoria.", "followup_for": None},
    {"id": "horizonte-inicial", "label": "Primeira vistoria", "fleet_name": "Frota Horizonte (simulada)", "machine_name": "Horizonte 01", "file_name": "horizonte-01-inicial-simulado.csv", "description": "Primeiro período com ocorrências para registrar achados de uma vistoria simulada.", "followup_for": None},
    {"id": "horizonte-novo-periodo", "label": "Após a vistoria", "fleet_name": "Frota Horizonte (simulada)", "machine_name": "Horizonte 01", "file_name": "horizonte-01-novo-periodo-simulado.csv", "description": "Período posterior, para distinguir novos episódios da evidência já vistoriada.", "followup_for": "horizonte-inicial"},
)


def scenario_csv(scenario_id: str) -> str:
    if scenario_id not in {item["id"] for item in SCENARIOS}:
        raise KeyError(scenario_id)
    start = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    if scenario_id == "horizonte-novo-periodo":
        start += timedelta(days=2)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for second in range(3600):
        minute = second // 60
        # Smooth background signal; separated sustained workload intervals produce
        # causal episodes. No scores or alert flags are encoded in the CSV.
        wave = math.sin(second / 19)
        loaded = scenario_id != "aurora-regular" and minute in ({10, 11, 30, 31, 50} if scenario_id == "aurora-carga" else {15, 16, 40})
        if loaded:
            work_wave = math.sin(second / 10)
            rpm = 1500 + 495 * work_wave
            torque = 65 + 51 * work_wave
            load = 75 + 41 * work_wave
            ground = 2 + 0.8 * work_wave
            wheel = ground / (0.8 + 0.07 * work_wave)
            pto = 500 + 100 * work_wave
            hitch, work = 40 + 15 * work_wave, 1
            force, draft = 20 + 10 * work_wave, 10000 + 5000 * work_wave
        else:
            rpm = 1700 + 35 * wave
            torque = 38 + 5 * math.sin(second / 13)
            load = 43 + 6 * math.sin(second / 11)
            ground = 5.5 + 0.15 * wave
            wheel = ground / 0.97
            pto, hitch, work, force, draft = 0, 92, 0, 0, 0
        values = {
            "observed_at_utc": (start + timedelta(seconds=second)).isoformat().replace("+00:00", "Z"),
            "mission_index": 0,
            "engine_rpm": rpm, "actual_engine_torque_pct": torque, "engine_load_pct": load,
            "accelerator_pct": 83 if loaded else 55, "coolant_temp_c": 87 + math.sin(second / 180),
            "front_axle_speed_kph": wheel * 3.6, "speed_over_ground_mps": ground,
            "ground_implement_speed_mmps": ground * 1000, "wheel_vehicle_speed_kph": wheel * 3.6,
            "rear_pto_rpm": pto, "rear_hitch_position": hitch, "rear_hitch_in_work": work,
            "rear_link_force_pct": force, "rear_draft_n": draft,
            "ground_machine_speed_mps": ground, "machine_selected_speed_mps": ground,
            "wheel_machine_speed_mps": wheel,
        }
        writer.writerow({key: round(value, 3) if isinstance(value, float) else value for key, value in values.items()})
    return output.getvalue()
