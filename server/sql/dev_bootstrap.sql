-- Local development bootstrap for ANPR dashboard.
-- Applied automatically by docker-compose on first MySQL start.

CREATE USER IF NOT EXISTS 'analytics_ai'@'%' IDENTIFIED BY 'anpr_dev';
GRANT SELECT ON aiserver.* TO 'analytics_ai'@'%';
FLUSH PRIVILEGES;

CREATE TABLE IF NOT EXISTS anpr_app_users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(64) NOT NULL DEFAULT 'admin',
  must_change_password TINYINT(1) NOT NULL DEFAULT 0,
  token_version INT NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  disabled_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_anpr_app_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sites (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vehicle_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  camera_id VARCHAR(64) NOT NULL,
  vehicle_num VARCHAR(32) NULL,
  vehicle_num_raw VARCHAR(32) NULL,
  vehicle_category VARCHAR(64) NULL,
  vehicle_type VARCHAR(64) NULL,
  ocr_confidence DECIMAL(5,2) NULL,
  plate_read_trust VARCHAR(32) NULL,
  plate_read_risk_flags JSON NULL,
  plate_read_metrics JSON NULL,
  timestamp BIGINT NULL,
  full_image_url VARCHAR(512) NULL,
  plate_url VARCHAR(512) NULL,
  was_corrected TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_vehicle_events_event_id (event_id),
  KEY idx_vehicle_events_created_at (created_at),
  KEY idx_vehicle_events_camera_id (camera_id),
  KEY idx_vehicle_events_vehicle_num (vehicle_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS traffic_violations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  violation_type VARCHAR(64) NOT NULL,
  score DECIMAL(5,2) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_traffic_violations_event_id (event_id),
  KEY idx_traffic_violations_type (violation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS violation_ticket_flags (
  violation_id BIGINT UNSIGNED NOT NULL,
  flag TINYINT NOT NULL DEFAULT 0,
  challan_id BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (violation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lpr_vehicle_lists (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  name VARCHAR(255) NOT NULL,
  notes TEXT NULL,
  site_id BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lpr_vehicle_list_vehicles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vehicle_list_id BIGINT UNSIGNED NOT NULL,
  conditions JSON NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  KEY idx_lpr_list_vehicles_list_id (vehicle_list_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lpr_rules (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  barrierOpen TINYINT(1) NOT NULL DEFAULT 0,
  filterType VARCHAR(32) NOT NULL DEFAULT 'plate',
  vehicleListIds TEXT NULL,
  name VARCHAR(255) NOT NULL,
  access_type VARCHAR(64) NOT NULL,
  security_type VARCHAR(64) NOT NULL,
  priority INT NOT NULL DEFAULT 10,
  site_id BIGINT UNSIGNED NULL,
  conditions JSON NOT NULL,
  notes TEXT NULL,
  valid_from DATETIME NULL,
  valid_to DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO anpr_app_users (email, password_hash, role, must_change_password)
VALUES (
  'admin@anpr.local',
  '$2b$10$BWCedgkLoZWG/kRTA/K17uDLHPA6SkayBxvMzf33x2AUZ8C..L.mi',
  'admin',
  0
)
ON DUPLICATE KEY UPDATE email = email;

INSERT INTO sites (id, name) VALUES (1, 'Rodriguez')
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO lpr_vehicle_lists (id, enabled, name, notes, site_id, created_at, updated_at)
VALUES (1, 1, 'Stolen vehicles', 'Demo watchlist', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO lpr_vehicle_list_vehicles (vehicle_list_id, conditions, created_at, updated_at)
SELECT 1, JSON_OBJECT('plate', 'ABC1234'), NOW(), NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM lpr_vehicle_list_vehicles WHERE vehicle_list_id = 1 LIMIT 1
);

INSERT INTO lpr_rules (
  enabled, barrierOpen, filterType, vehicleListIds, name, access_type, security_type,
  priority, site_id, conditions, notes, created_at, updated_at
)
SELECT
  1, 0, 'plate', '""', 'Demo alert rule', 'deny', 'high', 10, 1,
  JSON_OBJECT('camera_ids', JSON_ARRAY('AEYE_1', 'AEYE_2')),
  'Local dev seed rule', NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM lpr_rules LIMIT 1);

-- Seed vehicle reads for the last 7 days (stored in IST wall clock per site.config.json).
INSERT INTO vehicle_events (
  event_id, camera_id, vehicle_num, vehicle_category, vehicle_type,
  ocr_confidence, timestamp, full_image_url, plate_url, created_at
)
SELECT
  CONCAT('evt-', n),
  ELT(1 + (n MOD 6), 'AEYE_1', 'AEYE_2', 'AEYE_3', 'AEYE_4', 'AEYE_5', 'AEYE_6'),
  CONCAT('ABC', LPAD(1000 + n, 4, '0')),
  ELT(1 + (n MOD 3), 'MOTORCYCLE', 'CAR', 'TRUCK'),
  ELT(1 + (n MOD 3), 'PRIVATE', 'PUBLIC_UTILITY', 'ELECTRIC'),
  ROUND(75 + (n MOD 20) + RAND(), 2),
  UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL (n MOD 168) HOUR)) * 1000,
  CONCAT('/receiver-results/demo/scene-', n, '.jpg'),
  CONCAT('/receiver-results/demo/plate-', n, '.jpg'),
  DATE_SUB(NOW(), INTERVAL (n MOD 168) HOUR)
FROM (
  SELECT a.N + b.N * 10 + 1 AS n
  FROM
    (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
     UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
    (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
     UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b
  WHERE a.N + b.N * 10 < 80
) seq
WHERE NOT EXISTS (SELECT 1 FROM vehicle_events LIMIT 1);

INSERT INTO traffic_violations (event_id, violation_type, score)
SELECT ve.event_id, vt.violation_type, ROUND(70 + RAND() * 25, 2)
FROM vehicle_events ve
JOIN (
  SELECT 'NO_HELMET' AS violation_type
  UNION ALL SELECT 'WRONG_PARKING'
  UNION ALL SELECT 'TRIPLE_RIDING'
  UNION ALL SELECT 'WRONG_ROUTE'
) vt
WHERE MOD(ve.id, 4) = 0
  AND NOT EXISTS (SELECT 1 FROM traffic_violations LIMIT 1)
LIMIT 20;
