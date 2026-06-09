"""Fisica orbital, solar, de bateria e termica. Deterministica: o ruido de sensor entra fora daqui."""

from __future__ import annotations

import math

from ephemnous.core.models import NodeParams, NodeState, Telemetry

SIGMA = 5.670374419e-8  # Stefan-Boltzmann (W/m^2 K^4)
R_EARTH_KM = 6371.0
MU_EARTH = 398600.0     # parametro gravitacional da Terra (km^3/s^2)


def orbit_period_s(altitude_km: float) -> float:
    """T = 2 pi sqrt(a^3 / mu), a = R_terra + altitude (3a lei de Kepler)."""
    a = R_EARTH_KM + altitude_km
    return 2.0 * math.pi * math.sqrt(a**3 / MU_EARTH)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _smoothstep(x: float) -> float:
    x = _clamp(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def eclipse_fraction(beta_deg: float, altitude_km: float) -> float:
    """Fracao da orbita em eclipse (0..~0.4), sombra cilindrica."""
    beta = math.radians(beta_deg)
    h, re = altitude_km, R_EARTH_KM
    denom = (re + h) * math.cos(beta)
    if denom <= 0:
        return 0.0
    arg = math.sqrt(h * h + 2 * re * h) / denom
    if arg >= 1.0:  # beta alto demais, sem eclipse
        return 0.0
    return math.acos(arg) / math.pi


def orbit_phase(t_s: float, period_s: float) -> float:
    return (t_s % period_s) / period_s


def illumination(phase: float, f_ecl: float, edge: float = 0.03) -> float:
    """Iluminacao 0..1. Eclipse centrado em phase=0.5 com penumbra (smoothstep)."""
    if f_ecl <= 0:
        return 1.0
    half = f_ecl / 2.0
    d = abs(phase - 0.5)  # distancia ao centro do eclipse
    return _smoothstep((d - (half - edge)) / (2.0 * edge))


def in_eclipse(phase: float, f_ecl: float) -> bool:
    return f_ecl > 0 and abs(phase - 0.5) <= f_ecl / 2.0


def initial_state(p: NodeParams) -> NodeState:
    return NodeState(
        t_s=0.0,
        soc_frac=0.8,
        temp_k=p.t_init_k,
        thermal_margin_k=p.t_max_k - p.t_init_k,
        power_avail_w=0.0,
        in_eclipse=False,
        orbit_phase=0.0,
    )


def advance(state: NodeState, tel: Telemetry, p: NodeParams) -> NodeState:
    """Avanca o estado fisico por um passo dt (Euler)."""
    t = state.t_s + p.dt_s
    phase = orbit_phase(t, p.orbit_period_s)
    f_ecl = eclipse_fraction(p.beta_deg, p.altitude_km)

    base_illum = 0.0 if tel.force_eclipse else illumination(phase, f_ecl)
    eff = _clamp(base_illum * _clamp(tel.irradiance_frac, 0.0, 1.0), 0.0, 1.0)

    load = _clamp(tel.load_frac, 0.0, 1.0)

    # termico
    q_solar = p.absorptivity * p.s_solar_w_m2 * p.a_panel_m2 * eff
    q_comp = load * p.q_comp_max_w
    q_rad = p.emissivity * SIGMA * p.a_rad_m2 * (state.temp_k**4 - p.t_sink_k**4)
    temp = state.temp_k + (p.dt_s / p.c_thermal_j_k) * (q_comp + q_solar - q_rad)

    # energia / bateria
    p_gen = p.panel_eff * p.s_solar_w_m2 * p.a_panel_m2 * eff
    p_draw = p.p_base_w + load * p.p_comp_max_w
    p_net = p_gen - p_draw
    e_cap_j = p.e_cap_wh * 3600.0
    energy_j = _clamp(state.soc_frac * e_cap_j + p_net * p.dt_s, 0.0, e_cap_j)
    soc = energy_j / e_cap_j

    return NodeState(
        t_s=t,
        soc_frac=soc,
        temp_k=temp,
        thermal_margin_k=p.t_max_k - temp,
        power_avail_w=max(p_gen, 0.0),
        in_eclipse=in_eclipse(phase, f_ecl) or tel.force_eclipse,
        orbit_phase=phase,
    )
