import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from werkzeug.utils import secure_filename
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from loguru import logger

from config import Config
from models.database import db, migrate
from models.user_model import User
from models.post_model import Post, BlogHostType
from routes.auth import auth_bp
from routes.posts import posts_bp
from routes.export import export_bp
from services.mlg_service import MlgService
from services.lmm_service import LmmService
from utils.auth import load_user
from celery_app import init_celery

def create_app(config_class=Config):
    """Фабрика приложения Flask."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Инициализация Celery
    init_celery(app)
    
    # Настройка аутентификации
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    login_manager.user_loader(load_user)
    
    # Регистрация маршрутов
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(posts_bp, url_prefix='/posts')
    app.register_blueprint(export_bp, url_prefix='/export')
    
    # Обработчик корневого маршрута
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('posts.dashboard'))
        return redirect(url_for('auth.login'))
    
    # Настройка логирования
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    file_handler = RotatingFileHandler('logs/epizode-webapp.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Epizode-Analyzer веб-приложение запущено')
    
    # Инициализация директорий
    Config.init_app(app)
    
    # Добавление datetime в глобальные переменные для шаблонов
    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}
    
    return app

def init_db(app):
    """Инициализация базы данных."""
    with app.app_context():
        db.create_all()
        # Создаем тестового пользователя, если его нет
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            app.logger.info('Создан тестовый пользователь: admin')

# Создаем экземпляр приложения для запуска из командной строки
app = create_app()

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True)