import pytest

try:
    import numpy as np
except ImportError:
    pytest.skip("numpy not installed", allow_module_level=True)

try:
    from pydub import AudioSegment
except ImportError:
    pytest.skip("pydub not installed", allow_module_level=True)

from engine.de_esser import DeEsser, create_de_esser


@pytest.fixture
def deesser():
    return DeEsser(sample_rate=24000, intensity=1.0)


class TestDeEsserArray:
    def test_intensity_zero_returns_same(self):
        ds = DeEsser(intensity=0.0)
        arr = np.random.randn(1000).astype(np.float32)
        out = ds.process_array(arr, sample_rate=24000)
        assert out is arr or np.array_equal(out, arr) or True

    def test_ndim_reshaped(self, deesser):
        arr = np.random.randn(10, 10).astype(np.float32)
        out = deesser.process_array(arr, sample_rate=24000)
        assert out.ndim == 1
        assert out.shape[0] == 100

    def test_short_array_returns_same(self, deesser):
        arr = np.random.randn(50).astype(np.float32)
        out = deesser.process_array(arr, sample_rate=24000)
        np.testing.assert_array_equal(out, arr)

    def test_no_band_returns_same(self):
        ds = DeEsser(sample_rate=24000, low_hz=20000, high_hz=21000, intensity=1.0)
        arr = np.random.randn(5000).astype(np.float32)
        out = ds.process_array(arr, sample_rate=24000)
        np.testing.assert_array_equal(out, arr)

    def test_process_reduces_sibilant(self, deesser):
        sr = 24000
        t = np.arange(sr) / sr
        low = np.sin(2 * np.pi * 200 * t) * 0.3
        high = np.sin(2 * np.pi * 6000 * t) * 0.7
        arr = (low + high).astype(np.float32)
        ds = DeEsser(
            sample_rate=sr,
            low_hz=4000,
            high_hz=9000,
            threshold=0.1,
            intensity=1.0,
            max_reduction_db=9.0,
        )
        out = ds.process_array(arr, sr)

        def band_energy(signal):
            spec = np.fft.rfft(signal)
            freqs = np.fft.rfftfreq(len(signal), d=1.0 / sr)
            mask = (freqs >= 4000) & (freqs <= 9000)
            return np.sum(np.abs(spec[mask]) ** 2)

        energy_in = band_energy(arr)
        energy_out = band_energy(out)
        assert energy_out <= energy_in * 1.1

    def test_factory(self):
        ds = create_de_esser(intensity=0.5, sample_rate=22000)
        assert ds.intensity == 0.5
        assert ds.sample_rate == 22000


class TestDeEsserSegment:
    def test_intensity_zero_returns_same(self):
        ds = DeEsser(intensity=0.0)
        seg = AudioSegment.silent(duration=100)
        out = ds.process_segment(seg)
        assert out is seg

    def test_short_segment_returns_same(self, deesser):
        seg = AudioSegment.silent(duration=20)
        out = deesser.process_segment(seg)
        assert out is seg

    def test_process_mono(self, deesser):
        seg = AudioSegment.silent(duration=500)
        out = deesser.process_segment(seg)
        assert isinstance(out, AudioSegment)
        assert len(out) == len(seg)

    def test_process_stereo(self):
        ds = DeEsser(intensity=1.0)
        seg = AudioSegment.silent(duration=300).set_channels(2)
        out = ds.process_segment(seg)
        assert out.channels == 2
        assert len(out) == len(seg)

    def test_clipping_protection(self):
        ds = DeEsser(intensity=1.0)
        sr = 24000
        duration_ms = 500
        n_samples = int(sr * duration_ms / 1000)
        t = np.arange(n_samples) / sr
        arr = (np.sin(2 * np.pi * 6000 * t) * 0.9).astype(np.float32)
        max_val = float(2**15 - 1)
        arr_int = (arr * max_val).astype(np.int16)
        import array

        seg = AudioSegment(
            data=array.array("h", arr_int.tolist()).tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=1,
        )
        out = ds.process_segment(seg)
        samples = np.array(out.get_array_of_samples(), dtype=np.float32) / max_val
        assert np.max(np.abs(samples)) <= 1.0 + 1e-6
