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

    # 3. Считаем текущую загрузку каждого аналитика
    current_load = {}
    for analyst in analysts:
        count = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE analyst_id = ? AND status = "В работе"', 
            (analyst['id'],)
        ).fetchone()[0]
        current_load[analyst['id']] = count

    # 4. ПРАВИЛА МАРШРУТИЗАЦИИ (Smart Routing)
    # Определяем, аналитики каких грейдов могут брать задачи разных приоритетов
    routing_rules = {
        'low': ['L1', 'L2', 'L3'],  # Низкий приоритет могут брать все (L1 — основные чернорабочие)
        'medium': ['L2', 'L3'],     # Средний приоритет доверяем только мидлам и сеньорам
        'high': ['L3']              # Высокий приоритет (инциденты) улетают строго экспертам
    }

    # 5. Умное распределение
    for task in pending_tasks:
        task_priority = task['priority']
        # Получаем список разрешенных грейдов для этой задачи
        allowed_levels = routing_rules.get(task_priority, ['L3']) 

        for analyst in analysts:
            a_id = analyst['id']
            a_level = analyst['level']
            
            # Проверяем ДВА условия: не превышен лимит И грейд аналитика подходит для задачи
            if current_load[a_id] < analyst['max_open_tasks'] and a_level in allowed_levels:
                
                # Назначаем задачу
                conn.execute(
                    'UPDATE tasks SET status = ?, analyst_id = ? WHERE id = ?',
                    ('В работе', a_id, task['id'])
                )
                
                current_load[a_id] += 1
                break # Задача распределена, берем следующую из очереди

    conn.commit()