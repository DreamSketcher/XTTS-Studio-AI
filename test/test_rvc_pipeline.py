import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.rvc_pipeline import RVCPostProcessor, RVCPipelineError, XTTSWithRVCPipeline


class TestRVCPostProcessorDevice:
    def test_normalize_cpu(self):
        assert RVCPostProcessor._normalize_device("cpu") == "cpu:0"
        assert RVCPostProcessor._normalize_device("cpu:0") == "cpu:0"
        assert RVCPostProcessor._normalize_device("CPU") == "cpu:0"
        assert RVCPostProcessor._normalize_device("") == "cpu:0"

    def test_normalize_cuda(self):
        assert RVCPostProcessor._normalize_device("cuda") == "cuda:0"
        assert RVCPostProcessor._normalize_device("gpu") == "cuda:0"
        assert RVCPostProcessor._normalize_device("cuda0") == "cuda:0"
        assert RVCPostProcessor._normalize_device("cuda:1") == "cuda:1"

    def test_normalize_other(self):
        assert RVCPostProcessor._normalize_device("cuda:0") == "cuda:0"
        assert RVCPostProcessor._normalize_device("custom:1") == "custom:1"


class TestRVCPostProcessorPaths:
    def test_init_creates_dir(self, tmp_path):
        models_dir = tmp_path / "rvc_models"
        proc = RVCPostProcessor(models_dir=str(models_dir), device="cpu:0")
        assert models_dir.exists()
        assert proc.device == "cpu:0"

    def test_model_not_found(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path), device="cpu:0")
        # мок rvc_python чтобы импорт прошёл, и тогда проверка файла сработает
        import sys, types

        fake_mod = types.ModuleType("rvc_python.infer")
        fake_mod.RVCInference = MagicMock()
        monkeypatch.setitem(sys.modules, "rvc_python.infer", fake_mod)
        monkeypatch.setitem(sys.modules, "rvc_python", types.ModuleType("rvc_python"))

        with pytest.raises(RVCPipelineError, match="не найдена"):
            proc.run_inference_via_lib(
                input_path="/tmp/in.wav",
                output_path="/tmp/out.wav",
                model_name="nonexistent",
            )


class TestRunInferenceViaLib:
    def test_import_error(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path), device="cpu:0")
        # создаём модель файл чтобы пройти первую проверку
        (tmp_path / "test.pth").write_text("fake")

        # мокаем отсутствие rvc_python
        import sys

        # удаляем если есть
        monkeypatch.delitem(sys.modules, "rvc_python.infer", raising=False)
        monkeypatch.delitem(sys.modules, "rvc_python", raising=False)

        # патчим __import__ чтобы кидал ImportError для rvc_python
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if "rvc_python" in name:
                raise ImportError("no rvc_python")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        with pytest.raises(RVCPipelineError, match="не установлена"):
            proc.run_inference_via_lib("/tmp/in.wav", "/tmp/out.wav", "test")

    def test_success_mocked(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path), device="cpu:0")
        model_path = tmp_path / "mymodel.pth"
        model_path.write_text("fake model")
        index_path = tmp_path / "mymodel.index"
        index_path.write_text("fake index")

        input_wav = tmp_path / "in.wav"
        input_wav.write_text("input")
        output_wav = tmp_path / "out.wav"

        # мок RVCInference
        mock_infer = MagicMock()
        mock_infer_instance = MagicMock()
        mock_infer.return_value = mock_infer_instance

        # мок модуля rvc_python.infer
        import sys, types

        fake_module = types.ModuleType("rvc_python.infer")
        fake_module.RVCInference = mock_infer
        monkeypatch.setitem(sys.modules, "rvc_python.infer", fake_module)
        fake_pkg = types.ModuleType("rvc_python")
        fake_pkg.infer = fake_module
        monkeypatch.setitem(sys.modules, "rvc_python", fake_pkg)

        # чтобы проверить что output создаётся, сделаем side effect создания файла
        def fake_infer_file(inp, out):
            Path(out).write_text("output data")

        mock_infer_instance.infer_file.side_effect = fake_infer_file

        result = proc.run_inference_via_lib(
            input_path=str(input_wav),
            output_path=str(output_wav),
            model_name="mymodel",
            index_rate=0.75,
            pitch_shift=0,
            f0_method="rmvpe",
        )

        assert result == str(output_wav)
        assert output_wav.exists()
        mock_infer_instance.load_model.assert_called_once()
        mock_infer_instance.set_params.assert_called_once()

    def test_no_output_file_raises(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path), device="cpu:0")
        (tmp_path / "model.pth").write_text("fake")

        import sys, types

        mock_infer = MagicMock()
        mock_instance = MagicMock()
        mock_infer.return_value = mock_instance
        mock_instance.infer_file.return_value = None  # не создаёт файл

        fake_mod = types.ModuleType("rvc_python.infer")
        fake_mod.RVCInference = mock_infer
        monkeypatch.setitem(sys.modules, "rvc_python.infer", fake_mod)
        monkeypatch.setitem(sys.modules, "rvc_python", types.ModuleType("rvc_python"))

        input_wav = tmp_path / "in.wav"
        input_wav.write_text("in")
        output_wav = tmp_path / "out.wav"

        with pytest.raises(RVCPipelineError, match="без выходного WAV-файла"):
            proc.run_inference_via_lib(str(input_wav), str(output_wav), "model")


