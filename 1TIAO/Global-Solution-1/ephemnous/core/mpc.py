"""MPC heuristico preditivo: decide run/defer/checkpoint/throttle."""

from __future__ import annotations

from ephemnous.core.models import Decision, Forecast, NodeParams, NodeState

MARGIN_CRIT_K = 5.0    # folga termica critica -> throttle forte
MARGIN_LOW_K = 12.0    # folga moderada -> meia carga
SOC_LOW = 0.25         # bateria baixa -> adiar
CHECKPOINT_SOC = 0.45  # eclipse a vista + bateria abaixo disto -> checkpoint antes


def decide(
    state: NodeState,
    forecast: Forecast,
    p: NodeParams,
    lookahead: int = 3,
    mode: str = "mpc",
) -> Decision:
    if lookahead <= 0:
        # modo reativo: so enxerga o agora
        fut_margin = state.thermal_margin_k
        fut_power = state.power_avail_w
        eclipse_soon = state.in_eclipse
    else:
        k = max(1, min(lookahead, len(forecast.pred_thermal_margin_k)))
        fut_margin = min([state.thermal_margin_k, *forecast.pred_thermal_margin_k[:k]])
        fut_power = min([state.power_avail_w, *forecast.pred_power_w[:k]])
        eclipse_soon = fut_power < p.p_base_w   # sol previsto nao cobre nem o basico

    # 1) termico manda: folga critica prevista -> throttle forte
    if fut_margin < MARGIN_CRIT_K:
        return Decision("throttle", 40, lookahead, f"folga termica critica prevista ({fut_margin:.1f} K)", mode)

    # 2) eclipse chegando + bateria nao vai sobrar -> checkpoint antes de perder energia
    if eclipse_soon and state.soc_frac < CHECKPOINT_SOC:
        return Decision("checkpoint", 0, lookahead, f"eclipse a vista + SoC {state.soc_frac:.2f}: checkpoint antes", mode)

    # 3) sem energia agora e bateria baixa -> adiar
    if state.power_avail_w < p.p_base_w and state.soc_frac < SOC_LOW:
        return Decision("defer", 0, lookahead, "sem energia disponivel, adiando", mode)

    # 4) folga moderada -> meia carga
    if fut_margin < MARGIN_LOW_K:
        return Decision("throttle", 128, lookahead, f"folga moderada ({fut_margin:.1f} K): meia carga", mode)

    # 5) tudo folgado -> plena carga
    return Decision("run", 255, lookahead, "energia e termica folgadas", mode)
