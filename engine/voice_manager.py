import os
import shutil
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VoiceProfile:
    name: str
    path: str
    original: Optional[str]
    converted: Optional[str]
    normalized: Optional[str]
    embedding: Optional[str]
    last_modified: float


class VoiceManager:
    def __init__(self, base_dir="library"):
        if os.path.isabs(base_dir):
            self.base_dir = base_dir
        else:
            self.base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), base_dir)

        self.voices: List[VoiceProfile] = []
        self.active_voice: Optional[VoiceProfile] = None

    # =========================
    # SAFE SCAN
    # =========================
    def scan_voices(self):
        voices = []

        try:
            os.makedirs(self.base_dir, exist_ok=True)
        except Exception as e:
            self.voices = []
            return []

        try:
            entries = os.listdir(self.base_dir)
        except Exception as e:
            print(f"[VoiceManager] Cannot list base_dir: {e}")
            self.voices = []
            return []

        for voice_name in entries:
            voice_path = os.path.join(self.base_dir, voice_name)

            try:
                if not os.path.isdir(voice_path):
                    continue

                files = os.listdir(voice_path)

                original = self._find_file(files, "original")
                converted = self._find_file(files, "converted")
                normalized = self._find_file(files, "normalized")
                embedding = self._find_file(files, "embedding")  # ← добавлено

                try:
                    last_modified = os.path.getmtime(voice_path)
                except Exception:
                    last_modified = 0.0

                voice = VoiceProfile(
                    name=voice_name,
                    path=voice_path,
                    original=original,
                    converted=converted,
                    normalized=normalized,
                    embedding=embedding,
                    last_modified=last_modified,
                )

                voices.append(voice)

            except Exception as e:
                print(f"[VoiceManager] Skip voice '{voice_name}': {e}")
                continue

        voices.sort(key=lambda v: v.last_modified, reverse=True)

        self.voices = voices
        return voices

    # =========================
    # HELPER
    # =========================
    def _find_file(self, files, keyword):
        try:
            for f in files:
                if keyword in f.lower():
                    return f
        except Exception:
            pass
        return None

    # =========================
    # LIST
    # =========================
    def list_voices(self):
        return self.voices

    # =========================
    # GET
    # =========================
    def get_voice(self, name: str) -> Optional[VoiceProfile]:
        for v in self.voices:
            if v.name == name:
                return v
        return None

    # =========================
    # ACTIVE
    # =========================
    def set_active(self, name: str):
        voice = self.get_voice(name)
        if voice:
            self.active_voice = voice
            return True
        return False

    def get_active(self):
        return self.active_voice

    # =========================
    # DELETE SAFE
    # =========================
    def delete_voice(self, name: str):
        voice = self.get_voice(name)
        if not voice:
            return False

        try:
            shutil.rmtree(voice.path, ignore_errors=True)
            self.scan_voices()
            return True
        except Exception as e:
            print(f"[VoiceManager] Delete error: {e}")
            return False

    # =========================
    # RENAME SAFE
    # =========================
    def rename_voice(self, old_name: str, new_name: str):
        old_voice = self.get_voice(old_name)
        if not old_voice:
            return False

        old_path = old_voice.path
        new_path = os.path.join(self.base_dir, new_name)

        try:
            os.rename(old_path, new_path)
            self.scan_voices()
            return True
        except Exception as e:
            print(f"[VoiceManager] Rename error: {e}")
            return False
