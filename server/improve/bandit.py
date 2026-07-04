"""Thompson sampling bandit for proposal ranking."""

from __future__ import annotations

import random

_ALPHA_PRIOR = 1.0
_BETA_PRIOR = 1.0
DEFAULT_K = 8
PRUNE_PROB_THRESHOLD = 0.2


class Bandit:
    """Beta-Bernoulli Thompson sampler over rule arms."""

    def __init__(self, arms: dict[str, tuple[float, float]] | None = None) -> None:
        self.arms: dict[str, list[float]] = {
            arm: [float(a), float(b)] for arm, (a, b) in (arms or {}).items()
        }
        self.holds: dict[str, int] = dict.fromkeys(self.arms, 0)
        self._rng = random.Random()

    def ensure(self, arm: str) -> None:
        if arm not in self.arms:
            self.arms[arm] = [_ALPHA_PRIOR, _BETA_PRIOR]
            self.holds[arm] = 0

    def sample(self, arm: str) -> float:
        self.ensure(arm)
        a, b = self.arms[arm]
        return float(self._rng.betavariate(max(a, 1e-3), max(b, 1e-3)))

    def select(self, candidates: list[str]) -> str | None:
        if not candidates:
            return None
        best: str | None = None
        best_draw = -1.0
        for arm in candidates:
            draw = self.sample(arm)
            if draw > best_draw:
                best_draw = draw
                best = arm
        return best

    def update(self, arm: str, reward: float) -> None:
        self.ensure(arm)
        reward = max(0.0, min(1.0, float(reward)))
        self.arms[arm][0] += reward
        self.arms[arm][1] += 1.0 - reward
        self.holds[arm] = self.holds.get(arm, 0) + 1

    def p_improve(self, arm: str) -> float:
        self.ensure(arm)
        a, b = self.arms[arm]
        denom = a + b
        return a / denom if denom > 0 else 0.0

    def prune(self, *, k: int = DEFAULT_K, threshold: float = PRUNE_PROB_THRESHOLD) -> list[str]:
        return [
            arm
            for arm in self.arms
            if self.holds.get(arm, 0) >= k and self.p_improve(arm) < threshold
        ]
