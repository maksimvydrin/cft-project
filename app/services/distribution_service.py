import logging
import json
import os
from app import get_db

# Подключаемся к нашему системному логгеру
audit_logger = logging.getLogger('cft_audit')

def distribute_tasks():
    conn = get_db()
    
    # Получаем все задачи в статусе Ожидает
    pending_tasks = conn.execute('''
        SELECT * FROM tasks 
        WHERE status = 'Ожидает'
        ORDER BY 
            CASE priority 
                WHEN 'high' THEN 1 
                WHEN 'medium' THEN 2 
                WHEN 'low' THEN 3 
            END, 
            id ASC
    ''').fetchall()

    if not pending_tasks:
        audit_logger.info("Распределение: Очередь пуста, новых задач нет.")
        return

    # Получаем всех доступных аналитиков
    analysts = conn.execute('SELECT * FROM analysts WHERE is_available = 1').fetchall()
    
    if not analysts:
        audit_logger.warning("Распределение: Нет доступных аналитиков на смене!")
        return

    # Считаем текущую загрузку каждого аналитика
    workloads = {a['id']: 0 for a in analysts}
    active_tasks = conn.execute('''
        SELECT analyst_id, COUNT(*) as count 
        FROM tasks 
        WHERE status = 'В работе' AND analyst_id IS NOT NULL 
        GROUP BY analyst_id
    ''').fetchall()
    
    for row in active_tasks:
        if row['analyst_id'] in workloads:
            workloads[row['analyst_id']] = row['count']

    # === ДИНАМИЧЕСКАЯ ЗАГРУЗКА ПРАВИЛ ИЗ НАСТРОЕК ===
    # Дефолтные правила на случай, если админ еще ничего не сохранял
    routing_rules = {
        'low': ['L1', 'L2', 'L3'],  
        'medium': ['L2', 'L3'],     
        'high': ['L3']              
    }
    
    # Пытаемся прочитать правила, сохраненные Суперадмином из интерфейса
    if os.path.exists('routing_rules.json'):
        try:
            with open('routing_rules.json', 'r', encoding='utf-8') as f:
                routing_rules = json.load(f)
        except Exception as e:
            audit_logger.error(f"Ошибка чтения матрицы распределения: {e}")

    # Распределение
    assigned_count = 0
    for task in pending_tasks:
        task_priority = task['priority']
        allowed_levels = routing_rules.get(task_priority, ['L3']) 
        
        best_analyst = None
        lowest_load = float('inf')

        # Ищем наименее загруженного аналитика нужного уровня
        for analyst in analysts:
            a_id = analyst['id']
            a_level = analyst['level']
            current_load = workloads[a_id]

            # Проверяем лимит и наличие уровня в разрешенных (по галочкам из настроек)
            if current_load < analyst['max_open_tasks'] and a_level in allowed_levels:
                if current_load < lowest_load:
                    lowest_load = current_load
                    best_analyst = analyst

        # Если нашли подходящего сотрудника — назначаем
        if best_analyst:
            a_id = best_analyst['id']
            conn.execute(
                'UPDATE tasks SET status = ?, analyst_id = ? WHERE id = ?',
                ('В работе', a_id, task['id'])
            )
            workloads[a_id] += 1
            assigned_count += 1
            audit_logger.info(f"Задача #{task['id']} ({task_priority}) ушла к {best_analyst['name']} (Уровень {best_analyst['level']}). Загрузка: {workloads[a_id]}/{best_analyst['max_open_tasks']}")
        else:
            audit_logger.warning(f"Для задачи #{task['id']} ({task_priority}) не нашлось свободных аналитиков нужного уровня (Разрешены: {', '.join(allowed_levels)}).")

    conn.commit()
    if assigned_count > 0:
        audit_logger.info(f"Итог: Успешно распределено задач: {assigned_count}.")