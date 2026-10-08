# From Seed to Signal

[Yang et al. (2024) — paper and model](https://acp.copernicus.org/articles/24/13833/2024/acp-24-13833-2024.html)

1. **Build a Cloud using some model from yang et al**
   Use the 1D ice-growth model in section 2; check results against Figures 1–2.

2. **Incorperate the Algo for how much cloud seeding is needed to detect it**
   To hard :(, going to skip.

3. **Visulize the whole thing**
   Create a 2D ASCII illustration inspired by [ascii.rest](https://ascii.rest/), showing ice growth, falling particles, melting, and ground arrivals.

## Where we are

`model.py` handles individual crystals, collections of crystals, and new ice from AgI deposition nucleation (Yang Eq. 1). Particles grow inside the cloud, fall below it, melt at 0°C, and stop at the ground.

Quick test: `.venv/bin/python quick_plot.py --cloud`

## Website plan

**First version: preset simulations, animated ASCII**

- Tech Stack:
   - **Python + TypeScript + HTML Canvas**, with **Vite**  

### 1. Connect Python to the browser

- Keep the physics in Python. Add `export_simulations.py` to produce JSON for the website.
