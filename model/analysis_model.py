from datetime import datetime
import enum
from sqlalchemy import Enum

from models.database import db

class TonalityType(enum.Enum):
    NEGATIVE = 'негативная'
    NEUTRAL = 'нейтральная'
    POSITIVE = 'позитивная'
    UNKNOWN = 'неизвестно'

class PostAnalysis(db.Model):
    """Модель результатов анализа поста."""
    __tablename__ = 'post_analyses'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, unique=True)
    
    # Результаты анализа LMM
    lmm_title = db.Column(db.String(255), nullable=True)
    tonality = db.Column(Enum(TonalityType), default=TonalityType.UNKNOWN)
    description = db.Column(db.Text, nullable=True)
    
    # Метаданные анализа
    analyzed_at = db.Column(db.DateTime, default=datetime.utcnow)
    model_used = db.Column(db.String(255), nullable=True)
    
    def __repr__(self):
        return f'<PostAnalysis for post_id={self.post_id}>'
    
    def to_dict(self):
        """Преобразует объект анализа в словарь."""
        return {
            'id': self.id,
            'post_id': self.post_id,
            'lmm_title': self.lmm_title,
            'tonality': self.tonality.value if self.tonality else 'неизвестно',
            'description': self.description,
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
            'model_used': self.model_used,
        }