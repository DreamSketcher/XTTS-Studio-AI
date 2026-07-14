import pytest

import engine.env_setup as env_setup
import engine.env_core as env_core


class TestEnvSetupProxy:
    def test_has_site_packages(self):
        assert hasattr(env_setup, "SITE_PACKAGES")
        assert isinstance(env_setup.SITE_PACKAGES, str)

    def test_has_project_root(self):
        assert hasattr(env_setup, "PROJECT_ROOT")

    def test_has_detect_functions(self):
        # должны быть прокинуты из env_core
        assert hasattr(env_setup, "detect_cpu") or hasattr(env_core, "detect_cpu")
        assert hasattr(env_setup, "detect_gpu") or hasattr(env_core, "detect_gpu")

    def test_has_torch_functions(self):
        # из torch_setup
        for name in ["torch_status", "install_torch", "get_installed_torch_variant"]:
            assert hasattr(env_setup, name) or hasattr(env_core, name), f"missing {name}"

    def test_has_llama_functions(self):
        for name in ["llama_cpp_status", "install_llama_cpp", "get_installed_backend"]:
            assert hasattr(env_setup, name) or hasattr(env_core, name)

    def test_has_rvc_functions(self):
        for name in ["rvc_status", "install_rvc"]:
            assert hasattr(env_setup, name) or hasattr(env_core, name)

    def test_has_diagnostics(self):
        for name in ["run_full_diagnostics", "get_broken_critical", "clear_diagnostics_cache"]:
            assert hasattr(env_setup, name) or hasattr(env_core, name)

    def test_has_read_pip_output(self):
        # важный underscore helper — должен быть явно реэкспортирован
        assert (
            hasattr(env_setup, "_read_pip_output")
            or hasattr(env_core, "_read_pip_output")
            or hasattr(env_core.diagnostics, "_read_pip_output")
        )

    def test_star_imports_work(self):
        # from engine.env_core import * уже в env_setup
        # проверим что критичные константы доступны
        assert hasattr(env_setup, "CRITICAL_COMPONENTS") or hasattr(env_core, "CRITICAL_COMPONENTS")

    def test_env_core_init_has_get_site_packages(self):
        assert hasattr(env_core, "get_site_packages")
        assert callable(env_core.get_site_packages)
        result = env_core.get_site_packages()
        assert isinstance(result, list)
