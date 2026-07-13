# -*- coding: utf-8 -*-
"""
patch_updates.py — автоматический скрипт-мигратор импортов для XTTS Studio.

Этот скрипт находит все упоминания старого модуля 'engine.gui.updates' и его функций
во всех .py файлах проекта и заменяет их на новые 'engine.gui.env_settings' и 'env_settings_window'.

КАК ЗАПУСТИТЬ:
Положите этот файл в корень папки проекта (C:\XTTS Studio\) и запустите:
    python patch_updates.py
"""

import os
import re

def run_migration():
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"🔍 Начинаю поиск и миграцию старых импортов в директории: {project_root} ...\n")
    
    patched_count = 0
    
    for root_dir, dirs, files in os.walk(project_root):
        # Пропускаем папки виртуального окружения и кэш
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '.venv', 'python', '__pycache__')]
        
        for file in files:
            if not file.endswith('.py'):
                continue
                
            file_path = os.path.join(root_dir, file)
            # Пропускаем сам мигратор
            if file == "patch_updates.py":
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                
                content = original_content
                
                # ── СЛОВАРЬ ЗАМЕН (РЕГЕКСЫ) ──
                replacements = [
                    # 1. Замена импорта вида: from engine.gui.updates import ...
                    (r'from\s+engine\.gui\.updates\s+import', 'from engine.gui.env_settings import'),
                    
                    # 2. Замена импорта вида: import engine.gui.updates as ...
                    (r'import\s+engine\.gui\.updates\s+as', 'import engine.gui.env_settings as'),
                    
                    # 3. Замена импорта вида: from engine.gui import ..., updates, ...
                    (r'\bupdates\b', 'env_settings'),
                    
                    # 4. Замена вызова оконной функции: open_updates_settings_window() -> open_env_settings_window()
                    (r'open_updates_settings_window', 'open_env_settings_window'),
                    
                    # 5. Замена вызова синглтона: _settings_window -> _env_settings_window
                    (r'_settings_window', '_env_settings_window'),
                ]
                
                for pattern, replacement in replacements:
                    content = re.sub(pattern, replacement, content)
                
                # Если файл изменился — записываем его обратно
                if content != original_content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    rel_path = os.path.relpath(file_path, project_root)
                    print(f"  ✅ Успешно обновлен файл: {rel_path}")
                    patched_count += 1
                    
            except Exception as e:
                rel_path = os.path.relpath(file_path, project_root)
                print(f"  ❌ Ошибка при обработке {rel_path}: {e}")
                
    print(f"\n🎉 Миграция успешно завершена! Обновлено файлов: {patched_count}")

if __name__ == '__main__':
    run_migration()
