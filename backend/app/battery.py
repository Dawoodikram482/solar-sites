"""Household consumption model and the hour-by-hour battery simulation.

Pure functions only (no database, no HTTP), so they are easy to test and easy
to reason about.

THE CONSUMPTION ASSUMPTION (also in the README)
-----------------------------------------------
PVGIS gives production, not consumption. We need consumption per hour,
because what matters is whether the sun shines *while* the house uses power.
The advisor enters only one number: the client's yearly use in kWh (it is on
every energy bill). We spread it over the 8760 hours of the year with:

  - a fixed daily shape: low at night, a morning bump, a big evening peak
    (cooking, lights, TV) — the typical shape of a Dutch household;
  - a monthly factor: more in winter (lighting, more time indoors), less in
    summer.

The numbers are a simplified, hand-made approximation of that shape, not
measured data. They are scaled so the year adds up exactly to the yearly use
the advisor entered. Why this is good enough: the result we care about (how
much solar is used at home) depends mostly on "is use high during the day or
in the evening", and this shape captures that. Better: the official Dutch
standard profiles (NEDU) or the client's own smart-meter data.
"""

from datetime import date, timedelta

# Relative use per local clock hour 0..23 (only the proportions matter).
DAILY_SHAPE = [
    0.50, 0.40, 0.35, 0.35, 0.35, 0.40,  # 00-05 night: fridge, standby
    0.60, 0.90, 1.00, 0.80, 0.70, 0.70,  # 06-11 morning bump
    0.75, 0.70, 0.65, 0.70, 0.90, 1.30,  # 12-17 day, rising toward dinner
    1.60, 1.60, 1.40, 1.20, 0.90, 0.70,  # 18-23 evening peak
]

# Relative use per month, January..December.
MONTHLY_FACTOR = [1.20, 1.10, 1.05, 0.95, 0.90, 0.85, 0.85, 0.85, 0.90, 1.00, 1.10, 1.25]

# PVGIS timestamps are UTC; Dutch clocks run UTC+1 (UTC+2 in summer).
# We use +1 all year and ignore daylight saving time: a one-hour shift in
# summer barely changes the yearly totals.
UTC_OFFSET_HOURS = 1

# Battery assumptions.
ROUND_TRIP_EFFICIENCY = 0.90  # 10 % of the energy put in is lost (charge + discharge)
MAX_C_RATE = 0.5              # a 10 kWh battery charges/discharges at most 5 kW


def hourly_consumption(annual_kwh: float, year: int, hours: int = 8760) -> list[float]:
    """kWh used in each hour of the year (index 0 = 1 January 00:00 UTC)."""
    start = date(year, 1, 1)
    raw = []
    for i in range(hours):
        day = start + timedelta(days=i // 24)
        local_hour = (i % 24 + UTC_OFFSET_HOURS) % 24
        raw.append(DAILY_SHAPE[local_hour] * MONTHLY_FACTOR[day.month - 1])
    scale = annual_kwh / sum(raw)  # make the year add up to exactly annual_kwh
    return [r * scale for r in raw]


def simulate(production: list[float] | tuple[float, ...], consumption: list[float], capacity_kwh: float) -> dict:
    """Walk through the year hour by hour and keep an energy balance.

    Each hour:
      1. Solar goes straight to the house first (direct use).
      2. Left-over solar charges the battery (if there is room), the rest is
         exported to the grid.
      3. If the house needs more than the sun gives, the battery discharges;
         whatever is still missing is imported from the grid.

    With capacity_kwh = 0 this is exactly the "without battery" case, so one
    function covers both and they can never drift apart.
    """
    max_power = capacity_kwh * MAX_C_RATE  # kWh per hour = kW
    stored = 0.0  # battery state of charge in kWh; starts empty on 1 January
    self_used = grid_import = grid_export = 0.0

    for pv, load in zip(production, consumption, strict=True):
        direct = min(pv, load)
        surplus = pv - direct
        shortfall = load - direct

        # Charge: limited by the surplus, the battery's power, and free space.
        # All losses are booked on charging, for simplicity: putting in
        # 1 kWh stores 0.9 kWh.
        room = (capacity_kwh - stored) / ROUND_TRIP_EFFICIENCY
        charge = min(surplus, max_power, room)
        stored += charge * ROUND_TRIP_EFFICIENCY

        # Discharge: limited by the shortfall, the battery's power, and what is stored.
        discharge = min(shortfall, max_power, stored)
        stored -= discharge

        self_used += direct + discharge
        grid_export += surplus - charge
        grid_import += shortfall - discharge

    total_production = sum(production)
    total_consumption = sum(consumption)
    return {
        # Solar energy that ended up used in the house (directly or via the battery).
        "selfUsedKwh": round(self_used, 1),
        "gridImportKwh": round(grid_import, 1),
        "gridExportKwh": round(grid_export, 1),
        # Share of the solar production used at home.
        "selfConsumptionPercent": _percent(self_used, total_production),
        # Share of the household's use covered by its own solar.
        "selfSufficiencyPercent": _percent(self_used, total_consumption),
    }


def _percent(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole > 0 else 0.0


def battery_report(production: list[float] | tuple[float, ...], annual_use_kwh: float, capacity_kwh: float, year: int) -> dict:
    """The full answer of GET /api/sites/{id}/battery."""
    consumption = hourly_consumption(annual_use_kwh, year, hours=len(production))
    without = simulate(production, consumption, 0)
    with_battery = simulate(production, consumption, capacity_kwh)
    return {
        "productionKwh": round(sum(production), 1),
        "consumptionKwh": round(sum(consumption), 1),
        "capacityKwh": capacity_kwh,
        "year": year,
        "withoutBattery": without,
        "withBattery": with_battery,
        # What the battery adds: extra solar energy used at home per year.
        "batteryAddsKwh": round(with_battery["selfUsedKwh"] - without["selfUsedKwh"], 1),
    }
