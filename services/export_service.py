import os
import traceback
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from loguru import logger
from flask import current_app

from models.post_model import Post, BlogHostType
from models.analysis_model import PostAnalysis, TonalityType
from services.object_service import ObjectService

class ExportService:
    """Сервис для экспорта данных из БД."""
    
    def __init__(self):
        """Инициализация сервиса экспорта."""
        self.object_service = ObjectService()
    
    def clean_html_and_emoji(self, text: str) -> str:
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
    
    def export_posts_to_excel(self, posts: List[Post], output_file: str, include_analysis: bool = True) -> int:
        """
        Экспорт постов в Excel файл.
        
        Args:
            posts: Список постов для экспорта.
            output_file: Путь к выходному файлу.
            include_analysis: Включать ли результаты анализа.
            
        Returns:
            int: Количество экспортированных записей.
        """
        try:
            logger.info(f"Экспорт {len(posts)} постов в файл: {output_file}")
            
            # Подготовка данных для экспорта
            posts_data = []
            for post in posts:
                # Базовые данные поста
                post_dict = {
                    "post_id": post.post_id,
                    "title": post.title,
                    "content": self.clean_html_and_emoji(post.content),
                    "blog_host": post.blog_host,
                    "blog_host_type": post.blog_host_type.name if post.blog_host_type else "OTHER",
                    "published_on": post.published_on,
                    "simhash": post.simhash,
                    "url": post.url,
                    "object_ids": post.object_ids,
                    "object": self.object_service.get_object_names(post.object_ids)
                }
                
                # Если требуется включить результаты анализа
                if include_analysis and post.analysis:
                    post_dict.update({
                        "lmm_title": post.analysis.lmm_title,
                        "tonality": post.analysis.tonality.value if post.analysis.tonality else "неизвестно",
                        "description": post.analysis.description,
                        "analyzed_at": post.analysis.analyzed_at,
                        "model_used": post.analysis.model_used
                    })
                
                posts_data.append(post_dict)
            
            # Создаем DataFrame
            df = pd.DataFrame(posts_data)
            
            # Обработка столбца published_on: разделение на дату и время
            if 'published_on' in df.columns and not df['published_on'].empty:
                # Создаем отдельные столбцы для даты и времени
                df['date'] = df['published_on'].dt.date
                df['time'] = df['published_on'].dt.time
            
            # Упорядочиваем колонки для лучшей читаемости
            if include_analysis:
                columns_order = [
                    "post_id", "title", "lmm_title", "tonality", "description",
                    "published_on", "date", "time", "blog_host", "blog_host_type", 
                    "url", "content", "object_ids", "object", "simhash",
                    "analyzed_at", "model_used"
                ]
            else:
                columns_order = [
                    "post_id", "title", "published_on", "date", "time", "blog_host", "blog_host_type", 
                    "url", "content", "object_ids", "object", "simhash"
                ]
            
            # Переупорядочиваем колонки, если они есть в DataFrame
            existing_columns = [col for col in columns_order if col in df.columns]
            df = df[existing_columns]
            
            # Создаем директорию для экспорта, если её нет
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            
            # Сохраняем в Excel
            df.to_excel(output_file, index=False, engine="openpyxl")
            logger.info(f"Данные успешно экспортированы в файл: {output_file}")
            
            return len(df)
        except Exception as e:
            logger.error(f"Ошибка при экспорте в Excel: {e}")
            logger.error(traceback.format_exc())
            raise