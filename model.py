from dataclasses import dataclass, field, replace
from math import pi, exp, log, tanh, sqrt, isclose, isfinite
import numpy as np
from scipy.integrate import solve_ivp


def saturation_vapor_pressure_ice_pa(temperature_k: float) -> float:
    # Murphy-Koop saturation pressure over ice, in Pa.
    # these are published fit coefficients from Murphy-Koop (2005), eq (7)
    # input is kelvin, output is pascals; log is the natural logarithm
    # this gives e_si(T), not S_i; S_i = actual vapor pressure / e_si(T)
    T = temperature_k
    return exp(
        9.550426
        - 5723.265 / T
        + 3.53068 * log(T)
        - 0.00728332 * T
    )


def saturation_vapor_pressure_water_pa(temperature_k: float) -> float:
    # Murphy-Koop (2005), eq (10): saturation pressure over liquid water
    # source (formula 11): https://www.eol.ucar.edu/data-software/conventions-and-standards/water-vapor-pressure-formulations
    # the numbers are published fit coefficients, not cloud settings we chose
    # they approximate vapor-pressure calculations based on thermodynamics and
    # heat-capacity data, using 1/T, log(T), and T terms
    # input must be kelvin; the fit gives ln(pressure in Pa), so we use exp()
    # published fit range: 123 < T < 332 K, including supercooled liquid water
    T = temperature_k

    return exp(
        54.842763
        - 6763.22 / T
        - 4.21 * log(T)
        + 0.000367 * T
        # tanh smoothly joins the low- and high-temperature fits
        # 218.8 K sets the transition centre; 0.0415 per K sets its steepness
        + tanh(0.0415 * (T - 218.8)) * (
            53.878
            - 1331.22 / T
            - 9.44523 * log(T)
            + 0.014025 * T
        )
    )

def deposition_nucleation_fraction(temperature_k: float, ice_saturation_ratio: float) -> float:
    # Yang (2024), section 2.1, eq (1), based on Xue et al. (2013a)
    # https://acp.copernicus.org/articles/24/13833/2024/acp-24-13833-2024.html#section2.1
    # this is the fraction of AgI that nucleates ice, not an ice growth rate
    if not isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("Temperature must be positive and finite, in kelvin.")
    if not isfinite(ice_saturation_ratio) or ice_saturation_ratio < 0.0:
        raise ValueError("Ice saturation ratio must be nonnegative and finite.")
    # the paper's strict conditions: colder than 268.2 K and S_i greater than 1.04
    # zero here means no deposition nucleation in our model, not no possible nucleation
    if temperature_k >= 268.2 or ice_saturation_ratio <= 1.04:
        return 0.0

    x = ice_saturation_ratio - 1.0
    # 273.16 K and T_0 = 10 K are the reference and scale used in this fit
    # keep 273.16 as published; our separate melting rule uses 273.15 K
    y = (273.16 - temperature_k) / 10.0
    # a, b, c, d, e are published empirical fit coefficients, not settings we tuned
    fraction = (
        -3.25e-3 * x
        + 5.39e-5 * y
        + 4.35e-2 * x**2
        + 1.55e-4 * y**2
        - 0.07 * x**3
    )
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("Nucleation fit returned a fraction outside [0, 1].")
    return fraction


