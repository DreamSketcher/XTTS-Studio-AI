import os
import threading

_root = None
_colors = None
_create_button = None
_get_text = None
_set_text = None
_placeholder = None
_use_gpt_var = None

HISTORY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "history", "chat_sessions.json")
)
MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 100

_chat_window = None
_search_window = None
_settings_window = None
_editor_window = None
_sessions_loaded = False
_scroll_debounce_id = None

session_listbox = None
chat_canvas = None
chat_scrollbar = None
chat_messages_frame = None
chat_canvas_window = None
chat_input = None
chat_input_placeholder_label = None
chat_send_btn = None
chat_status_label = None
chat_token_label = None

improve_btn = None
paste_editor_btn = None
clear_btn = None
export_btn = None
settings_btn = None
new_chat_btn = None
delete_chat_btn = None

_typing_frame = None
_typing_label = None
_typing_after_id = None
_typing_step = 0

_new_message_btn = None

_generation_lock = threading.Lock()
_generation_running = False
_generation_token = None
_generation_cancel_event = None

_selected_bubble_frame = None
_selected_bubble_content = ""

editor_source_text = None
editor_comment_text = None
editor_stats_label = None
editor_status_label = None

_editor_mode = False
_free_chat_mode = False
_hint_text_var = None

_editor_preview_frame = None
_editor_preview_text = None
_editor_preview_content = ""

composer_outer_ref = [None]
composer_card_ref = [None]

_FALLBACK_COLORS = {
    "BG_MAIN": "#1a1b26",
    "BG_SEC": "#24283b",
    "BG_DARK": "#16161e",
    "TEXT_MAIN": "#c0caf5",
    "TEXT_DIM": "#565f89",
    "ACCENT": "#7aa2f7",
    "ACCENT_HOVER": "#8caaee",
    "ACCENT_DARK": "#3d59a1",
    "BORDER": "#414868",
    "SUCCESS": "#9ece6a",
    "ERROR": "#f7768e",
}

_HOTKEYS = {
    "new_chat": ["<Control-n>"],
    "focus_input": ["<Escape>"],
    "search": ["<Control-f>"],
    "settings": ["<Control-comma>"],
    "close_window": ["<Control-w>"],
    "send_msg": ["<Return>"],
    "newline": ["<Shift-Return>", "<Control-Return>"]
}

_sessions = []
_current_session_id = None
_message_labels = []
_search_results = []
