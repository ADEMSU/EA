from typing import List, Dict, Optional
from loguru import logger

from models.database import db
from models.object_model import Object, post_objects
from models.post_model import Post

class ObjectService:
    """Сервис для работы с объектами."""
    
    def __init__(self):
        """Инициализация сервиса."""
        # Загружаем словарь соответствия ID объектов и их названий
        self.object_mapping = self._load_object_mapping()
    
    def _load_object_mapping(self) -> Dict[str, str]:
        """
        Загружает словарь соответствия ID объектов и их названий из БД.
        
        Returns:
            Dict[str, str]: Словарь, где ключ - ID объекта, значение - название объекта.
        """
        mapping = {}
        objects = Object.query.all()
        
        for obj in objects:
            mapping[obj.object_id] = obj.name
        
        logger.info(f"Загружено объектов из БД: {len(mapping)}")
        
        # Если в БД нет объектов, инициализируем из словаря
        if not mapping:
            self._initialize_objects_from_dict()
            # Повторный запрос к БД после инициализации
            objects = Object.query.all()
            for obj in objects:
                mapping[obj.object_id] = obj.name
            logger.info(f"После инициализации загружено объектов: {len(mapping)}")
        
        return mapping
    
    def _initialize_objects_from_dict(self):
        """Инициализирует объекты в БД из словаря."""
        try:
            # Импортируем словарь из оригинального проекта
            from object_dict import OBJECT_MAPPING
            
            objects_to_add = []
            for object_id, name in OBJECT_MAPPING.items():
                # Проверяем, существует ли объект
                existing = Object.query.filter_by(object_id=object_id).first()
                if not existing:
                    obj = Object(object_id=object_id, name=name)
                    objects_to_add.append(obj)
            
            if objects_to_add:
                db.session.add_all(objects_to_add)
                db.session.commit()
                logger.info(f"Инициализировано {len(objects_to_add)} объектов из словаря")
        except Exception as e:
            logger.error(f"Ошибка при инициализации объектов из словаря: {e}")
            db.session.rollback()
    
    def get_object_by_id(self, object_id: str) -> Optional[Object]:
        """
        Получает объект по его ID.
        
        Args:
            object_id: ID объекта.
            
        Returns:
            Optional[Object]: Объект или None, если не найден.
        """
        return Object.query.filter_by(object_id=object_id).first()
    
    def create_object(self, object_id: str, name: str, description: str = "") -> Object:
        """
        Создает новый объект.
        
        Args:
            object_id: ID объекта.
            name: Название объекта.
            description: Описание объекта.
            
        Returns:
            Object: Созданный объект.
        """
        # Проверяем, существует ли объект с таким ID
        existing = self.get_object_by_id(object_id)
        if existing:
            # Обновляем существующий объект
            existing.name = name
            existing.description = description
            db.session.commit()
            logger.info(f"Обновлен объект {object_id}: {name}")
            return existing
        
        # Создаем новый объект
        obj = Object(object_id=object_id, name=name, description=description)
        db.session.add(obj)
        db.session.commit()
        
        # Обновляем кэш
        self.object_mapping[object_id] = name
        
        logger.info(f"Создан новый объект {object_id}: {name}")
        return obj
    
    def link_objects_with_post(self, post: Post, object_ids: List[str]):
        """
        Связывает пост с объектами.
        
        Args:
            post: Объект поста.
            object_ids: Список ID объектов.
        """
        try:
            # Получаем объекты из БД
            objects = []
            for obj_id in object_ids:
                obj = self.get_object_by_id(obj_id)
                if obj:
                    objects.append(obj)
                else:
                    # Если объект не найден, проверяем словарь
                    name = self.object_mapping.get(obj_id)
                    if name:
                        # Создаем объект, если есть информация о нем
                        obj = self.create_object(obj_id, name)
                        objects.append(obj)
                    else:
                        logger.warning(f"Объект с ID {obj_id} не найден в БД и словаре")
            
            # Очищаем текущие связи с объектами
            # db.session.execute(post_objects.delete().where(post_objects.c.post_id == post.id))
            
            # Добавляем новые связи
            for obj in objects:
                # Проверяем, существует ли связь
                exists = db.session.query(post_objects).filter_by(
                    post_id=post.id, object_id=obj.id
                ).first()
                
                if not exists:
                    # Добавляем связь
                    db.session.execute(post_objects.insert().values(post_id=post.id, object_id=obj.id))
            
            db.session.commit()
            logger.info(f"Связано {len(objects)} объектов с постом {post.post_id}")
        except Exception as e:
            logger.error(f"Ошибка при связывании объектов с постом: {e}")
            db.session.rollback()
    
    def get_object_names(self, object_ids_str: str) -> str:
        """
        Получает имена объектов по строке с их ID.
        
        Args:
            object_ids_str: Строка с ID объектов, разделенными запятыми.
            
        Returns:
            str: Строка с именами объектов, разделенными запятыми.
        """
        if not object_ids_str:
            return ""
        
        # Разделение строки идентификаторов на отдельные id
        object_ids = [obj_id.strip() for obj_id in object_ids_str.split(',') if obj_id.strip()]
        
        # Поиск соответствующих имен объектов
        object_names = []
        for obj_id in object_ids:
            # Пробуем сопоставить как строку
            if obj_id in self.object_mapping:
                object_names.append(self.object_mapping[obj_id])
            # Пробуем как числовое значение (для ID, которые могут быть числами)
            elif obj_id.isdigit() and str(int(obj_id)) in self.object_mapping:
                object_names.append(self.object_mapping[str(int(obj_id))])
            else:
                # Если не нашли в кэше, пробуем найти в БД
                obj = self.get_object_by_id(obj_id)
                if obj:
                    object_names.append(obj.name)
                    # Обновляем кэш
                    self.object_mapping[obj_id] = obj.name
                else:
                    # Если не нашли точное соответствие, логируем это для отладки
                    logger.debug(f"Не найдено соответствие для ID объекта: {obj_id}")
        
        return ", ".join(object_names)