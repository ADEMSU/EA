from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
import os
from datetime import datetime

from models.database import db
from models.post_model import Post
from models.analysis_model import PostAnalysis, TonalityType
from services.export_service import ExportService
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app

export_bp = Blueprint('export', __name__)

@export_bp.route('/', methods=['GET'])
@login_required
def export_page():
    """Страница экспорта данных."""
    return render_template('export.html', title='Экспорт данных')

@export_bp.route('/export-posts', methods=['POST'])
@login_required
def export_posts():
    """Экспорт постов в Excel."""
    try:
        # Получаем параметры из формы
        include_analysis = 'include_analysis' in request.form
        search_query = request.form.get('search_query', '')
        tonality = request.form.get('tonality', '')
        object_id = request.form.get('object_id', '')
        date_from = request.form.get('date_from', '')
        date_to = request.form.get('date_to', '')
        
        # Базовый запрос
        query = db.session.query(Post)
        
        # Применяем фильтры, если они указаны
        if search_query:
            query = query.filter(
                db.or_(
                    Post.title.ilike(f'%{search_query}%'),
                    Post.content.ilike(f'%{search_query}%')
                )
            )
        
        if tonality and include_analysis:
            query = query.join(PostAnalysis).filter(PostAnalysis.tonality == TonalityType[tonality])
        
        if object_id:
            query = query.filter(Post.object_ids.ilike(f'%{object_id}%'))
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(Post.published_on >= date_from_obj)
            except ValueError:
                flash('Неверный формат даты начала', 'warning')
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                query = query.filter(Post.published_on <= date_to_obj)
            except ValueError:
                flash('Неверный формат даты окончания', 'warning')
        
        # Если нужно включить результаты анализа, загружаем их
        if include_analysis:
            query = query.outerjoin(PostAnalysis)
        
        # Сортировка по дате публикации (сначала новые)
        query = query.order_by(Post.published_on.desc())
        
        # Получаем посты
        posts = query.all()
        
        if not posts:
            flash('Нет данных для экспорта', 'warning')
            return redirect(url_for('export.export_page'))
        
        # Формируем имя файла
        current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(current_app.config['EXPORT_DIRECTORY'])
        os.makedirs(export_dir, exist_ok=True)
        output_file = os.path.join(export_dir, f"export_{current_datetime}.xlsx")
        
        # Экспортируем данные
        export_service = ExportService()
        count = export_service.export_posts_to_excel(posts, output_file, include_analysis)
        
        flash(f'Успешно экспортировано {count} записей в файл', 'success')
        
        # Отправляем файл пользователю
        return send_file(output_file, as_attachment=True)
    
    except Exception as e:
        flash(f'Ошибка при экспорте: {str(e)}', 'danger')
        return redirect(url_for('export.export_page'))