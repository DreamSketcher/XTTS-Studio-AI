import importlib
import sys
import threading
from typing import Any, Dict

class LazyModule:
    """
    A thread-safe proxy that delays module import until its first use.
    Using this for heavy ML modules like `torch`, `torchaudio`, or `TTS`
    allows the GUI to launch immediately without block-loading delays.
    """
    _loaded_modules: Dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, name: str):
        self._name = name

    def _get_module(self) -> Any:
        # Fast double-checked locking pattern for thread safety
        if self._name in LazyModule._loaded_modules:
            return LazyModule._loaded_modules[self._name]
            
        with LazyModule._lock:
            if self._name not in LazyModule._loaded_modules:
                print(f"[LazyLoader] Real import triggered for heavy package: '{self._name}'")
                LazyModule._loaded_modules[self._name] = importlib.import_module(self._name)
            return LazyModule._loaded_modules[self._name]

    def __getattr__(self, name: str) -> Any:
        module = self._get_module()
        return getattr(module, name)

    def __dir__(self):
        module = self._get_module()
        return dir(module)

    def __repr__(self) -> str:
        return f"<LazyModule proxy for '{self._name}'>"


def lazy_import(name: str):
    """
    Utility wrapper to assign lazy modules.
    
    Example:
        torch = lazy_import("torch")
        torchaudio = lazy_import("torchaudio")
        
        # When you call torch.cuda.is_available(), it will finally import torch under the hood.
    """
    return LazyModule(name)