@dataclass
class IceCrystal:
    height_m: float # height in cloud (Moves in 1D up or down only)
    mass_kg: float
    a_m: float  # horizontal raduis  
    c_m: float  # veritcal raduis 
    # note if a_m = c_m then crystal = sphere 

    def volume_m3(self)->float:
        return (4.0 / 3.0) * pi * self.a_m**2 * self.c_m

    def terminal_velocity_m_s(
        self,
        air_density_kg_m3: float,
        dynamic_viscosity_pa_s: float,
    ) -> float:
        # yang section 2.3, eq (22): V_t = eta * Re / (rho_air * D)
        # positive means falling relative to the air, in m/s
        # this version is for our sphere; plates/columns need their own geometry
        values = (self.a_m, self.c_m, air_density_kg_m3, dynamic_viscosity_pa_s)
        if any(not isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("Radii, air density and viscosity must be positive and finite.")
        if not isfinite(self.mass_kg) or self.mass_kg < 0.0:
            raise ValueError("Mass must be nonnegative and finite.")
        if not isclose(self.a_m, self.c_m, rel_tol=1e-9, abs_tol=0.0):
            raise ValueError("Terminal velocity currently assumes a spherical crystal.")

        diameter_m = 2.0 * self.a_m  # sphere diameter D = 2r
        area_ratio = 1.0  # eq (25): sphere's projected disk fills its outer circle
        gravity_m_s2 = 9.81  # approximate gravitational acceleration near Earth
        delta_0 = 8.0  # dimensionless drag-fit constants from Heymsfield-Westbrook (2010)
        c_0 = 0.35
        k = 0.5  # their fitted exponent; HW uses A_r^(1-k), also 0.5 here

        # Heymsfield-Westbrook (2010), section 4, eq (8) and steps on p. 2478
        # https://doi.org/10.1175/2010JAS3379.1
        # this is the method yang cites; printed yang eqs (23)-(24) differ
        # we follow HW here; we haven't verified yang's restricted source code
        # X* = 8 * rho_air * m * g / (pi * eta^2 * A_r^(1-k))
        # 8/pi comes from the drag balance and circular area, not a fitted number
        best_number = (
            air_density_kg_m3 / dynamic_viscosity_pa_s**2
            * (8.0 * self.mass_kg * gravity_m_s2 / (pi * area_ratio**(1.0 - k)))
        )

        # HW: Re = (delta_0^2 / 4) * (sqrt(1 + x) - 1)^2
        # x/(sqrt(1+x)+1) is the same as sqrt(1+x)-1, but more accurate for tiny ice
        x = 4.0 * sqrt(best_number) / (delta_0**2 * sqrt(c_0))
        reynolds_number = (delta_0**2 / 4.0) * (x / (sqrt(1.0 + x) + 1.0))**2

        return dynamic_viscosity_pa_s * reynolds_number / (air_density_kg_m3 * diameter_m)

    def mass_growth_rate_kg_s(
        self,temperature_k: float,
        ice_saturation_ratio: float, 
        saturation_vapor_density_kg_m3: float,
        )-> float:
        # from yang et al section 2.2, equation (5): 
        # note these are fixed approximate constants for our first version
        # they are not a full reproduction of yang's parameter choices
        latent_heat = 2.834e6        # L_d: heat released per kg of deposited ice, J/kg
        air_conductivity = 0.024     # K: how easily air carries heat away, W/(m K)
        vapor_gas_constant = 461.5   # R_v: gas constant for water vapor, J/(kg K)
        vapor_diffusivity = 2.0e-5   # D_v: how easily vapor diffuses through air, m²/s

        # first part of the denominator in eq (5): L_d² / (K * R_v * T_a²)
        # depositing vapor releases heat, and removing that heat limits growth
        heat_resistance = latent_heat**2 / (
            air_conductivity * vapor_gas_constant * temperature_k**2
        )

        # second part of the denominator in eq (5): 1 / (D_v * rho_s)
        # vapor has to diffuse to the crystal; rho_s is the saturation vapor density
        vapor_resistance = 1.0 / (
            vapor_diffusivity * saturation_vapor_density_kg_m3
        )   
        
        # numerator in eq (5): 4 * pi * C * (S_i - 1) * f_v
        # for now the crystal is a sphere: C = radius = self.a_m (a_m = c_m)
        # we set f_v = 1 for now, leaving out the airflow correction from eq (6)
        # S_i - 1 is the surplus above equilibrium; returns mass change in kg/s
        return (4.0 * pi * self.a_m * (ice_saturation_ratio - 1.0) / (heat_resistance + vapor_resistance))
        

@dataclass
class RainDrop:
    height_m: float
    mass_kg: float

    def radius_m(self) -> float:
        if not isfinite(self.mass_kg) or self.mass_kg <= 0.0:
            raise ValueError("A rain drop needs positive, finite mass.")
        water_density_kg_m3 = 1000.0  # rounded liquid-water density, kg/m^3
        return (3.0 * self.mass_kg / (4.0 * pi * water_density_kg_m3)) ** (1.0 / 3.0)

    def terminal_velocity_m_s(self, air_density_kg_m3: float, dynamic_viscosity_pa_s: float) -> float:
        # simple smooth-sphere approximation for a small liquid drop, not Yang's ice fit
        # Heymsfield-Westbrook (2010), section 2a, eqs (3)-(5), p. 2471:
        # https://doi.org/10.1175/2010JAS3379.1
        # 9.06 and 0.292 are the reported sphere drag-fit constants
        # this leaves out drop deformation and breakup
        if any(not isfinite(v) or v <= 0.0 for v in (air_density_kg_m3, dynamic_viscosity_pa_s)):
            raise ValueError("Air density and viscosity must be positive and finite.")
        diameter_m = 2.0 * self.radius_m()
        delta_0, c_0 = 9.06, 0.292
        gravity_m_s2 = 9.81  # approximate gravitational acceleration near Earth
        best_number = 8.0 * air_density_kg_m3 * self.mass_kg * gravity_m_s2 / (pi * dynamic_viscosity_pa_s**2)
        x = 4.0 * sqrt(best_number) / (delta_0**2 * sqrt(c_0))
        reynolds_number = (delta_0**2 / 4.0) * (x / (sqrt(1.0 + x) + 1.0))**2
        if reynolds_number >= 1e4:  # upper Reynolds-number range discussed for this sphere fit
            raise ValueError("Drop is outside the Reynolds-number range of the sphere approximation.")
        return dynamic_viscosity_pa_s * reynolds_number / (air_density_kg_m3 * diameter_m)


@dataclass
class Environment:  # this is the enviroment where the cloud exsits in
    cloud_base_height_m: float
    ground_height_m: float
    top_height_m: float 
    reference_height_m: float     # where the cloud may start
    reference_temperature_k: float      # the temp at the ref height 
    lapse_rate_k_per_m: float = 0.0055  # taken from yang et al paper
    relative_humidity_water: float = 1.0  # our assumption: 100% relative to liquid water

    def __post_init__(self):
        if not all(isfinite(v) for v in vars(self).values()):
            raise ValueError("Environment settings must be finite.")
        if not self.ground_height_m <= self.cloud_base_height_m < self.top_height_m:
            raise ValueError("Need ground <= cloud base < cloud top.")
        if self.lapse_rate_k_per_m < 0.0:
            raise ValueError("This simple model supports constant temperature or warming downward.")
        if self.relative_humidity_water < 0.0:
            raise ValueError("Relative humidity cannot be negative.")

    def temperature_k(self, height_m: float) -> float:
        if not self.ground_height_m <= height_m <= self.top_height_m:
            raise ValueError("Height is outside the environment.")

        # returns the temp at any given height
        return ( 
        self.reference_temperature_k
        - (height_m - self.reference_height_m)
        * self.lapse_rate_k_per_m
        )

    def vapor_pressure_pa(self, height_m: float) -> float:
        # actual vapor pressure = relative humidity * saturation pressure over water
        # 1.0 means 100%, 0.9 means 90%; this is a ratio, not a percentage input
        # the profile varies with height, but we don't deplete moisture over time yet
        temperature = self.temperature_k(height_m)
        saturation_pressure = saturation_vapor_pressure_water_pa(temperature)
        return self.relative_humidity_water * saturation_pressure


def simulate_crystal(
    crystal: IceCrystal,
    environment: Environment,
    duration_s: float,
    air_density_kg_m3: float = 1.0,
    dynamic_viscosity_pa_s: float = 1.65e-5,
):
    # one spherical crystal growing and falling in still air
    # air density and viscosity are fixed example values for now, as above
    # temperature and vapor pressure are sampled again at every trial height
    if not isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("Duration must be positive and finite.")
    if not environment.cloud_base_height_m < crystal.height_m <= environment.top_height_m:
        raise ValueError("Start the crystal above the cloud bottom and inside the cloud.")
    if not isfinite(crystal.mass_kg) or crystal.mass_kg <= 0.0:
        raise ValueError("Start with a positive, finite ice mass.")
    crystal.terminal_velocity_m_s(air_density_kg_m3, dynamic_viscosity_pa_s)

    # preserve the starting sphere's density as it grows (our example uses 910 kg/m^3)
    ice_density_kg_m3 = crystal.mass_kg / crystal.volume_m3()
    vapor_gas_constant = 461.5  # R_v, J/(kg K), same as our growth calculation
    # only the cloud must be cold; below-cloud melting is handled by simulate_to_ground
    # 123 K is the water saturation fit's lower limit; 273.15 K is 0 C
    for height in (environment.cloud_base_height_m, environment.top_height_m):
        if not 123.0 < environment.temperature_k(height) <= 273.15:
            raise ValueError("This ice cloud needs 123 < temperature <= 273.15 K throughout.")

    def growth_and_fall_ode(time_s, state):
        mass_kg, height_m = state
        # RK45 may try a point past complete sublimation before locating the event
        if mass_kg <= 0.0:
            return [0.0, 0.0]
        radius_m = (3.0 * mass_kg / (4.0 * pi * ice_density_kg_m3)) ** (1.0 / 3.0)
        trial_crystal = replace(
            crystal, mass_kg=mass_kg, height_m=height_m, a_m=radius_m, c_m=radius_m,
        )

        # the solver can also trial a point below the bottom before finding the crossing
        # use boundary conditions there; the bottom event ends the actual trajectory
        sample_height = min(environment.top_height_m, max(environment.cloud_base_height_m, height_m))
        temperature = environment.temperature_k(sample_height)
        saturation_pressure = saturation_vapor_pressure_ice_pa(temperature)
        saturation_ratio = environment.vapor_pressure_pa(sample_height) / saturation_pressure
        saturation_density = saturation_pressure / (vapor_gas_constant * temperature)

        growth_rate = trial_crystal.mass_growth_rate_kg_s(
            temperature, saturation_ratio, saturation_density,
        )
        fall_speed = trial_crystal.terminal_velocity_m_s(
            air_density_kg_m3, dynamic_viscosity_pa_s,
        )
        # dz/dt = -V_t: height increases upward, and we assume no vertical air motion
        return [growth_rate, -fall_speed]

    def cloud_bottom(time_s, state):
        return state[1] - environment.cloud_base_height_m

    cloud_bottom.terminal = True  # stop integration at the crossing
    cloud_bottom.direction = -1  # only crossings from above to below

    def ice_gone(time_s, state):
        return state[0]

    ice_gone.terminal = True
    ice_gone.direction = -1

    solution = solve_ivp(
        growth_and_fall_ode,
        t_span=(0.0, duration_s),
        y0=[crystal.mass_kg, crystal.height_m],
        method="RK45",
        events=[cloud_bottom, ice_gone],
        dense_output=True,  # lets us sample the trajectory at chosen times afterwards
        rtol=1e-7,  # numerical accuracy setting, not a physical constant
        atol=[1e-22, 1e-6],  # absolute error scales: tiny mass in kg, height in metres
    )
    if not solution.success:
        raise RuntimeError(solution.message)
    return solution


@dataclass
class ParticleTrajectory:
    time_s: list[float]
    height_m: list[float]
    mass_kg: list[float]
    phase: list[str]  # "ice", "liquid", or "gone"
    stop_reason: str
    cloud_exit_time_s: float | None = None
    melting_time_s: float | None = None
    origin: str = "background"


def simulate_to_ground(
    crystal: IceCrystal,
    environment: Environment,
    duration_s: float,
    air_density_kg_m3: float = 1.0,
    dynamic_viscosity_pa_s: float = 1.65e-5,
    sample_interval_s: float = 10.0,
) -> ParticleTrajectory:
    # our extension: below cloud, no growth, sublimation or evaporation
    # melting is instantaneous at 0 C with mass conserved; this is NOT a Yang melting model
    # the lapse profile warms downward, so there is no refreezing stage
    if not isfinite(sample_interval_s) or sample_interval_s <= 0.0:
        raise ValueError("Sample interval must be positive and finite.")
    result = ParticleTrajectory([], [], [], [], "time_limit")

    def record_segment(solution, phase):
        # include every stage endpoint exactly, even between regular output samples
        times = list(np.arange(solution.t[0], solution.t[-1], sample_interval_s))
        times.append(float(solution.t[-1]))
        for time_s in times:
            mass_kg, height_m = solution.sol(time_s)
            # shared endpoints appear once, with the phase after the transition
            if result.time_s and time_s == result.time_s[-1]:
                result.phase[-1] = phase
                continue
            result.time_s.append(float(time_s))
            result.height_m.append(float(height_m))
            result.mass_kg.append(float(mass_kg))
            result.phase.append(phase)

    cloud = simulate_crystal(crystal, environment, duration_s, air_density_kg_m3, dynamic_viscosity_pa_s)
    record_segment(cloud, "ice")
    if cloud.t_events[1].size:
        result.mass_kg[-1] = 0.0  # remove root-finding roundoff at complete sublimation
        result.phase[-1] = "gone"
        result.stop_reason = "sublimated"
        return result
    if not cloud.t_events[0].size:
        return result

    time_s = float(cloud.t[-1])
    result.cloud_exit_time_s = time_s
    mass_kg = float(cloud.y[0, -1])
    height_m = environment.cloud_base_height_m
    result.height_m[-1] = height_m
    ice_density = crystal.mass_kg / crystal.volume_m3()
    radius_m = (3.0 * mass_kg / (4.0 * pi * ice_density)) ** (1.0 / 3.0)
    phase = "ice"
    if environment.temperature_k(height_m) >= 273.15:
        phase = "liquid"
        result.melting_time_s = time_s
        result.phase[-1] = phase
    if height_m == environment.ground_height_m:
        result.stop_reason = "ground"
        return result

    def ground(time_s, state):
        return state[1] - environment.ground_height_m

    ground.terminal, ground.direction = True, -1

    def melting(time_s, state):
        # same linear temperature profile, extended for trial steps past the ground
        # events locate the crossing before we accept any out-of-domain trajectory
        return (environment.reference_temperature_k
                - (state[1] - environment.reference_height_m) * environment.lapse_rate_k_per_m
                - 273.15)

    melting.terminal, melting.direction = True, 1  # warming through 0 C

    while time_s < duration_s:
        if phase == "ice":
            particle = replace(crystal, mass_kg=mass_kg, height_m=height_m, a_m=radius_m, c_m=radius_m)
        else:
            particle = RainDrop(height_m, mass_kg)  # same mass; liquid density gives its new radius
        fall_speed = particle.terminal_velocity_m_s(air_density_kg_m3, dynamic_viscosity_pa_s)
        # constant mass and air properties make the speed constant within each descent stage
        descent = solve_ivp(
            lambda t, state: [0.0, -fall_speed],
            (time_s, duration_s), [mass_kg, height_m],
            method="RK45", events=[ground, melting] if phase == "ice" else [ground],
            dense_output=True, rtol=1e-7, atol=[1e-22, 1e-6],
        )
        if not descent.success:
            raise RuntimeError(descent.message)
        record_segment(descent, phase)
        time_s, height_m = float(descent.t[-1]), float(descent.y[1, -1])
        if descent.t_events[0].size:
            result.height_m[-1] = environment.ground_height_m
            # also handle a 0 C crossing exactly at the ground
            if phase == "ice" and environment.temperature_k(environment.ground_height_m) >= 273.15:
                result.phase[-1] = "liquid"
                result.melting_time_s = time_s
            result.stop_reason = "ground"
            return result
        if phase == "ice" and descent.t_events[1].size:
            phase = "liquid"
            result.phase[-1] = phase
            result.melting_time_s = time_s
        else:
            break  # time limit; the clock is shared across all stages
    return result


@dataclass
class Cloud:
    environment: Environment
    crystals: list[IceCrystal]
    seeded_crystals: list[IceCrystal] = field(default_factory=list)

    def seed(
        self,
        height_m: float,
        agi_concentration_per_m3: float,
        seeded_volume_m3: float,
    ) -> list[IceCrystal]:
        # each call adds a fresh AgI burst at t = 0, before simulate()
        # our simplification: apply deposition eq (1) once; no later activation of unused AgI
        # Yang includes four nucleation modes and ongoing nucleation; we only use deposition
        if not self.environment.cloud_base_height_m < height_m <= self.environment.top_height_m:
            raise ValueError("Seed above the cloud base and inside the cloud.")
        if not isfinite(agi_concentration_per_m3) or agi_concentration_per_m3 < 0.0:
            raise ValueError("AgI concentration must be nonnegative and finite, in particles/m^3.")
        if not isfinite(seeded_volume_m3) or seeded_volume_m3 <= 0.0:
            raise ValueError("Seeded air volume must be positive and finite, in m^3.")

        temperature = self.environment.temperature_k(height_m)
        if not 123.0 < temperature < 332.0:  # range of the water saturation fit we use
            raise ValueError("Seeding temperature must be within the vapor-pressure fit range.")
        saturation_ratio = (
            self.environment.vapor_pressure_pa(height_m)
            / saturation_vapor_pressure_ice_pa(temperature)
        )
        fraction = deposition_nucleation_fraction(temperature, saturation_ratio)
        expected_count = fraction * agi_concentration_per_m3 * seeded_volume_m3
        if not isfinite(expected_count):
            raise ValueError("Calculated ice count must be finite.")
        # our discrete-particle choice: round to the nearest whole crystal
        # Python round uses ties-to-even (e.g. 2.5 -> 2, 3.5 -> 4); no fractional weights
        new_ice_count = round(expected_count)

        # use the same starting sphere as our prototype: 4 micrometres and 910 kg/m^3
        # 4 micrometres follows Yang's single-crystal example (section 3.1), not its size distribution
        # 910 kg/m^3 = 0.91 g/cm^3, the paper's bulk density of solid ice
        radius_m = 4e-6
        mass_kg = 910.0 * (4.0 / 3.0) * pi * radius_m**3
        # construct each object separately so each crystal can later have its own path
        new_crystals = [
            IceCrystal(height_m, mass_kg, radius_m, radius_m)
            for _ in range(new_ice_count)
        ]
        self.seeded_crystals.extend(new_crystals)
        return new_crystals  # empty if the rounded count is zero

    def simulate(
        self,
        duration_s: float,
        air_density_kg_m3: float = 1.0,
        dynamic_viscosity_pa_s: float = 1.65e-5,
        sample_interval_s: float = 10.0,
    ) -> list[ParticleTrajectory]:
        # our first cloud is a collection of ice crystals sharing the same environment
        # every object is one crystal with its own trajectory
        # all start at t = 0; results are background first, then seeded crystals in insertion order
        # moisture is prescribed: no competition for vapor or collisions
        if not isfinite(duration_s) or duration_s <= 0.0:
            raise ValueError("Duration must be positive and finite.")
        if not isfinite(sample_interval_s) or sample_interval_s <= 0.0:
            raise ValueError("Sample interval must be positive and finite.")
        trajectories = [
            simulate_to_ground(
                crystal, self.environment, duration_s,
                air_density_kg_m3, dynamic_viscosity_pa_s, sample_interval_s,
            )
            for crystal in self.crystals
        ]
        for crystal in self.seeded_crystals:
            trajectory = simulate_to_ground(
                crystal, self.environment, duration_s,
                air_density_kg_m3, dynamic_viscosity_pa_s, sample_interval_s,
            )
            trajectory.origin = "seeded"
            trajectories.append(trajectory)
        return trajectories


if __name__ == "__main__":
    radius_m = 4e-6
    ice_density_kg_m3 = 910.0

    initial_volume_m3 = (4.0 / 3.0) * pi * radius_m**3

    crystal = IceCrystal(
        height_m=3000.0,
        mass_kg=ice_density_kg_m3 * initial_volume_m3,
        a_m=radius_m,
        c_m=radius_m,
    )
    environment = Environment(
        cloud_base_height_m=2000.0,
        ground_height_m=0.0,
        top_height_m=4000.0,
        reference_height_m=3000.0,
        reference_temperature_k=258.15,  # −15°C
        lapse_rate_k_per_m=0.0055,
    )


    temperature_k = environment.temperature_k(crystal.height_m)
    saturation_pressure_pa = saturation_vapor_pressure_ice_pa(temperature_k)

    actual_vapor_pressure_pa = environment.vapor_pressure_pa(crystal.height_m)
    ice_saturation_ratio = actual_vapor_pressure_pa / saturation_pressure_pa

    vapor_gas_constant = 461.5  # J / (kg K)

    # NOTE :  **Saturation vapor density:** the amount that would balance the ice at that temperature.
    saturation_vapor_density_kg_m3 = (
        saturation_pressure_pa
        / (vapor_gas_constant * temperature_k)
    )

    growth_rate = crystal.mass_growth_rate_kg_s(
        temperature_k=temperature_k,
        ice_saturation_ratio=ice_saturation_ratio,
        saturation_vapor_density_kg_m3=saturation_vapor_density_kg_m3,
    )

    print("Mass growth rate:", growth_rate, "kg/s")

    print(
        "Saturation vapor density:",
        saturation_vapor_density_kg_m3,
        "kg/m³",
    )
    print("Saturation pressure:", saturation_pressure_pa, "Pa")
    print("Ice saturation ratio:", ice_saturation_ratio)

    print("Crystal's surrounding temperature:", temperature_k - 273.15, "°C")

    print("Volume:", crystal.volume_m3(), "m³")
    print("Mass:", crystal.mass_kg, "kg")

    # example air properties only, not yet calculated from our environment
    # 1.0 kg/m^3 is a rounded air density; 1.65e-5 Pa s approximates cold-air viscosity
    fall_speed = crystal.terminal_velocity_m_s(
        air_density_kg_m3=1.0,
        dynamic_viscosity_pa_s=1.65e-5,
    )
    print("Initial terminal fall speed (example air):", fall_speed, "m/s")

    def growth_ode(time_s, state):
        # scipy gives us a trial mass; calculate its matching radius
        mass_kg = state[0]
        radius_m = (
            3.0 * mass_kg / (4.0 * pi * ice_density_kg_m3)
        ) ** (1.0 / 3.0)

        # temporary crystal so trial calculations don't change our original
        trial_crystal = replace(
            crystal,
            mass_kg=mass_kg,
            a_m=radius_m,
            c_m=radius_m,
        )

        rate = trial_crystal.mass_growth_rate_kg_s(
            temperature_k=temperature_k,
            ice_saturation_ratio=ice_saturation_ratio,
            saturation_vapor_density_kg_m3=saturation_vapor_density_kg_m3,
        )
        return [rate]

    solution = solve_ivp(
        fun=growth_ode,
        t_span=(0.0, 60.0),
        y0=[crystal.mass_kg],
        method="RK45",
        t_eval=[0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        rtol=1e-7,
        atol=1e-22,
    )

    if not solution.success:
        raise RuntimeError(solution.message)

    for time_s, mass_kg in zip(solution.t, solution.y[0]):
        print(f"{time_s:5.1f} s: {mass_kg:.6e} kg")

    # exact solution for our fixed-condition spherical model
    initial_radius_m = crystal.a_m

    G = growth_rate / (
        4.0 * pi * ice_density_kg_m3 * initial_radius_m
    )

    exact_radius_m = (
        initial_radius_m**2 + 2.0 * G * solution.t
    ) ** 0.5

    exact_mass_kg = (
        (4.0 / 3.0) * pi * ice_density_kg_m3 * exact_radius_m**3
    )

    relative_error = abs(solution.y[0] - exact_mass_kg) / exact_mass_kg

    print("Largest relative mass error:", max(relative_error))

    # separate run: the analytic comparison above only applies to fixed conditions
    # 7200 s (two hours) is our chosen demo limit; 600 s is just the print interval
    trajectory = simulate_to_ground(crystal, environment, duration_s=7200.0, sample_interval_s=600.0)
    print("\nCloud to ground (fixed example air density and viscosity):")
    for time_s, height_m, mass_kg, phase in zip(
        trajectory.time_s, trajectory.height_m, trajectory.mass_kg, trajectory.phase,
    ):
        temperature_c = environment.temperature_k(height_m) - 273.15
        print(f"{time_s:7.1f} s: {height_m:8.2f} m, {mass_kg:.6e} kg, {temperature_c:.2f} C, {phase}")
    print("Stopped:", trajectory.stop_reason)

    # seeding demo: 35 AgI particles/cm^3 in a 1-litre volume of air at our reference height
    # 1 m^3 = 10^6 cm^3; 1 litre = 10^-3 m^3 (these are unit conversions)
    cloud = Cloud(environment, [])
    new_crystals = cloud.seed(height_m=3000.0, agi_concentration_per_m3=35.0 * 1e6, seeded_volume_m3=1e-3)
    if new_crystals:
        seeded_trajectories = cloud.simulate(7200.0)
        print("\nOne-burst, deposition-only seeding example:")
        print("New ice crystals in the seeded litre (rounded):", len(new_crystals))
        print("Simulated trajectories:", len(seeded_trajectories))
        print("Final total particle mass:", sum(t.mass_kg[-1] for t in seeded_trajectories), "kg")
