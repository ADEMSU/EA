from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Инициализация SQLAlchemy и Flask-Migrate
db = SQLAlchemy()
migrate = Migrate()