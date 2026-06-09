"""Entidades puras do dominio (dataclasses). Sem framework, sem IO.

Unidades canonicas: potencia em Watts, temperatura em Kelvin, fracoes em 0..1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeParams:
    """Parametros fisicos de um no (satelite). Defaults ~ LEO 550 km."""

    # orbita
    orbit_period_s: float = 5730.0   # Kepler para 550 km (= physics.orbit_period_s(550), ~95.5 min)
    altitude_km: float = 550.0
    beta_deg: float = 0.0            # angulo beta (afeta duracao do eclipse)
    dt_s: float = 300.0             # segundos orbitais por passo (1 orbita ~ 19 passos)

    # termico (massa concentrada, radiacao Stefan-Boltzmann)
    c_thermal_j_k: float = 5000.0
    a_rad_m2: float = 0.2
    emissivity: float = 0.85
    t_sink_k: float = 2.7
    t_max_k: float = 313.15          # 40 C
    t_init_k: float = 293.15         # 20 C

    # solar / painel
    s_solar_w_m2: float = 1361.0     # constante solar
    a_panel_m2: float = 0.2
    absorptivity: float = 0.3        # fracao do sol absorvida como calor
    panel_eff: float = 0.3           # fracao convertida em eletricidade

    # potencia / bateria
    p_base_w: float = 5.0            # housekeeping
    p_comp_max_w: float = 40.0       # consumo eletrico a plena carga
    q_comp_max_w: float = 40.0       # calor gerado a plena carga
    e_cap_wh: float = 40.0


@dataclass
class NodeState:
    """Estado fisico de um no num instante (a verdade avancada pelo backend)."""

    t_s: float               # tempo orbital acumulado
    soc_frac: float          # estado de carga da bateria 0..1
    temp_k: float
    thermal_margin_k: float  # t_max - temp
    power_avail_w: float     # potencia solar disponivel agora
    in_eclipse: bool
    orbit_phase: float       # 0..1


@dataclass
class Telemetry:
    """O que um no reporta. irradiance_frac vem do potenciometro (sol/eclipse)."""

    node_name: str
    irradiance_frac: float = 1.0
    force_eclipse: bool = False
    temp_k: float | None = None     # opcional (se o device tiver sensor)
    load_frac: float = 0.0          # 0..1 (espelha o PWM atual)
    state: str = "idle"
    ts_device: int | None = None


@dataclass
class Forecast:
    """Previsao multi-passo do forecaster."""

    horizon_s: int
    pred_power_w: list[float]
    pred_thermal_margin_k: list[float]
    model_version: str = "stub"


@dataclass
class Decision:
    """Decisao do MPC para o proximo passo."""

    action: str          # run | defer | checkpoint | throttle
    target_pwm: int      # 0..255
    lookahead: int = 0   # 0 = modo burro (reativo)
    reason: str = ""
    mode: str = "mpc"    # mpc | greedy


@dataclass
class History:
    """Janela de historico recente por no para o forecaster ML extrair lags.

    A persistencia ignora; o ML usa.
    """

    power: list[float]
    temp: list[float]
    load: list[float]
    phase: list[float]
    soc: list[float]
    beta: float
    f_ecl: float
    period_s: float
