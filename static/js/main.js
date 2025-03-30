/**
 * Главный JavaScript файл приложения
 */
document.addEventListener('DOMContentLoaded', function() {
    
    // Автоматическое скрытие уведомлений через 5 секунд
    const alerts = document.querySelectorAll('.alert:not(.alert-persistent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // Инициализация всех выпадающих меню
    const dropdowns = document.querySelectorAll('.dropdown-toggle');
    dropdowns.forEach(dropdown => {
        new bootstrap.Dropdown(dropdown);
    });
    
    // Инициализация всех тултипов
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => {
        new bootstrap.Tooltip(tooltip);
    });
    
    // Инициализация всех поповеров
    const popovers = document.querySelectorAll('[data-bs-toggle="popover"]');
    popovers.forEach(popover => {
        new bootstrap.Popover(popover);
    });
    
    // Обработка события отправки формы с предварительным подтверждением
    const confirmForms = document.querySelectorAll('.confirm-form');
    confirmForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            
            const confirmMessage = this.dataset.confirmMessage || 'Вы уверены, что хотите выполнить это действие?';
            
            if (confirm(confirmMessage)) {
                this.submit();
            }
        });
    });
    
    // Обработчик для копирования в буфер обмена
    const copyButtons = document.querySelectorAll('.copy-to-clipboard');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const text = this.dataset.copyText;
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            
            // Обратная связь для пользователя
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-check"></i> Скопировано!';
            
            setTimeout(() => {
                this.innerHTML = originalText;
            }, 1500);
        });
    });
    
    // Обработчик для переключения видимости пароля
    const togglePasswordButtons = document.querySelectorAll('.toggle-password');
    togglePasswordButtons.forEach(button => {
        button.addEventListener('click', function() {
            const passwordInput = document.getElementById(this.dataset.target);
            
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                this.innerHTML = '<i class="bi bi-eye-slash"></i>';
            } else {
                passwordInput.type = 'password';
                this.innerHTML = '<i class="bi bi-eye"></i>';
            }
        });
    });

    // Обработчик для проверки статуса задач
    function checkTasksStatus(taskIds) {
        if (!taskIds || taskIds.length === 0) return;
        
        // Формируем URL с параметрами задач
        const queryParams = taskIds.map(id => `task_ids=${id}`).join('&');
        const url = `/api/tasks-status?${queryParams}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Обновляем информацию о статусе задач
                if (data.completed && data.completed.length > 0) {
                    // Если есть завершенные задачи, обновляем страницу
                    window.location.reload();
                } else if (data.pending && data.pending.length > 0) {
                    // Если есть незавершенные задачи, проверяем статус через 5 секунд
                    setTimeout(() => checkTasksStatus(data.pending), 5000);
                }
            })
            .catch(error => console.error('Ошибка при проверке статуса задач:', error));
    }
    
    // Проверка наличия задач для мониторинга
    const taskMonitor = document.querySelector('[data-task-ids]');
    if (taskMonitor) {
        const taskIds = taskMonitor.dataset.taskIds.split(',');
        if (taskIds.length > 0) {
            checkTasksStatus(taskIds);
        }
    }
});