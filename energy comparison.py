import json
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class EnergyReport:
    system_name: str
    total_energy_kwh: float
    annual_cost_usd: float
    co2_kg: float
    hours_in_comfort: float
    total_hours: float
    comfort_pct: float
    avg_temp: float
    peak_temp: float

    def __str__(self):
        return (
            f"\n{'='*50}\n"
            f"  System: {self.system_name}\n"
            f"{'='*50}\n"
            f"  Energy used:       {self.total_energy_kwh:.2f} kWh\n"
            f"  Annual cost (est): ${self.annual_cost_usd:.2f}\n"
            f"  CO₂ emitted:       {self.co2_kg:.2f} kg\n"
            f"  Comfort time:      {self.comfort_pct:.1f}%\n"
            f"  Avg indoor temp:   {self.avg_temp:.1f}°C\n"
            f"  Peak indoor temp:  {self.peak_temp:.1f}°C\n"
        )


class ACBaseline:
    """
    Simple AC model: maintains T_target by consuming energy proportional
    to the cooling load (outside temp - T_target) when outside is hotter.
    COP (Coefficient of Performance) ≈ 3.0 for modern AC.
    """

    def __init__(self, T_target: float = 22.0, COP: float = 3.0,
                 capacity_kw: float = 3.5):
        self.T_target = T_target
        self.COP = COP
        self.capacity_kw = capacity_kw

    def simulate(self, outdoor_temps: list[float], dt_h: float = 1.0,
                 building_ua: float = 50.0) -> dict:
        """Simulate AC energy use over a temperature profile."""
        energy_kwh = 0.0
        indoor_temps = []
        T_inside = self.T_target

        for T_out in outdoor_temps:
            Q_load_w = building_ua * max(0.0, T_out - self.T_target)
            Q_ac_w = min(Q_load_w, self.capacity_kw * 1000)
            power_w = Q_ac_w / self.COP
            energy_kwh += power_w * dt_h / 1000.0
            # Simplified: AC keeps temp at target when running
            T_inside = self.T_target if Q_ac_w >= Q_load_w else (
                T_inside + (Q_load_w - Q_ac_w) * dt_h * 3600 / (50_000)
            )
            indoor_temps.append(T_inside)

        return {"energy_kwh": energy_kwh, "indoor_temps": indoor_temps}


class EnergyAnalyzer:
    """Compare fan system vs AC across multiple scenarios."""

    ELECTRICITY_PRICE_USD_KWH = 0.13    # US average 2024
    CO2_KG_PER_KWH = 0.386             # US grid average kg CO₂/kWh
    DAYS_PER_YEAR_COOLING = 120         # Summer season

    def __init__(self, T_min: float = 20.0, T_max: float = 25.0):
        self.T_min = T_min
        self.T_max = T_max

    def analyze_fan_simulation(self, history: list,
                               simulation_days: float = 3.0) -> EnergyReport:
        """Analyze results from a building simulation run."""
        temps = [s.T_inside for s in history]
        total_hours = simulation_days * 24
        dt_h = total_hours / len(temps)

        total_energy_kwh = history[-1].energy_used_wh / 1000.0
        annual_kwh = total_energy_kwh / simulation_days * self.DAYS_PER_YEAR_COOLING

        in_comfort = sum(1 for t in temps if self.T_min <= t <= self.T_max)
        comfort_pct = 100.0 * in_comfort / len(temps)

        return EnergyReport(
            system_name="Intelligent Fan System",
            total_energy_kwh=annual_kwh,
            annual_cost_usd=annual_kwh * self.ELECTRICITY_PRICE_USD_KWH,
            co2_kg=annual_kwh * self.CO2_KG_PER_KWH,
            hours_in_comfort=comfort_pct * total_hours / 100,
            total_hours=total_hours,
            comfort_pct=comfort_pct,
            avg_temp=float(np.mean(temps)),
            peak_temp=float(np.max(temps)),
        )

    def analyze_ac_baseline(self, outdoor_temps: list[float],
                            building_ua: float = 50.0,
                            simulation_days: float = 3.0) -> EnergyReport:
        ac = ACBaseline()
        result = ac.simulate(outdoor_temps, dt_h=1.0, building_ua=building_ua)
        temps = result["indoor_temps"]
        total_hours = len(outdoor_temps)

        energy_per_season_kwh = result["energy_kwh"] / simulation_days * self.DAYS_PER_YEAR_COOLING
        in_comfort = sum(1 for t in temps if self.T_min <= t <= self.T_max)

        return EnergyReport(
            system_name="Traditional Air Conditioner",
            total_energy_kwh=energy_per_season_kwh,
            annual_cost_usd=energy_per_season_kwh * self.ELECTRICITY_PRICE_USD_KWH,
            co2_kg=energy_per_season_kwh * self.CO2_KG_PER_KWH,
            hours_in_comfort=float(in_comfort),
            total_hours=float(total_hours),
            comfort_pct=100.0 * in_comfort / max(1, len(temps)),
            avg_temp=float(np.mean(temps)),
            peak_temp=float(np.max(temps)),
        )

    def print_comparison(self, fan_report: EnergyReport, ac_report: EnergyReport):
        print(fan_report)
        print(ac_report)
        energy_saving = ac_report.total_energy_kwh - fan_report.total_energy_kwh
        cost_saving = ac_report.annual_cost_usd - fan_report.annual_cost_usd
        co2_saving = ac_report.co2_kg - fan_report.co2_kg
        print(f"\n{'='*50}")
        print(f"  SAVINGS (Fan vs AC):")
        print(f"  Energy saved:  {energy_saving:.1f} kWh/year")
        print(f"  Cost saved:    ${cost_saving:.2f}/year")
        print(f"  CO₂ saved:     {co2_saving:.1f} kg/year")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    # Mock outdoor temperatures for 3-day period (hourly)
    hours = np.arange(0, 72)
    outdoor_temps = [18.0 + 9.0 * np.sin(2 * np.pi * (h - 8) / 24.0) for h in hours]

    analyzer = EnergyAnalyzer()
    ac_report = analyzer.analyze_ac_baseline(outdoor_temps, simulation_days=3.0)
    print(ac_report)
