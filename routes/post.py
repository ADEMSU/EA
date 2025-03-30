from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from models.database import db
from models.post_model import Post, BlogHostType
from models.analysis_model import PostAnalysis, TonalityType
from services.mlg_service import MlgService
from services.lmm_service import LmmService
from services.object_service import ObjectService
from models.database import db
from models.post_model import Post, BlogHostType
from models.analysis_model import PostAnalysis, TonalityType
from models.object_model import Object

posts_bp = Blueprint('posts', __name__)

@posts_bp.route('/dashboard')
@login_required
def dashboard():
    """Главная панель управления."""
    # Получаем общие статистики для отображения на дашборде
    posts_count = db.session.query(Post).count()
    analyzed_posts_count = db.session.query(PostAnalysis).count()
    
    # Статистика по тональности
    tonality_stats = db.session.query(
        PostAnalysis.tonality, 
        db.func.count(PostAnalysis.id)
    ).group_by(PostAnalysis.tonality).all()
    
    # Преобразуем статистику в словарь для использования в шаблоне
    tonality_data = {t.name: 0 for t in TonalityType}
    for tonality, count in tonality_stats:
        if tonality:
            tonality_data[tonality.name] = count
    
    # Получаем последние посты
    latest_posts = db.session.query(Post).order_by(Post.created_at.desc()).limit(5).all()
    
    return render_template('dashboard.html', 
                           title='Панель управления',
                           posts_count=posts_count,
                           analyzed_posts_count=analyzed_posts_count,
                           tonality_data=tonality_data,
                           latest_posts=latest_posts)

@posts_bp.route('/posts', methods=['GET'])
@login_required
def posts_list():
    """Список постов с фильтрацией и пагинацией."""
    # Параметры для фильтрации и пагинации
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Фильтры
    search_query = request.args.get('q', '')
    tonality = request.args.get('tonality', '')
    object_id = request.args.get('object_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
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
    
    if tonality:
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
    
    # Сортировка по дате публикации (сначала новые)
    query = query.order_by(Post.published_on.desc())
    
    # Выполняем запрос с пагинацией
    posts_pagination = query.paginate(page=page, per_page=per_page)
    
    # Получаем сервис объектов для отображения имен
    object_service = ObjectService()
    
    # Получаем доступные объекты для фильтра
    objects = db.session.query(Object).all()
    
    return render_template('posts.html',
                           title='Список постов',
                           posts_pagination=posts_pagination,
                           search_query=search_query,
                           tonality=tonality,
                           object_id=object_id,
                           date_from=date_from,
                           date_to=date_to,
                           object_service=object_service,
                           objects=objects)

@posts_bp.route('/posts/<string:post_id>', methods=['GET'])
@login_required
def post_detail(post_id):
    """Детальная информация о посте."""
    post = Post.query.filter_by(post_id=post_id).first_or_404()
    
    # Получаем сервис объектов для отображения имен
    object_service = ObjectService()
    
    return render_template('post_detail.html',
                           title=post.title or 'Детали поста',
                           post=post,
                           object_service=object_service)

@posts_bp.route('/fetch-posts', methods=['POST'])
@login_required
def fetch_posts():
    """API для получения постов из Медиалогии."""
    try:
        # Получаем параметры из формы
        report_id = request.form.get('report_id')
        days_ago = request.form.get('days_ago', type=int)
        date_from = request.form.get('date_from')
        date_to = request.form.get('date_to')
        time_from = request.form.get('time_from')
        time_to = request.form.get('time_to')
        
        # Проверка обязательных параметров
        if not report_id:
            flash('ID отчета Медиалогии обязателен', 'danger')
            return redirect(url_for('posts.dashboard'))
        
        # Определяем период
        if days_ago is not None:
            date_from_obj, date_to_obj = MlgService.get_msk_date_range(days_ago, time_from, time_to)
        elif date_from and date_to:
            # Здесь нужна функция парсинга дат из формы
            # Используем заглушку для примера
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            
            # Если указано время, устанавливаем его
            if time_from:
                hour, minute = map(int, time_from.split(':'))
                date_from_obj = date_from_obj.replace(hour=hour, minute=minute)
            
            if time_to:
                hour, minute = map(int, time_to.split(':'))
                date_to_obj = date_to_obj.replace(hour=hour, minute=minute)
            
            # Добавляем временную зону
            date_from_obj = date_from_obj.replace(tzinfo=ZoneInfo('Europe/Moscow'))
            date_to_obj = date_to_obj.replace(tzinfo=ZoneInfo('Europe/Moscow'))
        else:
            flash('Необходимо указать либо количество дней назад, либо конкретный период', 'danger')
            return redirect(url_for('posts.dashboard'))
        
        # Инициализируем сервис Медиалогии
        mlg_service = MlgService()
        
        # Получаем количество постов
        n_posts = mlg_service.get_n_posts(report_id, date_from_obj, date_to_obj)
        
        if n_posts == 0:
            flash('Нет постов за указанный период', 'warning')
            return redirect(url_for('posts.dashboard'))
        
        # Получаем посты
        posts = mlg_service.get_posts(report_id, date_from_obj, date_to_obj)
        
        flash(f'Успешно получено {len(posts)} постов из Медиалогии', 'success')
        return redirect(url_for('posts.posts_list'))
    
    except Exception as e:
        flash(f'Ошибка при получении постов: {str(e)}', 'danger')
        return redirect(url_for('posts.dashboard'))

@posts_bp.route('/analyze-posts', methods=['POST'])
@login_required
def analyze_posts():
    """API для анализа постов с помощью LMM."""
    try:
        # Получаем параметры из формы
        post_ids = request.form.getlist('post_ids')
        
        if not post_ids:
            # Проверяем, указан ли фильтр для анализа всех отфильтрованных постов
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
            
            if tonality:
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
            
            # Получаем все ID постов по фильтру
            posts = query.all()
            post_ids = [post.post_id for post in posts]
        
        if not post_ids:
            flash('Не выбраны посты для анализа', 'danger')
            return redirect(url_for('posts.posts_list'))
        
        # Получаем данные постов для анализа
        posts_data = []
        object_service = ObjectService()
        
        for post_id in post_ids:
            post = Post.query.filter_by(post_id=post_id).first()
            if post:
                posts_data.append({
                    'post_id': post.post_id,
                    'content': post.content,
                    'object': object_service.get_object_names(post.object_ids)
                })
        
        # Инициализируем сервис LMM
        lmm_service = LmmService()
        
        # Запускаем анализ
        result = lmm_service.analyze_posts(posts_data)
        
        # Здесь можно сохранить task_ids для последующей проверки статуса
        
        flash(f'Запущен анализ {len(posts_data)} постов. Результаты будут доступны после завершения обработки.', 'success')
        return redirect(url_for('posts.posts_list'))
    
    except Exception as e:
        flash(f'Ошибка при анализе постов: {str(e)}', 'danger')
        return redirect(url_for('posts.posts_list'))

@posts_bp.route('/api/tasks-status', methods=['GET'])
@login_required
def tasks_status():
    """API для проверки статуса задач анализа."""
    task_ids = request.args.getlist('task_ids')
    
    # Здесь должна быть логика проверки статуса задач Celery
    # Заглушка для примера
    statuses = {"completed": [], "pending": task_ids}
    
    return jsonify(statuses)