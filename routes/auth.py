from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse

from models.database import db
from models.user_model import User
from utils.auth import validate_password

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа в систему."""
    if current_user.is_authenticated:
        return redirect(url_for('posts.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return redirect(url_for('auth.login'))
        
        # Успешный вход
        login_user(user, remember=remember)
        user.last_login = db.func.now()
        db.session.commit()
        
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('posts.dashboard')
            
        flash('Вы успешно вошли в систему', 'success')
        return redirect(next_page)
    
    return render_template('login.html', title='Вход в систему')

@auth_bp.route('/logout')
@login_required
def logout():
    """Выход из системы."""
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Страница профиля пользователя."""
    if request.method == 'POST':
        # Обновление данных профиля
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if current_password and new_password:
            # Проверка текущего пароля
            if not current_user.check_password(current_password):
                flash('Неверный текущий пароль', 'danger')
                return redirect(url_for('auth.profile'))
            
            # Проверка нового пароля
            if not validate_password(new_password):
                flash('Новый пароль не соответствует требованиям безопасности', 'danger')
                return redirect(url_for('auth.profile'))
            
            # Обновление пароля
            current_user.set_password(new_password)
            db.session.commit()
            flash('Пароль успешно обновлен', 'success')
        
        return redirect(url_for('auth.profile'))
    
    return render_template('profile.html', title='Профиль пользователя')