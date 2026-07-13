# -*- coding: utf-8 -*-
"""
engine/env_core/rvc_setup.py — логика установки и проверки rvc-python и fairseq.
"""
import os
import re
import sys
import subprocess
import shutil
from engine.paths import BASE_DIR

PYTHON_EXE = sys.executable
SITE_PACKAGES = os.path.join(BASE_DIR, "python", "xtts_env", "Lib", "site-packages")
PORTABLE_TEMP_DIR = os.path.join(BASE_DIR, "python", "temp")
PORTABLE_CACHE_DIR = os.path.join(BASE_DIR, "python", "pip_cache")


def _build_rvc_constraints(frozen_reqs: dict, site_packages: str) -> list:
    """
    Строит список строк для constraint-файла установки зависимостей RVC.

    Каждая зафиксированная в requirements.txt зависимость пинится к ТОЙ
    версии, что реально установлена в целевом site-packages (включая суффикс
    сборки +cu118 / +cpu). Если пакет ещё не установлен — берётся версия из
    requirements.txt.

    Зачем: раньше requirements.txt жёстко пинил torch==2.2.2+cu118, тогда как
    в целевом окружении мог уже стоять torch 2.2.2+cpu (или наоборот). Из-за
    этого несовпадения варианта сборки pip считал установленный torch «не
    подходящим» под constraint и перетягивал 2.7 ГБ заново при каждой
    установке RVC. Теперь requirements.txt нейтральный (без суффикса), а
    динамический пин ровно к установленной сборке убирает этот конфликт —
    уже стоящий torch считается удовлетворённым и не качается.
    """
    import importlib.metadata as ilm

    def _installed_ver(name: str):
        # importlib.metadata нормализует имена, но перестрахуемся по
        # вариантам разделителей (torchaudio / torch-audio и т.п.).
        for cand in {name, name.replace("-", "_"), name.replace("_", "-")}:
            try:
                return ilm.version(cand)
            except Exception:
                continue
        return None

    prev_path = list(sys.path)
    # SITE_PACKAGES должен проверяться в первую очередь, чтобы версия бралась
    # именно из целевого окружения, а не из интерпретатора, которым запущен pip.
    sys.path.insert(0, site_packages)
    lines = []
    try:
        for name, spec in frozen_reqs.items():
            ver = _installed_ver(name)
            if ver:
                # Пиним ровно к установленной сборке (с суффиксом +cu118/+cpu).
                lines.append(f"{name}=={ver}")
            else:
                # Пакет ещё не стоит — оставляем как в requirements.txt,
                # чтобы свежая установка взяла именно ту версию, что в проекте.
                lines.append(spec)
    finally:
        sys.path[:] = prev_path
    return lines


def _detect_installed_torch_variant(site_packages: str):
    """Возвращает установленную сборку torch ('cu118'/'cpu') или None."""
    import importlib.metadata as ilm

    prev = list(sys.path)
    sys.path.insert(0, site_packages)
    installed = None
    try:
        try:
            installed = ilm.version("torch")
        except Exception:
            installed = None
    finally:
        sys.path[:] = prev
    if not installed:
        return None
    return "cu118" if "+cu" in installed else "cpu"


def _fallback_cuda_available() -> bool:
    """Запасной детект NVIDIA-GPU, если недоступен основной механизм проекта."""
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            return True
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Where-Object { $_.Name -match 'NVIDIA' } | Measure-Object | "
                    "Select-Object -ExpandProperty Count",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if out.returncode == 0 and out.stdout.strip() not in ("", "0"):
                return True
        except Exception:
            pass
    return False


def detect_torch_build(site_packages: str):
    """
    Возвращает (build_tag, index_url) для установки torch, переиспользуя
    ЕДИНУЮ логику выбора сборки из engine.env_core.torch_setup, чтобы RVC-путь
    и базовая установка torch всегда выбирали один и тот же вариант:
      - если torch уже стоит — берём его сборку (+cu118 / +cpu);
      - иначе — ту же логику, что у базовой установки (настройка
        torch_device_preference, наличие NVIDIA-GPU и версия CUDA,
        список «битых» вариантов). Это гарантирует адаптивность под
        любой вариант без ручного переключения.
    """
    from engine.env_core.torch_setup import _TORCH_INDEX_URLS

    installed = _detect_installed_torch_variant(site_packages)
    if installed:
        return (installed, _TORCH_INDEX_URLS[installed])

    # torch ещё не стоит — делегируем выбор базовому установщику torch.
    try:
        from engine.env_core.torch_setup import _pick_torch_variant
        from engine.env_core.cpu_gpu import detect_gpu

        variant, index_url = _pick_torch_variant(detect_gpu())
        return (variant, index_url)
    except Exception:
        pass

    # Запасной вариант, если модули torch_setup недоступны.
    if _fallback_cuda_available():
        return ("cu118", _TORCH_INDEX_URLS["cu118"])
    return ("cpu", _TORCH_INDEX_URLS["cpu"])


