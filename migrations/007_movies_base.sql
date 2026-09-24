-- База фильмов для случайного фильма
CREATE TABLE IF NOT EXISTS movies_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    genre TEXT,
    duration INTEGER,
    description TEXT,
    rating REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_movies_base_genre ON movies_base(genre);

-- Лимиты случайного фильма
CREATE TABLE IF NOT EXISTS movie_limits (
    user_id INTEGER,
    date TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, date)
);