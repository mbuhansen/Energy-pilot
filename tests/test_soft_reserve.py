"""Soft reserve (Predbat's best_soc_keep): the plan keeps the battery above a soft floor, but may still use it."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from energy_pilot.engine import Battery, Engine, Hour, plan_battery

T0 = datetime(2026, 11, 27, 12, tzinfo=ZoneInfo("Europe/Copenhagen"))


def _day():
    dear = [Hour(T0 + timedelta(hours=i), 4.0, 2.0, 1.0, 0.0) for i in range(10)]
    night = [Hour(T0 + timedelta(hours=10 + i), 2.0, 1.0, 0.5, 0.0) for i in range(6)]
    return dear + night


def _battery(soft=0.0):
    return Battery(capacity_kwh=45, max_charge_kw=11.85, max_discharge_kw=11.85, min_soc=5, efficiency=0.9,
                   grid_charge=True, wear=0.133, soft_soc=soft)


def _levels(plan):
    return [s.soc_end for s in plan.steps]


def test_without_a_soft_floor_the_battery_runs_down_early():
    lv = _levels(plan_battery(_day(), 30, _battery(), end_value=2.0))
    assert min(lv[:8]) < 15


def test_the_soft_floor_is_kept_through_the_dear_hours():
    lv = _levels(plan_battery(_day(), 30, _battery(soft=15), end_value=2.0))
    assert min(lv[:8]) >= 15 - 1e-6  # kept above it while more dear hours follow


def test_the_soft_floor_is_soft():
    # Little in the battery and only dear hours left: it still uses what is below the soft floor.
    hours = [Hour(T0 + timedelta(hours=i), 4.0, 2.0, 1.0, 0.0) for i in range(2)]
    lv = _levels(plan_battery(hours, 14, _battery(soft=15), end_value=2.0))
    assert lv[-1] < 14


def test_a_soft_floor_at_or_below_the_minimum_is_off():
    eng = SimpleNamespace(ov=SimpleNamespace(settings={"battery_soft_min": 10}))
    assert Engine.soft_floor(eng, 10.0) == 0.0
    assert Engine.soft_floor(eng, 5.0) == 10.0
    eng.ov.settings = {}
    assert Engine.soft_floor(eng, 5.0) == 0.0
