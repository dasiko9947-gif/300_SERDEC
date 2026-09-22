CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    couple_id INTEGER,
    user_id INTEGER,
    admin_id INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_type ON logs(type);

CREATE TABLE IF NOT EXISTS bans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    user_id INTEGER,
    reason TEXT,
    banned_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_bans_couple ON bans(couple_id);
CREATE INDEX IF NOT EXISTS idx_bans_user ON bans(user_id);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    audience TEXT,
    target_id INTEGER,
    text TEXT,
    button_text TEXT,
    button_url TEXT,
    sent_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    couple_id INTEGER,
    user_id INTEGER,
    amount INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);