"""Run 20 crystals in Python and save their journeys for the website."""

from dataclasses import asdict
import json
from math import pi
from pathlib import Path
from random import Random

from model import Environment, IceCrystal, simulate_to_ground


def main():
    # Match the cloud drawn on the website: base at 2000 m, top at 3000 m.
    environment = Environment(
        cloud_base_height_m=2000.0,
        ground_height_m=0.0,
        top_height_m=3000.0,
        reference_height_m=3000.0,
        reference_temperature_k=258.15,  # -15 C, same reference as our earlier demo
        lapse_rate_k_per_m=0.0055,  # 5.5 K/km, the lapse rate used in our Yang model
        relative_humidity_water=1.0,  # water-saturated cloud, as in the existing model
    )

    # Same spherical starting crystal as model.py: 4 micrometres, density 910 kg/m3.
    radius_m = 4e-6
    ice_density_kg_m3 = 910.0

    settings = {
        "duration_s": 7200.0,  # a two-hour limit, enough for this example to reach ground
        "sample_interval_s": 10.0,  # saved frames, NOT the adaptive RK45 solver's step size
        "air_density_kg_m3": 1.0,  # fixed example value already used in model.py
        "dynamic_viscosity_pa_s": 1.65e-5,  # same fixed air viscosity as model.py
    }
    count = 20
    rng = Random(42)  # fixed seed makes this visual example reproducible
    # Start in the middle 400 m of the cloud so the particles also fit inside
    # the rounded ASCII outline on narrow screens. These are scene choices.
    heights = [2300.0 + (i + rng.random()) / count * 400.0 for i in range(count)]
    rng.shuffle(heights)
    particles = []
    for i, height_m in enumerate(heights):
        crystal = IceCrystal(
            height_m=height_m,
            mass_kg=ice_density_kg_m3 * (4.0 / 3.0) * pi * radius_m**3,
            a_m=radius_m,
            c_m=radius_m,
        )
        trajectory = simulate_to_ground(crystal, environment, **settings)
        particles.append({
            "id": f"crystal-{i + 1}",
            # Fraction across the available interior at this starting height.
            # This is display layout, not a horizontal coordinate in the model.
            "display_x_fraction": (i + 0.5) / count,
            "initial_state": asdict(crystal),
            **asdict(trajectory),
        })

    # Entries at the same index describe the same instant: time_s[i], height_m[i],
    # mass_kg[i], phase[i]. The model also saves exact cloud-exit and melting times.
    # Keep SI units here; the browser can display minutes or micrograms later.
    data = {
        "schema_version": 1,
        "environment": asdict(environment),
        "simulation": settings,
        "particles": particles,
    }

    # Vite serves public/ files directly; the browser will read /data/cloud.json.
    output = Path(__file__).resolve().parent / "web/public/data/cloud.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {count} crystal trajectories to {output}")


if __name__ == "__main__":
    main()
