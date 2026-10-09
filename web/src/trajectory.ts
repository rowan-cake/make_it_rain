// Field names and SI units match export_simulations.py.
export type Phase = 'ice' | 'liquid' | 'gone';

export interface Trajectory {
  id: string;
  origin: 'background' | 'seeded';
  display_x_fraction: number;
  time_s: number[];
  height_m: number[];
  mass_kg: number[];
  phase: Phase[];
  stop_reason: string;
  cloud_exit_time_s: number | null;
  melting_time_s: number | null;
}

// A seeding burst runs once. Its clock is relative to the button click, and
// particles disappear at their endpoint instead of wrapping around to age zero.
export function sampleBurst(trajectories: Trajectory[], age: number) {
  let waterMassKg = 0;
  const particles = trajectories.flatMap(trajectory => {
    if (age < 0) return [];
    const last = trajectory.time_s.length - 1;
    if (age >= trajectory.time_s[last]) {
      if (trajectory.stop_reason === 'ground' && trajectory.phase[last] === 'liquid') {
        waterMassKg += trajectory.mass_kg[last];
      }
      return [];
    }
    return [{ trajectory, ...sampleTrajectory(trajectory, age) }];
  });
  return { particles, waterMassKg };
}

export interface SeedingBurst {
  injection: {
    heights_m: number[];
    agi_concentration_per_m3: number;
    seeded_volume_m3: number;
  };
  crystal_count: number;
  agi_particle_count: number;
  layers: {
    injection: { height_m: number };
    temperature_k: number;
    ice_saturation_ratio: number;
    nucleation_fraction: number;
    expected_crystal_count: number;
    crystal_count: number;
  }[];
  time_reference: 'seconds_since_injection';
  repeat: false;
  particles: Trajectory[];
}

// Each particle's clock starts at its scheduled birth. Subsequent loops use
// that same clock, so a delayed birth stays offset on every replay.
export function samplePopulation(trajectories: Trajectory[], time: number, startTimes: number[] = []) {
  let waterMassKg = 0;
  const particles = trajectories.flatMap((trajectory, index) => {
    const age = time - (startTimes[index] ?? 0);
    if (age < 0) return []; // not born yet: nothing to draw or add to the counter
    const last = trajectory.time_s.length - 1;
    const duration = trajectory.time_s[last];
    const completed = Math.floor(age / duration);
    if (trajectory.stop_reason === 'ground' && trajectory.phase[last] === 'liquid') {
      waterMassKg += completed * trajectory.mass_kg[last];
    }
    return [{ trajectory, ...sampleTrajectory(trajectory, age % duration) }];
  });
  return { particles, waterMassKg };
}

export interface SimulationData {
  schema_version: number;
  environment: {
    ground_height_m: number;
    cloud_base_height_m: number;
    top_height_m: number;
    reference_height_m: number;
    reference_temperature_k: number;
    lapse_rate_k_per_m: number;
    relative_humidity_water: number;
  };
  simulation: {
    duration_s: number;
    sample_interval_s: number;
    air_density_kg_m3: number;
    dynamic_viscosity_pa_s: number;
  };
  particles: Trajectory[];
  seeding_burst: SeedingBurst;
}

export function sampleTrajectory(trajectory: Trajectory, time: number) {
  const times = trajectory.time_s;
  // Find the last saved sample at or before this time, including exact events.
  let low = 0;
  let high = times.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (times[middle] <= time) low = middle;
    else high = middle - 1;
  }
  const next = Math.min(low + 1, times.length - 1);
  const fraction = next === low ? 0 :
    Math.max(0, Math.min(1, (time - times[low]) / (times[next] - times[low])));
  const interpolate = (values: number[]) => values[low] + fraction * (values[next] - values[low]);
  return {
    height_m: interpolate(trajectory.height_m),
    mass_kg: interpolate(trajectory.mass_kg),
    // Phase is discrete: switch at the event, never blend ice and liquid.
    phase: trajectory.phase[low],
  };
}
