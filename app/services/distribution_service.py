from app.db import get_db

def distribute_tasks():
    conn = get_db()
    
    # 1. Получаем все задачи в статусе 'Ожидает' (сначала с высоким приоритетом)
    pending_tasks = conn.execute('''
        SELECT * FROM tasks 
        WHERE status = 'Ожидает'
        ORDER BY 
            CASE priority 
                WHEN 'high' THEN 1 
                WHEN 'medium' THEN 2 
                WHEN 'low' THEN 3 
            END, 
            created_at ASC
    ''').fetchall()

    # 2. Получаем всех доступных аналитиков
    analysts = conn.execute('SELECT * FROM analysts WHERE is_available = 1').fetchall()

    # 3. Считаем, сколько задач сейчас "В работе" у каждого аналитика
    current_load = {}
    for analyst in analysts:
        count = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE analyst_id = ? AND status = "В работе"', 
            (analyst['id'],)
        ).fetchone()[0]
        current_load[analyst['id']] = count

    # 4. Само распределение
    for task in pending_tasks:
        for analyst in analysts:
            a_id = analyst['id']
            
            # Временно назначаем любую задачу без учета уровня L1/L2 (добавим позже).
            # Главное условие: лимит задач аналитика не должен быть превышен
            if current_load[a_id] < analyst['max_open_tasks']:
                
                # Назначаем задачу на аналитика
                conn.execute(
                    'UPDATE tasks SET status = ?, analyst_id = ? WHERE id = ?',
                    ('В работе', a_id, task['id'])
                )
                
                # Увеличиваем счетчик его задач
                current_load[a_id] += 1
                break # Задача распределена, переходим к следующей

    conn.commit()