# -*- coding: utf-8 -*-
"""
engine/env_core/__init__.py — Единая точка доступа к методам системного окружения.
Выделено в отдельный пакет env_core для структурирования и порядка.
"""

from engine.env_core.cpu_gpu import (
    detect_cpu,
    detect_gpu,
    PYTHON_EXE, # Экспортируем PYTHON_EXE в публичный интерфейс
    PROJECT_ROOT, # Экспортируем PROJECT_ROOT для динамических путей в GUI
)

from engine.env_core.torch_setup import (
    install_torch,
    uninstall_torch,
    torch_status,
    cancel_install_torch,
    clean_torch_cache,
    get_installed_torch_variant,
    get_broken_torch_variants,
    mark_torch_variant_broken,
    load_torch_checkpoint,
    save_torch_checkpoint,
    clear_torch_checkpoint,
    TORCH_VERSION,
    TORCHAUDIO_VERSION,
    TORCHVISION_VERSION,
    SITE_PACKAGES, # Экспортируем SITE_PACKAGES в публичный интерфейс для пип-установок
)

from engine.env_core.llama_setup import (
    install_llama_cpp,
    uninstall_llama_cpp,
    llama_cpp_status,
    get_installed_backend,
    resolve_backend,
    get_startup_install_state,
    cleanup_orphaned_checkpoint,
)

from engine.env_core.rvc_setup import (
    install_rvc,
    uninstall_rvc,
    rvc_status,
)

from engine.env_core.diagnostics import (
    run_full_diagnostics,
    scan_for_garbage,
    finalize_deletion,
    run_error_recovery,
    get_python_env_info,
    format_env_info,
    load_safe_files_cache,
    save_safe_files_cache,
    clear_diagnostics_cache,
    clean_pip_download_cache,
    get_broken_critical,
    get_optional_status,
    CRITICAL_COMPONENTS,
    OPTIONAL_COMPONENTS,
)

# Функция обратной совместимости, возвращающая список sitepackages
def get_site_packages() -> list:
    return [SITE_PACKAGES]
