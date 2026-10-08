import unittest
from dataclasses import replace
from math import pi, sqrt

import numpy as np

from model import (
    Environment, IceCrystal, RainDrop, simulate_crystal, simulate_to_ground,
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


if __name__ == "__main__":
    unittest.main()
