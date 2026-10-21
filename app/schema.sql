DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS analysts;

CREATE TABLE analysts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    is_available BOOLEAN DEFAULT 1,
    max_open_tasks INTEGER NOT NULL
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL,
    status TEXT DEFAULT 'Ожидает',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analyst_id INTEGER,
    FOREIGN KEY (analyst_id) REFERENCES analysts (id)
);