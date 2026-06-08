import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class BuildingConfig:
    """Physical parameters of the building."""
    floor_area: float = 100.0          # m²
    ceiling_height: float = 2.8        # m
    wall_u_value: float = 0.35         # W/m²K (thermal transmittance)
    window_u_value: float = 1.8        # W/m²K
    window_area: float = 12.0          # m²
    wall_area: float = 80.0            # m²
    roof_u_value: float = 0.25         # W/m²K
    roof_area: float = 100.0           # m²
    thermal_mass: float = 15_000.0     # J/K (capacitive mass: concrete, furniture)
    air_density: float = 1.2           # kg/m³
    air_specific_heat: float = 1005.0  # J/kgK
    infiltration_rate: float = 0.3     # ACH (air changes per hour, natural)
    solar_gain_coeff: float = 0.5      # SHGC for windows
    internal_heat_gain: float = 400.0  # W (occupants, appliances)


@dataclass
class FanConfig:
    """Fan system parameters."""
    max_flow_rate: float = 0.8         # m³/s at max speed
    fan_power_max: float = 150.0       # W at max speed
    num_speeds: int = 5                # discrete speed levels
    direction: str = "bidirectional"   # "extract", "inject", or "bidirectional"


@dataclass
class SimulationState:
    """Current state of the simulation."""
    time: float = 0.0
    T_inside: float = 22.0
    T_wall: float = 20.0              # Wall surface temperature
    T_mass: float = 20.0              # Thermal mass temperature
    fan_speed: float = 0.0            # 0.0 to 1.0 (fraction of max)
    fan_direction: int = 0            # -1=extract, 0=off, 1=inject
    energy_used_wh: float = 0.0


class WeatherProfile:
    """Generates outdoor temperature profiles (sinusoidal day/night model)."""

    def __init__(self, T_mean: float = 18.0, T_amplitude: float = 8.0,
                 peak_hour: float = 14.0, season_offset: float = 0.0):
        self.T_mean = T_mean
        self.T_amplitude = T_amplitude
        self.peak_hour = peak_hour
        self.season_offset = season_offset

    def get_temperature(self, time_seconds: float) -> float:
        """Return outdoor temperature at a given simulation time (seconds)."""
        hour = (time_seconds / 3600.0) % 24.0
        T_out = self.T_mean + self.T_amplitude * np.sin(
            2 * np.pi * (hour - self.peak_hour + 6) / 24.0
        ) + self.season_offset
        return T_out

    def get_solar_irradiance(self, time_seconds: float) -> float:
        """Return approximate solar irradiance W/m² (0 at night)."""
        hour = (time_seconds / 3600.0) % 24.0
        if 6 <= hour <= 20:
            irradiance = 800 * np.sin(np.pi * (hour - 6) / 14.0)
        else:
            irradiance = 0.0
        return max(0.0, irradiance)