def _run_pip_capture(cmd, env, progress_cb=None):
    """Запускает pip, стримит вывод в progress_cb и возвращает (returncode, текст)."""
    from engine.env_core.diagnostics import _read_pip_output

    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=0,
    )
    buf = []

    def _cb(line):
        buf.append(line)
        if progress_cb:
            progress_cb(line)

    _read_pip_output(proc, _cb)
    proc.wait()
    return proc.returncode, "\n".join(buf)


def _read_requires_dist(dist_name: str) -> list:
    """Читает Requires-Dist из установленного dist-info пакета dist_name."""
    dist_info_dirs = [
        d
        for d in os.listdir(SITE_PACKAGES)
        if d.lower().startswith(dist_name.lower() + "-") and d.endswith(".dist-info")
    ]
    if not dist_info_dirs:
        return []
    metadata_path = os.path.join(SITE_PACKAGES, sorted(dist_info_dirs)[-1], "METADATA")
    deps = []
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []
    for line in text.splitlines():
        m = re.match(r"^Requires-Dist:\s*(.+)$", line.strip(), re.IGNORECASE)
        if not m:
            continue
        spec = m.group(1).strip()
        if "extra ==" in spec:
            continue
        deps.append(spec.split(";")[0].strip())
    return deps


def _install_with_retry(cmd, env, progress_cb=None):
    """
    Запускает pip install с отказоустойчивостью к блокировкам файлов Windows:
    при ошибке доступа (WinError 5 / PermissionError) повторяет БЕЗ --upgrade,
    чтобы не перезаписывать залоченные .pyd запущенного приложения.
    Возвращает (returncode, текст_вывода).
    """
    rc, output = _run_pip_capture(cmd, env, progress_cb)
    if rc != 0 and (
        "PermissionError" in output
        or "WinError 5" in output
        or "Access is denied" in output
        or "Отказано" in output
    ):
        if progress_cb:
            progress_cb(
                "⚠️ pip не смог перезаписать залоченные .pyd (приложение запущено). "
                "Повторяю установку без --upgrade — уже стоящие пакеты будут пропущены."
            )
        cmd2 = [c for c in cmd if c != "--upgrade"]
        rc, output = _run_pip_capture(cmd2, env, progress_cb)
    return rc, output


