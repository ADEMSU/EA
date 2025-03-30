import json
import traceback
import time
import re
import os
import hashlib
import requests
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from loguru import logger
from flask import current_app
from celery_app import celery
from celery import shared_task


from models.database import db
from models.post_model import Post
from models.analysis_model import PostAnalysis, TonalityType

@celery.task(name='analyze_batch_task')
def analyze_batch_task(batch, api_key, model, site_url, site_name):
    """
    Celery-задача для асинхронного анализа батча постов.
    
    Args:
        batch: Список постов для анализа.
        api_key: API ключ для LMM.
        model: Название модели для LMM.
        site_url: URL сайта.
        site_name: Название сайта.
        
    Returns:
        List[Dict]: Результаты анализа.
    """
    try:
        logger.info(f"Запуск асинхронной задачи анализа батча из {len(batch)} постов")
        
        # Создаем экземпляр сервиса LMM для анализа
        lmm_service = LmmService(api_key=api_key, model=model, site_url=site_url, site_name=site_name)
        
        # Создаем промпт для текущего батча
        prompt = lmm_service._create_prompt(batch)
        
        # Отправляем запрос в LMM
        results = lmm_service._send_to_lmm(prompt)
        
        logger.info(f"Задача завершена, получено {len(results)} результатов")
        
        # Обрабатываем результаты и сохраняем в БД
        # При использовании ContextTask в celery_app.py app.app_context() уже активен
        lmm_service.process_results(results)
        
        return results
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи анализа батча: {e}")
        logger.error(traceback.format_exc())
        return []


