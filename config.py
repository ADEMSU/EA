import os
from datetime import timedelta
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

class Config:
    """Базовая конфигурация приложения."""
    # Основные настройки
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    TESTING = False
    
    # Настройки базы данных
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Настройки сессии
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    
    # Настройки загрузки файлов
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    
    # Настройки Медиалогии
    MEDIALOGIA_USERNAME = os.environ.get('MEDIALOGIA_USERNAME')
    MEDIALOGIA_PASSWORD = os.environ.get('MEDIALOGIA_PASSWORD')
    MEDIALOGIA_WSDL_URL = os.environ.get('MEDIALOGIA_WSDL_URL')
    MEDIALOGIA_REPORT_ID = os.environ.get('MEDIALOGIA_REPORT_ID')
    
    # Настройки OpenRouter API для LLM
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
    LMM_MODEL = os.environ.get('LMM_MODEL', 'deepseek/deepseek-chat-v3-0324:free')
    
    # Настройки Celery для асинхронных задач
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
    
    # Директории для хранения данных
    DATA_DIRECTORY = os.environ.get('DATA_DIRECTORY') or 'data'
    EXPORT_DIRECTORY = os.path.join(DATA_DIRECTORY, 'exports')
    
    # Создаем директории, если они не существуют
    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.EXPORT_DIRECTORY, exist_ok=True)


class DevelopmentConfig(Config):
    """Конфигурация для разработки."""
    DEBUG = True


class TestingConfig(Config):
    """Конфигурация для тестирования."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Конфигурация для production."""
    DEBUG = False
    # В продакшене нужно настроить более надежную базу данных
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Более строгие настройки безопасности
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


# Словарь конфигураций
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}