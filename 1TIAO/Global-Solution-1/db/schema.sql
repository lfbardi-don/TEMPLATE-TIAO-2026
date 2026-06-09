-- Schema do banco (PostgreSQL). Idempotente.
-- Unidades: potencia em Watts, temperatura em Kelvin, fracoes em 0..1.

CREATE TABLE IF NOT EXISTS nodes (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL CHECK (kind IN ('wokwi', 'sim')),
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Telemetria crua recebida do no (append-only).
CREATE TABLE IF NOT EXISTS telemetry (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id         BIGINT NOT NULL REFERENCES nodes(id),
    ts_device       BIGINT,                              -- epoch ms reportado pelo device
    ts_server       TIMESTAMPTZ NOT NULL DEFAULT now(),
    irradiance_frac DOUBLE PRECISION NOT NULL,           -- 0..1
    force_eclipse   BOOLEAN NOT NULL DEFAULT false,
    temp_k          DOUBLE PRECISION,                     -- opcional
    load_frac       DOUBLE PRECISION NOT NULL DEFAULT 0,  -- 0..1
    state           TEXT NOT NULL DEFAULT 'idle'
                    CHECK (state IN ('idle', 'running', 'throttled', 'checkpointing')),
    raw             JSONB
);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry (node_id, ts_server DESC);

-- Estado fisico derivado pelo backend a partir da telemetria + tempo.
CREATE TABLE IF NOT EXISTS node_state (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id          BIGINT NOT NULL REFERENCES nodes(id),
    ts_server        TIMESTAMPTZ NOT NULL DEFAULT now(),
    soc_frac         DOUBLE PRECISION NOT NULL,    -- 0..1
    temp_k           DOUBLE PRECISION NOT NULL,
    thermal_margin_k DOUBLE PRECISION NOT NULL,    -- T_max - T
    power_avail_w    DOUBLE PRECISION NOT NULL,
    in_eclipse       BOOLEAN NOT NULL,
    orbit_phase      DOUBLE PRECISION NOT NULL     -- 0..1
);
CREATE INDEX IF NOT EXISTS idx_node_state_node_ts ON node_state (node_id, ts_server DESC);

-- Previsoes do forecaster (multi-passo; arrays em JSONB).
CREATE TABLE IF NOT EXISTS forecasts (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id               BIGINT NOT NULL REFERENCES nodes(id),
    ts_server             TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_s             INTEGER NOT NULL,
    pred_power_w          JSONB NOT NULL,   -- [w_t+1, w_t+2, ...]
    pred_thermal_margin_k JSONB NOT NULL,   -- [m_t+1, m_t+2, ...]
    model_version         TEXT NOT NULL DEFAULT 'stub',
    features              JSONB
);

-- Decisoes do MPC (uma por ciclo de controle).
CREATE TABLE IF NOT EXISTS decisions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id     BIGINT NOT NULL REFERENCES nodes(id),
    ts_server   TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_id BIGINT REFERENCES forecasts(id),
    action      TEXT NOT NULL CHECK (action IN ('run', 'defer', 'checkpoint', 'throttle')),
    target_pwm  INTEGER NOT NULL CHECK (target_pwm BETWEEN 0 AND 255),
    lookahead   INTEGER NOT NULL DEFAULT 0,    -- 0 = reativo
    reason      TEXT,
    mode        TEXT NOT NULL DEFAULT 'mpc' CHECK (mode IN ('mpc', 'greedy'))
);
CREATE INDEX IF NOT EXISTS idx_decisions_node_ts ON decisions (node_id, ts_server DESC);

-- Catalogo de cargas a escalonar.
CREATE TABLE IF NOT EXISTS jobs (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           TEXT NOT NULL,
    energy_cost_w  DOUBLE PRECISION NOT NULL,
    duration_s     INTEGER NOT NULL,
    checkpointable BOOLEAN NOT NULL DEFAULT true,
    priority       INTEGER NOT NULL DEFAULT 0
);

-- Execucoes de jobs (com checkpoints/defers).
CREATE TABLE IF NOT EXISTS runs (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id         BIGINT REFERENCES jobs(id),
    node_id        BIGINT NOT NULL REFERENCES nodes(id),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    status         TEXT NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running', 'deferred', 'checkpointed', 'done')),
    energy_used_wh DOUBLE PRECISION NOT NULL DEFAULT 0
);
