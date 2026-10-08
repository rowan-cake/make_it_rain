"""Export 20 background crystals and one separate, fixed AgI seeding burst."""

from dataclasses import asdict
import json
from math import pi
from pathlib import Path
from random import Random

from model import (
    Cloud,
    Environment,
    IceCrystal,
    deposition_nucleation_fraction,
    saturation_vapor_pressure_ice_pa,
    simulate_to_ground,
)


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

    # One fixed example dose. These are demo inputs, not a recommended dose:
    # 35 AgI particles/cm3 = 35 million/m3; 0.001 m3 = one litre of seeded air.
    # The volume converts concentration to a particle count, not cloud geometry.
    injection = {
        "heights_m": [2100.0, 2500.0, 2650.0],
        "agi_concentration_per_m3": 35e6,
        "seeded_volume_m3": 0.001,  # total air volume shared across all three layers
    }
    seeded_cloud = Cloud(environment, [])
    layers = []
    seeded_particles = []
    # Keep the total AgI dose unchanged: use the same concentration in a third
    # of the air volume at each height. Round the ice count separately per layer.
    layer_volume_m3 = injection["seeded_volume_m3"] / len(injection["heights_m"])
    for height_m in injection["heights_m"]:
        layer_injection = {
            "height_m": height_m,
            "agi_concentration_per_m3": injection["agi_concentration_per_m3"],
            "seeded_volume_m3": layer_volume_m3,
        }
        crystals = seeded_cloud.seed(**layer_injection)

        # Each layer gets its own local conditions and Yang Eq. (1) fraction.
        # Cloud.seed() performs the actual nucleation calculation above.
        temperature_k = environment.temperature_k(height_m)
        saturation_ratio = (
            environment.vapor_pressure_pa(height_m)
            / saturation_vapor_pressure_ice_pa(temperature_k)
        )
        fraction = deposition_nucleation_fraction(temperature_k, saturation_ratio)
        agi_count = injection["agi_concentration_per_m3"] * layer_volume_m3
        layers.append({
            "injection": layer_injection,
            "temperature_k": temperature_k,
            "ice_saturation_ratio": saturation_ratio,
            "nucleation_fraction": fraction,
            "agi_particle_count": agi_count,
            "expected_crystal_count": fraction * agi_count,
            "crystal_count": len(crystals),
        })
        for i, crystal in enumerate(crystals):
            seeded_particles.append({
                "id": f"seeded-{len(seeded_particles) + 1}",
                "display_x_fraction": (i + 0.5) / len(crystals),
                "initial_state": asdict(crystal),
            })

    # Every layer starts at time zero together. Different starting heights now
    # produce different growth and fall histories, using the existing physics.
    for particle, trajectory in zip(seeded_particles, seeded_cloud.simulate(**settings)):
        particle.update(asdict(trajectory))
    seeded_count = len(seeded_particles)
    seeding_burst = {
        "injection": injection,
        "layers": layers,
        "agi_particle_count": sum(layer["agi_particle_count"] for layer in layers),
        "expected_crystal_count": sum(layer["expected_crystal_count"] for layer in layers),
        "crystal_count": seeded_count,
        # Start these clocks when the button is clicked. Each burst runs
        # once; only our background particles repeat their journeys automatically.
        "time_reference": "seconds_since_injection",
        "repeat": False,
        "particles": seeded_particles,
    }

    # Entries at the same index describe the same instant: time_s[i], height_m[i],
    # mass_kg[i], phase[i]. The model also saves exact cloud-exit and melting times.
    # Keep SI units here; the browser can display minutes or micrograms later.
    data = {
        "schema_version": 1,
        "environment": asdict(environment),
        "simulation": settings,
        "particles": particles,
        "seeding_burst": seeding_burst,
    }

    # Vite serves public/ files directly; the browser will read /data/cloud.json.
    output = Path(__file__).resolve().parent / "web/public/data/cloud.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {count} crystal trajectories to {output}")
    print(f"Seeding burst: {seeded_count} crystals across {len(layers)} heights")
    for layer in layers:
        print(f"  {layer['injection']['height_m']:g} m: {layer['crystal_count']} crystals")


if __name__ == "__main__":
    main()
