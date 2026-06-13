# Intelligent Fan Air Cooling System

> An AI-driven fan cooling system that reduces or eliminates the need for air conditioning — saving energy, cutting costs, and reducing carbon emissions.
## Overview

Air conditioners consume ~6% of all US electricity (~$29B/year) and emit ~117 million metric tons of CO₂ annually. This project designs an **intelligent fan-based cooling system** using:

- Physics-based **thermal building simulation** (Simulink/Simscape + Python)
- **Predictive control** using weather forecasts
- **Energy analytics** comparing fan vs. AC systems
- **Arduino prototype** for real-world validation

## System Components

### Part 1 — Thermal Building Model
- Convective heat transfer (airflow via drafts, fans)
- Conductive heat transfer (walls, windows, doors)
- Capacitive thermal mass (furniture, concrete, etc.)

### Part 2 — Fan Device Model
- Extractor fan or twin-fan physics model
- Airflow rate as a function of fan speed and pressure differential
- Parameterized & calibrated against measured data

### Part 3 — Intelligent Control System
- Temperature sensors (inside + outside)
- PID baseline controller
- Model Predictive Controller (MPC) using weather forecasts
- User-configurable comfort range (temp min/max, humidity)

## Getting Started

### Prerequisites
- Python 3.10+
- MATLAB R2023a+ with Simulink & Simscape (for `.slx` models)
- Arduino IDE (for prototype)

### Installation

```bash
git clone https://github.com/your-org/intelligent-fan-cooling.git
cd intelligent-fan-cooling
pip install -r requirements.txt
```

### Run the Simulation

```bash
python src/simulation/building_model.py --config data/config.json
```

### Run the Control System

```bash
python src/control/predictive_controller.py \
  --location "New York" \
  --target-temp 22 \
  --temp-min 20 \
  --temp-max 26
```
## Results & Impact

| Metric | Fan System | Traditional AC |
|--------|-----------|----------------|
| Energy Use (kWh/day) | ~0.5 | ~15–30 |
| Annual Cost (USD) | ~$15 | ~$500 |
| CO₂ Emissions | Minimal | High |
| Effectiveness | Climate-dependent | Universal |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE)
## References

1. IEA (2018), *The Future of Cooling*, IEA, Paris
2. US Department of Energy, Air Conditioning Overview
3. Simulink Thermal Model of a House
4. Simscape House Heating System
5. Building and HVAC Simulation in MATLAB/Simulink — FFG Project SaLüH!
