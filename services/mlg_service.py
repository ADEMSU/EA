import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import zeep
from loguru import logger
from flask import current_app

from models.database import db
from models.post_model import Post, BlogHostType
from services.object_service import ObjectService

class MlgService:
    """Сервис для работы с API Медиалогии."""
    
    def __init__(self, username=None, password=None, wsdl=None):
        """
        Инициализация сервиса с данными для доступа к API.
        
        Args:
            username (str, optional): Имя пользователя для API Медиалогии.
            password (str, optional): Пароль для API Медиалогии.
            wsdl (str, optional): URL WSDL API Медиалогии.
        """
        self.username = username or current_app.config['MEDIALOGIA_USERNAME']
        self.password = password or current_app.config['MEDIALOGIA_PASSWORD']
        self.wsdl = wsdl or current_app.config['MEDIALOGIA_WSDL_URL']
        self.batch_size = 200
        
        try:
            self.client = zeep.Client(wsdl=self.wsdl)
            logger.info(f"Инициализация Медиалогии: WSDL {self.wsdl}")
        except Exception as e:
            logger.error(f"Ошибка инициализации клиента Медиалогии: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def call_api(self, method_name: str, **kwargs) -> Any:
        """
        Вызов метода API Медиалогии.
        
        Args:
            method_name: Название метода API.
            **kwargs: Аргументы для вызова метода.
        
        Returns:
            Any: Результат вызова метода API.
        """
        try:
            method = getattr(self.client.service, method_name)
            logger.info(f"Вызов метода {method_name} с параметрами: {kwargs}")
            
            reply = method(**kwargs)
            
            # Проверка наличия ошибки через hasattr вместо get
            if hasattr(reply, 'Error') and reply.Error is not None:
                logger.error(f"Ошибка в ответе API: {reply.Error}")
                raise RuntimeError(f"API Error: {reply.Error}")
            
            return reply
        except Exception as e:
            logger.error(f"Ошибка при вызове метода {method_name}: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def get_posts(self, report_id: str, date_from: datetime, date_to: datetime, page: int = 1) -> List[Post]:
        """
        Получение постов из Медиалогии за указанный период.
        
        Args:
            report_id: ID отчета в Медиалогии.
            date_from: Начальная дата периода.
            date_to: Конечная дата периода.
            page: Номер страницы (для пагинации).
        
        Returns:
            List[Post]: Список объектов Post.
        """
        logger.info(f"Получение постов: report_id={report_id}, date_from={date_from}, date_to={date_to}")
        
        try:
            posts = self.get_posts_page(report_id, date_from, date_to, page, self.batch_size)
            
            logger.info(f"Получено постов на первой странице: {len(posts)}")
            
            if len(posts) == self.batch_size:
                logger.info("Загрузка следующих страниц...")
                posts += self.get_posts(report_id, date_from, date_to, page + 1)

            return posts
        except Exception as e:
            logger.error(f"Ошибка получения постов: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def get_posts_page(self, report_id: str, date_from: datetime, date_to: datetime, 
                       page_index: int, page_size: Optional[int] = None) -> List[Post]:
        """
        Получение одной страницы постов из Медиалогии.
        
        Args:
            report_id: ID отчета в Медиалогии.
            date_from: Начальная дата периода.
            date_to: Конечная дата периода.
            page_index: Номер страницы.
            page_size: Размер страницы (кол-во постов).
        
        Returns:
            List[Post]: Список объектов Post.
        """
        if not page_size:
            page_size = self.batch_size
        
        logger.info(f"Получение страницы {page_index} по {page_size} постов")
        
        try:
            reply = self.call_api(
                "GetPosts",
                credentials={"Login": self.username, "Password": self.password},
                reportId=report_id,
                dateFrom=date_from,
                dateTo=date_to,
                pageIndex=page_index,
                pageSize=page_size,
            )

            # Обработка ответа с учетом структуры Zeep
            cubus_posts = getattr(reply.Posts, 'CubusPost', []) if hasattr(reply, 'Posts') else []
            
            logger.info(f"Получено постов на странице {page_index}: {len(cubus_posts)}")
            
            return self.parse_posts(cubus_posts)
        except Exception as e:
            logger.error(f"Ошибка получения страницы постов: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def get_n_posts(self, report_id: str, date_from: datetime, date_to: datetime) -> int:
        """
        Получение количества постов за указанный период.
        
        Args:
            report_id: ID отчета в Медиалогии.
            date_from: Начальная дата периода.
            date_to: Конечная дата периода.
        
        Returns:
            int: Количество постов.
        """
        try:
            reply = self.call_api(
                "GetPostsStatsByDate",
                credentials={"Login": self.username, "Password": self.password},
                reportId=report_id,
                dateFrom=date_from,
                dateTo=date_to,
            )

            # Обработка с учетом структуры Zeep
            count = sum(
                entry.PostsCount
                for entry in getattr(reply.Entries, 'CubusDateStats', [])
            )
            
            logger.info(f"Количество постов: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка подсчета постов: {e}")
            logger.error(traceback.format_exc())
            return 0
    
    def parse_posts(self, cubus_posts) -> List[Post]:
        """
        Преобразование постов из формата Медиалогии в модели Post.
        
        Args:
            cubus_posts: Посты в формате API Медиалогии.
        
        Returns:
            List[Post]: Список моделей Post.
        """
        from services.object_service import ObjectService
        
        object_service = ObjectService()
        posts = []
        
        for cubus_post in cubus_posts:
            try:
                # Преобразование объекта Zeep в словарь
                if hasattr(cubus_post, '__values__'):
                    cubus_dict = dict(cubus_post.__values__)
                else:
                    cubus_dict = cubus_post
                
                # Получение данных из объекта
                post_id = str(cubus_dict.get('PostId', ''))
                content = self.get_content(cubus_dict)
                object_ids = self.get_object_ids(cubus_dict)
                title = self.get_title(cubus_dict, content)
                
                # Проверка, существует ли пост с таким post_id
                existing_post = Post.query.filter_by(post_id=post_id).first()
                if existing_post:
                    # Обновление существующего поста
                    existing_post.title = title
                    existing_post.content = content
                    existing_post.blog_host = cubus_dict.get("BlogHost", "")
                    existing_post.blog_host_type = self.parse_blog_host_type(cubus_dict.get("BlogHostType"))
                    existing_post.published_on = cubus_dict.get("PublishDate")
                    existing_post.simhash = str(cubus_dict.get("Simhash", ""))
                    existing_post.url = cubus_dict.get("Url", "")
                    existing_post.object_ids_list = object_ids
                    existing_post.updated_at = datetime.utcnow()
                    
                    posts.append(existing_post)
                else:
                    # Создание нового поста
                    post = Post(
                        post_id=post_id,
                        title=title,
                        content=content,
                        blog_host=cubus_dict.get("BlogHost", ""),
                        blog_host_type=self.parse_blog_host_type(cubus_dict.get("BlogHostType")),
                        published_on=cubus_dict.get("PublishDate"),
                        simhash=str(cubus_dict.get("Simhash", "")),
                        url=cubus_dict.get("Url", ""),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    post.object_ids_list = object_ids
                    
                    posts.append(post)
                
                # Связываем пост с объектами в БД
                if object_ids:
                    object_service.link_objects_with_post(post, object_ids)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке поста: {e}")
                logger.error(traceback.format_exc())
        
        # Сохраняем изменения в БД
        db.session.add_all(posts)
        db.session.commit()
        
        logger.info(f"Успешно обработано постов: {len(posts)}")
        return posts
    
    @staticmethod
    def parse_blog_host_type(blog_host_type_value) -> BlogHostType:
        """
        Преобразование значения типа блога из API в Enum.
        
        Args:
            blog_host_type_value: Значение типа блога из API.
        
        Returns:
            BlogHostType: Значение Enum BlogHostType.
        """
        try:
            if isinstance(blog_host_type_value, int):
                return BlogHostType(blog_host_type_value)
            return BlogHostType.OTHER
        except (ValueError, TypeError):
            return BlogHostType.OTHER
    
    @staticmethod
    def get_content(cubus_post) -> str:
        """
        Извлечение контента из поста в формате API.
        
        Args:
            cubus_post: Пост в формате API.
        
        Returns:
            str: Контент поста.
        """
        # Обработка разных форматов входных данных
        contents = []
        
        # Извлечение контента
        content = (cubus_post.get('Content') if isinstance(cubus_post, dict) 
                   else getattr(cubus_post, 'Content', ''))
        if content:
            contents.append(content)
        
        # Проверка текста на картинках
        images = (cubus_post.get('Images') if isinstance(cubus_post, dict) 
                  else getattr(cubus_post, 'Images', None))
        
        if images:
            # Обработка разных форматов Images
            image_list = (images.get('CubusImage') if isinstance(images, dict) 
                          else getattr(images, 'CubusImage', []))
            
            for image in image_list:
                body = (image.get('Body') if isinstance(image, dict) 
                        else getattr(image, 'Body', ''))
                if body:
                    contents.append(body)

        return "\n".join(contents) if contents else ""
    
    @staticmethod
    def get_object_ids(cubus_post) -> List[str]:
        """
        Извлечение идентификаторов объектов из поста в формате API.
        
        Args:
            cubus_post: Пост в формате API.
        
        Returns:
            List[str]: Список идентификаторов объектов.
        """
        object_ids = []
        # Обработка разных форматов входных данных
        if isinstance(cubus_post, dict):
            objects = cubus_post.get('Objects', {})
        else:
            objects = getattr(cubus_post, 'Objects', {})
        
        # Безопасное извлечение object_ids
        if hasattr(objects, 'CubusObject'):
            for obj in objects.CubusObject:
                obj_id = getattr(obj, 'ObjectId', None) if hasattr(obj, 'ObjectId') else obj.get('ObjectId')
                if obj_id and (not hasattr(obj, 'ClassId') or getattr(obj, 'ClassId', 0) == 0):
                    object_ids.append(str(obj_id))
        elif isinstance(objects, dict) and 'CubusObject' in objects:
            for obj in objects['CubusObject']:
                if obj.get('ClassId', 0) == 0:
                    object_ids.append(str(obj.get('ObjectId', '')))
        
        return object_ids
    
    @staticmethod
    def get_title(cubus_post, content: str) -> str:
        """
        Получение заголовка поста.
        
        Args:
            cubus_post: Пост в формате API.
            content: Контент поста для формирования заголовка, если отсутствует.
        
        Returns:
            str: Заголовок поста.
        """
        MIN_TITLE_LEN = 10
        MAX_TITLE_LEN = 100
        
        cubus_title = cubus_post.get("Title", "") if isinstance(cubus_post, dict) else ""
        if cubus_title and len(cubus_title.split()) >= MIN_TITLE_LEN:
            return cubus_title
        elif content:
            title_array = content[:MAX_TITLE_LEN].split()
            if title_array:
                title_array.pop(-1)
                return " ".join(title_array)
        return ""
    
    @staticmethod
    def get_msk_date_range(days_ago=1, time_from=None, time_to=None) -> Tuple[datetime, datetime]:
        """
        Получает диапазон дат с учетом московского часового пояса
        
        Args:
            days_ago: Количество дней назад от текущей даты
            time_from: Время начала в формате HH:MM
            time_to: Время окончания в формате HH:MM
            
        Returns:
            Tuple[datetime, datetime]: (date_from, date_to) в UTC
        """
        # Получаем текущее время в московском часовом поясе
        msk_now = datetime.now(ZoneInfo('Europe/Moscow'))
        
        # Устанавливаем конечную дату
        date_to = msk_now
        
        # Если указано смещение, вычитаем дни
        if days_ago > 0:
            date_to = date_to - datetime.timedelta(days=days_ago)
        
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