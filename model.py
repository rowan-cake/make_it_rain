from dataclasses import dataclass, replace
from math import pi, exp, log, tanh, sqrt, isclose, isfinite
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
class Environment:  # this is the enviroment where the cloud exsits in 
    bottom_height_m: float  # always 0
    top_height_m: float 
    reference_height_m: float     # where the cloud may start
    reference_temperature_k: float      # the temp at the ref height 
    lapse_rate_k_per_m: float = 0.0055  # taken from yang et al paper
    relative_humidity_water: float = 1.0  # our assumption: 100% relative to liquid water


    def temperature_k(self, height_m: float) -> float:
        if not self.bottom_height_m <= height_m <= self.top_height_m:
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
        bottom_height_m=2000.0,
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
