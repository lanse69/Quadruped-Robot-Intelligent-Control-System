import pytest

from qrics.training import EpisodeSummary, calculate_metrics


def test_calculate_metrics_aggregates_episode_summaries() -> None:
    digest = calculate_metrics(
        [
            EpisodeSummary(
                success=True,
                collision=False,
                tracking_error_m=0.10,
                recovered=True,
                energy_proxy=10.0,
            ),
            EpisodeSummary(
                success=False,
                collision=True,
                tracking_error_m=0.30,
                recovered=False,
                energy_proxy=20.0,
                hard_constraint_violation_count=2,
            ),
        ]
    )

    assert digest.success_rate == 0.5
    assert digest.collision_rate == 0.5
    assert digest.tracking_error_m == pytest.approx(0.20)
    assert digest.recovery_rate == 0.5
    assert digest.energy_proxy == pytest.approx(15.0)
    assert digest.hard_constraint_violation_count == 2


def test_calculate_metrics_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="episodes must not be empty"):
        calculate_metrics([])
