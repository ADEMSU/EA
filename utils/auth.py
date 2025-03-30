from flask_login import current_user
from models.user_model import User

def load_user(user_id):
    """
    Загрузка пользователя по ID для Flask-Login.
    
    Args:
        user_id: ID пользователя.
    
    Returns:
        User: Объект пользователя или None, если не найден.
    """
    return User.query.get(int(user_id))

def validate_password(password):
    """
    Проверка пароля на соответствие требованиям безопасности.
    
    Args:
        password: Пароль для проверки.
    
    Returns:
        bool: True, если пароль соответствует требованиям, иначе False.
    """
    if not password or len(password) < 8:
        return False
    
    # Проверка наличия цифр, букв верхнего и нижнего регистра
    has_digit = any(char.isdigit() for char in password)
    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    
    return has_digit and has_upper and has_lower

def is_admin():
    """
    Проверка, является ли текущий пользователь администратором.
    
    Returns:
        bool: True, если пользователь администратор, иначе False.
    """
    return current_user.is_authenticated and current_user.is_admin
