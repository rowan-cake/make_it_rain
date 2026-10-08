import unittest
from unittest.mock import patch
from dataclasses import replace
from math import pi, sqrt

import numpy as np

from model import (
    Cloud, Environment, IceCrystal, RainDrop, simulate_crystal, simulate_to_ground,
    deposition_nucleation_fraction,
    saturation_vapor_pressure_ice_pa, saturation_vapor_pressure_water_pa,
)


class ParticleJourneyTests(unittest.TestCase):
    def setUp(self):
        radius = 4e-6
        self.ice = IceCrystal(3000.0, 910.0 * 4.0 * pi * radius**3 / 3.0, radius, radius)
        self.env = Environment(
            cloud_base_height_m=2000.0, ground_height_m=0.0, top_height_m=4000.0,
            reference_height_m=3000.0, reference_temperature_k=258.15,
        )

    def test_warm_ground_mass_conservation_and_analytic_descent_time(self):
        original = replace(self.ice)
        result = simulate_to_ground(self.ice, self.env, 7200)
        self.assertEqual(self.ice, original)
        self.assertEqual(result.stop_reason, "ground")
        self.assertEqual(result.phase[-1], "liquid")
        self.assertEqual(result.height_m[-1], 0.0)
        self.assertTrue(np.all(np.diff(result.time_s) > 0))
        self.assertTrue(np.all(np.diff(result.height_m) < 0))

        exit_index = result.time_s.index(result.cloud_exit_time_s)
        mass = result.mass_kg[exit_index]
        self.assertTrue(all(m == mass for m in result.mass_kg[exit_index:]))
        melt_index = result.time_s.index(result.melting_time_s)
        self.assertAlmostEqual(self.env.temperature_k(result.height_m[melt_index]), 273.15)

        # independently integrate dz/dt = constant for each below-cloud stage
        radius = (3 * mass / (4 * pi * 910)) ** (1 / 3)
        ice_speed = replace(self.ice, mass_kg=mass, a_m=radius, c_m=radius).terminal_velocity_m_s(1, 1.65e-5)
        rain_speed = RainDrop(0, mass).terminal_velocity_m_s(1, 1.65e-5)
        freezing_height = 3000 + (258.15 - 273.15) / 0.0055
        expected_time = result.cloud_exit_time_s + (2000 - freezing_height) / ice_speed + freezing_height / rain_speed
        self.assertAlmostEqual(result.time_s[-1], expected_time, places=6)

    def test_cold_ground_and_isothermal_profile(self):
        for env in (replace(self.env, reference_temperature_k=253.15),
                    replace(self.env, lapse_rate_k_per_m=0)):
            with self.subTest(env=env):
                result = simulate_to_ground(self.ice, env, 20000)
                self.assertEqual(result.stop_reason, "ground")
                self.assertEqual(result.phase[-1], "ice")
                self.assertIsNone(result.melting_time_s)

    def test_shared_time_limit_in_each_stage(self):
        for duration, phase, exited in ((60, "ice", False), (2500, "ice", True), (4100, "liquid", True)):
            with self.subTest(duration=duration):
                result = simulate_to_ground(self.ice, self.env, duration)
                self.assertEqual(result.stop_reason, "time_limit")
                self.assertEqual(result.time_s[-1], duration)
                self.assertEqual(result.phase[-1], phase)
                self.assertEqual(result.cloud_exit_time_s is not None, exited)
                self.assertGreater(result.height_m[-1], 0)

    def test_melting_at_cloud_base_or_ground_and_base_at_ground(self):
        freezing_height = 3000 + (258.15 - 273.15) / 0.0055
        at_base = simulate_to_ground(self.ice, replace(self.env, cloud_base_height_m=freezing_height), 20000)
        self.assertEqual(at_base.cloud_exit_time_s, at_base.melting_time_s)
        self.assertEqual(at_base.stop_reason, "ground")
        at_ground = simulate_to_ground(self.ice, replace(self.env, ground_height_m=freezing_height), 7200)
        self.assertEqual(at_ground.melting_time_s, at_ground.time_s[-1])
        self.assertEqual(at_ground.phase[-1], "liquid")
        no_descent = simulate_to_ground(self.ice, replace(self.env, ground_height_m=2000), 7200)
        self.assertEqual(no_descent.stop_reason, "ground")
        self.assertEqual(no_descent.time_s[-1], no_descent.cloud_exit_time_s)

    def test_sublimation_ends_journey_inside_cloud(self):
        result = simulate_to_ground(self.ice, replace(self.env, relative_humidity_water=0), 7200)
        self.assertEqual(result.stop_reason, "sublimated")
        self.assertEqual(result.mass_kg[-1], 0)
        self.assertEqual(result.phase[-1], "gone")
        self.assertIsNone(result.cloud_exit_time_s)

    def test_rain_drop_mass_radius_and_drag_balance(self):
        drop = RainDrop(100, 6e-9)
        radius = drop.radius_m()
        self.assertAlmostEqual((4*pi*radius**3*1000/3) / drop.mass_kg, 1.0)
        speed = drop.terminal_velocity_m_s(1.0, 1.65e-5)
        reynolds = speed * 2*radius / 1.65e-5
        drag_coefficient = 0.292 * (1 + 9.06/sqrt(reynolds))**2
        drag = 0.5 * speed**2 * pi*radius**2 * drag_coefficient
        self.assertAlmostEqual(drag / (drop.mass_kg * 9.81), 1.0)

    def test_uniform_cloud_growth_still_matches_analytic_solution(self):
        env = replace(self.env, lapse_rate_k_per_m=0)
        temperature = env.reference_temperature_k
        e_si = saturation_vapor_pressure_ice_pa(temperature)
        rate = self.ice.mass_growth_rate_kg_s(
            temperature, saturation_vapor_pressure_water_pa(temperature)/e_si, e_si/(461.5*temperature),
        )
        g = rate / (4*pi*910*self.ice.a_m)
        result = simulate_crystal(self.ice, env, 60)
        times = np.linspace(0, 60, 61)
        exact_mass = 4*pi*910/3 * (self.ice.a_m**2 + 2*g*times)**1.5
        np.testing.assert_allclose(result.sol(times)[0], exact_mass, rtol=2e-6, atol=1e-22)

    def test_invalid_boundaries_and_warm_cloud_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.env, ground_height_m=2500)
        with self.assertRaises(ValueError):
            simulate_to_ground(self.ice, replace(self.env, reference_temperature_k=280), 7200)

    def test_collection_preserves_independent_particle_results_and_inputs(self):
        crystals = [self.ice, replace(self.ice, height_m=2800)]
        original = [replace(ice) for ice in crystals]
        cloud = Cloud(self.env, crystals)
        results = cloud.simulate(7200, sample_interval_s=60)
        self.assertEqual(len(results), 2)
        self.assertEqual(crystals, original)
        for crystal, result in zip(crystals, results):
            self.assertEqual(result, simulate_to_ground(crystal, self.env, 7200, sample_interval_s=60))
        self.assertNotEqual(results[0].time_s[-1], results[1].time_s[-1])
        self.assertEqual(Cloud(self.env, []).simulate(60), [])

    def test_deposition_fraction_reference_and_strict_boundaries(self):
        # Eq (1) at -15 C and water saturation using our vapor-pressure functions
        fraction = deposition_nucleation_fraction(258.15, 1.1574174546356564)
        self.assertAlmostEqual(fraction, 0.000723394294000074, places=15)
        for temperature, ratio in ((268.2, 1.2), (270, 1.2), (258.15, 1.04), (258.15, 1.0)):
            self.assertEqual(deposition_nucleation_fraction(temperature, ratio), 0.0)
        self.assertGreater(deposition_nucleation_fraction(268.19, 1.05), 0.0)
        # don't silently turn an unphysical fitted fraction into a population
        with self.assertRaises(ValueError):
            deposition_nucleation_fraction(258.15, 2.0)
        with self.assertRaises(ValueError):
            deposition_nucleation_fraction(float("nan"), 1.2)

    def test_seeding_converts_concentration_and_preserves_background(self):
        cloud = Cloud(self.env, [self.ice])
        original = replace(self.ice)
        # 35/cm^3 = 35 million/m^3; 1 litre = 0.001 m^3
        crystals = cloud.seed(3000, 35e6, 1e-3)
        self.assertEqual(len(crystals), 25)  # expected 25.3188..., rounded to nearest integer
        self.assertEqual(len(cloud.seeded_crystals), 25)
        self.assertEqual(len({id(crystal) for crystal in crystals}), 25)
        self.assertEqual(cloud.crystals, [original])
        for crystal in crystals:
            self.assertEqual(crystal.a_m, 4e-6)
            self.assertEqual(crystal.c_m, 4e-6)
            self.assertEqual(crystal.height_m, 3000)
        crystals[0].height_m = 2900
        self.assertEqual(crystals[1].height_m, 3000)

    def test_seeding_creates_separate_trajectories_without_changing_growth(self):
        small = Cloud(self.env, [self.ice])
        large = Cloud(self.env, [self.ice])
        small.seed(3000, 35e6, 1e-3)
        large.seed(3000, 70e6, 1e-3)
        a, b = small.simulate(7200), large.simulate(7200)
        # 25.3188 rounds to 25; doubling gives 50.6376, which rounds to 51
        self.assertEqual(a[0], b[0])
        self.assertEqual(len(a), 26)
        self.assertEqual(len(b), 52)
        self.assertEqual(len({id(t) for t in a}), 26)
        self.assertEqual(len({id(t.mass_kg) for t in a}), 26)
        self.assertEqual(a[1].origin, "seeded")
        self.assertEqual(a[1].mass_kg, b[1].mass_kg)
        self.assertEqual(a[1].height_m, b[1].height_m)
        self.assertAlmostEqual(sum(t.mass_kg[-1] for t in a[1:]) / a[1].mass_kg[-1], 25)
        # rerunning the cloud doesn't activate another batch of AgI
        self.assertEqual(a, small.simulate(7200))
        self.assertEqual(len(small.seeded_crystals), 25)

    def test_zero_dose_and_inactive_conditions_add_no_crystals(self):
        cases = ((self.env, 0), (replace(self.env, relative_humidity_water=0.5), 35e6),
                 (replace(self.env, reference_temperature_k=270), 35e6))
        for env, concentration in cases:
            with self.subTest(concentration=concentration, env=env):
                cloud = Cloud(env, [self.ice])
                self.assertEqual(cloud.seed(3000, concentration, 1e-3), [])
                self.assertEqual(cloud.seeded_crystals, [])
                self.assertEqual(cloud.crystals, [self.ice])

    def test_rounding_volume_scaling_and_fresh_bursts(self):
        cloud = Cloud(self.env, [])
        self.assertEqual(cloud.seed(3000, 35e6, 1e-6), [])
        first = cloud.seed(3000, 35e6, 1e-3)
        second = cloud.seed(3000, 35e6, 2e-3)
        self.assertEqual(len(first), 25)
        self.assertEqual(len(second), 51)
        self.assertEqual(len(cloud.seeded_crystals), 76)
        self.assertEqual(Cloud(self.env, []).seeded_crystals, [])
        # isolate the count conversion to test exact half-integer ties
        with patch("model.deposition_nucleation_fraction", return_value=0.5):
            self.assertEqual(len(cloud.seed(3000, 5, 1)), 2)
            self.assertEqual(len(cloud.seed(3000, 7, 1)), 4)

    def test_invalid_seeding_inputs_leave_cloud_unchanged(self):
        cloud = Cloud(self.env, [])
        for height, concentration, volume in ((2000, 1, 1), (4500, 1, 1), (3000, -1, 1),
                                               (3000, 1, 0), (3000, float("nan"), 1)):
            with self.subTest(height=height, concentration=concentration, volume=volume):
                with self.assertRaises(ValueError):
                    cloud.seed(height, concentration, volume)
                self.assertEqual(cloud.seeded_crystals, [])


if __name__ == "__main__":
    unittest.main()
