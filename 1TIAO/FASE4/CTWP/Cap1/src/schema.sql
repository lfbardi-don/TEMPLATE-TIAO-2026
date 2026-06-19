-- ===========================================================================
-- FarmTech Solutions — schema.sql  (PostgreSQL — Ir Além 1)
-- ===========================================================================
-- Simple relational model to store sensor data (real or simulated in Wokwi)
-- and the predictions produced by the ML models.
--
-- Idempotent: can be executed multiple times without dropping data (uses
-- IF NOT EXISTS and ON CONFLICT). Executed automatically by src/database.py
-- (init_db) and also mounted by docker-compose on container creation.
-- ===========================================================================

-- IoT devices registered on the farm -------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id_device        INTEGER      PRIMARY KEY,   -- unique node id
    plantation_sector VARCHAR(60),               -- farm plot / sector
    sensor_model     VARCHAR(60),                -- hardware (e.g., ESP32 + DHT22)
    install_date     DATE
);

-- History: sensor readings + AI predictions ------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id_reading       SERIAL       PRIMARY KEY,
    id_device        INTEGER      NOT NULL REFERENCES devices (id_device),
    reading_ts       TIMESTAMP    NOT NULL DEFAULT now(),

    -- Sensor readings
    temperature      REAL,                        -- °C
    ph               REAL,                        -- soil acidity
    soil_humidity    REAL,                        -- % humidity
    n                INTEGER      DEFAULT 0,       -- Nitrogen present? (0/1)
    p                INTEGER      DEFAULT 0,       -- Phosphorus present? (0/1)
    k                INTEGER      DEFAULT 0,       -- Potassium present? (0/1)
    pump             INTEGER      DEFAULT 0,       -- pump active? (0/1)

    -- Regression model predictions (PARTE 1 + PARTE 2)
    yield_ton_ha           REAL,
    irrigation_volume_l_m2 REAL,
    fertilizer_kg_ha       REAL,

    -- Management recommendations (text)
    recommendation_irrigation    TEXT,
    recommendation_fertilization TEXT,
    recommendation_yield         TEXT
);

-- Index to speed up history lookups by device/time -----------------------------
CREATE INDEX IF NOT EXISTS idx_readings_device_ts
    ON sensor_readings (id_device, reading_ts DESC);

-- Example device (North plot) --------------------------------------------------
INSERT INTO devices (id_device, plantation_sector, sensor_model, install_date)
VALUES (101, 'Talhão Norte - Soja', 'ESP32 + DHT22 + sensores NPK', '2026-06-15')
ON CONFLICT (id_device) DO NOTHING;

-- View joining reading history + device sector (JOIN) --------------------------
CREATE OR REPLACE VIEW history_view AS
SELECT
    r.id_reading,
    d.plantation_sector,
    d.sensor_model,
    r.reading_ts,
    r.temperature,
    r.ph,
    r.soil_humidity,
    r.n, r.p, r.k, r.pump,
    r.yield_ton_ha,
    r.irrigation_volume_l_m2,
    r.fertilizer_kg_ha,
    r.recommendation_irrigation,
    r.recommendation_fertilization,
    r.recommendation_yield
FROM sensor_readings r
INNER JOIN devices d
    ON r.id_device = d.id_device
ORDER BY r.id_reading DESC;
