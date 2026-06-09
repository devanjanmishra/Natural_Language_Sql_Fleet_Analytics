-- Fleet telemetry warehouse — simple star schema
-- Fact: telemetry readings.  Dimensions: vehicle, date.
-- Plus a maintenance_log table (free text) for the optional semantic-search module.

CREATE TABLE IF NOT EXISTS dim_vehicle (
    vehicle_id      INT PRIMARY KEY,
    registration    VARCHAR(16)  NOT NULL,
    model           VARCHAR(40)  NOT NULL,
    model_raw       VARCHAR(40)  NOT NULL,   -- messy free-entry value, for canonicalization demo
    fuel_type       VARCHAR(16)  NOT NULL,   -- diesel / electric / hybrid
    region          VARCHAR(32)  NOT NULL,
    in_service_date DATE         NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_telemetry (
    reading_id      BIGINT PRIMARY KEY AUTO_INCREMENT,
    vehicle_id      INT          NOT NULL,
    reading_ts      DATETIME     NOT NULL,
    odometer_km     INT          NOT NULL,
    speed_kmph      DECIMAL(5,1) NOT NULL,
    engine_temp_c   DECIMAL(5,1) NOT NULL,
    fuel_level_pct  DECIMAL(5,1) NOT NULL,
    battery_soc_pct DECIMAL(5,1),            -- null for non-electric
    fault_code      VARCHAR(8),              -- null when healthy
    INDEX idx_vehicle (vehicle_id),
    INDEX idx_ts (reading_ts),
    FOREIGN KEY (vehicle_id) REFERENCES dim_vehicle(vehicle_id)
);

CREATE TABLE IF NOT EXISTS maintenance_log (
    log_id          INT PRIMARY KEY AUTO_INCREMENT,
    vehicle_id      INT          NOT NULL,
    log_date        DATE         NOT NULL,
    technician      VARCHAR(40)  NOT NULL,
    note            TEXT         NOT NULL,   -- free-text → embedded for semantic search
    FOREIGN KEY (vehicle_id) REFERENCES dim_vehicle(vehicle_id)
);
