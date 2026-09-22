-- Состояние пятницы: кто принял, кто подтвердил
ALTER TABLE friday_events ADD COLUMN user_a_accepted INTEGER DEFAULT 0;
ALTER TABLE friday_events ADD COLUMN user_b_accepted INTEGER DEFAULT 0;
ALTER TABLE friday_events ADD COLUMN user_a_done INTEGER DEFAULT 0;
ALTER TABLE friday_events ADD COLUMN user_b_done INTEGER DEFAULT 0;