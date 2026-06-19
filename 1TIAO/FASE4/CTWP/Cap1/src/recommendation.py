"""
Agricultural management recommendation engine (Python).

Converts the regression model PREDICTIONS into suggested ACTIONS for the
manager — irrigation, fertilization and yield reading — fulfilling the
assignment's goal ("sugerir ações futuras de irrigação e manejo baseadas nas
previsões geradas").

Each function returns a (level, text) tuple, where `level` ∈
{"ok", "warning", "critical"} maps directly to st.success / st.warning /
st.error in the dashboard. The `text` is in Portuguese (user-facing).
"""
from __future__ import annotations

from config import OPTIMAL_PH, OPTIMAL_HUMIDITY


def recommend_irrigation(volume_l_m2: float, humidity: float,
                         temperature: float) -> tuple[str, str]:
    """Irrigation recommendation from the predicted volume (L/m²)."""
    if volume_l_m2 < 1.5:
        return ("ok", "Umidade adequada. Não é necessário irrigar nas próximas horas.")
    if volume_l_m2 < 5.0:
        return ("warning",
                f"Umidade abaixo do ideal. Aplicar lâmina moderada de "
                f"{volume_l_m2:.1f} L/m².")
    return ("critical",
            f"Solo seco ({humidity:.0f}%) com temperatura de {temperature:.0f} °C. "
            f"Irrigar {volume_l_m2:.1f} L/m² com urgência para evitar estresse hídrico.")


def recommend_fertilization(fertilizer_kg_ha: float, n: int, p: int, k: int,
                            ph: float) -> tuple[str, str]:
    """Fertilization recommendation from the predicted amount (kg/ha)."""
    missing = [name for name, v in (("N", n), ("P", p), ("K", k)) if v == 0]
    missing_txt = ", ".join(missing) if missing else "nenhum"

    if fertilizer_kg_ha < 35:
        return ("ok", "Nutrientes (N/P/K) e pH adequados. Sem aplicação necessária.")
    if fertilizer_kg_ha < 75:
        return ("warning",
                f"Déficit moderado. Aplicar {fertilizer_kg_ha:.1f} kg/ha, "
                f"priorizando: {missing_txt}.")

    deviation = abs(ph - OPTIMAL_PH)
    ph_msg = (f" e pH {ph:.1f} (desvio de {deviation:.1f} do ótimo {OPTIMAL_PH})"
              if deviation > 0.4 else "")
    lime_hint = " Recomenda-se calagem (pH < 6,0)." if ph < 6.0 else ""
    return ("critical",
            f"Déficit severo — ausentes: {missing_txt}{ph_msg}. "
            f"Aplicar {fertilizer_kg_ha:.1f} kg/ha.{lime_hint}")


def recommend_yield(yield_ton_ha: float) -> tuple[str, str]:
    """Interpret the predicted yield (ton/ha)."""
    if yield_ton_ha >= 3.5:
        return ("ok",
                f"Produtividade estimada: {yield_ton_ha:.2f} ton/ha — "
                f"condições favoráveis.")
    if yield_ton_ha >= 1.5:
        return ("warning",
                f"Produtividade estimada: {yield_ton_ha:.2f} ton/ha — "
                f"condições subótimas. Seguir as recomendações pode elevar o rendimento.")
    return ("critical",
            f"Produtividade estimada: {yield_ton_ha:.2f} ton/ha — "
            f"condições críticas. Ação imediata necessária para evitar perdas na safra.")


def limiting_factors(humidity: float, ph: float, total_npk: int,
                     temperature: float) -> list[str]:
    """List the factors pulling the scenario away from the agronomic optimum."""
    factors: list[str] = []
    if humidity < 40:
        factors.append(f"umidade crítica ({humidity:.0f}%)")
    elif abs(humidity - OPTIMAL_HUMIDITY) > 20:
        factors.append(f"umidade distante do ótimo ({humidity:.0f}% vs {OPTIMAL_HUMIDITY:.0f}%)")
    if ph < 5.8 or ph > 7.0:
        factors.append(f"pH fora da faixa ideal ({ph:.1f})")
    if total_npk == 0:
        factors.append("nenhum nutriente presente (N, P e K ausentes)")
    elif total_npk < 2:
        factors.append(f"apenas {total_npk}/3 nutrientes presentes")
    if temperature > 35:
        factors.append(f"temperatura elevada ({temperature:.0f} °C)")
    elif temperature < 18:
        factors.append(f"temperatura baixa ({temperature:.0f} °C)")
    return factors
