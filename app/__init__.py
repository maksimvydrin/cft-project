from flask import Flask, render_template, request, redirect, url_for
from . import db

def create_app():
    app = Flask(__name__)
    app.teardown_appcontext(db.close_db)

    @app.route('/', methods=['GET', 'POST'])
    def home():
        conn = db.get_db()
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
        # Джоиним таблицу аналитиков, чтобы получить их имена
        tasks = conn.execute('''
            SELECT tasks.*, analysts.name as analyst_name 
            FROM tasks 
            LEFT JOIN analysts ON tasks.analyst_id = analysts.id
        ''').fetchall()
        return render_template('index.html', analysts=analysts, tasks=tasks)

# Маршрут для ручного запуска распределения
    @app.route('/distribute', methods=['POST'])
    def distribute():
        # Импортируем нашу новую функцию
        from app.services.distribution_service import distribute_tasks
        distribute_tasks()
        return redirect(url_for('home'))
    # заглушки настроек
    @app.route('/settings')
    def settings():
        return render_template('settings.html')

    return app