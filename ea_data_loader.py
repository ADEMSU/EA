#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import traceback
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger
from dotenv import load_dotenv

from mlg_manager import MlgManager
from post import Post, BlogHostType
from object_dict import get_object_mapping
from lmm_analyzer import LmmAnalyzer

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логгера
logger.add("export_data.log", rotation="10 MB", level="INFO")


def get_msk_date_range(days_ago=1, time_from=None, time_to=None):
    """
    Получает диапазон дат с учетом московского часового пояса
    Возвращает период с указанного времени начальной даты до указанного времени конечной даты по МСК
    
    Args:
        days_ago (int): Количество дней назад от текущей даты
        time_from (str, optional): Время начала в формате HH:MM
        time_to (str, optional): Время окончания в формате HH:MM
        
    Returns:
        tuple: (date_from, date_to) в UTC
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
        except (ValueError, TypeError) as e:
            logger.warning(f"Неверный формат времени начала ({time_from}): {e}. Используем 00:00.")
    
    # Если указано время окончания, устанавливаем его
    if time_to:
        try:
            hour, minute = map(int, time_to.split(':'))
            date_to = date_to.replace(hour=hour, minute=minute, second=59, microsecond=0)
        except (ValueError, TypeError) as e:
            logger.warning(f"Неверный формат времени окончания ({time_to}): {e}. Используем 23:59.")
    
    # Преобразуем в UTC для совместимости с API
    date_from = date_from.astimezone(ZoneInfo('UTC'))
    date_to = date_to.astimezone(ZoneInfo('UTC'))
    
    return date_from, date_to


def parse_date(date_str):
    """Парсинг даты из строки с поддержкой разных форматов."""
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


def get_date_range(date_from_str, date_to_str, time_from=None, time_to=None):
    """
    Получает диапазон дат из строковых представлений с учетом московского часового пояса.
    Устанавливает указанное время для начальной и конечной даты.
    
    Args:
        date_from_str (str): Строковое представление начальной даты
        date_to_str (str): Строковое представление конечной даты
        time_from (str, optional): Время начала в формате HH:MM
        time_to (str, optional): Время окончания в формате HH:MM
        
    Returns:
        tuple: (date_from, date_to) в UTC
    """
    try:
        date_from = parse_date(date_from_str)
        date_to = parse_date(date_to_str)
        
        # Устанавливаем время начала
        if time_from:
            try:
                hour, minute = map(int, time_from.split(':'))
                date_from = date_from.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except (ValueError, TypeError) as e:
                logger.warning(f"Неверный формат времени начала ({time_from}): {e}. Используем 00:00.")
                date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Устанавливаем время окончания
        if time_to:
            try:
                hour, minute = map(int, time_to.split(':'))
                date_to = date_to.replace(hour=hour, minute=minute, second=59, microsecond=0)
            except (ValueError, TypeError) as e:
                logger.warning(f"Неверный формат времени окончания ({time_to}): {e}. Используем 23:59.")
                date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=0)
        
        # Преобразуем в UTC для совместимости с API
        date_from = date_from.astimezone(ZoneInfo('UTC'))
        date_to = date_to.astimezone(ZoneInfo('UTC'))
        
        return date_from, date_to
    except Exception as e:
        logger.error(f"Ошибка при обработке дат: {e}")
        logger.error(traceback.format_exc())
        raise


def post_to_dict(post):
    """Преобразование объекта Post в словарь для DataFrame."""
    try:
        # Подготовим объект, преобразовав вложенные структуры в строки
        post_dict = post.dict(exclude={"raw"})
        
        # Преобразование типа блога в текстовое представление
        post_dict["blog_host_type"] = BlogHostType(post_dict["blog_host_type"]).name
        
        # Преобразуем списки в строки
        post_dict["object_ids"] = ", ".join(post_dict["object_ids"]) if post_dict["object_ids"] else ""
        
        return post_dict
    except Exception as e:
        logger.error(f"Ошибка при преобразовании поста в словарь: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "post_id": getattr(post, "post_id", "unknown")}


def clean_html_and_emoji(text):
    """Удаление HTML-тегов и эмодзи из текста."""
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


def map_object_ids_to_names(object_ids_str, object_mapping):
    """Сопоставление id объектов с их названиями."""
    if not object_ids_str:
        return ""
    
    # Разделение строки идентификаторов на отдельные id
    object_ids = [obj_id.strip() for obj_id in object_ids_str.split(',') if obj_id.strip()]
    
    # Поиск соответствующих имен объектов
    object_names = []
    for obj_id in object_ids:
        # Пробуем сопоставить как строку
        if obj_id in object_mapping:
            object_names.append(object_mapping[obj_id])
        # Пробуем как числовое значение (для ID, которые могут быть числами)
        elif obj_id.isdigit() and str(int(obj_id)) in object_mapping:
            object_names.append(object_mapping[str(int(obj_id))])
        else:
            # Если не нашли точное соответствие, логируем это для отладки
            logger.debug(f"Не найдено соответствие для ID объекта: {obj_id}")
    
    return ", ".join(object_names)


def prepare_posts_data(posts):
    """Подготовка данных постов к экспорту в Excel"""
    # Преобразуем посты в список словарей
    logger.info(f"Подготовка {len(posts)} постов")
    posts_data = [post_to_dict(post) for post in posts]
    
    # Создаем DataFrame
    df = pd.DataFrame(posts_data)
    
    # Загрузка маппинга объектов из словаря
    object_mapping = get_object_mapping()
    
    # Очистка столбцов title и content от HTML-тегов и эмодзи
    if 'title' in df.columns:
        df['title'] = df['title'].apply(clean_html_and_emoji)
    
    if 'content' in df.columns:
        df['content'] = df['content'].apply(clean_html_and_emoji)
    
    # Создание нового столбца object на основе object_ids
    if 'object_ids' in df.columns:
        df['object'] = df['object_ids'].apply(lambda x: map_object_ids_to_names(x, object_mapping))
    
    # Обработка столбца published_on: разделение на дату и время
    if 'published_on' in df.columns and not df['published_on'].empty:
        # Сохраняем исходное значение published_on
        df['published_on_original'] = df['published_on']
        
        # Преобразуем в локальное время (без информации о часовом поясе)
        df['published_on'] = df['published_on'].dt.tz_localize(None)
        
        # Создаем отдельные столбцы для даты и времени
        df['date'] = df['published_on'].dt.date
        df['time'] = df['published_on'].dt.time
        
        # Удаляем временный столбец
        df.drop('published_on_original', axis=1, inplace=True)
    
    return df


def export_to_excel(posts, output_file, analyze_with_lmm=False):
    """Экспорт постов в Excel файл с дополнительной обработкой."""
    try:
        # Подготовка данных для экспорта
        df = prepare_posts_data(posts)
        
        # Если требуется анализ LMM
        if analyze_with_lmm:
            # Получаем только нужные для анализа колонки
            analysis_data = []
            for _, row in df.iterrows():
                analysis_data.append({
                    'post_id': row['post_id'],
                    'content': row['content'],
                    'object': row['object'] if 'object' in row else ''
                })
            
            # Запускаем анализ через LMM
            lmm_results = analyze_with_lmm_api(analysis_data, output_file)
            
            # Создаем DataFrame с результатами анализа
            lmm_df = pd.DataFrame(lmm_results)
            
            # Объединяем результаты с основным DataFrame
            if not lmm_df.empty:
                # Преобразуем post_id в одинаковый тип для обоих DataFrame
                df['post_id'] = df['post_id'].astype(str)
                lmm_df['post_id'] = lmm_df['post_id'].astype(str)
                
                # Выполняем слияние по post_id
                df = pd.merge(df, lmm_df, on='post_id', how='left')
                
                # Добавляем колонку с заголовком от LMM если изначальный заголовок пустой
                df['final_title'] = df.apply(
                    lambda row: row['title_y'] if pd.isna(row['title_x']) or row['title_x'] == '' else row['title_x'], 
                    axis=1
                )
                
                # Переименовываем колонки для удобства
                if 'title_x' in df.columns and 'title_y' in df.columns:
                    df = df.rename(columns={'title_x': 'orig_title', 'title_y': 'lmm_title'})
                
                # Удаляем колонку final_title, если не нужна
                # df.drop('final_title', axis=1, inplace=True)
        else:
            # Экспортируем данные в Excel
            _save_dataframe_to_excel(df, output_file)
        
        # Упорядочиваем колонки для лучшей читаемости
        if analyze_with_lmm:
            columns_order = [
                "post_id", "orig_title", "lmm_title", "final_title", "tonality", "description",
                "published_on", "date", "time", "blog_host", "blog_host_type", 
                "url", "content", "object_ids", "object", "simhash"
            ]
        else:
            columns_order = [
                "post_id", "title", "published_on", "date", "time", "blog_host", "blog_host_type", 
                "url", "content", "object_ids", "object", "simhash"
            ]
        
        # Переупорядочиваем колонки, если они есть в DataFrame
        existing_columns = [col for col in columns_order if col in df.columns]
        df = df[existing_columns]
        
        # Сохраняем финальный результат в Excel
        _save_dataframe_to_excel(df, output_file)
        
        return len(df)
    except Exception as e:
        logger.error(f"Ошибка при экспорте в Excel: {e}")
        logger.error(traceback.format_exc())
        raise


def _save_dataframe_to_excel(df, output_file):
    """Сохранение DataFrame в Excel файл"""
    try:
        # Создаем директорию для экспорта, если её нет
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Сохраняем в Excel
        logger.info(f"Сохранение данных в файл: {output_file}")
        df.to_excel(output_file, index=False, engine="openpyxl")
        logger.info(f"Данные успешно сохранены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении в Excel: {e}")
        logger.error(traceback.format_exc())
        return False


def append_lmm_results_to_excel(batch, batch_results, output_file):
    """
    Функция обратного вызова для обработки результатов батча LMM анализа
    и добавления их в промежуточный Excel файл
    
    Args:
        batch: Список постов в текущем батче
        batch_results: Результаты анализа LMM для текущего батча
        output_file: Путь к файлу Excel для сохранения результатов
    """
    try:
        logger.info(f"Обработка результатов батча LMM ({len(batch_results)} результатов)")
        
        # Создаем DataFrame с результатами анализа текущего батча
        lmm_df = pd.DataFrame(batch_results)
        
        # Проверяем существование файла
        file_exists = os.path.isfile(output_file)
        
        if file_exists:
            # Если файл существует, загружаем его и добавляем новые данные
            try:
                # Загружаем существующий файл
                existing_df = pd.read_excel(output_file)
                
                # Конвертируем post_id в строки
                if 'post_id' in existing_df.columns:
                    existing_df['post_id'] = existing_df['post_id'].astype(str)
                
                # Конвертируем post_id в строки в новом DataFrame
                if 'post_id' in lmm_df.columns:
                    lmm_df['post_id'] = lmm_df['post_id'].astype(str)
                
                # Удаляем дублирующиеся записи (по post_id)
                combined_df = pd.concat([existing_df, lmm_df])
                combined_df = combined_df.drop_duplicates(subset=['post_id'], keep='last')
                
                # Сохраняем обновленный DataFrame
                _save_dataframe_to_excel(combined_df, output_file)
                logger.info(f"Результаты батча добавлены в существующий файл: {output_file}")
            except Exception as e:
                logger.error(f"Ошибка при обновлении существующего Excel файла: {e}")
                logger.error(traceback.format_exc())
                
                # В случае ошибки, пробуем сохранить только новые данные с уникальным именем
                backup_file = f"{os.path.splitext(output_file)[0]}_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                _save_dataframe_to_excel(lmm_df, backup_file)
                logger.info(f"Результаты батча сохранены в резервный файл: {backup_file}")
        else:
            # Если файл не существует, просто сохраняем новые данные
            _save_dataframe_to_excel(lmm_df, output_file)
            logger.info(f"Создан новый файл с результатами батча: {output_file}")
    
    except Exception as e:
        logger.error(f"Ошибка при обработке результатов батча: {e}")
        logger.error(traceback.format_exc())


def analyze_with_lmm_api(posts_data, output_file):
    """
    Анализирует посты с помощью LMM API
    
    Args:
        posts_data: Список словарей с данными постов
        output_file: Путь к файлу Excel для сохранения результатов
        
    Returns:
        List[Dict]: Результаты анализа
    """
    try:
        logger.info(f"Начинаем анализ {len(posts_data)} постов с помощью LMM")
        
        # Получаем ключ API из переменных окружения
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("Отсутствует ключ API для OpenRouter в переменных окружения (OPENROUTER_API_KEY)")
            return []
        
        # Получаем модель из переменных окружения или используем значение по умолчанию
        model = os.getenv("LMM_MODEL", "deepseek/deepseek-chat-v3-0324:free")
        
        # Инициализируем анализатор
        analyzer = LmmAnalyzer(
            api_key=api_key,
            model=model,
            site_url=os.getenv("SITE_URL", "https://epizode-analyzer.app"),
            site_name=os.getenv("SITE_NAME", "Epizode Analyzer")
        )
        
        # Создаем промежуточный файл для результатов LMM
        lmm_output_file = f"{os.path.splitext(output_file)[0]}_lmm_results.xlsx"
        
        # Определяем функцию обратного вызова для обработки каждого батча
        def batch_callback(batch, batch_results):
            append_lmm_results_to_excel(batch, batch_results, lmm_output_file)
        
        # Запускаем анализ с функцией обратного вызова
        results = analyzer.analyze_posts(posts_data, batch_callback=batch_callback)
        
        logger.info(f"Успешно получены результаты анализа для {len(results)} постов")
        return results
    except Exception as e:
        logger.error(f"Ошибка при анализе постов с помощью LMM: {e}")
        logger.error(traceback.format_exc())
        return []


def get_medialogiya_data(username, password, wsdl, report_id, date_from, date_to, output_file, analyze_with_lmm=False):
    """Получение данных из Медиалогии и сохранение в Excel."""
    try:
        logger.info(f"Запуск экспорта данных из Медиалогии за период {date_from} - {date_to}")
        
        # Инициализация менеджера Медиалогии
        mlg = MlgManager(username, password, wsdl)
        
        # Проверка количества постов в указанном периоде
        logger.info("Получение количества постов в указанном периоде...")
        n_posts = mlg.get_n_posts(report_id, date_from, date_to)
        logger.info(f"Найдено постов за период: {n_posts}")
        
        if n_posts == 0:
            logger.warning("Нет данных за указанный период")
            return 0
        
        # Получение постов
        logger.info("Загрузка постов из Медиалогии...")
        posts = mlg.get_posts(report_id, date_from, date_to)
        logger.info(f"Получено постов: {len(posts)}")
        
        # Если нужно проанализировать с помощью LMM
        if analyze_with_lmm:
            # Генерируем имя файла с суффиксом _F для финального файла с результатами LMM
            output_file_base, output_file_ext = os.path.splitext(output_file)
            output_file_lmm = f"{output_file_base}_F{output_file_ext}"
            
            # Сначала сохраняем исходные данные в обычный файл
            df = prepare_posts_data(posts)
            _save_dataframe_to_excel(df, output_file)
            
            # Затем анализируем и сохраняем в финальный файл с результатами LMM
            return export_to_excel(posts, output_file_lmm, analyze_with_lmm=True)
        else:
            # Если анализ не нужен, просто экспортируем в Excel
            return export_to_excel(posts, output_file)
    except Exception as e:
        logger.error(f"Ошибка при получении данных из Медиалогии: {e}")
        logger.error(traceback.format_exc())
        raise


def main():
    try:
        parser = argparse.ArgumentParser(description="Экспорт данных из Медиалогии в Excel")
        
        # Параметры авторизации и подключения (можно взять из .env)
        parser.add_argument("--username", default=os.getenv("MEDIALOGIA_USERNAME"), help="Имя пользователя для Медиалогии")
        parser.add_argument("--password", default=os.getenv("MEDIALOGIA_PASSWORD"), help="Пароль для Медиалогии")
        parser.add_argument("--wsdl", default=os.getenv("MEDIALOGIA_WSDL_URL"), help="URL WSDL API Медиалогии")
        
        # Параметры запроса
        parser.add_argument("--report-id", default=os.getenv("MEDIALOGIA_REPORT_ID"), help="ID отчета в Медиалогии")
        
        # Группа взаимоисключающих параметров для выбора периода
        date_group = parser.add_mutually_exclusive_group(required=True)
        date_group.add_argument("--days-ago", type=int, help="Количество дней назад (например, 1 для вчерашнего дня)")
        date_group.add_argument("--date-from", help="Дата начала периода (YYYY-MM-DD или DD.MM.YYYY)")
        
        parser.add_argument("--date-to", help="Дата окончания периода (YYYY-MM-DD или DD.MM.YYYY, обязательно если указан --date-from)")
        
        # Новые параметры для указания времени
        parser.add_argument("--time-from", help="Время начала в формате HH:MM (например, 09:30)")
        parser.add_argument("--time-to", help="Время окончания в формате HH:MM (например, 18:45)")
        
        # Параметры сохранения
        default_export_dir = os.path.join(os.getenv("DATA_DIRECTORY", "data"), "exports")
        parser.add_argument("--output", default=None, help="Путь для сохранения Excel файла")
        
        # Параметр для анализа с помощью LMM
        parser.add_argument("--analyze", action="store_true", help="Анализировать данные с помощью LMM")
        
        args = parser.parse_args()
        
        # Проверка обязательных параметров
        if not args.username or not args.password or not args.wsdl or not args.report_id:
            missing = []
            if not args.username:
                missing.append("username")
            if not args.password:
                missing.append("password")
            if not args.wsdl:
                missing.append("wsdl")
            if not args.report_id:
                missing.append("report-id")
            
            parser.error(f"Отсутствуют обязательные параметры: {', '.join(missing)}. "
                        f"Укажите их в командной строке или в файле .env")
        
        # Проверка соответствия параметров дат
        if args.date_from and not args.date_to:
            parser.error("Если указан --date-from, также должен быть указан --date-to")
        
        # Если указан анализ LMM, проверяем наличие API ключа
        if args.analyze and not os.getenv("OPENROUTER_API_KEY"):
            parser.error("Для анализа с помощью LMM необходимо указать OPENROUTER_API_KEY в файле .env")
        
        # Определение периода с учетом времени
        if args.days_ago is not None:
            date_from, date_to = get_msk_date_range(args.days_ago, args.time_from, args.time_to)
        else:
            date_from, date_to = get_date_range(args.date_from, args.date_to, args.time_from, args.time_to)
        
        # Формирование имени выходного файла с текущей датой/временем в названии
        if args.output is None:
            # Создаем директорию, если её нет
            os.makedirs(default_export_dir, exist_ok=True)
            
            # Используем текущую дату и время для имени файла
            current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
            args.output = os.path.join(default_export_dir, f"{current_datetime}_data.xlsx")
        
        # Проверка расширения файла
        if not args.output.endswith(".xlsx"):
            args.output += ".xlsx"
        
        # Получение и сохранение данных
        count = get_medialogiya_data(
            args.username, 
            args.password, 
            args.wsdl, 
            args.report_id, 
            date_from, 
            date_to, 
            args.output,
            analyze_with_lmm=args.analyze
        )
        
        # Формируем сообщение в зависимости от режима
        output_msg = args.output
        if args.analyze:
            output_base, output_ext = os.path.splitext(args.output)
            output_lmm = f"{output_base}_F{output_ext}"
            lmm_results = f"{output_base}_lmm_results{output_ext}"
            output_msg = f"{args.output}, {lmm_results} (промежуточные результаты LMM) и {output_lmm} (с анализом LMM)"
        
        # Добавляем информацию о временном периоде
        time_period = ""
        if args.time_from or args.time_to:
            time_from = args.time_from or "00:00"
            time_to = args.time_to or "23:59"
            time_period = f" в период с {time_from} до {time_to}"
        
        logger.info(f"Экспорт завершен{time_period}. Сохранено {count} записей в файлы {output_msg}")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()