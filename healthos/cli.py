from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

from .domain import Environment, Event, Goal, NutritionTrend, ReadinessInput, TrainingEnvironment
from .orchestrator import HealthOS


def demo() -> dict[str, object]:
    today = date.today()
    goals = (
        Goal("synthetic-strength", "Synthetic strength goal", 5, None, None, None, "strength"),
        Goal("synthetic-body", "Synthetic body composition goal", 3, None, None, None, "body composition"),
        Goal(
            "synthetic-endurance",
            "Synthetic endurance preparation",
            4,
            5,
            18,
            today + timedelta(days=48),
            "walking distance endurance",
        ),
    )
    env = TrainingEnvironment(
        Environment.HOME,
        frozenset({"dumbbells", "band", "step"}),
        10.0,
        available_minutes=50,
    )
    readiness = ReadinessInput(7.5, 4, 4, 2, 2, 2, resting_hr_delta_pct=1.0, hrv_delta_pct=-2.0)
    trend = NutritionTrend(21, 2350, 82.0, 80.5, 2900)
    event = Event(
        "synthetic-endurance",
        "Synthetic endurance event",
        today + timedelta(days=48),
        ("walking", "endurance"),
        distance_km=18,
    )
    result = HealthOS().next_block(
        goals=goals,
        environment=env,
        readiness=readiness,
        nutrition_trend=trend,
        event=event,
        today=today,
    )
    return {"plan": asdict(result.plan), "audit": asdict(result.audit)}


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, default=str))
