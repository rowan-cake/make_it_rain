import argparse
from pathlib import Path
import runpy

import matplotlib


def main():
    parser = argparse.ArgumentParser(description="Plot the single-particle demo.")
    parser.add_argument("--no-show", action="store_true", help="Save the graph without opening a window.")
    args = parser.parse_args()
    if args.no_show:
        matplotlib.use("Agg")  # file-only plotting, works without a desktop display

    import matplotlib.pyplot as plt

    project = Path(__file__).resolve().parent
    # run our existing demo and grab its trajectory
    demo = runpy.run_path(str(project / "model.py"), run_name="__main__")
    trajectory = demo["trajectory"]
    environment = demo["environment"]
    minutes = [t / 60 for t in trajectory.time_s]

    fig, (height_plot, mass_plot) = plt.subplots(2, 1, sharex=True, figsize=(9, 7))
    height_plot.plot(minutes, trajectory.height_m, color="gray", linewidth=1.5)
    for phase, color in (("ice", "royalblue"), ("liquid", "darkorange"), ("gone", "gray")):
        indices = [i for i, value in enumerate(trajectory.phase) if value == phase]
        if indices:
            height_plot.scatter(
                [minutes[i] for i in indices], [trajectory.height_m[i] for i in indices],
                color=color, label=phase.capitalize(), zorder=3,
            )
    height_plot.axhline(
        environment.cloud_base_height_m, linestyle="--", color="gray", label="Cloud base",
    )
    height_plot.axhline(environment.ground_height_m, color="black", linewidth=0.8)
    height_plot.set_ylabel("Height (m)")
    height_plot.set_title("One particle: cloud to ground")
    height_plot.legend(loc="upper right")

    # 1 kg = 1 billion micrograms; use a readable scale for our tiny particle
    mass_plot.plot(minutes, [m * 1e9 for m in trajectory.mass_kg], color="royalblue", marker=".")
    mass_plot.set_ylabel("Mass (micrograms)")
    mass_plot.set_xlabel("Time (minutes)")
    for axis in (height_plot, mass_plot):
        axis.grid(alpha=0.2)
        if trajectory.melting_time_s is not None:
            axis.axvline(trajectory.melting_time_s / 60, color="darkorange", linestyle=":")
    mass_plot.set_title("Mass stays constant below cloud; orange dotted line marks melting", fontsize=10)
    fig.text(0.5, 0.015, "Simplified model: fixed air properties, no mass loss below cloud, instant melting at 0°C",
             ha="center", fontsize=9, color="dimgray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    output = project / "trajectory.png"
    fig.savefig(output, dpi=150)
    print(f"Saved graph: {output}")
    if not args.no_show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
