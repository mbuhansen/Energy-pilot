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


def test_below_the_soft_floor_it_never_buys_dear_to_fill_it():
    # Already in the reserve with only dear hours left: it holds (buys for the house), it doesn't charge.
    hours = [Hour(T0 + timedelta(hours=i), 4.0, 2.0, 1.0, 0.0) for i in range(3)]
    plan = plan_battery(hours, 12, _battery(soft=15), end_value=2.0)
    assert all(s.action != "charge_grid" for s in plan.steps)
    assert all(s.soc_end >= 12 - 1e-6 for s in plan.steps)


def _ctl(first, now, soc, soft=10.0):
    from energy_pilot import control as C

    c = C.Controller.__new__(C.Controller)
    bat = Battery(capacity_kwh=45, max_charge_kw=11.85, max_discharge_kw=11.85, min_soc=5, soft_soc=soft)
    step = {"t": "2026-11-27T20:00:00+00:00", "action": first, "soc": 10, "grid": 1.2}
    c.engine = SimpleNamespace(result={"battery": {"steps": [step], "slot_min": 60, "target": 10}}, settings=lambda: bat)
    c.ov = SimpleNamespace(flow=lambda: {"soc": soc, "house": 1500, "pv": 0}, settings={"inverter_profile": "victron"}, sell_sun=lambda: False, ev=lambda: None)
    c.ha = SimpleNamespace(config={"time_zone": "UTC"})
    c.car_why = ""
    c.bat_parts = lambda: []
    c.intents()  # the first plan of the hour
    step["action"] = now  # a later plan of the same hour
    _ctl.last = c
    return c.intents()["battery"]["intent"]


def test_an_hour_planned_to_cover_the_house_runs_on_into_the_reserve():
    # The house took more than foreseen: the battery reached the soft floor early and the plan turned the rest into a hold
    assert _ctl("discharge", "hold", soc=10) == "normal"


def test_the_plan_shows_the_hour_covered_from_the_reserve():
    _ctl("discharge", "hold", soc=10)
    assert _ctl.last.reserve_slot == "2026-11-27T20:00:00+00:00"
    _ctl("hold", "hold", soc=10)
    assert _ctl.last.reserve_slot is None


def test_an_hour_planned_as_hold_keeps_the_reserve():
    assert _ctl("hold", "hold", soc=10) == "hold"


def test_at_the_real_minimum_it_holds():
    assert _ctl("discharge", "hold", soc=5) == "hold"


def test_without_a_soft_floor_nothing_changes():
    assert _ctl("discharge", "hold", soc=10, soft=0.0) == "hold"


def test_a_soft_floor_at_or_below_the_minimum_is_off():
    eng = SimpleNamespace(ov=SimpleNamespace(settings={"battery_soft_min": 10}))
    assert Engine.soft_floor(eng, 10.0) == 0.0
    assert Engine.soft_floor(eng, 5.0) == 10.0
    eng.ov.settings = {}
    assert Engine.soft_floor(eng, 5.0) == 0.0
