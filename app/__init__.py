from flask import Flask, render_template, request, redirect, url_for, send_file, Response
from . import db
import sqlite3
import os
import logging

# Базовая настройка записи логов в файл
logging.basicConfig(
    filename='system.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def create_app():
    app = Flask(__name__)
    app.teardown_appcontext(db.close_db)

    @app.route('/', methods=['GET', 'POST'])
    def home():
        conn = get_db()
        if request.method == 'POST':
            task_type = request.form['task_type']
            description = request.form['description']
            priority = request.form['priority']
            
            conn.execute(
                'INSERT INTO tasks (task_type, description, priority) VALUES (?, ?, ?)',
                (task_type, description, priority)
            )
            conn.commit()
            return redirect(url_for('home'))

        analysts = conn.execute('SELECT * FROM analysts').fetchall()

        tasks = conn.execute('''
            SELECT tasks.*, analysts.name as analyst_name 
            FROM tasks 
            LEFT JOIN analysts ON tasks.analyst_id = analysts.id
        ''').fetchall()
        return render_template('index.html', analysts=analysts, tasks=tasks)

    # Запуск распределения
    @app.route('/distribute', methods=['POST'])
    def distribute():
        from app.services.distribution_service import distribute_tasks
        distribute_tasks()
        return redirect(url_for('home'))

    # Завершение задачи
    @app.route('/complete/<int:task_id>', methods=['POST'])
    def complete_task(task_id):
        conn = get_db()
        conn.execute('UPDATE tasks SET status = "Завершена" WHERE id = ?', (task_id,))
        conn.commit()
        return redirect(url_for('home'))

    # Эскалация задачи
    @app.route('/escalate/<int:task_id>', methods=['POST'])
    def escalate_task(task_id):
        conn = get_db()
        conn.execute('''
            UPDATE tasks 
            SET status = "Ожидает", analyst_id = NULL, priority = "high" 
            WHERE id = ?
        ''', (task_id,))
        conn.commit()
        return redirect(url_for('home'))

    @app.route('/settings')
    def settings():
        log_content = ""
        # Читаем последние 50 строк логов
        if os.path.exists('system.log'):
            with open('system.log', 'r', encoding='utf-8') as f:
                log_content = "".join(f.readlines()[-50:])
        
        # Ищем JSON-файлы в текущей директории
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        
        return render_template('settings.html', log_content=log_content, json_files=json_files)

    @app.route('/settings/view_logs')
    def view_logs():
        log_path = os.path.abspath('system.log')
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype='text/plain')
        return "Журнал пуст или еще не создан."

    @app.route('/settings/download_logs')
    def download_logs():
        log_path = os.path.abspath('system.log')
        if os.path.exists(log_path):
            return send_file(log_path, as_attachment=True)
        return redirect(url_for('settings'))

    @app.route('/settings/clear_logs', methods=['POST'])
    def clear_logs():
        # Очищаем файл логов
        open('system.log', 'w').close()
        logging.info("Системный журнал был принудительно очищен Суперадмином.")
        return redirect(url_for('settings'))

    @app.route('/settings/load_json', methods=['POST'])
    def load_json():
        json_file = request.form.get('json_file')
        # Здесь будет функция парсинга JSON и заливки в БД, пока просто пишем лог
        logging.info(f"Запущена инициализация базы аналитиков из файла: {json_file}")
        return redirect(url_for('settings'))

    @app.route('/settings/reset', methods=['POST'])
    def reset_db():
        conn = get_db()
        conn.execute('DELETE FROM tasks')
        conn.commit()
        logging.warning("Суперадмин очистил всю очередь задач (Опасная зона).")
        return redirect(url_for('settings'))

    @app.route('/update_analyst/<int:id>', methods=['POST'])
    def update_analyst(id):
        is_available = 1 if request.form.get('is_available') else 0
        max_open_tasks = request.form.get('max_open_tasks')
    
        conn = get_db()
        conn.execute(
            'UPDATE analysts SET is_available = ?, max_open_tasks = ? WHERE id = ?',
            (is_available, max_open_tasks, id)
        )
        conn.commit()
        return redirect(url_for('home'))


    return app