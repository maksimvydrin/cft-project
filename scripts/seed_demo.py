import json
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo.json')

def seed_data():
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Убедимся, что папка instance существует, чтобы не было ошибки при создании базы
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Создаем каркас таблиц
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT NOT NULL,
            is_available INTEGER NOT NULL,
            max_open_tasks INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            description TEXT,
            priority TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Ожидает',
            analyst_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Записываем аналитиков
    for analyst in data.get('analysts', []):
        cursor.execute(
            "INSERT INTO analysts (name, level, is_available, max_open_tasks) VALUES (?, ?, ?, ?)",
            (analyst['name'], analyst['level'], analyst['is_available'], analyst['max_open_tasks'])
        )

    # 3. Записываем задачи
    for task in data.get('tasks', []):
        cursor.execute(
            "INSERT INTO tasks (task_type, description, priority) VALUES (?, ?, ?)",
            (task['task_type'], task['description'], task['priority'])
        )

    conn.commit()
    conn.close()
    print("Таблицы созданы, данные успешно загружены в базу!")

if __name__ == '__main__':
    seed_data()