"""AIMD-based rate controller for soak testing.

Implements Additive Increase / Multiplicative Decrease (AIMD) algorithm
to adapt request rate based on throttle detection:

- On success: additive increase (slowly ramp up)
- On throttle: multiplicative decrease (quickly back off)

This is the same algorithm used in TCP congestion control.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RateControllerConfig:
    """Configuration for the rate controller.

    Attributes:
        initial_rate: Starting rate (requests per second).
        min_rate: Minimum rate floor.
        max_rate: Maximum rate ceiling.
        additive_increase: How much to add on success (per stable period).
        multiplicative_decrease: Factor to multiply on throttle (e.g., 0.5 = halve).
        stability_window: Seconds of stability before increasing rate.
        cooldown_seconds: Minimum seconds between rate changes.
    """

    initial_rate: float = 1.0
    min_rate: float = 0.1
    max_rate: float = 10.0
    additive_increase: float = 0.1  # Add 0.1 req/s per stable window
    multiplicative_decrease: float = 0.5  # Halve on throttle
    stability_window: float = 10.0  # 10 seconds of stability to increase
    cooldown_seconds: float = 5.0  # Min 5 seconds between changes


@dataclass
class RateChange:
    """Record of a rate change event."""

    timestamp: str
    old_rate: float
    new_rate: float
    reason: str  # "throttle", "stability", "manual"
    iteration: Optional[int] = None


@dataclass
class RateController:
    """AIMD-based rate controller.

    Tracks throttle events and adjusts rate accordingly.
    """

    config: RateControllerConfig = field(default_factory=RateControllerConfig)
    current_rate: float = field(default=1.0)
    last_throttle_time: Optional[float] = None
    last_rate_change_time: Optional[float] = None
    last_stable_since: Optional[float] = None
    history: list[RateChange] = field(default_factory=list)
    _initialized: bool = False

    def __post_init__(self) -> None:
        if not self._initialized:
            self.current_rate = self.config.initial_rate
            self._initialized = True

    @property
    def interval_seconds(self) -> float:
        """Calculate interval between requests based on current rate."""
        if self.current_rate <= 0:
            return float("inf")
        return 1.0 / self.current_rate

    def record_success(self, iteration: Optional[int] = None) -> None:
        """Record a successful iteration (no throttle).

        May increase rate if stable for long enough.
        """
        now = time.monotonic()

        # Start stability tracking if not already
        if self.last_stable_since is None:
            self.last_stable_since = now
            return

        # Check if we've been stable long enough to increase
        stable_duration = now - self.last_stable_since

        if stable_duration >= self.config.stability_window:
            # Check cooldown
            if self.last_rate_change_time is not None:
                if now - self.last_rate_change_time < self.config.cooldown_seconds:
                    return

            # Increase rate
            old_rate = self.current_rate
            self.current_rate = min(
                self.current_rate + self.config.additive_increase,
                self.config.max_rate,
            )

            if self.current_rate != old_rate:
                self._record_change(old_rate, self.current_rate, "stability", iteration)
                self.last_rate_change_time = now
                # Reset stability window
                self.last_stable_since = now

    def record_throttle(self, iteration: Optional[int] = None) -> None:
        """Record a throttle event.

        Immediately decreases rate (multiplicative decrease).
        """
        now = time.monotonic()
        self.last_throttle_time = now
        self.last_stable_since = None  # Reset stability tracking

        # Check cooldown (but throttles are more urgent)
        if self.last_rate_change_time is not None:
            if now - self.last_rate_change_time < self.config.cooldown_seconds / 2:
                # Shorter cooldown for throttles - we want to back off quickly
                return

        # Decrease rate
        old_rate = self.current_rate
        self.current_rate = max(
            self.current_rate * self.config.multiplicative_decrease,
            self.config.min_rate,
        )

        if self.current_rate != old_rate:
            self._record_change(old_rate, self.current_rate, "throttle", iteration)
            self.last_rate_change_time = now

    def set_rate(self, rate: float, reason: str = "manual") -> None:
        """Manually set the rate."""
        old_rate = self.current_rate
        self.current_rate = max(min(rate, self.config.max_rate), self.config.min_rate)

        if self.current_rate != old_rate:
            self._record_change(old_rate, self.current_rate, reason, None)
            self.last_rate_change_time = time.monotonic()

    def reset(self) -> None:
        """Reset controller to initial state."""
        self.current_rate = self.config.initial_rate
        self.last_throttle_time = None
        self.last_rate_change_time = None
        self.last_stable_since = None
        self.history.clear()

    def _record_change(
        self,
        old_rate: float,
        new_rate: float,
        reason: str,
        iteration: Optional[int],
    ) -> None:
        """Record a rate change in history."""
        self.history.append(
            RateChange(
                timestamp=datetime.now(timezone.utc).isoformat(),
                old_rate=old_rate,
                new_rate=new_rate,
                reason=reason,
                iteration=iteration,
            )
        )

    def get_stats(self) -> dict:
        """Get controller statistics."""
        throttle_count = sum(1 for h in self.history if h.reason == "throttle")
        increase_count = sum(1 for h in self.history if h.reason == "stability")

        return {
            "current_rate": self.current_rate,
            "interval_seconds": self.interval_seconds,
            "total_adjustments": len(self.history),
            "throttle_decreases": throttle_count,
            "stability_increases": increase_count,
            "min_rate_hit": self.current_rate <= self.config.min_rate,
            "max_rate_hit": self.current_rate >= self.config.max_rate,
        }


def create_rate_controller(
    initial_rate: float = 1.0,
    min_rate: float = 0.1,
    max_rate: float = 10.0,
) -> RateController:
    """Create a rate controller with common defaults."""
    config = RateControllerConfig(
        initial_rate=initial_rate,
        min_rate=min_rate,
        max_rate=max_rate,
    )
    return RateController(config=config)