class TestRunInferenceViaCli:
    def test_cli_model_not_found(self, tmp_path):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        with pytest.raises(RVCPipelineError, match="не найдена"):
            proc.run_inference_via_cli("/tmp/in.wav", "/tmp/out.wav", "nonexistent")

    def test_cli_success_mocked(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        (tmp_path / "model.pth").write_text("fake")

        mock_which = MagicMock(return_value="/usr/bin/python")
        monkeypatch.setattr("shutil.which", mock_which)

        output_wav = tmp_path / "out.wav"

        # subprocess.run в реальности запускает CLI, который и создаёт WAV;
        # мок должен повторить этот побочный эффект, иначе код закономерно
        # решит, что конвертация не удалась (файла нет).
        def fake_run(*a, **kw):
            output_wav.write_text("output data")
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)

        result = proc.run_inference_via_cli("/tmp/in.wav", str(output_wav), "model")
        assert result == str(output_wav)

    def test_cli_failure(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        (tmp_path / "model.pth").write_text("fake")

        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/python")
        import subprocess

        def fake_run(*a, **kw):
            raise subprocess.CalledProcessError(
                returncode=1, cmd="rvc", output="fail", stderr="error"
            )

        monkeypatch.setattr("subprocess.run", fake_run)

        with pytest.raises(RVCPipelineError, match="CLI завершился с кодом"):
            proc.run_inference_via_cli("/tmp/in.wav", "/tmp/out.wav", "model")


class TestXTTSWithRVCPipeline:
    def test_no_rvc_model_returns_xtts_direct(self, tmp_path):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        pipeline = XTTSWithRVCPipeline(rvc_processor=proc)

        mock_xtts = MagicMock(return_value="/tmp/out.wav")

        result = pipeline.generate_and_enhance(
            text="hello",
            language="en",
            speaker_wav="/tmp/ref.wav",
            output_path="/tmp/out.wav",
            xtts_generator_func=mock_xtts,
            rvc_model=None,
        )

        assert result == "/tmp/out.wav"
        assert mock_xtts.called

    def test_with_rvc(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        # мок run_inference_via_lib
        monkeypatch.setattr(proc, "run_inference_via_lib", lambda **kw: kw["output_path"])

        pipeline = XTTSWithRVCPipeline(rvc_processor=proc)

        def mock_xtts(text, language, speaker_wav, output_path):
            Path(output_path).write_text("xtts output")
            return output_path

        output = tmp_path / "final.wav"
        result = pipeline.generate_and_enhance(
            text="hello",
            language="en",
            speaker_wav="/tmp/ref.wav",
            output_path=str(output),
            xtts_generator_func=mock_xtts,
            rvc_model="mymodel",
            rvc_settings={"index_rate": 0.8},
        )

        assert result == str(output)
        # временный файл должен быть удалён
        temp = tmp_path / "final_temp_xtts.wav"
        assert not temp.exists()

    def test_xtts_fails_no_output(self, tmp_path, monkeypatch):
        proc = RVCPostProcessor(models_dir=str(tmp_path))
        monkeypatch.setattr(proc, "run_inference_via_lib", lambda **kw: kw["output_path"])

        pipeline = XTTSWithRVCPipeline(rvc_processor=proc)

        def mock_xtts_fail(*a, **kw):
            # не создаёт файл
            return kw.get("output_path", "/tmp/out.wav")

        # удаляем файл если создался случайно
        output = tmp_path / "out.wav"
        if output.exists():
            output.unlink()

        # в generate_and_enhance проверяется существование temp файла после xtts
        # если mock не создаёт файл, должен кинуть RVCPipelineError
        def mock_xtts_no_file(text, language, speaker_wav, output_path):
            # не создаёт файл
            return output_path

        with pytest.raises(RVCPipelineError, match="base generation failed"):
            pipeline.generate_and_enhance(
                text="hello",
                language="en",
                speaker_wav="/tmp/ref.wav",
                output_path=str(output),
                xtts_generator_func=mock_xtts_no_file,
                rvc_model="model",
            )
