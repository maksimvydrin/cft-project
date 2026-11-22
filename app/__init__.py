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
        role = session.get('role')
        user_name = session.get('user_name')
        
        if role == 'admin':
            tasks = conn.execute('''
                SELECT tasks.*, analysts.name as analyst_name 
                FROM tasks 
                LEFT JOIN analysts ON tasks.analyst_id = analysts.id
            ''').fetchall()
        else:
            tasks = conn.execute('''
                SELECT tasks.*, analysts.name as analyst_name 
                FROM tasks 
                LEFT JOIN analysts ON tasks.analyst_id = analysts.id
                WHERE analysts.name = ?
            ''', (user_name,)).fetchall()
        
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

    @app.route('/assign_manual/<int:task_id>', methods=['POST'])
    def assign_manual(task_id):
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        
        analyst_id = request.form.get('analyst_id')
        if not analyst_id:
            return redirect(url_for('home'))
            
        conn = get_db()
        task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        analyst = conn.execute('SELECT * FROM analysts WHERE id = ?', (analyst_id,)).fetchone()
        current_load = conn.execute('SELECT COUNT(*) FROM tasks WHERE analyst_id = ? AND status = "В работе"', (analyst_id,)).fetchone()[0]
        
        warnings = []
        if current_load >= analyst['max_open_tasks']:
            warnings.append(f"Превышен лимит (уже {current_load}/{analyst['max_open_tasks']})")
        if task['priority'] == 'high' and analyst['level'] not in ['L3']:
            warnings.append(f"Нарушен уровень (задача High отдана {analyst['level']})")
        if analyst['is_available'] == 0:
            warnings.append("Сотрудник не на смене")

        action_label = "Переназначение" if task['analyst_id'] else "Ручное назначение"
        conn.execute('UPDATE tasks SET analyst_id = ?, status = "В работе" WHERE id = ?', (analyst_id, task_id))
        conn.commit()
        
        if warnings:
            audit_logger.warning(f"РУЧНОЕ ПЕРЕОПРЕДЕЛЕНИЕ ({action_label}): Админ назначил задачу #{task_id} на {analyst['name']}. Игнорировано: {', '.join(warnings)}.")
        else:
            audit_logger.info(f"{action_label}: Админ назначил задачу #{task_id} на {analyst['name']}.")
            
        return redirect(url_for('home'))

    @app.route('/unassign_task/<int:task_id>', methods=['POST'])
    def unassign_task(task_id):
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        conn = get_db()
        conn.execute('UPDATE tasks SET analyst_id = NULL, status = "Ожидает" WHERE id = ?', (task_id,))
        conn.commit()
        audit_logger.warning(f"Суперадмин снял исполнителя с задачи #{task_id} и вернул её в очередь.")
        return redirect(url_for('home'))

    @app.route('/delete_task/<int:task_id>', methods=['POST'])
    def delete_task(task_id):
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        conn = get_db()
        task = conn.execute('SELECT task_type, priority FROM tasks WHERE id = ?', (task_id,)).fetchone()
        conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        if task:
            audit_logger.warning(f"Суперадмин удалил задачу #{task_id} (Тип={task['task_type']}, Приоритет={task['priority']}).")
        return redirect(url_for('home'))

    @app.route('/complete/<int:task_id>', methods=['POST'])
    def complete_task(task_id):
        conn = get_db()
        comment = request.form.get('resolution_comment', 'Без комментариев')
        
        conn.execute('UPDATE tasks SET status = "Завершена" WHERE id = ?', (task_id,))
        conn.commit()
        
        audit_logger.info(f"Задача #{task_id} завершена пользователем {session.get('user_name')}. Результат: {comment}")
        return redirect(url_for('home'))

    @app.route('/escalate/<int:task_id>', methods=['POST'])
    def escalate_task(task_id):
        conn = get_db()
        user_name = session.get('user_name')
        role = session.get('role')
        
        analyst = conn.execute('SELECT level FROM analysts WHERE name = ?', (user_name,)).fetchone()
        
        if role == 'admin':
            new_priority = 'high'
        else:
            if analyst and analyst['level'] == 'L3':
                audit_logger.warning(f"Нарушение прав: {user_name} (L3) попытался эскалировать задачу #{task_id}.")
                return redirect(url_for('home'))
            new_priority = 'medium' if analyst['level'] == 'L1' else 'high'

        conn.execute('''
            UPDATE tasks 
            SET status = "Ожидает", analyst_id = NULL, priority = ? 
            WHERE id = ?
        ''', (new_priority, task_id))
        conn.commit()
        
        audit_logger.warning(f"Задача #{task_id} эскалирована пользователем {user_name}. Новый приоритет: {new_priority}.")
        return redirect(url_for('home'))

    @app.route('/edit_task/<int:task_id>', methods=['POST'])
    def edit_task(task_id):
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
            
        new_type = request.form.get('new_type')
        new_priority = request.form.get('new_priority')
        reason = request.form.get('reason')
        
        conn = get_db()
        old = conn.execute('SELECT task_type, priority FROM tasks WHERE id = ?', (task_id,)).fetchone()
        
        conn.execute('UPDATE tasks SET task_type = ?, priority = ? WHERE id = ?', (new_type, new_priority, task_id))
        conn.commit()
        
        audit_logger.warning(f"Админ изменил задачу #{task_id}. Тип: {old['task_type']} -> {new_type}, Приоритет: {old['priority']} -> {new_priority}. Причина: {reason}")
        return redirect(url_for('home'))

    @app.route('/add_analyst', methods=['POST'])
    def add_analyst():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        name = request.form.get('name', '').strip()
        level = request.form.get('level', 'L1')
        max_open_tasks = int(request.form.get('max_open_tasks', 3))
        is_available = 1 if request.form.get('is_available') else 0

        if name:
            conn = get_db()
            conn.execute(
                'INSERT INTO analysts (name, level, is_available, max_open_tasks) VALUES (?, ?, ?, ?)',
                (name, level, is_available, max_open_tasks)
            )
            conn.commit()
            audit_logger.info(f"Суперадмин добавил аналитика: {name} ({level}), Лимит={max_open_tasks}, Доступен={bool(is_available)}")
        return redirect(url_for('home'))

    @app.route('/delete_analyst/<int:id>', methods=['POST'])
    def delete_analyst(id):
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        conn = get_db()
        analyst = conn.execute('SELECT name FROM analysts WHERE id = ?', (id,)).fetchone()
        if analyst:
            conn.execute('UPDATE tasks SET analyst_id = NULL, status = "Ожидает" WHERE analyst_id = ? AND status = "В работе"', (id,))
            conn.execute('DELETE FROM analysts WHERE id = ?', (id,))
            conn.commit()
            audit_logger.warning(f"Суперадмин удалил аналитика #{id} ({analyst['name']}). Его активные задачи возвращены в очередь.")
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

    @app.route('/settings/update_rules', methods=['POST'])
    def update_rules():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        
        rules = {'low': [], 'medium': [], 'high': []}
        for priority in rules.keys():
            for level in ['L1', 'L2', 'L3']:
                if request.form.get(f'rule_{priority}_{level}'):
                    rules[priority].append(level)
                    
        with open('routing_rules.json', 'w', encoding='utf-8') as f:
            json.dump(rules, f)
            
        audit_logger.info(f"Суперадмин обновил матрицу компетенций: {rules}")
        return redirect(url_for('settings'))

    @app.route('/settings')
    def settings():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
            
        log_content = ""
        if os.path.exists('system.log'):
            with open('system.log', 'r', encoding='utf-8') as f:
                log_content = "".join(f.readlines()[-50:])
        
        rules = {'low': ['L1', 'L2', 'L3'], 'medium': ['L2', 'L3'], 'high': ['L3']}
        if os.path.exists('routing_rules.json'):
            with open('routing_rules.json', 'r', encoding='utf-8') as f:
                rules = json.load(f)
        
        json_files = [f for f in os.listdir('.') if f.endswith('.json') and f != 'routing_rules.json']
        current_scenario = get_current_scenario()
        return render_template('settings.html', log_content=log_content, json_files=json_files, current_scenario=current_scenario, rules=rules)

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

    @app.route('/settings/load_json', methods=['POST'])
    def load_json():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
            
        selected_file = request.form.get('json_file')
        if not selected_file or not os.path.exists(selected_file):
            audit_logger.error(f"Ошибка загрузки: файл {selected_file} не найден.")
            return redirect(url_for('settings'))

        try:
            conn = get_db()
            all_json_files = [f for f in os.listdir('.') if f.endswith('.json')]
            for jf in all_json_files:
                try:
                    with open(jf, 'r', encoding='utf-8') as f:
                        jf_data = json.load(f)
                        analysts_list = jf_data.get('analysts', []) if isinstance(jf_data, dict) else jf_data
                        
                        for a in analysts_list:
                            name = a.get('name')
                            level = a.get('level', 'L1')
                            max_tasks = a.get('max_open_tasks', 3)
                            
                            existing = conn.execute('SELECT id FROM analysts WHERE name = ?', (name,)).fetchone()
                            if not existing:
                                conn.execute(
                                    'INSERT INTO analysts (name, level, is_available, max_open_tasks) VALUES (?, ?, 0, ?)',
                                    (name, level, max_tasks)
                                )
                except Exception:
                    pass

            conn.execute('DELETE FROM tasks')
            conn.execute('DELETE FROM sqlite_sequence WHERE name = "tasks"')
            conn.execute('UPDATE analysts SET is_available = 0')

            with open(selected_file, 'r', encoding='utf-8') as f:
                scenario_data = json.load(f)
            
            s_analysts = scenario_data.get('analysts', []) if isinstance(scenario_data, dict) else scenario_data
            s_tasks = scenario_data.get('tasks', []) if isinstance(scenario_data, dict) else []

            for a in s_analysts:
                conn.execute(
                    'UPDATE analysts SET is_available = 1, max_open_tasks = ?, level = ? WHERE name = ?',
                    (a.get('max_open_tasks', 3), a.get('level', 'L1'), a.get('name'))
                )

            for t in s_tasks:
                conn.execute(
                    'INSERT INTO tasks (task_type, description, priority, status) VALUES (?, ?, ?, ?)',
                    (t.get('task_type'), t.get('description', ''), t.get('priority', 'medium'), t.get('status', 'Ожидает'))
                )

            conn.commit()
            
            with open('current_scenario.txt', 'w', encoding='utf-8') as f:
                f.write(selected_file)
                
            audit_logger.info(f"Синхронизирован штат. Загружен сценарий {selected_file}.")
        except Exception as e:
            audit_logger.error(f"Ошибка при инициализации базы: {e}")

        return redirect(url_for('settings'))

    @app.route('/settings/reset', methods=['POST'])
    def reset_db():
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        conn = get_db()
        conn.execute('DELETE FROM tasks')
        conn.commit()
        
        with open('current_scenario.txt', 'w', encoding='utf-8') as f:
            f.write("База очищена (Пустая)")
            
        audit_logger.warning("Суперадмин очистил всю очередь задач (Опасная зона).")
        return redirect(url_for('settings'))

    return app