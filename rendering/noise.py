from __future__ import annotations

import math
import random

class SmoothNoise:
    """Fast deterministic multi-frequency smooth noise generator."""

    _FREQUENCIES = (1.0, 2.17, 4.43, 8.61, 15.7)
    _WEIGHTS = (1.0, 0.55, 0.28, 0.13, 0.06)
    _TOTAL_WEIGHT = sum(_WEIGHTS)
    _TAU = math.tau

    def __init__(self, seed: int):
        rng = random.Random(seed)
        self.phases = tuple(rng.uniform(0.0, self._TAU) for _ in range(5))
        self.offsets = tuple(rng.uniform(0.0, 1000.0) for _ in range(5))

    def sample(self, t: float, frequency: float = 1.0) -> float:
        """Sample deterministic multi-frequency smooth noise."""
        value = 0.0
        tau = self._TAU
        for phase, offset, freq, weight in zip(
            self.phases, self.offsets, self._FREQUENCIES, self._WEIGHTS
        ):
            value += math.sin(tau * (t * frequency * freq + offset) + phase) * weight
        return value / self._TOTAL_WEIGHT
