"""The simulation is pure Python, so it is tested directly with tiny examples."""

import pytest

from app.battery import ROUND_TRIP_EFFICIENCY, hourly_consumption, simulate


def test_consumption_adds_up_to_the_yearly_use():
    hours = hourly_consumption(3000, 2023)
    assert len(hours) == 8760
    assert sum(hours) == pytest.approx(3000)


def test_consumption_has_an_evening_peak_and_more_use_in_winter():
    hours = hourly_consumption(3000, 2023)
    # 18:00 UTC = 19:00 local (evening) vs 02:00 UTC = 03:00 local (night), 1 January
    assert hours[18] > hours[2]
    january, july = sum(hours[: 31 * 24]), sum(hours[181 * 24 : 212 * 24])
    assert january > july


def test_without_battery_solar_goes_to_house_first():
    # Two hours: sunny with low use, then dark with use.
    result = simulate([3.0, 0.0], [1.0, 2.0], capacity_kwh=0)
    assert result["selfUsedKwh"] == 1.0
    assert result["gridExportKwh"] == 2.0
    assert result["gridImportKwh"] == 2.0


def test_battery_moves_daytime_surplus_to_the_evening():
    result = simulate([3.0, 0.0], [1.0, 2.0], capacity_kwh=10)
    # 2 kWh surplus, but the battery charges at most 5 kW and loses 10 %.
    stored = 2.0 * ROUND_TRIP_EFFICIENCY  # 1.8 kWh
    assert result["selfUsedKwh"] == round(1.0 + stored, 1)
    assert result["gridExportKwh"] == 0.0
    assert result["gridImportKwh"] == round(2.0 - stored, 1)


def test_battery_capacity_is_a_limit():
    result = simulate([10.0, 0.0], [0.0, 10.0], capacity_kwh=2)
    # Charge power 1 kW (C-rate 0.5) limits it first: only 1 kWh in, 0.9 stored.
    assert result["selfUsedKwh"] == 0.9


def test_energy_balance_holds():
    production = [max(0.0, 4 - abs(12 - h % 24)) for h in range(24 * 7)]
    consumption = [0.5 + (1 if 17 <= h % 24 <= 21 else 0) for h in range(24 * 7)]
    for capacity in (0, 5, 13.5):
        r = simulate(production, consumption, capacity)
        # Everything the house used came from solar or the grid.
        assert r["selfUsedKwh"] + r["gridImportKwh"] == pytest.approx(sum(consumption), abs=0.2)
        assert r["selfUsedKwh"] <= sum(production)


def test_zero_capacity_equals_no_battery():
    p, c = [1.0, 0.0, 2.0], [0.5, 1.0, 1.0]
    assert simulate(p, c, 0) == simulate(p, c, 0.0)
