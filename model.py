from dataclasses import dataclass, replace
from math import pi, exp, log
from scipy.integrate import solve_ivp


def saturation_vapor_pressure_ice_pa(temperature_k: float) -> float:
    # Murphy-Koop saturation pressure over ice, in Pa.
    # This is the S_i they speak of in section 2.2 yang et al
    T = temperature_k
    return exp(
        9.550426
        - 5723.265 / T
        + 3.53068 * log(T)
        - 0.00728332 * T
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


    def temperature_k(self, height_m: float) -> float:
        if not self.bottom_height_m <= height_m <= self.top_height_m:
            raise ValueError("Height is outside the environment.")

        # returns the temp at any given height
        return ( 
        self.reference_temperature_k
        - (height_m - self.reference_height_m)
        * self.lapse_rate_k_per_m
        )



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

    actual_vapor_pressure_pa = 182.0  # Temporary example value
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
