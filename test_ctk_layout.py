"""
ОБНОВЛЁННЫЙ диагностический патч v2.

Куда вставить: в самый конец функции open_chat_window(),
ПЕРЕД строкой:
    win.protocol("WM_DELETE_WINDOW", on_close)

Скопируй блок ниже (с тем же отступом 4 пробела) и вставь туда.
"""

def _debug_dump_layout_v2():
    print("\n" + "=" * 70)
    print("=== ДИАГНОСТИКА v2: COMPOSER/INPUT ===")
    print("=" * 70)

    try:
        import customtkinter as _ctk_check
        print(f"customtkinter version: {_ctk_check.__version__}")
    except Exception as e:
        print(f"customtkinter import error: {e}")

    widgets = {
        "composer_outer_ref[0]": composer_outer_ref[0],
        "composer_card_ref[0]": composer_card_ref[0],
        "chat_input": chat_input,
        "chat_send_btn": chat_send_btn,
        "chat_input_placeholder_label": chat_input_placeholder_label,
    }
    for name, w in widgets.items():
        try:
            if w is None:
                print(f"{name}: None (не создан)")
                continue
            exists = bool(w.winfo_exists())
            if not exists:
                print(f"{name}: НЕ СУЩЕСТВУЕТ (destroyed)")
                continue
            print(
                f"{name}: "
                f"height={w.winfo_height()} reqheight={w.winfo_reqheight()} "
                f"width={w.winfo_width()} reqwidth={w.winfo_reqwidth()} "
                f"mapped={w.winfo_ismapped()} viewable={w.winfo_viewable()} "
                f"manager={w.winfo_manager()} class={w.winfo_class()}"
            )
        except Exception as e:
            print(f"{name}: ERROR {e}")

    # Полная цепочка родителей от chat_input до toplevel — с типом КАЖДОГО
    print("\n--- ПОЛНАЯ ЦЕПОЧКА РОДИТЕЛЕЙ (chat_input -> toplevel) ---")
    try:
        w = chat_input
        depth = 0
        while w is not None and depth < 20:
            try:
                py_class = type(w).__name__
                tk_class = w.winfo_class()
                h = w.winfo_height()
                rh = w.winfo_reqheight()
                mgr = w.winfo_manager()
                print(f"  [{depth}] py_class={py_class:20s} tk_class={tk_class:12s} "
                      f"height={h:4d} reqheight={rh:4d} manager={mgr}")
            except Exception as e:
                print(f"  [{depth}] ERROR reading widget: {e}")
                break
            if isinstance(w, tk.Tk) or isinstance(w, tk.Toplevel):
                break
            try:
                w = w.master
            except Exception:
                break
            depth += 1
    except Exception as e:
        print(f"Ошибка обхода цепочки: {e}")

    print("=" * 70 + "\n")

_safe_after(1500, _debug_dump_layout_v2)