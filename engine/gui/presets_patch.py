# -*- coding: utf-8 -*-
"""
engine/gui/presets_patch.py — пример интеграции RVC-параметров в систему пресетов.

Этот файл показывает, как расширить существующую модель настроек/пресетов в XTTS Studio,
чтобы RVC-параметры сохранялись в JSON-конфигурациях и корректно загружались/применялись.
"""

from typing import Dict, Any, Union

# ── 1. ДЕФОЛТНЫЕ НАСТРОЙКИ ПРЕСЕТОВ ──
# Добавьте эти ключи в базовый словарь настроек по умолчанию (обычно находится в engine/settings_store.py или engine/gui/presets.py)

DEFAULT_RVC_PRESET_VALUES = {
    "rvc_enable": False,            # Включено ли RVC-улучшение по умолчанию
    "rvc_model": "",               # Имя выбранной RVC модели (*.pth)
    "rvc_index_rate": 0.75,         # Схожесть тембра (индексный файл): 0.0 - 1.0
    "rvc_pitch_shift": 0,          # Сдвиг тональности (полутона): -12 до +12
    "rvc_f0_method": "rmvpe",       # Метод определения высоты тона (f0): rmvpe, harvest, pm, crepe
}


class PresetManagerPatch:
    """
    Класс-пример для демонстрации того, как интегрировать RVC-параметры
    в логику сохранения/загрузки пресетов.
    """

    @staticmethod
    def get_default_preset(name: str = "high") -> Dict[str, Any]:
        """
        Пример расширения дефолтных пресетов (Нарратив, Динамика, Экспрессия).
        """
        # Базовые параметры XTTS
        preset = {
            "temperature": 0.75,
            "top_p": 0.85,
            "top_k": 50,
            "repetition_penalty": 10.0,
            "speed": 1.0,
            "prosody": True,
            "deesser": True,
            "trim_end_ms": 0,
            "trim_mode": "auto",
        }

        # Расширяем пресет дефолтными RVC-параметрами
        preset.update(DEFAULT_RVC_PRESET_VALUES)

        # Тонкая кастомизация RVC под конкретные встроенные пресеты
        if name == "narrative":
            preset["rvc_index_rate"] = 0.85  # Для спокойного чтения берем больше оригинала
            preset["rvc_f0_method"] = "rmvpe"
        elif name == "dynamic":
            preset["rvc_index_rate"] = 0.65  # Для энергичного темпа снижаем влияние индекса во избежание сбоев
            preset["rvc_f0_method"] = "pm"
        elif name == "expressive":
            preset["rvc_index_rate"] = 0.75
            preset["rvc_f0_method"] = "harvest"  # Harvest хорош на выразительных эмоциях, хотя и медленнее

        return preset

    @staticmethod
    def sanitize_preset(preset_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Метод очистки/заполнения недостающих полей при чтении старых пресетов с диска.
        Гарантирует, что старые пресеты пользователей (без RVC) не вызовут KeyError.
        """
        sanitized = preset_data.copy()
        for key, default_value in DEFAULT_RVC_PRESET_VALUES.items():
            if key not in sanitized:
                sanitized[key] = default_value
        return sanitized


# ── 2. ШАБЛОН ДЛЯ ИНТЕГРАЦИИ В ИНТЕРФЕЙС GUI (gui.py / presets.py) ──

class PresetWindowUIController:
    """
    Контроллер для биндинга виджетов RVC к данным пресета в окне настроек качества (Quality Settings).
    Показывает, как связать CustomTkinter (или PySide/Tkinter) виджеты с данными пресета.
    """
    def __init__(self, ui_widgets: Dict[str, Any]):
        # Сохраняем ссылки на виджеты интерфейса
        self.widgets = ui_widgets 
        # Виджеты обычно представляют собой:
        # self.widgets["chk_rvc"] -> ctk.CTkCheckBox
        # self.widgets["combo_rvc_model"] -> ctk.CTkOptionMenu
        # self.widgets["slider_rvc_index"] -> ctk.CTkSlider
        # self.widgets["spin_rvc_pitch"] -> ctk.CTkEntry (или кастомный спинбокс)
        # self.widgets["combo_rvc_f0"] -> ctk.CTkOptionMenu

    def load_preset_to_widgets(self, preset_data: Dict[str, Any]):
        """
        Заполняет виджеты интерфейса значениями из загруженного пресета.
        """
        # Убеждаемся, что в пресете есть RVC-параметры (для совместимости со старыми пресетами)
        data = PresetManagerPatch.sanitize_preset(preset_data)

        # 1. Чекбокс включения RVC
        if "chk_rvc" in self.widgets:
            if data["rvc_enable"]:
                self.widgets["chk_rvc"].select()
            else:
                self.widgets["chk_rvc"].deselect()
                
            # Вызываем переключатель активности остальных RVC-контролов
            self.toggle_rvc_widgets_state(data["rvc_enable"])

        # 2. Выбор модели RVC
        if "combo_rvc_model" in self.widgets:
            model_val = data["rvc_model"] or "Не выбрана"
            self.widgets["combo_rvc_model"].set(model_val)

        # 3. Слайдер Index Rate
        if "slider_rvc_index" in self.widgets:
            self.widgets["slider_rvc_index"].set(data["rvc_index_rate"])
            # Если есть лейбл отображения значения (например, "0.75")
            if "lbl_rvc_index_val" in self.widgets:
                self.widgets["lbl_rvc_index_val"].configure(text=f"{data['rvc_index_rate']:.2f}")

        # 4. Сдвиг тона Pitch
        if "spin_rvc_pitch" in self.widgets:
            self.widgets["spin_rvc_pitch"].delete(0, 'end')
            # Форматируем как "+3" или "-2" или "0"
            pitch_val = int(data["rvc_pitch_shift"])
            pitch_str = f"+{pitch_val}" if pitch_val > 0 else str(pitch_val)
            self.widgets["spin_rvc_pitch"].insert(0, pitch_str)

        # 5. Метод f0
        if "combo_rvc_f0" in self.widgets:
            self.widgets["combo_rvc_f0"].set(data["rvc_f0_method"])

    def save_widgets_to_preset(self) -> Dict[str, Any]:
        """
        Считывает текущие значения из виджетов GUI и возвращает словарь параметров пресета.
        """
        preset_rvc_data = {}

        # 1. Чекбокс
        if "chk_rvc" in self.widgets:
            preset_rvc_data["rvc_enable"] = bool(self.widgets["chk_rvc"].get())
        else:
            preset_rvc_data["rvc_enable"] = False

        # 2. Модель RVC
        if "combo_rvc_model" in self.widgets:
            val = self.widgets["combo_rvc_model"].get()
            preset_rvc_data["rvc_model"] = "" if val == "Не выбрана" else val

        # 3. Слайдер Index
        if "slider_rvc_index" in self.widgets:
            preset_rvc_data["rvc_index_rate"] = round(float(self.widgets["slider_rvc_index"].get()), 2)

        # 4. Pitch
        if "spin_rvc_pitch" in self.widgets:
            try:
                # Очищаем от возможных "+" и конвертируем в int
                raw_pitch = self.widgets["spin_rvc_pitch"].get().replace("+", "").strip()
                preset_rvc_data["rvc_pitch_shift"] = int(raw_pitch)
            except ValueError:
                preset_rvc_data["rvc_pitch_shift"] = 0

        # 5. f0 метод
        if "combo_rvc_f0" in self.widgets:
            preset_rvc_data["rvc_f0_method"] = self.widgets["combo_rvc_f0"].get()

        return preset_rvc_data

    def toggle_rvc_widgets_state(self, enabled: bool):
        """
        Управляет доступностью (state) виджетов RVC в зависимости от чекбокса "Включить RVC".
        Повышает эргономику интерфейса: если RVC выключен, слайдеры и меню становятся серыми.
        """
        state = "normal" if enabled else "disabled"
        
        target_keys = ["combo_rvc_model", "slider_rvc_index", "spin_rvc_pitch", "combo_rvc_f0", "btn_pitch_up", "btn_pitch_down"]
        for key in target_keys:
            if key in self.widgets:
                self.widgets[key].configure(state=state)
                
        # Если есть текстовые подписи, приглушаем их цвет
        text_color = "#ffffff" if enabled else "#777777"
        label_keys = ["lbl_rvc_model_title", "lbl_rvc_index_title", "lbl_rvc_pitch_title", "lbl_rvc_f0_title", "lbl_rvc_index_val"]
        for key in label_keys:
            if key in self.widgets:
                self.widgets[key].configure(text_color=text_color)
