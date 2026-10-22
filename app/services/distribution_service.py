from app.db import get_db

def distribute_tasks():
    conn = get_db()
    
    #Получаем все задачи в статусе Ожидает
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

    #Получаем всех доступных аналитиков
    analysts = conn.execute('SELECT * FROM analysts WHERE is_available = 1').fetchall()

    #Считаем текущую загрузку каждого аналитика
    current_load = {}
    for analyst in analysts:
        count = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE analyst_id = ? AND status = "В работе"', 
            (analyst['id'],)
        ).fetchone()[0]
        current_load[analyst['id']] = count

    #ПРАВИЛА МАРШРУТИЗАЦИИ
    
    routing_rules = {
        'low': ['L1', 'L2', 'L3'],  # Низкий приоритет могут брать все
        'medium': ['L2', 'L3'],     # Средний приоритет
        'high': ['L3']              # Высокий приоритет строго экспертам
    }

    #распределение
    for task in pending_tasks:
        task_priority = task['priority']

        allowed_levels = routing_rules.get(task_priority, ['L3']) 

        for analyst in analysts:
            a_id = analyst['id']
            a_level = analyst['level']
            
            # Проверяем 2 условия не превышен лимит уровень аналитика подходит для задачи
            if current_load[a_id] < analyst['max_open_tasks'] and a_level in allowed_levels:
                
                # Назначаем задачу
                conn.execute(
                    'UPDATE tasks SET status = ?, analyst_id = ? WHERE id = ?',
                    ('В работе', a_id, task['id'])
                )
                
                current_load[a_id] += 1
                break # Задача распределена, берем следующую из очереди

    conn.commit()