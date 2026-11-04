"""Mono PCM processing and measurements, using NumPy and the standard library.

Pitch and duration editing use an STFT phase vocoder. F0 is an autocorrelation
estimate, intentionally absent on unvoiced/noisy frames; it is not a phoneme
recognizer. Original files are never overwritten by an edit.
"""
import io
import math
import wave

import numpy as np

MAX_SECONDS = 120
MAX_BYTES = 32_000_000


def finite(value, low, high, name):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: введите число") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name}: допустимо от {low} до {high}")
    return value


def decode(data):
    if len(data) > MAX_BYTES:
        raise ValueError("WAV больше 32 МБ")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate, width, channels, count = (wav.getframerate(), wav.getsampwidth(),
                                             wav.getnchannels(), wav.getnframes())
            if wav.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
                raise ValueError("Нужен несжатый PCM WAV (8/16/24/32 бит)")
            if not 4000 <= rate <= 96000 or channels not in (1, 2):
                raise ValueError("Нужен WAV 4–96 кГц, моно или стерео")
            if not 1 <= count <= rate * MAX_SECONDS:
                raise ValueError("Длительность записи должна быть от одного отсчёта до 120 с")
            raw = wav.readframes(count)
            if len(raw) != count * channels * width:
                raise ValueError("WAV содержит неполные аудиоданные")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Не удалось прочитать PCM WAV") from exc
    if width == 1:
        samples = (np.frombuffer(raw, np.uint8).astype(float) - 128) / 128
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        samples = ((v ^ 0x800000) - 0x800000) / 8388608.0
    else:
        samples = np.frombuffer(raw, "<i2" if width == 2 else "<i4").astype(float)
        samples /= 2 ** (8 * width - 1)
    return samples.reshape(-1, channels).mean(axis=1), rate, width * 8


def encode(samples, rate, bits=16):
    samples = np.asarray(samples, dtype=float)
    if not len(samples) or len(samples) > rate * MAX_SECONDS:
        raise ValueError("Результат должен иметь длительность не более 120 с и не быть пустым")
    if not np.all(np.isfinite(samples)):
        raise ValueError("Аудиоданные содержат недопустимые значения")
    samples = np.clip(samples, -1, 1)
    if bits == 8:
        pcm = np.clip(np.rint(samples * 128 + 128), 0, 255).astype(np.uint8)
    elif bits == 16:
        pcm = np.clip(np.rint(samples * 32768), -32768, 32767).astype("<i2")
    else:
        raise ValueError("Выберите 8 или 16 бит")
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, bits // 8, int(rate), 0, "NONE", "not compressed"))
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


