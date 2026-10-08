import argparse
from pathlib import Path
import runpy
from math import pi

import matplotlib


def main():
    parser = argparse.ArgumentParser(description="Plot a particle or a collection in a cloud.")
    parser.add_argument("--cloud", action="store_true", help="Simulate a collection of 12 crystals.")
    parser.add_argument("--no-show", action="store_true", help="Save the graph without opening a window.")
    args = parser.parse_args()
    if args.no_show:
        matplotlib.use("Agg")  # file-only plotting, works without a desktop display

    import matplotlib.pyplot as plt

    project = Path(__file__).resolve().parent
    if args.cloud:
        from model import Cloud, Environment, IceCrystal

        environment = Environment(
            cloud_base_height_m=2000.0, ground_height_m=0.0, top_height_m=4000.0,
            reference_height_m=3000.0, reference_temperature_k=258.15,
        )
        # 4 heights x 3 radii = 12 tracked crystals; chosen demo values, not Yang's size distribution
        # 910 kg/m^3 is our solid-ice density, as in the single-crystal demo
        crystals = [
            IceCrystal(height, 910.0 * (4.0 / 3.0) * pi * radius**3, radius, radius)
            for height in (2600.0, 2800.0, 3000.0, 3200.0)
            for radius in (3e-6, 4e-6, 5e-6)
        ]
        cloud = Cloud(environment, crystals)
        # two-hour limit; one-minute plot samples plus exact stage endpoints
        trajectories = cloud.simulate(duration_s=7200.0, sample_interval_s=60.0)
        arrivals = [t for t in trajectories if t.stop_reason == "ground"]
        print(f"Tracked crystals: {len(trajectories)}; ground arrivals: {len(arrivals)}")
        if arrivals:
            times = [t.time_s[-1] / 60 for t in arrivals]
            print(f"Arrival times: {min(times):.1f} to {max(times):.1f} minutes")
    else:
        # run our existing demo and grab its trajectory
        demo = runpy.run_path(str(project / "model.py"), run_name="__main__")
        trajectories = [demo["trajectory"]]
        environment = demo["environment"]

    fig, (height_plot, mass_plot) = plt.subplots(2, 1, sharex=True, figsize=(9, 7))
    labels = set()
    for trajectory in trajectories:
        minutes = [t / 60 for t in trajectory.time_s]
        height_plot.plot(minutes, trajectory.height_m, color="gray", linewidth=1, alpha=0.6)
        for phase, color in (("ice", "royalblue"), ("liquid", "darkorange"), ("gone", "gray")):
            indices = [i for i, value in enumerate(trajectory.phase) if value == phase]
            if indices:
                height_plot.scatter(
                    [minutes[i] for i in indices], [trajectory.height_m[i] for i in indices],
                    color=color, label=phase.capitalize() if phase not in labels else None,
                    s=8 if args.cloud else 36, zorder=3,
                )
                labels.add(phase)
        # 1 kg = 1 billion micrograms; each curve is one particle's mass
        mass_plot.plot(minutes, [m * 1e9 for m in trajectory.mass_kg], color="royalblue",
                       alpha=0.5 if args.cloud else 1.0, marker=None if args.cloud else ".")
        if not args.cloud and trajectory.melting_time_s is not None:
            for axis in (height_plot, mass_plot):
                axis.axvline(trajectory.melting_time_s / 60, color="darkorange", linestyle=":")
    height_plot.axhline(
        environment.cloud_base_height_m, linestyle="--", color="gray", label="Cloud base",
    )
    height_plot.axhline(environment.ground_height_m, color="black", linewidth=0.8)
    height_plot.set_ylabel("Height (m)")
    height_plot.set_title("12 crystals sharing one environment" if args.cloud else "One particle: cloud to ground")
    height_plot.legend(loc="upper right")

    mass_plot.set_ylabel("Mass (micrograms)")
    mass_plot.set_xlabel("Time (minutes)")
    for axis in (height_plot, mass_plot):
        axis.grid(alpha=0.2)
    mass_plot.set_title(
        "Each curve is one particle; mass stays constant below cloud" if args.cloud
        else "Mass stays constant below cloud; orange dotted line marks melting", fontsize=10,
    )
    fig.text(0.5, 0.015, "Simplified model: fixed air properties, no mass loss below cloud, instant melting at 0°C",
             ha="center", fontsize=9, color="dimgray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    output = project / ("cloud_trajectories.png" if args.cloud else "trajectory.png")
    fig.savefig(output, dpi=150)
    print(f"Saved graph: {output}")
    if not args.no_show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
