from __future__ import annotations
import math
import random
import numpy as np

class SmoothNoise:
    """Deterministic multi-frequency smooth noise with scalar and batch sampling."""
    _FREQUENCIES = (1.0, 2.17, 4.43, 8.61, 15.7)
    _WEIGHTS = (1.0, 0.55, 0.28, 0.13, 0.06)
    _TOTAL_WEIGHT = sum(_WEIGHTS)
    _TAU = math.tau

    def __init__(self, seed: int):
        rng = random.Random(seed)
        self.phases = tuple(rng.uniform(0.0, self._TAU) for _ in range(5))
        self.offsets = tuple(rng.uniform(0.0, 1000.0) for _ in range(5))

    def sample(self, t: float, frequency: float = 1.0) -> float:
        value = 0.0
        for phase, offset, freq, weight in zip(self.phases, self.offsets, self._FREQUENCIES, self._WEIGHTS):
            value += math.sin(self._TAU * (t * frequency * freq + offset) + phase) * weight
        return value / self._TOTAL_WEIGHT

    def sample_array(self, t: np.ndarray, frequency: float = 1.0) -> np.ndarray:
        t = np.asarray(t, dtype=np.float32)
        freqs = np.asarray(self._FREQUENCIES, dtype=np.float32)[:, None]
        weights = np.asarray(self._WEIGHTS, dtype=np.float32)[:, None]
        phases = np.asarray(self.phases, dtype=np.float32)[:, None]
        offsets = np.asarray(self.offsets, dtype=np.float32)[:, None]
        return (np.sin(self._TAU * (t[None, :] * frequency * freqs + offsets) + phases) * weights).sum(axis=0) / self._TOTAL_WEIGHT