def resample(samples, count):
    """Fourier resampling, truncating frequencies above the new Nyquist limit."""
    count = int(count)
    if count < 1:
        raise ValueError("Слишком короткий фрагмент")
    n = len(samples)
    if n == count:
        return np.array(samples, dtype=float, copy=True)
    spectrum = np.fft.rfft(samples)
    target = np.zeros(count // 2 + 1, dtype=complex)
    common = min(n, count)
    target[:common // 2 + 1] = spectrum[:common // 2 + 1]
    if common % 2 == 0:
        if count < n:
            target[common // 2] *= 2
        elif n < count:
            target[common // 2] *= .5
    return np.fft.irfft(target, n=count) * count / n


def bounds(samples, rate, start=0, end=None):
    duration = len(samples) / rate
    start = finite(start, 0, duration, "Начало")
    end = finite(duration if end is None else end, 0, duration + 1 / rate, "Конец")
    a, b = round(start * rate), min(len(samples), round(end * rate))
    if b <= a:
        raise ValueError("Выделите непустой фрагмент: конец должен быть позже начала")
    return a, b


def stretch(samples, factor):
    """Change duration while preserving harmonic pitch (phase vocoder)."""
    target = max(1, round(len(samples) * factor))
    if abs(factor - 1) < 1e-8:
        return samples.copy()
    if len(samples) < 128:
        raise ValueError("Для изменения длительности без изменения тона выделите более длинный фрагмент")
    size, hop = 1024, 256
    pad = size // 2
    x = np.pad(samples, (pad, size + pad))
    frames = np.lib.stride_tricks.sliding_window_view(x, size)[::hop]
    window = np.hanning(size + 1)[:-1]
    spectra = np.fft.rfft(frames * window, axis=1)
    steps = np.arange(0, len(spectra) - 1, 1 / factor)
    phase = np.angle(spectra[0])
    advance = 2 * np.pi * hop * np.arange(size // 2 + 1) / size
    out = np.zeros(size + len(steps) * hop)
    weights = np.zeros_like(out)
    for k, step in enumerate(steps):
        i, frac = int(step), step % 1
        magnitude = (1 - frac) * abs(spectra[i]) + frac * abs(spectra[i + 1])
        frame = np.fft.irfft(magnitude * np.exp(1j * phase), n=size)
        offset = k * hop
        out[offset:offset + size] += frame * window
        weights[offset:offset + size] += window ** 2
        delta = np.angle(spectra[i + 1]) - np.angle(spectra[i]) - advance
        phase += advance + (delta + np.pi) % (2 * np.pi) - np.pi
    out /= np.maximum(weights, 1e-9)
    result = out[pad:pad + target]
    return np.pad(result, (0, max(0, target - len(result))))


def join(parts, rate, gap_ms=0, fade_ms=0):
    gap = round(finite(gap_ms, 0, 2000, "Пауза, мс") * rate / 1000)
    fade = round(finite(fade_ms, 0, 100, "Склейка, мс") * rate / 1000)
    if not parts:
        raise ValueError("Добавьте фрагменты в монтаж")
    if sum(len(p) + gap for p in parts) > rate * MAX_SECONDS:
        raise ValueError("Собранная фраза длиннее 120 с")
    result = parts[0].copy()
    for part in parts[1:]:
        if gap:
            result = np.concatenate((result, np.zeros(gap), part))
        else:
            overlap = min(fade, len(result) // 2, len(part) // 2)
            if overlap:
                ramp = np.linspace(0, 1, overlap)
                blend = result[-overlap:] * (1 - ramp) + part[:overlap] * ramp
                result = np.concatenate((result[:-overlap], blend, part[overlap:]))
            else:
                result = np.concatenate((result, part))
    return result


def process(samples, rate, operation, params):
    a, b = bounds(samples, rate, params.get("start", 0), params.get("end"))
    selected = samples[a:b].copy()
    if operation == "crop":
        return selected, rate
    if operation == "remove":
        result = np.concatenate((samples[:a], samples[b:]))
    elif operation == "repeat":
        times = int(finite(params.get("times", 20), 2, 1000, "Число повторов"))
        if len(selected) * times > rate * MAX_SECONDS:
            raise ValueError("Повтор длиннее 120 с")
        return np.tile(selected, times), rate
    elif operation == "resample":
        new_rate = int(finite(params.get("rate", 16000), 4000, 48000, "Частота дискретизации"))
        return resample(selected, round(len(selected) * new_rate / rate)), new_rate
    elif operation == "gain":
        gains = [finite(params.get(key, 0), -40, 18, "Усиление, дБ")
                 for key in ("gain_start", "gain_mid", "gain_end")]
        selected *= 10 ** (np.interp(np.linspace(0, 1, len(selected)), [0, .5, 1], gains) / 20)
        result = np.concatenate((samples[:a], selected, samples[b:]))
    elif operation == "stretch":
        factor = finite(params.get("factor", 1), .5, 2, "Множитель длительности")
        if len(samples) + len(selected) * (factor - 1) > rate * MAX_SECONDS:
            raise ValueError("Результат длиннее 120 с")
        result = np.concatenate((samples[:a], stretch(selected, factor), samples[b:]))
    elif operation == "pitch":
        semitones = finite(params.get("semitones", 0), -12, 12, "Полутона")
        ratio = 2 ** (semitones / 12)
        shifted = resample(stretch(selected, ratio), len(selected))
        result = np.concatenate((samples[:a], shifted, samples[b:]))
    elif operation in ("bend", "pitch_contour"):
        tones = [finite(params.get(key, 0), -12, 12, "Полутона")
                 for key in ("pitch_start", "pitch_mid", "pitch_end")]
        # Integrate output time over the input timeline; interpolate the inverse.
        speed = 2 ** (np.interp(np.linspace(0, 1, len(selected)), [0, .5, 1], tones) / 12)
        timeline = np.cumsum(1 / speed) - 1 / speed[0]
        changed = np.interp(np.arange(max(1, round(float(timeline[-1] + 1 / speed[-1])))),
                            timeline, selected)
        if operation == "pitch_contour":
            changed = stretch(changed, len(selected) / len(changed))
        result = np.concatenate((samples[:a], changed, samples[b:]))
    else:
        raise ValueError("Неизвестное преобразование")
    if not len(result) or len(result) > rate * MAX_SECONDS:
        raise ValueError("Результат пустой или длиннее 120 с")
    return result, rate


def analyze(samples, rate, start=0, end=None):
    a, b = bounds(samples, rate, start, end)
    x = samples[a:b]
    hop, frame_size = max(1, rate // 100), max(32, round(rate * .04))
    # Limit expensive F0 work to at most 600 frames, retaining timestamps.
    stride = max(hop, int(np.ceil(max(1, len(x) - frame_size) / 599)))
    times, energy, f0 = [], [], []
    offsets = list(range(0, max(1, len(x) - frame_size + 1), stride))
    frame_energy = [float(np.sqrt(np.mean(x[o:o + frame_size] ** 2))) for o in offsets]
    low, high = np.quantile(frame_energy, [.15, .9])
    # Only estimate a noise floor when the recording actually contains pauses.
    voicing_floor = max(.005, float(low) * 1.5) if high > low * 2 else .005
    for offset, rms in zip(offsets, frame_energy):
        frame = x[offset:offset + frame_size]
        window = np.hanning(len(frame))
        centered = (frame - np.mean(frame)) * window
        nfft = 1 << (2 * len(frame) - 1).bit_length()
        spectrum = np.fft.rfft(centered, n=nfft)
        corr = np.fft.irfft(abs(spectrum) ** 2, n=nfft)[:len(frame)]
        # Compensate Hann's decreasing overlap. Otherwise low voices are biased
        # toward short boundary lags instead of a true periodicity maximum.
        window_corr = np.fft.irfft(abs(np.fft.rfft(window, n=nfft)) ** 2, n=nfft)[:len(frame)]
        corr /= np.maximum(window_corr / max(window_corr[0], 1e-10), 1e-4)
        lo, hi = max(2, rate // 500), min(len(frame) - 2, rate // 60)
        pitch = None
        if hi > lo and rms > voicing_floor and corr[0] > 1e-10:
            candidates = np.arange(lo, hi + 1)
            peaks = candidates[(corr[candidates] > corr[candidates - 1]) &
                               (corr[candidates] >= corr[candidates + 1])]
            if len(peaks):
                best = float(np.max(corr[peaks]))
                strong = peaks[corr[peaks] >= max(.55 * corr[0], .9 * best)]
                if len(strong):
                    lag = int(strong[0])
                    denom = corr[lag - 1] - 2 * corr[lag] + corr[lag + 1]
                    offset_lag = .5 * (corr[lag - 1] - corr[lag + 1]) / denom if abs(denom) > 1e-12 else 0
                    hz = rate / (lag + np.clip(offset_lag, -.5, .5))
                    if 60 <= hz <= 500:
                        pitch = round(float(hz), 2)
        times.append(round((a + offset + len(frame) / 2) / rate, 5))
        energy.append(round(rms, 6))
        f0.append(pitch)
    # Reject isolated pitch guesses in noise; real voiced spans have neighbours.
    f0 = [v if v is not None and any(
        other is not None and .8 <= other / v <= 1.25
        for j, other in enumerate(f0[max(0, i-2):i+3], max(0, i-2)) if j != i)
        else None for i, v in enumerate(f0)]
    # Min/max bins preserve narrow impulses when zoomed out.
    edges = np.linspace(0, len(x), min(1400, len(x)) + 1, dtype=int)
    lows, highs = [], []
    for left, right in zip(edges[:-1], edges[1:]):
        lows.append(round(float(np.min(x[left:right])), 6))
        highs.append(round(float(np.max(x[left:right])), 6))
    peak = float(np.max(abs(x)))
    return {"start": a / rate, "end": b / rate, "duration": len(x) / rate,
            "peak": peak, "rms": float(np.sqrt(np.mean(x ** 2))),
            "clipped_percent": float(np.mean(abs(x) >= .999) * 100),
            "wave": {"low": lows, "high": highs}, "times": times,
            "energy": energy, "f0": f0,
            "median_f0": float(np.median([v for v in f0 if v is not None]))
            if any(v is not None for v in f0) else None}
