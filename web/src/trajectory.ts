// Field names and SI units match export_simulations.py.
export type Phase = 'ice' | 'liquid' | 'gone';

export interface Trajectory {
  id: string;
  display_x_fraction: number;
  time_s: number[];
  height_m: number[];
  mass_kg: number[];
  phase: Phase[];
  stop_reason: string;
  cloud_exit_time_s: number | null;
  melting_time_s: number | null;
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
  };
  particles: Trajectory[];
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