def rvc_status() -> dict:
    """Проверяет работоспособность rvc-python в отдельном процессе."""
    probe_script = (
        """import sys
try:
    sys.path.insert(0, r'%s')
    from rvc_python.infer import RVCInference
    print('OK')
except Exception as e:
    print('FAIL=' + str(e))
"""
        % SITE_PACKAGES
    )
    try:
        proc = subprocess.run(
            [PYTHON_EXE, "-c", probe_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = proc.stdout or ""
        if "OK" in out:
            return {"installed": True, "error": None}
        return {"installed": False, "error": out.strip() or "не импортируется"}
    except Exception as e:
        return {"installed": False, "error": str(e)}


def install_rvc(progress_cb=None) -> dict:
    """
    Устанавливает пакет rvc-python во встроенное окружение site-packages.
    На Windows автоматически обходит проблему компиляции fairseq, устанавливая prebuilt wheel.
    """
    from engine.env_core.diagnostics import (
        _read_pip_output,
        clear_diagnostics_cache,
        parse_requirements_txt,
    )
    from engine.logging_utils import write_log

    # Импортируем проверку лока установки для защиты кэша
    try:
        from engine.gui.env_settings import _can_clear_diagnostics_cache
    except ImportError:

        def _can_clear_diagnostics_cache():
            return True

    def emit(line):
        write_log(line)
        if progress_cb:
            progress_cb(line)

    emit("Начинаю установку rvc-python во встроенное окружение...")

    # Принудительно очищаем кэш перед установкой (только если нет активной установки/восстановления)
    if _can_clear_diagnostics_cache():
        clear_diagnostics_cache()
    uninstall_rvc(progress_cb)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
    os.makedirs(PORTABLE_CACHE_DIR, exist_ok=True)
    env["TMPDIR"] = PORTABLE_TEMP_DIR
    env["TEMP"] = PORTABLE_TEMP_DIR
    env["TMP"] = PORTABLE_TEMP_DIR
    env["PIP_CACHE_DIR"] = PORTABLE_CACHE_DIR
    # pip при install --target не считает пакеты, уже лежащие в целевой папке,
    # "установленными" — он ориентируется на sys.path интерпретатора, которым
    # его вызвали, а SITE_PACKAGES туда не входит (используется отдельный
    # PYTHON_EXE, не сам интерпретатор venv). Из-за этого любая транзитивная
    # ссылка на torch/torchaudio/librosa заставляла pip качать их заново,
    # хотя они уже стоят. Добавляем SITE_PACKAGES в PYTHONPATH, чтобы pip
    # увидел уже установленные пакеты через sys.path и не трогал их.
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SITE_PACKAGES + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )

    # ── Восстановление numpy до зафиксированной версии ──
    # Предыдущие попытки установки зависимостей RVC без --no-deps могли
    # частично затереть numpy более новой версией поверх старой (pip install
    # --target не делает чистое удаление перед установкой — файлы разных
    # версий смешиваются в одной папке). Форсированно переустанавливаем
    # numpy строго той версии, что зафиксирована в requirements.txt,
    # с --force-reinstall --no-deps, чтобы гарантированно вычистить любые
    # смешанные/битые файлы перед тем как продолжать.
    frozen_reqs = parse_requirements_txt()
    numpy_spec = frozen_reqs.get("numpy", "numpy==1.26.4")
    emit(f"Восстанавливаю numpy ({numpy_spec}) на случай порчи предыдущими попытками...")
    cmd_numpy = [
        PYTHON_EXE,
        "-m",
        "pip",
        "install",
        numpy_spec,
        "--target",
        SITE_PACKAGES,
        "--force-reinstall",
        "--no-deps",
        # Без --no-cache-dir: pip возьмёт уже скачанный wheel из
        # PIP_CACHE_DIR (python/pip_cache) вместо повторной закачки.
    ]
    try:
        proc = subprocess.Popen(
            cmd_numpy,
            cwd=BASE_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            bufsize=0,
        )
        _read_pip_output(proc, progress_cb)
        proc.wait()
        if proc.returncode == 0:
            emit("✅ numpy восстановлен до зафиксированной версии.")
        else:
            emit("⚠️ Не удалось восстановить numpy — продолжаю, но возможны проблемы.")
    except Exception as numpy_err:
        emit(f"⚠️ Ошибка при восстановлении numpy: {numpy_err}")

    # Windows prebuilt wheel bypass
    fairseq_wheel_installed = False
    if sys.platform == "win32":
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        # Прекомпилированные стабильные колеса от gdiaz384 для беспроблемной установки без MSVC Build Tools!
        fairseq_wheels = {
            "3.10": "https://github.com/gdiaz384/fairseq/releases/download/v0.12.2.2024Feb07/fairseq-0.12.2-cp310-cp310-win_amd64.whl",
            "3.11": "https://github.com/gdiaz384/fairseq/releases/download/v0.12.2.2024Feb07/fairseq-0.12.3.1-cp311-cp311-win_amd64.whl",
            "3.12": "https://github.com/gdiaz384/fairseq/releases/download/v0.12.2.2024Feb07/fairseq-0.12.3.1-cp312-cp312-win_amd64.whl",
        }

        if py_ver in fairseq_wheels:
            wheel_url = fairseq_wheels[py_ver]
            emit(
                f"Windows & Python {py_ver} обнаружены. Для обхода компиляции fairseq сначала устанавливаю prebuilt wheel..."
            )

            cmd_wheel = [
                PYTHON_EXE,
                "-m",
                "pip",
                "install",
                wheel_url,
                "--target",
                SITE_PACKAGES,
                "--upgrade",
                "--no-deps",
                # Без --no-cache-dir: повторная установка того же wheel
                # (например после переустановки rvc-python) возьмётся
                # из PIP_CACHE_DIR, а не будет качаться с GitHub заново.
            ]
            emit(f"Команда установки wheel: {' '.join(cmd_wheel)}")
            try:
                proc = subprocess.Popen(
                    cmd_wheel,
                    cwd=BASE_DIR,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    bufsize=0,
                )
                _read_pip_output(proc, progress_cb)
                proc.wait()
                if proc.returncode == 0:
                    emit("✅ Prebuilt wheel для fairseq успешно установлен!")
                    fairseq_wheel_installed = True
                else:
                    emit(
                        "⚠️ Не удалось установить prebuilt wheel для fairseq. Попробую установить rvc-python стандартным методом..."
                    )
            except Exception as wheel_err:
                emit(f"⚠️ Ошибка при установке wheel: {wheel_err}. Попробую стандартный метод...")

    # ── Установка rvc-python: --no-deps + отдельная установка его реальных зависимостей ──
    # Раньше зависимости (av, faiss-cpu, ...) ставились по одной вручную —
    # тупиковый путь, заранее нельзя знать полный список. Потом пробовали
    # отдать резолвинг зависимостей самому pip через --constraint — тоже
    # тупик, но по двум независимым причинам сразу:
    #   1. rvc-python сам пинует numpy<=1.25.3 (у нас зафиксирован 1.26.4);
    #   2. rvc-python пинует fairseq==0.12.2, который тянет omegaconf==2.0.6,
    #      а у ВСЕХ версий omegaconf 2.0.x (2.0.3–2.0.6) битые метаданные
    #      (".* suffix can only be used with == or != operators" в PyYAML)
    #      — современный pip (>=24.1) их просто отбраковывает при чтении,
    #      это не конфликт версий, а неразбираемый пакет, никаким
    #      constraints-файлом это не обойти.
    #
    # Поэтому: ставим сам rvc-python с --no-deps (пропускаем оба пина),
    # а его РЕАЛЬНЫЙ список зависимостей читаем из уже установленного
    # dist-info/METADATA (Requires-Dist) — это не наша догадка по логам,
    # а то, что сам пакет объявляет. fairseq из общего пакетного вызова
    # исключаем всегда (он идёт своим путём — либо уже стоит через prebuilt
    # wheel выше, либо, если wheel не встал, ставится отдельно чуть ниже
    # через --no-deps, см. fairseq_wheel_installed). С остальных зависимостей
    # снимаем любой точный "==" пин (см. ниже) — у rvc-python они системно
    # старые и тянут несовместимо низкие потолки numpy (сначала это была
    # omegaconf==2.0.6 с битыми метаданными, потом faiss-cpu==1.7.3 с
    # numpy<=1.23.5 — вероятно, всплывут и другие, если появятся новые
    # версии rvc-python с новыми пинами).
    emit("Устанавливаю rvc-python (--no-deps, зависимости разберём отдельно)...")
    cmd_rvc = [
        PYTHON_EXE,
        "-m",
        "pip",
        "install",
        "rvc-python",
        "--target",
        SITE_PACKAGES,
        "--upgrade",
        "--no-deps",
    ]
    emit(f"Команда установки RVC: {' '.join(cmd_rvc)}")
    proc = subprocess.Popen(
        cmd_rvc,
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=0,
    )
    _read_pip_output(proc, progress_cb)
    proc.wait()
    if proc.returncode != 0:
        if _can_clear_diagnostics_cache():
            clear_diagnostics_cache()
        emit(f"❌ Ошибка при установке rvc-python: pip завершился с кодом {proc.returncode}")
        raise RuntimeError(f"pip завершился с кодом {proc.returncode}")

    # Читаем реальные Requires-Dist из только что установленного dist-info.
    extra_deps = []
    fairseq_spec = None
    try:
        dist_info_dirs = [
            d
            for d in os.listdir(SITE_PACKAGES)
            if d.lower().startswith("rvc_python-") and d.endswith(".dist-info")
        ]
        if not dist_info_dirs:
            raise FileNotFoundError("dist-info для rvc_python не найден после установки")
        metadata_path = os.path.join(SITE_PACKAGES, sorted(dist_info_dirs)[-1], "METADATA")
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata_text = f.read()
        for line in metadata_text.splitlines():
            m = re.match(r"^Requires-Dist:\s*(.+)$", line.strip(), re.IGNORECASE)
            if not m:
                continue
            spec = m.group(1).strip()
            # Пропускаем опциональные extras (маркеры вида `; extra == "..."`)
            if "extra ==" in spec:
                continue
            clause = spec.split(";")[0].strip()
            pkg_name = re.split(r"[\s<>=!\[]", clause, 1)[0].strip()
            if not pkg_name:
                continue
            if pkg_name.lower() == "fairseq":
                fairseq_spec = clause
                continue  # ставится отдельно ниже — либо уже стоит через wheel, либо через --no-deps
            if pkg_name.lower() in frozen_reqs:
                # Пакет уже зафиксирован в requirements.txt (numpy, torch и т.п.) и
                # уже стоит нужной версии — вообще не включаем его в список на
                # установку, даже голым именем. Голое имя не спасает: команда
                # ниже идёт с --upgrade, и pip всё равно лезет на индекс проверять
                # версию для КАЖДОГО пакета в списке, включая уже установленные.
                # Для torch==2.2.2+cu118 это фатально — такой сборки нет на
                # обычном PyPI (она только на отдельном индексе PyTorch), и без
                # --extra-index-url pip не находит её и падает тем же
                # ResolutionImpossible, что мы уже видели на numpy. Раз пакет
                # уже стоит нужной версии — просто не трогаем его здесь.
                continue
            # Снимаем ЛЮБОЙ точный "==X.Y.Z" пин (без диапазонов вроде ">=") —
            # такие пины в METADATA rvc-python оказались стабильно старыми и
            # тянут за собой несовместимо низкие потолки numpy (сначала
            # omegaconf==2.0.6 с битыми метаданными, потом faiss-cpu==1.7.3
            # с numpy<=1.23.5) — берём последнюю совместимую версию вместо
            # жёсткого пина автора rvc-python.
            version_part = clause[len(pkg_name) :].strip()
            if re.fullmatch(r"==\s*[\w.\-+]+", version_part):
                extra_deps.append(pkg_name)
            else:
                extra_deps.append(clause)
        emit(
            f"Реальные зависимости rvc-python из METADATA: {', '.join(extra_deps) if extra_deps else '(пусто)'}"
            + (f"; fairseq: {fairseq_spec}" if fairseq_spec else "")
        )
    except Exception as meta_err:
        if _can_clear_diagnostics_cache():
            clear_diagnostics_cache()
        emit(f"❌ Не удалось прочитать зависимости rvc-python из METADATA: {meta_err}")
        raise RuntimeError(f"Не удалось прочитать зависимости rvc-python: {meta_err}")

    # Если prebuilt wheel для fairseq не встал (сеть/неподдерживаемая версия Python),
    # rvc-python молча остался бы без fairseq — ставим его явно отдельным вызовом
    # с --no-deps (используя ровно ту версию, что объявлена в METADATA rvc-python),
    # чтобы не тянуть следом omegaconf==2.0.6 с битыми метаданными.
    if fairseq_spec and not fairseq_wheel_installed:
        emit(
            f"⚠️ Prebuilt wheel для fairseq не установился — ставлю {fairseq_spec} через pip напрямую (--no-deps, без резолвинга omegaconf)..."
        )
        cmd_fairseq = [
            PYTHON_EXE,
            "-m",
            "pip",
            "install",
            fairseq_spec,
            "--target",
            SITE_PACKAGES,
            "--upgrade",
            "--no-deps",
        ]
        proc = subprocess.Popen(
            cmd_fairseq,
            cwd=BASE_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            bufsize=0,
        )
        _read_pip_output(proc, progress_cb)
        proc.wait()
        if proc.returncode != 0:
            if _can_clear_diagnostics_cache():
                clear_diagnostics_cache()
            emit(
                f"❌ Не удалось установить {fairseq_spec}: pip завершился с кодом {proc.returncode}"
            )
            raise RuntimeError(
                f"Не удалось установить {fairseq_spec} (ни через wheel, ни через pip)"
            )
        emit(f"✅ {fairseq_spec} установлен напрямую через pip.")

    # ── Доставка зависимостей fairseq ──
    # Prebuilt wheel fairseq ставится через --no-deps, поэтому его реальные
    # зависимости (hydra-core, bitarray, sacrebleu, ...) не попадают в
    # окружение, и при импорте rvc_python (который тянет fairseq) получаем
    # «No module named 'hydra'». Доставляем их отдельным вызовом, читая
    # Requires-Dist из METADATA самого fairseq. omegaconf исключаем — его
    # держит динамический constraint на уже стоящую версию (2.3.1), чтобы не
    # подхватить битый omegaconf==2.0.6.
    #
    # ВАЖНО: fairseq (и sacrebleu) объявляют зависимость dataclasses — это
    # бэкпорт ТОЛЬКО для Python <3.7; на 3.11 dataclasses уже в stdlib, а
    # установка бэкпорта ТЕНЕВЫМ образом перекрывает стандартный модуль и
    # ломает сам pip (AttributeError: module 'typing' has no attribute
    # '_ClassVar'). Поэтому dataclasses НИКОГДА не ставим, а sacrebleu
    # ставим отдельно с --no-deps (его реальные зависимости regex/tabulate/
    # colorama уже есть в базовом окружении и dataclasses не требуют).
    try:
        fairseq_reqs = _read_requires_dist("fairseq")
    except Exception:
        fairseq_reqs = []
    sacrebleu_needed = False
    core_fairseq_deps = []
    for clause in fairseq_reqs:
        pkg_name = re.split(r"[\s<>=!\[]", clause, 1)[0].strip()
        low = pkg_name.lower()
        if low in ("omegaconf", "fairseq", "dataclasses"):
            continue
        if low == "sacrebleu":
            sacrebleu_needed = True
            continue
        if low in frozen_reqs:
            continue
        version_part = clause[len(pkg_name) :].strip()
        if re.fullmatch(r"==\s*[\w.\-+]+", version_part):
            core_fairseq_deps.append(pkg_name)
        else:
            core_fairseq_deps.append(clause)

    def _install_fairseq_chunk(specs):
        cmd = [
            PYTHON_EXE,
            "-m",
            "pip",
            "install",
            *specs,
            "--target",
            SITE_PACKAGES,
            "--upgrade",
        ]
        torch_build, torch_index = detect_torch_build(SITE_PACKAGES)
        if torch_index:
            cmd.extend(["--extra-index-url", torch_index])
        constraints_path = os.path.join(PORTABLE_TEMP_DIR, "rvc_constraints.txt")
        constraint_lines = _build_rvc_constraints(frozen_reqs, SITE_PACKAGES)
        with open(constraints_path, "w", encoding="utf-8") as f:
            f.write("\n".join(constraint_lines) + "\n")
        cmd.extend(["--constraint", constraints_path])
        emit(f"Команда установки зависимостей fairseq: {' '.join(cmd)}")
        rc, _ = _install_with_retry(cmd, env, progress_cb)
        return rc

    if core_fairseq_deps:
        emit(
            f"Доставляю зависимости fairseq: {', '.join(core_fairseq_deps)} (нужны для импорта RVC)..."
        )
        rc = _install_fairseq_chunk(core_fairseq_deps)
        if rc != 0:
            emit("⚠️ Не удалось доставить зависимости fairseq — импорт RVC может не пройти.")
    else:
        emit("Зависимости fairseq (ядро) уже на месте (или fairseq не установлен — пропускаю).")

    if sacrebleu_needed:
        emit("Доставляю sacrebleu (--no-deps, без dataclasses-бэкпорта) + его зависимости...")
        # sacrebleu с --no-deps, чтобы не подхватить dataclasses-бэкпорт
        _install_fairseq_chunk(["sacrebleu", "--no-deps"])
        # Доставляем реальные зависимости sacrebleu, читая их прямо из
        # METADATA самого sacrebleu (исключая dataclasses-бэкпорт, который
        # ломает stdlib на Python 3.11). Раньше здесь были захардкожены
        # только regex/tabulate/colorama, из-за чего не хватало реальных
        # зависимостей (прежде всего portalocker) — и импорт rvc_python
        # (через fairseq→sacrebleu) падал с «No module named 'portalocker'».
        try:
            sacrebleu_reqs = _read_requires_dist("sacrebleu")
        except Exception:
            sacrebleu_reqs = []
        sacrebleu_deps = []
        for clause in sacrebleu_reqs:
            pkg_name = re.split(r"[\s<>=!\[\]]", clause, 1)[0].strip()
            low = pkg_name.lower()
            if low in ("dataclasses",):
                continue
            if low in frozen_reqs:
                continue
            version_part = clause[len(pkg_name) :].strip()
            if re.fullmatch(r"==\s*[\w\.\-+]+", version_part):
                sacrebleu_deps.append(pkg_name)
            else:
                sacrebleu_deps.append(clause)
        if sacrebleu_deps:
            emit(f"Зависимости sacrebleu из METADATA: {', '.join(sacrebleu_deps)}")
            _install_fairseq_chunk(sacrebleu_deps)
        else:
            # Запасной вариант, если METADATA sacrebleu не прочитался:
            # ставим минимально известный набор, включая portalocker.
            emit(
                "⚠️ Не удалось прочитать METADATA sacrebleu — ставлю запасной набор зависимостей (regex/tabulate/colorama/portalocker)."
            )
            _install_fairseq_chunk(["regex", "tabulate", "colorama", "portalocker"])

    if extra_deps:
        requirements_path = os.path.join(BASE_DIR, "requirements.txt")
        deps_file_path = os.path.join(PORTABLE_TEMP_DIR, "rvc_extra_deps.txt")
        os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
        with open(deps_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(extra_deps) + "\n")

        cmd_deps = [
            PYTHON_EXE,
            "-m",
            "pip",
            "install",
            "-r",
            deps_file_path,
            "--target",
            SITE_PACKAGES,
            "--upgrade",
            # Без --no-cache-dir: при повторных попытках уже скачанные
            # av/faiss-cpu/torchcrepe и т.п. возьмутся из PIP_CACHE_DIR.
        ]
        # Адаптивный выбор сборки torch (detect_torch_build переиспользует
        # ЕДИНУЮ логику engine.env_core.torch_setup — тот же механизм, что у
        # базовой установки torch): берём ту сборку, что уже стоит в
        # окружении, либо авто-детектим CUDA, если torch ещё не установлен.
        # Соответствующий --extra-index-url (cu118 или cpu) подставляется
        # всегда и согласован с базовой установкой, чтобы RVC-путь и
        # первичная установка резолвили одну и ту же сборку без ручного
        # переключения.
        torch_build, torch_index = detect_torch_build(SITE_PACKAGES)
        if torch_index:
            cmd_deps.extend(["--extra-index-url", torch_index])
        # Динамический constraint вместо статического requirements.txt:
        # пиним зафиксированные пакеты к РЕАЛЬНО установленным версиям
        # (с учётом варианта сборки +cu118/+cpu). requirements.txt теперь
        # нейтральный (torch==2.2.2 без суффикса), а реальный вариант
        # выбирается кодом — поэтому уже стоящий torch считается
        # удовлетворённым и больше не перетягивается (не будет 2.7 ГБ).
        constraints_path = os.path.join(PORTABLE_TEMP_DIR, "rvc_constraints.txt")
        constraint_lines = _build_rvc_constraints(frozen_reqs, SITE_PACKAGES)
        with open(constraints_path, "w", encoding="utf-8") as f:
            f.write("\n".join(constraint_lines) + "\n")
        emit(
            f"Динамический constraint для зависимостей RVC (по установленным версиям): "
            f"torch→{next((l for l in constraint_lines if l.lower().startswith('torch==')), 'n/a')}; "
            f"целевая сборка torch: {torch_build}"
        )
        cmd_deps.extend(["--constraint", constraints_path])
        emit(f"Команда установки зависимостей RVC: {' '.join(cmd_deps)}")

        # Запуск с отказоустойчивостью к блокировкам файлов Windows:
        # _install_with_retry при PermissionError (WinError 5) повторяет
        # БЕЗ --upgrade, чтобы не трогать залоченные .pyd запущенного приложения.
        rc, _ = _install_with_retry(cmd_deps, env, progress_cb)
        if rc != 0:
            if _can_clear_diagnostics_cache():
                clear_diagnostics_cache()
            emit(f"❌ Ошибка при установке зависимостей rvc-python: pip завершился с кодом {rc}")
            raise RuntimeError(f"pip завершился с кодом {rc} при установке зависимостей rvc-python")

    # ── Восстановление PyYAML (модуль yaml) ──
    # rvc-python (и всё приложение) критически зависит от yaml, но PyYAML
    # может оказаться побитым/неполным (напр. отсутствует yaml/error.py) из-за
    # предыдущих --no-deps/--target установок. pip при --upgrade НЕ чинит уже
    # «удовлетворённую» по метаданным версию с битыми файлами (и динамический
    # constraint только мешает этому, пиня PyYAML к установленной версии),
    # поэтому импорт падает с "No module named 'yaml.error'". Восстанавливаем
    # принудительно (force-reinstall, без зависимостей — у PyYAML их нет),
    # чтобы гарантированно вернуть целый yaml/error.py и _yaml.
    emit("Восстанавливаю PyYAML (модуль yaml) — критично для импорта rvc-python...")
    cmd_yaml = [
        PYTHON_EXE,
        "-m",
        "pip",
        "install",
        "PyYAML",
        "--target",
        SITE_PACKAGES,
        "--force-reinstall",
        "--no-deps",
    ]
    rc_yaml, _ = _install_with_retry(cmd_yaml, env, progress_cb)
    if rc_yaml != 0:
        emit("⚠️ Не удалось восстановить PyYAML — импорт rvc-python может не пройти.")
    else:
        emit("✅ PyYAML восстановлен.")

    # ── Проверка импорта с АВТО-ЛЕЧЕНИЕМ недостающих модулей ──
    # rvc_python тянет глубокое дерево зависимостей (fairseq → sacrebleu →
    # portalocker и т.д.). Если на каком-то уровне не хватает модуля, вместо
    # «бесконечной» ручной правки под конкретное имя — доустанавливаем
    # недостающий пакет и повторяем проверку импорта. Это закрывает случаи
    # вроде «No module named 'portalocker'» и любой другой транзитивный
    # модуль без жёсткой привязки к конкретному названию.
    _MODULE_TO_PIP = {
        "yaml": "PyYAML",
        "PIL": "Pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "bs4": "beautifulsoup4",
        "sacrebleu": "sacrebleu",
        "fairseq": "fairseq",
        "portalocker": "portalocker",
    }
    status = None
    max_attempts = 6
    for attempt in range(max_attempts):
        emit(f"Проверяю корректность импорта rvc-python (попытка {attempt + 1})...")
        status = rvc_status()
        if status["installed"]:
            break
        err = status.get("error", "") or ""
        m = re.search(r"No module named '([^']+)'", err)
        if not m:
            # Ошибка импорта не связана с отсутствующим модулем —
            # дальше угадывать бессмысленно, пробрасываем как есть.
            break
        missing_mod = m.group(1).split(".")[0]
        pip_pkg = _MODULE_TO_PIP.get(missing_mod, missing_mod)
        emit(f"⚠️ Не хватает модуля '{missing_mod}' (пакет {pip_pkg}) — доустанавливаю...")
        cmd_missing = [
            PYTHON_EXE,
            "-m",
            "pip",
            "install",
            pip_pkg,
            "--target",
            SITE_PACKAGES,
            "--upgrade",
        ]
        torch_build, torch_index = detect_torch_build(SITE_PACKAGES)
        if torch_index:
            cmd_missing.extend(["--extra-index-url", torch_index])
        rc, _ = _install_with_retry(cmd_missing, env, progress_cb)
        if rc != 0:
            emit(f"⚠️ Не удалось доустановить {pip_pkg} (rc={rc}).")
            break

    # Принудительно очищаем кэш после установки (успешной или нет) — только если нет активной установки/восстановления
    if _can_clear_diagnostics_cache():
        clear_diagnostics_cache()

    if not status or not status["installed"]:
        msg = status.get("error") if status else "импорт не прошёл без сообщения об ошибке"
        raise RuntimeError(f"Установка завершена, но импорт не удался: {msg}")

    emit("✅ Готово — rvc-python успешно установлен и работает.")
    return status


def uninstall_rvc(progress_cb=None) -> bool:
    from engine.logging_utils import write_log

    def emit(line):
        write_log(line)
        if progress_cb:
            progress_cb(line)

    emit(
        "Удаляю rvc-python и возможные хвосты от предыдущих попыток установки (fairseq и его зависимости)..."
    )
    if not os.path.isdir(SITE_PACKAGES):
        return True

    # rvc_python/rvc-python, а также fairseq и типичные зависимости fairseq,
    # которые могли протащиться при установке без --no-deps в прошлый раз
    # и остаться в site-packages даже после удаления самого rvc-python.
    prefixes = (
        "rvc_python",
        "rvc-python",
        "fairseq",
        "omegaconf",
        "omegaconf-",
        "hydra_core",
        "hydra-core",
        "antlr4",
        "sacrebleu",
        "bitarray",
        "dataclasses",
        # НЕ удаляем portalocker: это НЕ пакет RVC, а общая зависимость
        # (её тянет sacrebleu ← fairseq ← rvc_python, и она же нужна TTS).
        # Раньше uninstall_rvc вытирал portalocker, из-за чего импорт
        # rvc_python падал с «No module named 'portalocker'», а после
        # установки RVC ломался ещё и TTS (его глубокая проверка тоже
        # требует portalocker). Оставляем его на месте как разделяемый пакет.
        "av-",  # dist-info/egg-info от предыдущих ручных попыток
        "faiss",
        "faiss_cpu",
        "faiss-cpu",
    )
    for name in os.listdir(SITE_PACKAGES):
        low = name.lower()
        if low.startswith(prefixes) or low == "av":
            full = os.path.join(SITE_PACKAGES, name)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                elif os.path.isfile(full):
                    os.remove(full)
            except Exception:
                pass
    emit("✅ rvc-python и сопутствующие хвосты удалены.")
    return True
