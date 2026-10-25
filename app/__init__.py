from flask import Flask, render_template, request, redirect, url_for, send_file, Response, session
from . import db
import sqlite3
import os
import logging
import json

audit_logger = logging.getLogger('cft_audit')
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    file_handler = logging.FileHandler('system.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    audit_logger.addHandler(file_handler)

def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'app.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Вспомогательная функция для получения названия текущей базы
def get_current_scenario():
    if os.path.exists('current_scenario.txt'):
        with open('current_scenario.txt', 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "Не выбрана (Ручной режим)"

def create_app():
    app = Flask(__name__)
    app.secret_key = 'cft-service-desk-secret-key'
    app.teardown_appcontext(db.close_db)

    @app.before_request
    def check_auth():
        if 'role' not in session and request.endpoint not in ['login', 'static']:
            return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        conn = get_db()
        if request.method == 'POST':
            selected = request.form.get('role_select')
            if selected == 'admin':
                session['role'] = 'admin'
                session['user_name'] = 'Суперадмин'
            else:
                analyst_name = selected.split(':', 1)[1]
                session['role'] = 'analyst'
                session['user_name'] = analyst_name
            
            audit_logger.info(f"Вход в систему: {session['user_name']} (Роль: {session['role']})")
            return redirect(url_for('home'))

        analysts = conn.execute('SELECT * FROM analysts').fetchall()
        return render_template('login.html', analysts=analysts)

    @app.route('/logout')
    def logout():
        user = session.get('user_name', 'Неизвестный')
        audit_logger.info(f"Выход из системы: {user}")
        session.clear()
        return redirect(url_for('login'))

    @app.route('/', methods=['GET', 'POST'])
    def home():
        conn = get_db()
        if request.method == 'POST':
            if session.get('role') != 'admin':
                return redirect(url_for('home'))
                
            task_type = request.form['task_type']
            description = request.form['description']
            priority = request.form['priority']
            
            conn.execute(
                'INSERT INTO tasks (task_type, description, priority) VALUES (?, ?, ?)',
                (task_type, description, priority)
            )
            conn.commit()
            audit_logger.info(f"Суперадмин создал задачу: Тип={task_type}, Приоритет={priority}")
            return redirect(url_for('home'))

        analysts = conn.execute('SELECT * FROM analysts').fetchall()
        tasks = conn.execute('''
            SELECT tasks.*, analysts.name as analyst_name 
            FROM tasks 
            LEFT JOIN analysts ON tasks.analyst_id = analysts.id
        ''').fetchall()
        
        current_scenario = get_current_scenario()
        return render_template('index.html', analysts=analysts, tasks=tasks, current_scenario=current_scenario)

    @app.route('/distribute', methods=['POST'])
    def distribute():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        from app.services.distribution_service import distribute_tasks
        distribute_tasks()
        audit_logger.info("Суперадмин запустил распределение задач.")
        return redirect(url_for('home'))

    @app.route('/complete/<int:task_id>', methods=['POST'])
    def complete_task(task_id):
        conn = get_db()
        conn.execute('UPDATE tasks SET status = "Завершена" WHERE id = ?', (task_id,))
        conn.commit()
        audit_logger.info(f"Задача #{task_id} переведена в статус 'Завершена' пользователем {session.get('user_name')}.")
        return redirect(url_for('home'))

    @app.route('/escalate/<int:task_id>', methods=['POST'])
    def escalate_task(task_id):
        conn = get_db()
        conn.execute('''
            UPDATE tasks 
            SET status = "Ожидает", analyst_id = NULL, priority = "high" 
            WHERE id = ?
        ''', (task_id,))
        conn.commit()
        audit_logger.warning(f"Задача #{task_id} была эскалирована пользователем {session.get('user_name')}!")
        return redirect(url_for('home'))

    @app.route('/update_analyst/<int:id>', methods=['POST'])
    def update_analyst(id):
        conn = get_db()
        analyst = conn.execute('SELECT * FROM analysts WHERE id = ?', (id,)).fetchone()
        
        if session.get('role') != 'admin' and (not analyst or analyst['name'] != session.get('user_name')):
            return redirect(url_for('home'))
            
        is_available = 1 if request.form.get('is_available') else 0
        max_open_tasks = request.form.get('max_open_tasks')
    
        conn.execute(
            'UPDATE analysts SET is_available = ?, max_open_tasks = ? WHERE id = ?',
            (is_available, max_open_tasks, id)
        )
        conn.commit()
        audit_logger.info(f"Пользователь {session.get('user_name')} обновил статус аналитика #{id}: Доступен={bool(is_available)}, Лимит={max_open_tasks}")
        return redirect(url_for('home'))

    @app.route('/settings')
    def settings():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        log_content = ""
        if os.path.exists('system.log'):
            with open('system.log', 'r', encoding='utf-8') as f:
                log_content = "".join(f.readlines()[-50:])
        
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        current_scenario = get_current_scenario()
        return render_template('settings.html', log_content=log_content, json_files=json_files, current_scenario=current_scenario)

    @app.route('/settings/view_logs')
    def view_logs():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        log_path = os.path.abspath('system.log')
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype='text/plain')
        return "Журнал пуст или еще не создан."

    @app.route('/settings/download_logs')
    def download_logs():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        log_path = os.path.abspath('system.log')
        if os.path.exists(log_path):
            return send_file(log_path, as_attachment=True)
        return redirect(url_for('settings'))

    @app.route('/settings/clear_logs', methods=['POST'])
    def clear_logs():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        open('system.log', 'w').close()
        audit_logger.info("Системный журнал был принудительно очищен Суперадмином.")
        return redirect(url_for('settings'))

    @app.route('/settings/load_json', methods=['POST'])
    def load_json():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
            
        json_file = request.form.get('json_file')
        if not json_file or not os.path.exists(json_file):
            audit_logger.error(f"Ошибка загрузки: файл {json_file} не найден.")
            return redirect(url_for('settings'))

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                analysts_data = data.get('analysts', [])
                tasks_data = data.get('tasks', [])
            else:
                analysts_data = data
                tasks_data = []

            conn = get_db()
            conn.execute('DELETE FROM tasks')
            conn.execute('DELETE FROM analysts')
            conn.execute('DELETE FROM sqlite_sequence WHERE name IN ("tasks", "analysts")')

            for a in analysts_data:
                conn.execute(
                    'INSERT INTO analysts (name, level, is_available, max_open_tasks) VALUES (?, ?, ?, ?)',
                    (a.get('name'), a.get('level', 'L1'), a.get('is_available', 1), a.get('max_open_tasks', 3))
                )

            for t in tasks_data:
                conn.execute(
                    'INSERT INTO tasks (task_type, description, priority, status) VALUES (?, ?, ?, ?)',
                    (t.get('task_type'), t.get('description', ''), t.get('priority', 'medium'), t.get('status', 'Ожидает'))
                )

            conn.commit()
            
            # Сохраняем название текущего файла
            with open('current_scenario.txt', 'w', encoding='utf-8') as f:
                f.write(json_file)
                
            audit_logger.info(f"Загружен сценарий {json_file}: аналитиков — {len(analysts_data)}, задач — {len(tasks_data)}.")
        except Exception as e:
            audit_logger.error(f"Ошибка при чтении JSON ({json_file}): {e}")

        return redirect(url_for('settings'))

    @app.route('/settings/reset', methods=['POST'])
    def reset_db():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        conn = get_db()
        conn.execute('DELETE FROM tasks')
        conn.commit()
        
        # Обновляем статус при ручной очистке
        with open('current_scenario.txt', 'w', encoding='utf-8') as f:
            f.write("База очищена (Пустая)")
            
        audit_logger.warning("Суперадмин очистил всю очередь задач (Опасная зона).")
        return redirect(url_for('settings'))

    return app