from app import create_app
from app.db import init_db

app = create_app()

# Запускаем создание таблиц
with app.app_context():
    init_db()
