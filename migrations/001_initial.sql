-- 001_initial.sql
-- Начальная схема БД «300 Сердец»
-- Использует IF NOT EXISTS, чтобы не сломать старую БД.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    partner_name TEXT,
    partner_nick TEXT,
    gender TEXT,
    couple_id INTEGER,
    hearts_balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    tz TEXT DEFAULT 'Europe/Moscow',
    avatar_pref TEXT DEFAULT 'auto',
    last_gift_reminder TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS couples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id INTEGER,
    user_b_id INTEGER,
    status TEXT DEFAULT 'pending',
    common_balance INTEGER DEFAULT 0,
    status_level TEXT,
    avatar_type TEXT,
    relationship_start TEXT,
    last_love_status TEXT,
    last_hearts_status TEXT,
    last_status_check TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    title TEXT,
    added_by INTEGER,
    status TEXT DEFAULT 'pending',
    rating_a INTEGER,
    rating_b INTEGER,
    watched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    text TEXT,
    author_id INTEGER,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS friday_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    wish_id INTEGER,
    wish_text TEXT,
    is_bot_wish INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    week_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    from_user INTEGER,
    to_user INTEGER,
    gift_key TEXT,
    is_shared INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    title TEXT,
    date TEXT,
    remind INTEGER DEFAULT 1,
    date_type TEXT DEFAULT 'other',
    owner_id INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    couple_id INTEGER PRIMARY KEY,
    friday_mode INTEGER DEFAULT 1,
    notifications INTEGER DEFAULT 1,
    question_time TEXT DEFAULT '10:00',
    friday_time TEXT DEFAULT '18:00',
    tests_paused INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    code TEXT,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    telegram_id INTEGER,
    avatar_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    invited_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS question_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    q_id INTEGER,
    user_a_answer TEXT,
    user_b_answer TEXT,
    matched INTEGER DEFAULT 0,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    package INTEGER,
    price INTEGER,
    bonus_percent INTEGER,
    hearts_amount INTEGER,
    is_first INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    from_user INTEGER,
    to_user INTEGER,
    amount INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    title TEXT,
    price INTEGER,
    author_id INTEGER,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    from_user INTEGER,
    to_user INTEGER,
    amount INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_num INTEGER,
    title TEXT,
    level TEXT,
    mechanics TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER,
    order_num INTEGER,
    text TEXT,
    q_type TEXT,
    option_a TEXT,
    option_b TEXT
);

CREATE TABLE IF NOT EXISTS test_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    test_id INTEGER,
    question_id INTEGER,
    user_a_answer TEXT,
    user_b_answer TEXT,
    matched INTEGER DEFAULT 0,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    test_id INTEGER,
    current_q INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    percent INTEGER,
    UNIQUE(couple_id, test_id)
);

CREATE TABLE IF NOT EXISTS portraits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    test_id INTEGER,
    percent INTEGER,
    matches INTEGER,
    total INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id INTEGER,
    question_id INTEGER,
    user_id INTEGER,
    answer TEXT,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(couple_id, question_id, user_id)
);

CREATE TABLE IF NOT EXISTS payments_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yookassa_id TEXT UNIQUE,
    user_id INTEGER,
    recipient_id INTEGER,
    hearts INTEGER,
    package INTEGER,
    bonus_percent INTEGER,
    is_first INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);