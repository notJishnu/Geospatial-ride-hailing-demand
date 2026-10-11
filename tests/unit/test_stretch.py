"""Tests for explicitly synthetic portability and local replay helpers."""

import pytest

from stretch.kolkata_simulated import simulate_kolkata_deliveries
from stretch.replay import replay_delays


def test_kolkata_simulation_is_deterministic_and_labeled() -> None:
    first = simulate_kolkata_deliveries(rows=3, seed=7)
    second = simulate_kolkata_deliveries(rows=3, seed=7)
    assert first.equals(second)
    assert first["is_simulated"].all()
    assert (first["synthetic_duration_seconds"] > 0).all()


def test_replay_delays_scale_time() -> None:
    assert replay_delays([0.0, 10.0, 30.0], speedup=10) == [0.0, 1.0, 2.0]
    with pytest.raises(ValueError, match="positive"):
        replay_delays([0.0], speedup=0)