class LmmService:
    """Сервис для анализа текстов с помощью LLM через OpenRouter API."""
    
    def __init__(self, api_key=None, model=None, max_tokens_per_batch=30000, 
                 max_retries=3, retry_delay=5, site_url=None, site_name=None):
        """
        Инициализация сервиса LMM.
        
        Args:
            api_key: API ключ для OpenRouter.
            model: Модель для использования в OpenRouter.
            max_tokens_per_batch: Максимальное количество токенов в одном батче.
            max_retries: Максимальное количество попыток при ошибке.
            retry_delay: Задержка между повторными попытками в секундах.
            site_url: URL сайта для запросов к API.
            site_name: Название сайта для запросов к API.
        """
        self.api_key = api_key or current_app.config['OPENROUTER_API_KEY']
        self.model = model or current_app.config['LMM_MODEL']
        self.max_tokens_per_batch = max_tokens_per_batch
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.site_url = site_url or "https://epizode-analyzer.app"
        self.site_name = site_name or "Epizode Analyzer"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Кэш результатов для обеспечения консистентности между батчами
        self.results_cache = {}
        
        logger.info(f"Инициализация LMM Analyzer с моделью: {model}")
    
    def _create_batches(self, posts: List[Dict]) -> List[List[Dict]]:
        """
        Разделяет список постов на батчи, учитывая ограничение по токенам.
        
        Args:
            posts: Список постов для анализа.
            
        Returns:
            List[List[Dict]]: Список батчей для отправки в LMM.
        """
        batches = []
        current_batch = []
        current_batch_tokens = 0
        
        # Максимальное количество постов в одном батче даже если они малы
        max_posts_per_batch = 20
        
        # Минимальный размер батча (для избежания избыточного количества запросов)
        min_batch_tokens = self.max_tokens_per_batch // 5
        
        # Примерная оценка токенов (считаем 1 токен = 4 символа)
        for post in posts:
            # Подсчет приблизительного количества токенов в посте
            post_content = post.get("content", "")
            post_object = post.get("object", "")
            
            # Примерно считаем токены (4 символа ~ 1 токен)
            post_tokens = (len(post_content) + len(post_object)) // 4
            
            # Установка минимального количества токенов на пост
            post_tokens = max(50, post_tokens)  # Минимум 50 токенов на пост
            
            # Если текущий батч пуст или добавление поста не превысит лимит и не превысит макс. кол-во постов
            if (not current_batch or 
                (current_batch_tokens + post_tokens <= self.max_tokens_per_batch and 
                len(current_batch) < max_posts_per_batch)):
                current_batch.append(post)
                current_batch_tokens += post_tokens
            else:
                # Если в текущем батче мало токенов, но много постов
                # или если достигли макс. кол-во постов, добавляем текущий батч и начинаем новый
                batches.append(current_batch)
                current_batch = [post]
                current_batch_tokens = post_tokens
                
            # Если текущий батч достиг оптимального размера, завершаем его
            if current_batch_tokens >= min_batch_tokens and len(current_batch) >= 5:
                batches.append(current_batch)
                current_batch = []
                current_batch_tokens = 0
        
        # Добавляем последний батч, если он не пустой
        if current_batch:
            batches.append(current_batch)
        
        # Логирование информации о созданных батчах
        batch_sizes = [len(batch) for batch in batches]
        logger.info(f"Создано {len(batches)} батчей для анализа")
        logger.info(f"Размеры батчей (кол-во постов): {batch_sizes}")
        logger.info(f"Минимальный размер батча: {min(batch_sizes) if batch_sizes else 0} постов")
        logger.info(f"Максимальный размер батча: {max(batch_sizes) if batch_sizes else 0} постов")
        logger.info(f"Средний размер батча: {sum(batch_sizes)/len(batch_sizes) if batch_sizes else 0:.1f} постов")
        
        return batches
    
    def _create_prompt(self, batch: List[Dict]) -> str:
        """
        Создает промпт для анализа постов в LMM с акцентом на консистентность.
        
        Args:
            batch: Список постов для анализа.
            
        Returns:
            str: Промпт для отправки в LMM.
        """
        prompt = """
Проанализируй следующие посты. Для каждого поста:

1. Определи тональность текста: "негативная", "нейтральная" или "позитивная".
2. Проведи NER-анализ, где главная сущность указана в поле "object".
3. Найди другие сущности в тексте и их отношения к главной сущности.
4. Сгенерируй краткое описание из 3-5 предложений на основе NER-анализа.
5. Создай заголовок для поста.

КРИТИЧЕСКИ ВАЖНО: Для ОДИНАКОВЫХ наборов сущностей и отношений между ними нужно генерировать ПОЛНОСТЬЮ ИДЕНТИЧНЫЕ тональности, описания и заголовки.
Например, если в двух постах упоминается "Скоч Андрей" и его благотворительная деятельность, описания и заголовки для этих постов должны быть идентичными.

Если сходные (не обязательно идентичные) посты упоминают одинаковые объекты и действия, тональность и общий смысл описаний должны совпадать.
Проанализируй посты как группу и установи общую схему именования и формулировок для похожих типов контента.

ВАЖНО: Ответ должен быть строго в следующем формате (без отклонений):

### АНАЛИЗ ПОСТА {post_id}
Тональность: [негативная/нейтральная/позитивная]
Краткое описание: [3-5 предложений]
Заголовок: [заголовок]

Анализируемые посты:
"""
        
        # Сначала группируем посты по объектам, чтобы помочь модели видеть связанные посты
        # Это помогает обеспечить консистентность между похожими постами
        object_groups = {}
        for post in batch:
            obj = post.get('object', 'неизвестно')
            if obj not in object_groups:
                object_groups[obj] = []
            object_groups[obj].append(post)
        
        # Теперь добавляем информацию о постах, группируя по объектам
        post_counter = 1
        
        for obj, posts in object_groups.items():
            prompt += f"\n--- Группа постов о '{obj}' ---\n"
            
            for post in posts:
                prompt += f"\n--- Пост {post_counter} (ID: {post.get('post_id', '')}) ---\n"
                prompt += f"post_id: {post.get('post_id', '')}\n"
                prompt += f"object: {obj}\n"
                content = post.get('content', '').strip()
                if not content:
                    content = "Контент отсутствует"
                prompt += f"content: {content}\n"
                post_counter += 1
        
        return prompt
    
    def analyze_posts(self, posts_data: List[Dict]) -> List[Dict]:
        """
        Анализирует посты с помощью LMM с обеспечением консистентности.
        
        Args:
            posts_data: Список словарей с данными постов.
                
        Returns:
            List[Dict]: Результаты анализа.
        """
        # Инициируем асинхронные задачи для обработки постов
        task_ids = []
        
        # Создаем батчи для обработки
        batches = self._create_batches(posts_data)
        logger.info(f"Начинаем анализ {len(posts_data)} постов в {len(batches)} батчах")
        
        # Запускаем задачи для каждого батча
        for i, batch in enumerate(batches):
            logger.info(f"Запуск задачи для батча {i+1}/{len(batches)} ({len(batch)} постов)")
            task = analyze_batch_task.delay(batch, self.api_key, self.model, self.site_url, self.site_name)
            task_ids.append(task.id)
        
        return {"task_ids": task_ids}
    
    def process_results(self, results: List[Dict]):
        """
        Обрабатывает результаты анализа LMM и сохраняет их в базу данных.
        
        Args:
            results: Список результатов анализа.
        """
        logger.info(f"Обработка {len(results)} результатов анализа")
        
        for result in results:
            try:
                post_id = result.get('post_id')
                if not post_id:
                    logger.warning(f"Результат без post_id: {result}")
                    continue
                
                # Ищем пост в базе данных
                post = Post.query.filter_by(post_id=post_id).first()
                if not post:
                    logger.warning(f"Пост с ID {post_id} не найден в базе данных")
                    continue
                
                # Ищем существующий анализ для обновления
                analysis = PostAnalysis.query.filter_by(post_id=post.id).first()
                if analysis:
                    # Обновляем существующий анализ
                    analysis.lmm_title = result.get('title', '')
                    analysis.description = result.get('description', '')
                    analysis.tonality = self._parse_tonality(result.get('tonality', ''))
                    analysis.analyzed_at = datetime.utcnow()
                    analysis.model_used = self.model
                else:
                    # Создаем новый анализ
                    analysis = PostAnalysis(
                        post_id=post.id,
                        lmm_title=result.get('title', ''),
                        description=result.get('description', ''),
                        tonality=self._parse_tonality(result.get('tonality', '')),
                        analyzed_at=datetime.utcnow(),
                        model_used=self.model
                    )
                    db.session.add(analysis)
                
                # Если для поста нет заголовка, используем заголовок из LMM
                if not post.title and result.get('title'):
                    post.title = result.get('title')
                
                db.session.commit()
                logger.info(f"Результаты анализа для поста {post_id} сохранены в БД")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке результата анализа: {e}")
                logger.error(traceback.format_exc())
                db.session.rollback()
        
        logger.info(f"Завершена обработка {len(results)} результатов анализа")
    
    def _send_to_lmm(self, prompt: str) -> List[Dict]:
        """
        Отправляет запрос в LMM и обрабатывает ответ.
        
        Args:
            prompt: Промпт для отправки.
            
        Returns:
            List[Dict]: Результаты анализа в виде списка словарей.
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Отправка запроса в LMM (попытка {attempt+1})")
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.site_name
                }
                
                # Проверяем длину промпта
                prompt_length = len(prompt)
                logger.info(f"Длина промпта: {prompt_length} символов")
                
                # Если промпт слишком длинный, возможно есть ограничения API
                if prompt_length > 100000:  # Большинство API имеют лимиты на длину запроса
                    logger.warning(f"Промпт очень длинный: {prompt_length} символов. Возможно превышение лимитов API.")
                
                # Логируем начало и конец промпта
                logger.debug(f"Начало промпта: {prompt[:200]}...")
                logger.debug(f"Конец промпта: ...{prompt[-200:]}")
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                
                # Проверяем размер JSON-запроса
                json_payload = json.dumps(payload)
                logger.info(f"Размер JSON-запроса: {len(json_payload)} байт")
                
                # Устанавливаем более длительный таймаут для больших запросов
                timeout = max(120, prompt_length // 1000)  # Адаптивный таймаут
                logger.info(f"Установлен таймаут запроса: {timeout} секунд")
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
                
                # Логируем статус ответа
                logger.info(f"Статус ответа: {response.status_code}")
                
                response.raise_for_status()
                response_data = response.json()
                
                # Проверка на наличие ошибок в ответе
                if "error" in response_data:
                    logger.error(f"Ошибка API: {response_data['error']}")
                    raise Exception(f"API вернул ошибку: {response_data['error']}")
                
                # Извлекаем ответ модели
                if "choices" not in response_data or not response_data["choices"]:
                    logger.error(f"Неожиданный формат ответа: {response_data}")
                    raise Exception("Неожиданный формат ответа API: отсутствует поле 'choices'")
                    
                content = response_data["choices"][0]["message"]["content"]
                
                # Логируем размер ответа
                response_length = len(content)
                logger.info(f"Длина ответа: {response_length} символов")
                
                # Сохраняем запрос и ответ для диагностики
                debug_dir = "logs"
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, f"lmm_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(f"==== LMM Request {datetime.now()} ====\n")
                    f.write(f"Prompt length: {prompt_length}\n")
                    f.write(f"Full prompt:\n{prompt}\n\n")
                    f.write(f"==== LMM Response ====\n")
                    f.write(f"Response length: {response_length}\n")
                    f.write(f"Full response:\n{content}\n")
                
                logger.info(f"Запрос и ответ сохранены в файл: {debug_file}")
                
                # Парсим структурированный текст
                results = self._parse_lmm_response(content)
                
                # Проверка результатов
                if not results:
                    logger.warning("Ответ получен, но результаты не распарсены")
                    
                logger.info(f"Успешно получен ответ с {len(results)} результатами")
                return results
                    
            except Exception as e:
                logger.error(f"Ошибка при запросе к LMM: {e}")
                logger.error(traceback.format_exc())
                
                if attempt < self.max_retries - 1:
                    logger.info(f"Повторная попытка через {self.retry_delay} секунд...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Исчерпаны все попытки")
                    return []
        
        return []
    
    def _parse_lmm_response(self, response_text: str) -> List[Dict]:
        """
        Парсит ответ LMM в структурированном текстовом формате.
        
        Args:
            response_text: Текстовый ответ от LMM.
            
        Returns:
            List[Dict]: Список словарей с результатами анализа.
        """
        try:
            results = []
            
            # Если ответ пустой или слишком короткий
            if not response_text or len(response_text) < 50:
                logger.warning(f"Слишком короткий ответ LMM: {response_text}")
                return results
            
            # Проверка на нераспознанные форматы ответов
            if "### АНАЛИЗ ПОСТА" not in response_text:
                logger.warning("Ответ не содержит ожидаемого маркера '### АНАЛИЗ ПОСТА'")
                
                # Попробуем найти альтернативные маркеры
                alternative_marker = False
                for marker in ["Пост", "Анализ поста", "Post analysis"]:
                    if marker in response_text:
                        logger.info(f"Найден альтернативный маркер: {marker}")
                        alternative_marker = True
                        break
                
                if not alternative_marker:
                    logger.error("Не удалось найти маркеры анализа поста в ответе")
                    return results
            
            # Регулярные выражения для извлечения данных
            post_blocks = re.split(r'###\s+АНАЛИЗ\s+ПОСТА\s+|Анализ\s+поста\s+|Пост\s+\d+:|Post\s+analysis\s+', response_text)
            
            # Пропускаем первый элемент, если он пустой (перед первым ###)
            if post_blocks and not post_blocks[0].strip():
                post_blocks = post_blocks[1:]
            
            for block in post_blocks:
                if not block.strip():
                    continue
                    
                try:
                    # Извлекаем post_id из первой строки разными способами
                    post_id_patterns = [
                        r'([^\n]+)',  # Любая строка до первого перевода строки
                        r'(\d+)',     # Любое число
                        r'post_id:\s*([^\n]+)',  # Явно указанный post_id
                        r'ID:\s*([^\n]+)'  # Альтернативное указание ID
                    ]
                    
                    post_id = "unknown"
                    for pattern in post_id_patterns:
                        match = re.search(pattern, block.strip())
                        if match:
                            post_id = match.group(1).strip()
                            break
                    
                    # Извлекаем тональность разными способами
                    tonality_patterns = [
                        r'Тональность:\s*([^\n]+)',
                        r'Тональность\s*[-:]\s*([^\n]+)',
                        r'Тон[^:]*:\s*([^\n]+)',
                        r'Sentiment:\s*([^\n]+)'
                    ]
                    
                    tonality = ""
                    for pattern in tonality_patterns:
                        match = re.search(pattern, block)
                        if match:
                            tonality = match.group(1).strip()
                            break
                    
                    # Извлекаем краткое описание разными способами
                    description_patterns = [
                        r'Краткое описание:\s*([^\n]+(?:\n[^\n]+)*?)(?=\nЗаголовок:|$)',
                        r'Описание:\s*([^\n]+(?:\n[^\n]+)*?)(?=\nЗаголовок:|$)',
                        r'Краткое содержание:\s*([^\n]+(?:\n[^\n]+)*?)(?=\nЗаголовок:|$)',
                        r'Description:\s*([^\n]+(?:\n[^\n]+)*?)(?=\nTitle:|$)'
                    ]
                    
                    description = ""
                    for pattern in description_patterns:
                        match = re.search(pattern, block, re.DOTALL)
                        if match:
                            description = match.group(1).strip()
                            break
                    
                    # Извлекаем заголовок разными способами
                    title_patterns = [
                        r'Заголовок:\s*([^\n]+)',
                        r'Заголовок\s*[-:]\s*([^\n]+)',
                        r'Тема:\s*([^\n]+)',
                        r'Title:\s*([^\n]+)'
                    ]
                    
                    title = ""
                    for pattern in title_patterns:
                        match = re.search(pattern, block)
                        if match:
                            title = match.group(1).strip()
                            break
                    
                    # Проверяем, что получены хотя бы некоторые данные
                    if any([tonality, description, title]) or post_id != "unknown":
                        results.append({
                            "post_id": post_id,
                            "tonality": tonality,
                            "description": description,
                            "title": title
                        })
                    else:
                        logger.warning(f"Не удалось извлечь данные из блока: {block[:100]}...")
                    
                except Exception as e:
                    logger.error(f"Ошибка при парсинге блока ответа: {e}")
                    logger.error(f"Содержимое блока: {block[:200]}...")
                    logger.error(traceback.format_exc())
            
            return results
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа LMM: {e}")
            logger.error(traceback.format_exc())
            return []

    def _get_content_hash(self, content: str) -> str:
        """Создаёт простой хэш контента для использования в кэше."""
        # Используем простое хеширование для нахождения похожих постов
        # Берем только первые 200 символов, чтобы похожие посты имели одинаковый хэш
        content_sample = content[:200].lower()
        return hashlib.md5(content_sample.encode('utf-8')).hexdigest()

    def _update_cache(self, batch: List[Dict], results: List[Dict]):
        """Обновляет кэш результатов для обеспечения консистентности."""
        for i, post in enumerate(batch):
            if i >= len(results) or not post or not results[i]:
                continue
            
            result = results[i]
            obj = post.get('object', '')
            content_hash = self._get_content_hash(post.get('content', ''))
            cache_key = f"{obj}:{content_hash}"
            
            # Сохраняем результат в кэш без post_id
            cached_result = result.copy()
            # Используем только нужные поля
            self.results_cache[cache_key] = {
                'post_id': cached_result.get('post_id', ''),
                'tonality': cached_result.get('tonality', ''),
                'description': cached_result.get('description', ''),
                'title': cached_result.get('title', '')
            }
    
    def _parse_tonality(self, tonality_str: str) -> TonalityType:
        """
        Преобразует строковое представление тональности в enum TonalityType.
        
        Args:
            tonality_str: Строковое представление тональности.
            
        Returns:
            TonalityType: Значение enum.
        """
        tonality_str = tonality_str.lower()
        if "негатив" in tonality_str:
            return TonalityType.NEGATIVE
        elif "позитив" in tonality_str:
            return TonalityType.POSITIVE
        elif "нейтрал" in tonality_str:
            return TonalityType.NEUTRAL
        else:
            return TonalityType.UNKNOWN


@shared_task
def analyze_batch_task(batch, api_key, model, site_url, site_name):
    """
    Celery-задача для асинхронного анализа батча постов.
    
    Args:
        batch: Список постов для анализа.
        api_key: API ключ для LMM.
        model: Название модели для LMM.
        site_url: URL сайта.
        site_name: Название сайта.
        
    Returns:
        List[Dict]: Результаты анализа.
    """
    try:
        logger.info(f"Запуск асинхронной задачи анализа батча из {len(batch)} постов")
        
        # Создаем экземпляр сервиса LMM для анализа
        lmm_service = LmmService(api_key=api_key, model=model, site_url=site_url, site_name=site_name)
        
        # Создаем промпт для текущего батча
        prompt = lmm_service._create_prompt(batch)
        
        # Отправляем запрос в LMM
        results = lmm_service._send_to_lmm(prompt)
        
        logger.info(f"Задача завершена, получено {len(results)} результатов")
        
        # Обрабатываем результаты и сохраняем в БД
        with app.app_context():
            lmm_service.process_results(results)
        
        return results
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи анализа батча: {e}")
        logger.error(traceback.format_exc())
        return []