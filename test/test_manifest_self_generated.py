import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_self_generated_release_files_are_excluded(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = Path(__file__).resolve().parents[1] / "generate_version_manifest.py"
    shutil.copy2(source, root / "generate_version_manifest.py")
    (root / "app.py").write_text("print('ok')", encoding="utf-8")
    (root / "version.json.sig").write_text("old", encoding="ascii")
    (root / "checksums.txt").write_text("old", encoding="utf-8")
    manifest = {
        "version": "1.0.0",
        "files": ["app.py", "version.json", "version.json.sig", "checksums.txt"],
        "sha256": {},
    }
    (root / "version.json").write_text(json.dumps(manifest), encoding="utf-8")
    # Remove the signature for this unit test: unsigned temporary projects are
    # allowed, while an existing production signature requires a signing key.
    (root / "version.json.sig").unlink()
    result = subprocess.run(
        [sys.executable, "generate_version_manifest.py", "--version", "1.0.1"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    updated = json.loads((root / "version.json").read_text(encoding="utf-8"))
    assert updated["files"] == ["app.py"]
    assert not (
        {"version.json", "version.json.sig", "checksums.txt"} & set(updated["removed_files"])
    )