class BuildingThermalModel:
    """
    Lumped-parameter thermal model of a single-zone building.

    Thermal network:
      T_outside --> [Conduction: walls/windows/roof] --> T_inside
      T_outside --> [Convection: fan airflow]         --> T_inside
      T_inside  --> [Coupling]                        --> T_mass (thermal mass)
      Solar gain, Internal gains --> T_inside
    """

    def __init__(self, building: BuildingConfig, fan: FanConfig,
                 weather: WeatherProfile, dt: float = 60.0):
        self.b = building
        self.f = fan
        self.w = weather
        self.dt = dt  # seconds per simulation step

        # Air thermal capacity inside building
        self.C_air = (building.floor_area * building.ceiling_height *
                      building.air_density * building.air_specific_heat)

        # Conductive heat loss coefficient (UA total) W/K
        self.UA_total = (
            building.wall_u_value * building.wall_area +
            building.window_u_value * building.window_area +
            building.roof_u_value * building.roof_area
        )

        # Infiltration conductance W/K
        vol = building.floor_area * building.ceiling_height
        self.UA_infiltration = (building.infiltration_rate / 3600.0 * vol *
                                building.air_density * building.air_specific_heat)

        # Thermal mass coupling W/K
        self.UA_mass_coupling = 50.0  # W/K (convective coupling to mass)

    def compute_fan_flow(self, state: SimulationState) -> float:
        """Compute volumetric airflow rate m³/s given fan speed fraction."""
        return self.f.max_flow_rate * state.fan_speed

    def compute_fan_power(self, state: SimulationState) -> float:
        """Fan power consumption W (cubic relationship with speed)."""
        return self.f.fan_power_max * (state.fan_speed ** 3)

    def step(self, state: SimulationState) -> SimulationState:
        """Advance simulation by one timestep dt using Euler integration."""
        t = state.time
        T_i = state.T_inside
        T_m = state.T_mass
        T_o = self.w.get_temperature(t)
        solar = self.w.get_solar_irradiance(t)

        # --- Heat flows (W) ---
        # Conduction through envelope
        Q_cond = self.UA_total * (T_o - T_i)

        # Natural infiltration
        Q_infil = self.UA_infiltration * (T_o - T_i)

        # Fan convective flow
        V_dot = self.compute_fan_flow(state)
        m_dot = V_dot * self.b.air_density  # kg/s
        if state.fan_direction == 1:   # inject cool outside air
            T_fan_in = T_o
        elif state.fan_direction == -1:  # extract inside air, draw in outside
            T_fan_in = T_o
        else:
            T_fan_in = T_i
        Q_fan = m_dot * self.b.air_specific_heat * (T_fan_in - T_i)

        # Solar gain through windows
        Q_solar = solar * self.b.window_area * self.b.solar_gain_coeff

        # Internal heat gains
        Q_internal = self.b.internal_heat_gain

        # Thermal mass exchange
        Q_mass = self.UA_mass_coupling * (T_m - T_i)

        # --- Air temperature update ---
        dT_i_dt = (Q_cond + Q_infil + Q_fan + Q_solar + Q_internal + Q_mass) / self.C_air
        T_i_new = T_i + dT_i_dt * self.dt

        # --- Thermal mass update ---
        dT_m_dt = -Q_mass / (self.b.thermal_mass)
        T_m_new = T_m + dT_m_dt * self.dt

        # --- Energy accounting ---
        fan_power = self.compute_fan_power(state)
        energy_delta = fan_power * self.dt / 3600.0  # Wh

        new_state = SimulationState(
            time=t + self.dt,
            T_inside=T_i_new,
            T_wall=(T_i_new + T_o) / 2.0,
            T_mass=T_m_new,
            fan_speed=state.fan_speed,
            fan_direction=state.fan_direction,
            energy_used_wh=state.energy_used_wh + energy_delta,
        )
        return new_state

    def run(self, duration_hours: float, controller,
            initial_state: Optional[SimulationState] = None) -> list[SimulationState]:
        """Run simulation for specified duration with a given controller."""
        state = initial_state or SimulationState(T_inside=22.0, T_mass=20.0)
        history = [state]
        steps = int(duration_hours * 3600 / self.dt)
        for _ in range(steps):
            T_out = self.w.get_temperature(state.time)
            fan_speed, fan_dir = controller.compute(state.T_inside, T_out, state.time)
            state = SimulationState(
                time=state.time,
                T_inside=state.T_inside,
                T_wall=state.T_wall,
                T_mass=state.T_mass,
                fan_speed=fan_speed,
                fan_direction=fan_dir,
                energy_used_wh=state.energy_used_wh,
            )
            state = self.step(state)
            history.append(state)
        return history


def save_results(history: list[SimulationState], path: str):
    """Save simulation results to JSON."""
    records = [
        {
            "time_h": s.time / 3600,
            "T_inside": round(s.T_inside, 3),
            "T_mass": round(s.T_mass, 3),
            "fan_speed": round(s.fan_speed, 3),
            "energy_wh": round(s.energy_used_wh, 3),
        }
        for s in history
    ]
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Saved {len(records)} records to {path}")


if __name__ == "__main__":
    from control.rule_based_controller import RuleBasedController
    weather = WeatherProfile(T_mean=20.0, T_amplitude=9.0)
    building = BuildingConfig()
    fan = FanConfig()
    model = BuildingThermalModel(building, fan, weather)
    controller = RuleBasedController(T_min=20.0, T_max=25.0)
    history = model.run(duration_hours=72, controller=controller)
    save_results(history, "data/simulation_output.json")
    final = history[-1]
    print(f"Final indoor temp: {final.T_inside:.1f}°C")
    print(f"Total fan energy: {final.energy_used_wh:.1f} Wh")
