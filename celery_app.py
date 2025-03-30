from celery import Celery

def make_celery(app):
    """
    Создает и настраивает экземпляр Celery для работы с Flask.
    
    Args:
        app: Экземпляр Flask приложения.
        
    Returns:
        Celery: Настроенный экземпляр Celery.
    """
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

# Инициализация Celery без привязки к конкретному приложению
celery = Celery()

# Функция для инициализации Celery при создании приложения
def init_celery(app):
    """
    Инициализирует Celery для работы с конкретным экземпляром Flask.
    
    Args:
        app: Экземпляр Flask приложения.
    """
    global celery
    celery = make_celery(app)
    
    # Импортируем задачи, чтобы Celery о них знал
    import services.lmm_service
    
    return celery