PRAGMA foreign_keys = ON;

-- =========================================================
-- 1. PERSONS
-- One row per elder being monitored
-- =========================================================

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    full_name TEXT NOT NULL,

    age INTEGER NOT NULL
        CHECK (age BETWEEN 0 AND 120),

    notes TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. DAILY CHECK-INS
-- One row = one person's daily check-in
-- Raw signals are stored here and NEVER overwritten
-- =========================================================

CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    person_id INTEGER NOT NULL,

    check_in_date TEXT NOT NULL,

    response_latency_seconds REAL NOT NULL
        CHECK (response_latency_seconds >= 0),

    sentiment_score REAL NOT NULL
        CHECK (sentiment_score BETWEEN -1.0 AND 1.0),

    medication_morning_confirmed INTEGER NOT NULL
        CHECK (medication_morning_confirmed IN (0, 1)),

    medication_evening_confirmed INTEGER NOT NULL
        CHECK (medication_evening_confirmed IN (0, 1)),

    -- Final state of the day's call.
    -- Detailed retry history is stored in call_attempts.
    call_answered INTEGER NOT NULL
        CHECK (call_answered IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (person_id)
        REFERENCES persons(id)
        ON DELETE CASCADE,

    -- A person can have only one daily check-in.
    UNIQUE (person_id, check_in_date)
);


CREATE INDEX IF NOT EXISTS idx_checkins_person_date
ON check_ins(person_id, check_in_date);


-- =========================================================
-- 3. CALL ATTEMPTS
-- Preserves unanswered calls and retries
-- =========================================================

CREATE TABLE IF NOT EXISTS call_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    check_in_id INTEGER NOT NULL,

    attempt_number INTEGER NOT NULL
        CHECK (attempt_number >= 1),

    answered INTEGER NOT NULL
        CHECK (answered IN (0, 1)),

    response_latency_seconds REAL,

    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (check_in_id)
        REFERENCES check_ins(id)
        ON DELETE CASCADE,

    UNIQUE (check_in_id, attempt_number)
);


CREATE INDEX IF NOT EXISTS idx_call_attempts_checkin
ON call_attempts(check_in_id);


-- =========================================================
-- 4. ANOMALY EVENTS
-- Stores the output of the anomaly-scoring system
-- Separate from raw check-in data
-- =========================================================

CREATE TABLE IF NOT EXISTS anomaly_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    check_in_id INTEGER NOT NULL,

    anomaly_score REAL NOT NULL
        CHECK (anomaly_score BETWEEN 0.0 AND 1.0),

    is_anomaly INTEGER NOT NULL
        CHECK (is_anomaly IN (0, 1)),

    reason TEXT,

    scoring_version TEXT NOT NULL DEFAULT 'v1',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (check_in_id)
        REFERENCES check_ins(id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_anomalies_checkin
ON anomaly_events(check_in_id);


-- =========================================================
-- 5. ESCALATIONS
-- Stores what action the system decided to take
-- =========================================================

CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    anomaly_id INTEGER NOT NULL,

    escalation_level TEXT NOT NULL
        CHECK (
            escalation_level IN (
                'none',
                'low',
                'medium',
                'high'
            )
        ),

    action TEXT NOT NULL,

    resolved INTEGER NOT NULL DEFAULT 0
        CHECK (resolved IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (anomaly_id)
        REFERENCES anomaly_events(id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_escalations_anomaly
ON escalations(anomaly_id);