from datetime import datetime
import enum
from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB

from models.database import db

# Взаимосвязи с аналитическими данными
analysis = db.relationship('PostAnalysis', backref='post', uselist=False, cascade='all, delete-orphan')
    # Связь с объектами через ассоциативную таблицу
objects = db.relationship('Object', secondary='post_objects', backref='posts')

# Перенесем существующий Enum из post.py
class BlogHostType(enum.IntEnum):
    OTHER = 0
    BLOG = 1
    MICROBLOG = 2
    SOCIAL = 3
    FORUM = 4
    MEDIA = 5
    REVIEW = 6
    MESSANGER = 7

# Определение модели поста
class Post(db.Model):
    """Модель поста из Медиалогии."""
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=True)
    blog_host = db.Column(db.String(255), nullable=True)
    blog_host_type = db.Column(Enum(BlogHostType), default=BlogHostType.OTHER)
    published_on = db.Column(db.DateTime, nullable=True)
    simhash = db.Column(db.String(64), nullable=True)
    url = db.Column(db.Text, nullable=True)
    
    # JSON-поле для хранения идентификаторов объектов
    object_ids = db.Column(db.Text, nullable=True)  # Хранение как строка с разделителями
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Взаимосвязи с аналитическими данными
    analysis = db.relationship('PostAnalysis', backref='post', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Post {self.post_id}>'
    
    @property
    def object_ids_list(self):
        """Возвращает список идентификаторов объектов."""
        if not self.object_ids:
            return []
        return [obj_id.strip() for obj_id in self.object_ids.split(',') if obj_id.strip()]
    
    @object_ids_list.setter
    def object_ids_list(self, ids_list):
        """Устанавливает идентификаторы объектов из списка."""
        if not ids_list:
            self.object_ids = ""
        else:
            self.object_ids = ", ".join(str(obj_id) for obj_id in ids_list)
    
    def to_dict(self):
        """Преобразует объект поста в словарь."""
        return {
            'id': self.id,
            'post_id': self.post_id,
            'title': self.title,
            'content': self.content,
            'blog_host': self.blog_host,
            'blog_host_type': self.blog_host_type.name if self.blog_host_type else 'OTHER',
            'published_on': self.published_on.isoformat() if self.published_on else None,
            'simhash': self.simhash,
            'url': self.url,
            'object_ids': self.object_ids,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }