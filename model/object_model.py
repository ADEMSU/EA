from datetime import datetime

from models.database import db

class Object(db.Model):
    """Модель объекта анализа (люди, организации и т.д.)."""
    __tablename__ = 'objects'

    id = db.Column(db.Integer, primary_key=True)
    object_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Object {self.name}>'
    
    def to_dict(self):
        """Преобразует объект в словарь."""
        return {
            'id': self.id,
            'object_id': self.object_id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

# Ассоциативная таблица для связи постов и объектов (многие-ко-многим)
post_objects = db.Table('post_objects',
    db.Column('post_id', db.Integer, db.ForeignKey('posts.id'), primary_key=True),
    db.Column('object_id', db.Integer, db.ForeignKey('objects.id'), primary_key=True)
)