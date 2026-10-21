import json
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo.json')

def seed_data():
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Записываем аналитиков
    for analyst in data.get('analysts', []):
        cursor.execute(
            "INSERT INTO analysts (name, level, is_available, max_open_tasks) VALUES (?, ?, ?, ?)",
            (analyst['name'], analyst['level'], analyst['is_available'], analyst['max_open_tasks'])
        )

    # Записываем задачи
    for task in data.get('tasks', []):
        cursor.execute(
            "INSERT INTO tasks (task_type, description, priority) VALUES (?, ?, ?)",
            (task['task_type'], task['description'], task['priority'])
        )

    conn.commit()
    conn.close()
    print("Данные об аналитиках и задачах успешно загружены в базу!")

if __name__ == '__main__':
    seed_data()