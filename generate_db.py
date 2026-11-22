import json
import random

random.seed(42)

TEMPLATES = {
    "low": [
        ("Auth", "Сброс пароля учетной записи сотрудника (филиал #{n})"),
        ("Access", "Выдача прав на чтение витрины отчетов модуль #{n}"),
        ("UI", "Не прогружается иконка в личном кабинете (клиент #{n})"),
        ("Mail", "Задержка доставки сервисного уведомления #{n}"),
        ("Access", "Разблокировка токена после 3 неверных попыток (АРМ #{n})"),
        ("Reports", "Опечатка в заголовке выгрузки за период #{n}"),
        ("Monitoring", "Алерт: заполнено 80% диска на сервере логов log-srv-{n}"),
        ("Backup", "Предупреждение при архивации тестового стенда dev-{n}"),
        ("UI", "Не работает кнопка скачивания квитанции PDF (заявка #{n})"),
        ("Mail", "Не приходят пуш-уведомления на iOS (устройство #{n})"),
    ],
    "medium": [
        ("API", "Ошибка 502 при обращении к шлюзу СБП (инстанс #{n})"),
        ("Payments", "Зависание статуса перевода в обработке > 10 мин (пакет #{n})"),
        ("DB", "Медленное выполнение запроса выписки по счетам (шард #{n})"),
        ("VPN", "Обрыв туннеля до удаленного офиса #{n}"),
        ("Integration", "Рассинхронизация справочника БИК на узле #{n}"),
        ("Auth", "Сбой двухфакторной аутентификации (SMS-шлюз #{n})"),
        ("Batch", "Задержка закрытия операционного дня (поток #{n})"),
        ("DB", "Падение репликации на резервную ноду db-replica-{n}"),
        ("Network", "Потеря пакетов на канале связи до ЦОД-{n}"),
        ("Certificates", "Истекает SSL-сертификат на шлюзе обмена gw-{n}"),
    ],
    "high": [
        ("Core", "Высокая нагрузка CPU (95%) на узле процессинга proc-{n}"),
        ("DB", "Блокировка (deadlock) таблицы транзакций на узле #{n}"),
        ("Security", "Подозрительная серия запросов к API переводов (IP-пул #{n})"),
        ("DDoS", "Аномальный всплеск HTTP-трафика на портал (сегмент #{n})"),
        ("Payments", "Массовые отказы при проведении платежей СБП (шлюз #{n})"),
        ("Core", "Критическая ошибка очереди сообщений Kafka (брокер #{n})"),
        ("Security", "Срабатывание WAF: попытка SQL-инъекции (эндпоинт #{n})"),
        ("Core", "Утечка памяти (OOM) в сервисе уведомлений pod-{n}"),
        ("DB", "Исчерпан пул подключений к основной БД (кластер #{n})"),
        ("API", "Недоступен сервис скоринга кредитных заявок (узел #{n})"),
    ],
}

def generate_tasks(count, weights):
    priorities = random.choices(["low", "medium", "high"], weights=weights, k=count)
    tasks = []
    for i, prio in enumerate(priorities, start=1):
        task_type, desc_tpl = random.choice(TEMPLATES[prio])
        tasks.append({
            "task_type": task_type,
            "description": desc_tpl.format(n=100 + i),
            "priority": prio,
            "status": "Ожидает"
        })
    return tasks

SCENARIOS = {
    "morning_shift.json": {
        "analysts": [
            {"name": "Алексей (L1)", "level": "L1", "max_open_tasks": 10},
            {"name": "Мария (L1)", "level": "L1", "max_open_tasks": 10},
            {"name": "Дмитрий (L2)", "level": "L2", "max_open_tasks": 12},
            {"name": "Елена (L2)", "level": "L2", "max_open_tasks": 12},
            {"name": "Виктор (L3 - Тимлид)", "level": "L3", "max_open_tasks": 8},
        ],
        "tasks": generate_tasks(120, weights=[50, 35, 15]),
    },
    "night_shift.json": {
        "analysts": [
            {"name": "Ольга (L1 - Дежурный)", "level": "L1", "max_open_tasks": 8},
            {"name": "Артем (L2 - Ночь)", "level": "L2", "max_open_tasks": 10},
            {"name": "Виктор (L3 - Тимлид)", "level": "L3", "max_open_tasks": 8},
        ],
        "tasks": generate_tasks(105, weights=[45, 35, 20]),
    },
    "stress_test.json": {
        "analysts": [
            {"name": "Ольга (L1 - Дежурный)", "level": "L1", "max_open_tasks": 10},
            {"name": "Алексей (L1)", "level": "L1", "max_open_tasks": 10},
            {"name": "Мария (L1)", "level": "L1", "max_open_tasks": 10},
            {"name": "Артем (L2 - Ночь)", "level": "L2", "max_open_tasks": 10},
            {"name": "Дмитрий (L2)", "level": "L2", "max_open_tasks": 10},
            {"name": "Виктор (L3 - Тимлид)", "level": "L3", "max_open_tasks": 10},
        ],
        "tasks": generate_tasks(250, weights=[30, 40, 30]),
    },
}

for filename, data in SCENARIOS.items():
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Создан {filename}: {len(data['tasks'])} задач")