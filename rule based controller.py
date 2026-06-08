import numpy as np
from dataclasses import dataclass
from typing import Tuple


@dataclass
class ControllerConfig:
    T_target: float = 22.0    # °C desired temperature
    T_min: float = 20.0       # °C comfort minimum
    T_max: float = 25.0       # °C comfort maximum
    hysteresis: float = 0.5   # °C hysteresis band


class RuleBasedController:
    """
    Simple threshold-based fan controller.
    Fan turns ON (inject cool air) when inside > T_max AND outside < inside.
    Fan turns OFF when inside < T_min OR outside > inside.
    """

    def __init__(self, T_min: float = 20.0, T_max: float = 25.0,
                 hysteresis: float = 0.5):
        self.T_min = T_min
        self.T_max = T_max
        self.hysteresis = hysteresis
        self._fan_on = False

    def compute(self, T_inside: float, T_outside: float,
                time_s: float) -> Tuple[float, int]:
        """
        Returns (fan_speed [0..1], fan_direction [-1|0|1]).
        """
        too_hot = T_inside > self.T_max
        outside_cooler = T_outside < (T_inside - self.hysteresis)
        inside_comfortable = T_inside <= self.T_min + self.hysteresis

        if too_hot and outside_cooler:
            self._fan_on = True
        if inside_comfortable or (T_outside >= T_inside):
            self._fan_on = False

        if self._fan_on:
            # Scale speed proportional to how hot it is above T_max
            excess = T_inside - self.T_max
            speed = min(1.0, 0.3 + 0.14 * excess)
            direction = 1  # inject outside air
        else:
            speed = 0.0
            direction = 0

        return speed, direction


class PIDController:
    """
    PID controller that drives indoor temperature toward T_target.
    Positive error (T_inside > T_target) → increase fan speed to cool.
    """

    def __init__(self, T_target: float = 22.0,
                 Kp: float = 0.1, Ki: float = 0.005, Kd: float = 0.02,
                 T_min: float = 20.0, T_max: float = 25.0):
        self.T_target = T_target
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.T_min = T_min
        self.T_max = T_max
        self._integral = 0.0
        self._prev_error = 0.0

    def compute(self, T_inside: float, T_outside: float,
                time_s: float) -> Tuple[float, int]:
        error = T_inside - self.T_target  # positive = too hot
        self._integral = np.clip(self._integral + error, -10.0, 10.0)
        derivative = error - self._prev_error
        self._prev_error = error

        u = self.Kp * error + self.Ki * self._integral + self.Kd * derivative

        # Only run fan when outside is cooler than inside
        if T_outside >= T_inside - 0.5:
            return 0.0, 0

        speed = float(np.clip(u, 0.0, 1.0))
        direction = 1 if speed > 0 else 0
        return speed, direction

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0


class PredictiveController:
    """
    Simplified Model Predictive Controller (MPC).
    Uses a weather forecast horizon to pre-cool the building during
    the coldest overnight window before the predicted daytime peak.

    Strategy:
    - Forecast the next 24h temperatures
    - Identify the coolest window (typically 2–6 AM)
    - Pre-cool aggressively during that window (charge thermal mass)
    - Coast through daytime with fan OFF or minimal
    - Engage fan at high speed when T_inside approaches T_max
    """

    def __init__(self, weather_forecast_fn,
                 T_target: float = 22.0,
                 T_min: float = 20.0, T_max: float = 25.0,
                 pre_cool_margin: float = 1.5,
                 horizon_hours: float = 24.0, dt: float = 3600.0):
        self.forecast = weather_forecast_fn
        self.T_target = T_target
        self.T_min = T_min
        self.T_max = T_max
        self.pre_cool_margin = pre_cool_margin
        self.horizon_hours = horizon_hours
        self.dt = dt

    def _get_forecast(self, current_time_s: float) -> np.ndarray:
        times = np.arange(current_time_s,
                          current_time_s + self.horizon_hours * 3600,
                          self.dt)
        return np.array([self.forecast(t) for t in times])

    def _is_pre_cool_window(self, current_time_s: float) -> bool:
        """True if now is within the coldest 4-hour window in forecast."""
        forecast = self._get_forecast(current_time_s)
        min_idx = int(np.argmin(forecast))
        window_start = max(0, min_idx - 2)
        window_end = min(len(forecast) - 1, min_idx + 2)
        # Check if current time is in that window
        return window_start <= 0 <= window_end  # simplified: check if min is near now

    def compute(self, T_inside: float, T_outside: float,
                time_s: float) -> Tuple[float, int]:
        forecast = self._get_forecast(time_s)
        T_forecast_max = float(np.max(forecast[:12]))  # next 12h peak
        T_forecast_min = float(np.min(forecast[:12]))

        emergency_cool = T_inside > self.T_max
        outside_cooler = T_outside < T_inside - 0.5

        # Pre-cooling: if next 12h will be hot and tonight is cold
        pre_cool = (T_forecast_max > self.T_max and
                    T_outside < self.T_target - self.pre_cool_margin and
                    T_inside > self.T_min + 0.3)

        if emergency_cool and outside_cooler:
            excess = T_inside - self.T_max
            speed = min(1.0, 0.5 + 0.1 * excess)
            return speed, 1

        if pre_cool and outside_cooler:
            speed = 0.7
            return speed, 1

        if T_inside > self.T_target and outside_cooler:
            speed = 0.3
            return speed, 1

        return 0.0, 0


if __name__ == "__main__":
    ctrl = RuleBasedController(T_min=20.0, T_max=25.0)
    speed, direction = ctrl.compute(T_inside=27.0, T_outside=18.0, time_s=3600 * 14)
    print(f"Fan speed: {speed:.2f}, direction: {direction}")
