from typing import Any, List, Optional, Tuple
import re
import os
import sys
import time
from datetime import datetime
import unicodedata as _unicodedata
import threading as _threading
import hashlib
import torch
import gc


_device = None


def detect_device() -> str:
    global _device
    if _device is None:
        import torch  # type: ignore

        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device
