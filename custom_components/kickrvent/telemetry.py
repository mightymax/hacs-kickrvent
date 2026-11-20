"""Bounded latest-value storage, freshness, sleeping and publication policy."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot:
    connected: bool = False
    active: bool | None = None
    speed: float | None = None
    power: int | None = None
    cadence: float | None = None


class Telemetry:
    """No timestamps in HA state; unchanged readings do not create state churn."""

    def __init__(self, interval: float = 5, stale_after: float = 30, sleep_after: float = 15):
        self.interval = interval
        self.stale_after = stale_after
        self.sleep_after = sleep_after
        self.values: dict[str, tuple[float, float]] = {}
        self.last_motion: float | None = None
        self.last_publish = -math.inf
        self.published = Snapshot()

    def reset(self) -> None:
        self.values.clear()
        self.last_motion = None
        # Allow the first sample from a new session to publish immediately.
        self.last_publish = -math.inf

    def ingest(self, sample: dict[str, float | int], now: float) -> None:
        for key in ("speed", "power", "cadence"):
            value = sample.get(key)
            if value is None or not math.isfinite(value):
                continue
            self.values[key] = (value, now)
            if value > 0:
                self.last_motion = now

    def snapshot(self, now: float, connected: bool) -> Snapshot:
        if not connected:
            return Snapshot()
        fresh = {
            key: val
            for key, (val, timestamp) in self.values.items()
            if now - timestamp < self.stale_after
        }
        active = (
            None
            if not fresh
            else self.last_motion is not None and now - self.last_motion < self.sleep_after
        )
        return Snapshot(
            connected=True,
            active=active,
            speed=round(fresh["speed"], 1) if "speed" in fresh else None,
            power=round(fresh["power"]) if "power" in fresh else None,
            cadence=round(fresh["cadence"], 1) if "cadence" in fresh else None,
        )

    def publish(self, now: float, connected: bool) -> Snapshot | None:
        snapshot = self.snapshot(now, connected)
        # Connection and stale transitions invalidate old readings immediately;
        # ordinary numeric changes remain limited to the configured interval.
        invalidated = any(
            getattr(self.published, key) is not None and getattr(snapshot, key) is None
            for key in ("speed", "power", "cadence", "active")
        )
        immediate = snapshot.connected != self.published.connected or invalidated
        if snapshot == self.published or (
            not immediate and now - self.last_publish < self.interval
        ):
            return None
        self.published = snapshot
        self.last_publish = now
        return snapshot
