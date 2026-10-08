# From Seed to Signal

[Yang et al. (2024) — paper and model](https://acp.copernicus.org/articles/24/13833/2024/acp-24-13833-2024.html)

1. **Build a Cloud using some model from yang et al**
   Use the 1D ice-growth model in section 2; check results against Figures 1–2.

2. **Incorperate the Algo for how much cloud seeding is needed to detect it**
   Use section 3.3, Eq. (32), to estimate the AgI concentration needed for a detectable radar signal.

3. **Visulize the whole thing**
   Create a 2D ASCII illustration of the model, inspired by [ascii.rest](https://ascii.rest/), showing ice growth, falling particles, and radar signal.



Check Point:
**`model.py` now simulates one particle’s journey from inside a cloud to the ground.**

It has three main pieces:

- **`Environment`** describes the ground, cloud base, cloud top, temperature profile, and humidity.
- **`IceCrystal`** calculates an ice particle’s growth from water vapor and its falling speed.
- **`RainDrop`** calculates the melted particle’s radius and falling speed.

The simulation connects them:

1. **Inside the cloud:** RK45 updates mass and height together. As the crystal falls, it encounters different temperature and vapor pressure, which change its growth.
2. **Below cloud base:** growth stops, mass stays constant, and it continues falling.
3. **At 0°C:** it instantly becomes a liquid drop with the same mass.
4. **At the ground:** we record whether it arrived as ice or liquid. It can also stop at the time limit or if it completely sublimates inside the cloud.

The output is a **trajectory containing time, height, mass, and phase**, ready for plotting or animation.

Our assumptions are spherical particles, still air, fixed air density/viscosity, no riming, and simplified melting.

**We have the individual-particle building block. We haven’t built a population of crystals, AgI seeding, or radar detection yet**