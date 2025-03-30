import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Tuple, Optional
from flask import current_app
from datetime import datetime, timedelta

def clean_html_and_emoji(text):
    """
    Удаление HTML-тегов и эмодзи из текста.
    
    Args:
        text: Исходный текст.
        
    Returns:
        str: Очищенный текст.
    """
    if text is None:
        return ""
    
    # Удаление HTML-тегов
    text = re.sub(r'<[^>]+>', '', text)
    
    # Удаление эмодзи
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # смайлики
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и символы карт
        "\U0001F700-\U0001F77F"  # алхимические символы
        "\U0001F780-\U0001F7FF"  # геометрические фигуры
        "\U0001F800-\U0001F8FF"  # дополнительные стрелки
        "\U0001F900-\U0001F9FF"  # дополнительные символы и пиктограммы
        "\U0001FA00-\U0001FA6F"  # символы шахмат
        "\U0001FA70-\U0001FAFF"  # символы эмодзи
        "\U00002702-\U000027B0"  # разные символы
        "\U000024C2-\U0001F251" 
        "]+", flags=re.UNICODE)
    
    text = emoji_pattern.sub(r'', text)
    
    # Удаление лишних пробелов
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def parse_date(date_str):
    """
    Парсинг даты из строки с поддержкой разных форматов.
    
    Args:
        date_str: Строка с датой.
        
    Returns:
        datetime: Объект datetime с московской временной зоной.
    """
    formats = ["%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"]
    
    for fmt in formats:
        try:
            date = datetime.strptime(date_str, fmt)
            # Устанавливаем московскую временную зону
            return date.replace(tzinfo=ZoneInfo('Europe/Moscow'))
        except ValueError:
            continue
    
    raise ValueError(
        "Неверный формат даты. Поддерживаемые форматы: YYYY-MM-DD, DD.MM.YYYY, YYYY/MM/DD, DD/MM/YYYY"
    )

def get_msk_date_range(days_ago=1, time_from=None, time_to=None) -> Tuple[datetime, datetime]:
    """
    Получает диапазон дат с учетом московского часового пояса.
    
    Args:
        days_ago: Количество дней назад от текущей даты.
        time_from: Время начала в формате HH:MM.
        time_to: Время окончания в формате HH:MM.
        
    Returns:
        Tuple[datetime, datetime]: (date_from, date_to) в UTC.
    """
    # Получаем текущее время в московском часовом поясе
    msk_now = datetime.now(ZoneInfo('Europe/Moscow'))
    
    # Устанавливаем конечную дату
    date_to = msk_now
    
    # Если указано смещение, вычитаем дни
    if days_ago > 0:
        date_to = date_to - timedelta(days=days_ago)
    
    # Начальная дата - это конечная
    date_from = date_to.replace(hour=0, minute=0, second=0, microsecond=0)
    date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # Если указано время начала, устанавливаем его
    if time_from:
        try:
            hour, minute = map(int, time_from.split(':'))
            date_from = date_from.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, TypeError):
            pass
    
    # Если указано время окончания, устанавливаем его
    if time_to:
        try:
            hour, minute = map(int, time_to.split(':'))
            date_to = date_to.replace(hour=hour, minute=minute, second=59, microsecond=0)
        except (ValueError, TypeError):
            pass
    
    # Преобразуем в UTC для совместимости с API
    date_from = date_from.astimezone(ZoneInfo('UTC'))
    date_to = date_to.astimezone(ZoneInfo('UTC'))
    
    return date_from, date_to

def get_date_range(date_from_str, date_to_str, time_from=None, time_to=None) -> Tuple[datetime, datetime]:
    """
    Получает диапазон дат из строковых представлений с учетом московского часового пояса.
    
    Args:
        date_from_str: Строковое представление начальной даты.
        date_to_str: Строковое представление конечной даты.
        time_from: Время начала в формате HH:MM.
        time_to: Время окончания в формате HH:MM.
        
    Returns:
        Tuple[datetime, datetime]: (date_from, date_to) в UTC.
    """
    date_from = parse_date(date_from_str)
    date_to = parse_date(date_to_str)
    
    # Устанавливаем время начала
    if time_from:
        try:
            hour, minute = map(int, time_from.split(':'))
            date_from = date_from.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, TypeError):
            date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Устанавливаем время окончания
    if time_to:
        try:
            hour, minute = map(int, time_to.split(':'))
            date_to = date_to.replace(hour=hour, minute=minute, second=59, microsecond=0)
        except (ValueError, TypeError):
            date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # Преобразуем в UTC для совместимости с API
    date_from = date_from.astimezone(ZoneInfo('UTC'))
    date_to = date_to.astimezone(ZoneInfo('UTC'))
    
    return date_from, date_to

def generate_unique_filename(original_filename: str, directory: Optional[str] = None) -> str:
    """
    Генерирует уникальное имя файла, добавляя timestamp.
    
    Args:
        original_filename: Исходное имя файла.
        directory: Директория для сохранения (опционально).
        
    Returns:
        str: Уникальное имя файла.
    """
    if directory is None:
        directory = current_app.config['UPLOAD_FOLDER']
    
    # Получаем расширение файла
    _, ext = os.path.splitext(original_filename)
    
    # Генерируем имя с timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.splitext(os.path.basename(original_filename))[0]
    
    # Очищаем имя файла от специальных символов
    basename = re.sub(r'[^\w\-_]', '', basename)
    
    # Создаем новое имя файла
    new_filename = f"{basename}_{timestamp}{ext}"
    
    # Проверяем, существует ли такой файл
    full_path = os.path.join(directory, new_filename)
    counter = 1
    while os.path.exists(full_path):
        new_filename = f"{basename}_{timestamp}_{counter}{ext}"
        full_path = os.path.join(directory, new_filename)
        counter += 1
    
    return new_filename