import katex from 'katex';
import 'katex/dist/katex.min.css';
import type { SimulationData } from './trajectory';

const paper = 'https://acp.copernicus.org/articles/24/13833/2024/acp-24-13833-2024.html';
const hw = 'https://doi.org/10.1175/2010JAS3379.1';
const mk = 'https://doi.org/10.1256/qj.04.94';

// Keep this account aligned with model.py, export_simulations.py, and trajectory.ts.
// These are the equations used by the preset, not the paper's entire model.
export const equations = [
  {
    title: 'Set the temperature and available vapor',
    source: 'Prescribed environment · lapse rate from Yang, section 2.2', url: `${paper}#section2.2`,
    code: 'model.py · Environment.temperature_k / vapor_pressure_pa · simulate_crystal',
    tex: String.raw`\begin{aligned}
T(z)&=T_{\mathrm{ref}}-(z-z_{\mathrm{ref}})\times L_T\\
L_T&=0.0055\;\mathrm{K/m}=5.5\;\mathrm{K/km}\\
T(z)&=258.15-0.0055\,(z-3000)\quad\text{(preset)}\\
e(z)&=H_w\,e_{sw}(T(z))\\
S_i&=\frac{e}{e_{si}(T)},\qquad \rho_s=\frac{e_{si}(T)}{R_vT}
\end{aligned}`,
    explanation: 'Height z increases upward; T is temperature in kelvin. L_T is the fixed lapse_rate_k_per_m setting in Python, not a function: this preset uses 0.0055 K/m (0.55°C per 100 m). In the numerical preset line, z is in metres and T is in kelvin; the reference is 258.15 K (−15°C) at 3,000 m. H_w is relative humidity with respect to water (a ratio), and e is vapor pressure in pascals. The saturation pressures over ice and water are e_si and e_sw. S_i measures saturation with respect to ice; ρ_s is saturated vapor density in kg/m³. R_v = 461.5 J/(kg K). I keep relative humidity fixed at 100% relative to liquid water. Ice growth does not reduce the available moisture.',
  },
  {
    title: 'Calculate saturation pressures',
    source: 'Murphy & Koop (2005), equations (7) and (10)', url: mk,
    code: 'model.py · saturation_vapor_pressure_ice_pa / saturation_vapor_pressure_water_pa',
    tex: String.raw`\begin{aligned}
\ln e_{si}&=9.550426-\frac{5723.265}{T}\\
&\quad+3.53068\ln T-0.00728332T\\[6pt]
\ln e_{sw}&=54.842763-\frac{6763.22}{T}\\
&\quad-4.21\ln T+0.000367T\\
&\quad+\tanh\!\left(0.0415(T-218.8)\right)\\
&\qquad\cdot\left(53.878-\frac{1331.22}{T}-9.44523\ln T+0.014025T\right)
\end{aligned}`,
    explanation: 'Use numerical T in kelvin and pressures in pascals in these empirical fits; Exponentiating each result gives the pressure used above. These published coefficients are fixed in the implementation. The water fit supports 123 < T < 332 K; the ice-cloud calculation stays at or below 273.15 K.',
  },
  {
    title: 'Turn the AgI dose into new ice crystals',
    source: 'Yang, equation (1) · whole-particle rounding added here', url: `${paper}#section2.1`,
    code: 'model.py · deposition_nucleation_fraction · Cloud.seed',
    tex: String.raw`\begin{aligned}
x&=S_i-1,\qquad y=\frac{273.16-T}{10}\\
P(x,y)&=-3.25\!\times\!10^{-3}x+5.39\!\times\!10^{-5}y\\
&\quad+4.35\!\times\!10^{-2}x^2+1.55\!\times\!10^{-4}y^2-0.07x^3\\
F_{\mathrm{dep}}&=\begin{cases}P(x,y),&T<268.2\;\mathrm{K},\ S_i>1.04\\0,&\text{otherwise in this model}\end{cases}\\
N_{\mathrm{AgI}}&=n_{\mathrm{AgI}}V_{\mathrm{seed}}\\
N_{\mathrm{ice}}&=\operatorname{round}_{\mathrm{even}}(F_{\mathrm{dep}}N_{\mathrm{AgI}})
\end{aligned}`,
    explanation: 'I use P(x,y) as a short name for the polynomial in Yang’s equation (1). It combines two dimensionless inputs: x = S_i − 1 measures the vapor excess above ice saturation (S_i = 1.10 gives x = 0.10, or 10% excess), and y = (273.16 − T)/10 measures cooling below the reference temperature in units of 10 K. The fixed coefficients are from the published empirical fit; I did not tune them. When the temperature and saturation conditions shown above are met, P gives F_dep: the fraction of AgI particles that nucleate ice. Its output is a fraction, not a crystal count or a growth rate.',
    extra: 'For example, the exported 2,500 m layer has P ≈ 0.000443, meaning about 0.0443% of its AgI activates. Concentration n_AgI times seeded air volume V_seed gives about 11,666.7 AgI particles in that layer. Multiplying by the fraction gives 5.17 expected crystals, which I round to 5 using Python’s ties-to-even rule. I apply this calculation once per layer. Outside the stated conditions, I set F_dep to zero; this only excludes deposition nucleation in this model, not every possible way ice can form.',
  },
  {
    title: 'Grow a spherical crystal',
    source: 'Yang, equation (5) · spherical, fixed-density approximation', url: `${paper}#section2.2`,
    code: 'model.py · IceCrystal.mass_growth_rate_kg_s · simulate_crystal',
    tex: String.raw`\begin{aligned}
V&=\frac{4\pi}{3}a^2c=\frac{4\pi}{3}r^3,\qquad m=\rho_iV\\
r(m)&=\left(\frac{3m}{4\pi\rho_i}\right)^{1/3},\qquad C=r,\quad f_v=1\\
\frac{dm}{dt}&=\frac{4\pi C(S_i-1)f_v}
{\dfrac{L_d^2}{KR_vT^2}+\dfrac{1}{D_v\rho_s}}
\end{aligned}`,
    explanation: 'The two radii a and c remain equal to r. The solver preserves each crystal’s initial density m₀/V₀; this preset starts at 910 kg/m³. Capacitance C is the sphere radius and ventilation factor f_v is fixed at 1. The denominator accounts for heat removal and vapor diffusion. I use L_d = 2.834 × 10⁶ J/kg (latent heat), K = 0.024 W/(m K) (air conductivity), and D_v = 2.0 × 10⁻⁵ m²/s (vapor diffusivity). These are fixed approximations in this implementation. S_i < 1 produces sublimation; integration stops if mass reaches zero.',
  },
  {
    title: 'Find the fall speed and integrate the journey',
    source: 'Heymsfield & Westbrook (2010) · method cited by Yang, section 2.3', url: hw,
    code: 'model.py · IceCrystal.terminal_velocity_m_s · simulate_crystal',
    tex: String.raw`\begin{aligned}
D&=2r,\qquad A_r=1,\qquad k=0.5\\
X^*&=\frac{8\rho_a m g}{\pi\eta^2 A_r^{1-k}}\\
q&=\frac{4\sqrt{X^*}}{\delta_0^2\sqrt{C_0}}\\
\mathrm{Re}&=\frac{\delta_0^2}{4}\left(\frac{q}{\sqrt{1+q}+1}\right)^2\\
V_t&=\frac{\eta\,\mathrm{Re}}{\rho_aD},\qquad \frac{dz}{dt}=-V_t
\end{aligned}`,
    explanation: 'D is diameter, A_r the projected area ratio, ρ_a air density, η dynamic viscosity, X* the modified Best number, and Re the Reynolds number. For ice I use δ₀ = 8, C₀ = 0.35, and g = 9.81 m/s². The expression for Re is algebraically equivalent to the published square-root form, evaluated to avoid cancellation for tiny crystals. I follow the original Heymsfield–Westbrook formulation.',
    extra: 'SciPy solve_ivp integrates dm/dt and dz/dt together with adaptive RK45, recalculating the local environment as height changes. Relative tolerance is 10⁻⁷; absolute tolerances are 10⁻²² kg and 10⁻⁶ m. Cloud-base crossing and complete sublimation are terminal events.',
  },
  {
    title: 'Descend below the cloud and melt',
    source: 'My below-cloud extension · liquid sphere drag from Heymsfield & Westbrook', url: hw,
    code: 'model.py · simulate_to_ground · RainDrop',
    tex: String.raw`\begin{aligned}
\frac{dm}{dt}&=0,\qquad \frac{dz}{dt}=-V_t\\
T(z)&\geq273.15\;\mathrm{K}\ \Longrightarrow\ \mathrm{ice}\to\mathrm{liquid}\\
m_{\mathrm{liquid}}&=m_{\mathrm{ice}},\qquad
r_w=\left(\frac{3m}{4\pi\rho_w}\right)^{1/3}\\
\rho_w&=1000\;\mathrm{kg\,m^{-3}},\qquad \delta_0=9.06,\quad C_0=0.292
\end{aligned}`,
    explanation: 'After cloud exit, mass stays constant: growth, sublimation, and evaporation are switched off. Ice melts instantly at 0°C with mass conserved. The liquid radius r_w uses water density, then the fall-speed equations above use the liquid sphere constants shown here and A_r = 1. Speed is constant within each below-cloud phase because mass and air properties are fixed. The drop approximation requires Re < 10⁴. The journey ends at ground.',
  },
  {
    title: 'Turn saved samples into animation frames',
    source: 'My export and browser playback',
    code: 'model.py · simulate_to_ground / record_segment · export_simulations.py · main · web/src/trajectory.ts · sampleTrajectory',
    tex: String.raw`\begin{aligned}
\alpha&=\frac{t-t_j}{t_{j+1}-t_j}\\
z(t)&=(1-\alpha)z_j+\alpha z_{j+1}\\
m(t)&=(1-\alpha)m_j+\alpha m_{j+1}\\
\mathrm{phase}(t)&=\mathrm{phase}_j\qquad (t_j\leq t<t_{j+1})
\end{aligned}`,
    explanation: 'α (alpha) tells me how far the animation is between two saved samples. It is a fraction with no units: 0 means the earlier sample, 0.5 means halfway, and 1 means the later sample. For example, between samples at 20 and 30 seconds, a playback age of 25 seconds gives α = (25 − 20)/(30 − 20) = 0.5. Height and mass are then halfway between their saved values. The gap between samples is 10 seconds in this example; α is the progress through that gap, not a time step.',
    extra: 'The Python model samples the solver’s continuous solution every 10 seconds within each stage and includes exact stage endpoints; the exporter writes those samples to JSON. Event endpoints can make the gaps shorter. These saved intervals are separate from the solver’s adaptive step size. For each browser frame, t is the particle’s playback age; j is its last saved sample. Height and mass interpolate linearly; phase changes only at a saved transition. At the final sample the endpoint is used directly.',
  },
  {
    title: 'Add up liquid water arriving at ground',
    source: 'My display counter · arrivals from replayed trajectories',
    code: 'web/src/trajectory.ts · samplePopulation / sampleBurst · web/src/main.ts · drawScene',
    tex: String.raw`\text{Collected water mass}
=\sum_{\text{liquid arrivals since start}}\text{particle mass}`,
    explanation: 'I count each liquid arrival at ground and display the total in micrograms.',
  },
];

export function renderEquations() {
  const list = document.querySelector<HTMLDivElement>('#equation-list')!;
  for (const [index, equation] of equations.entries()) {
    const article = document.createElement('article');
    article.className = 'equation-card';
    const heading = document.createElement('h3');
    heading.textContent = `${String(index + 1).padStart(2, '0')} / ${equation.title}`;
    article.append(heading);
    const source = document.createElement(equation.url ? 'a' : 'span');
    source.className = 'equation-source';
    source.textContent = equation.source;
    if (source instanceof HTMLAnchorElement && equation.url) {
      source.href = equation.url;
      source.target = '_blank';
      source.rel = 'noopener noreferrer';
    }
    article.append(source);
    const math = document.createElement('div');
    math.className = 'equation-math';
    math.tabIndex = 0;
    math.setAttribute('role', 'region');
    math.setAttribute('aria-label', `${equation.title}: equation`);
    katex.render(equation.tex, math, { displayMode: true, throwOnError: true, output: 'htmlAndMathml' });
    article.append(math);
    for (const text of [equation.explanation, equation.extra].filter(Boolean)) {
      const p = document.createElement('p');
      p.textContent = text!;
      article.append(p);
    }
    const location = document.createElement('p');
    location.className = 'code-location';
    const code = document.createElement('code');
    code.textContent = equation.code;
    location.append('Implemented in ', code);
    article.append(location);
    const details = document.createElement('details');
    details.className = 'latex-source';
    const summary = document.createElement('summary');
    summary.textContent = 'View LaTeX source';
    const pre = document.createElement('pre');
    const latex = document.createElement('code');
    latex.textContent = equation.tex;
    pre.append(latex);
    details.append(summary, pre);
    article.append(details);
    list.append(article);
  }
}

export function renderProvenance(data: SimulationData) {
  const env = data.environment;
  const sim = data.simulation;
  const burst = data.seeding_burst;
  document.querySelector('#preset-summary')!.textContent =
    `${data.particles.length} background trajectories and ${burst.crystal_count} seeded trajectories, generated in Python. ` +
    `Each trajectory runs for up to ${sim.duration_s / 60} minutes, with samples every ${sim.sample_interval_s} seconds plus exact transition endpoints.`;
  const settings = [
    ['Cloud altitude', `${env.cloud_base_height_m.toLocaleString()}–${env.top_height_m.toLocaleString()} m`],
    ['Reference temperature', `${env.reference_temperature_k} K at ${env.reference_height_m.toLocaleString()} m`],
    ['Lapse rate', `${env.lapse_rate_k_per_m * 1000} K/km`],
    ['Water-relative humidity', `${env.relative_humidity_water * 100}%`],
    ['Air density', `${sim.air_density_kg_m3} kg/m³`],
    ['Air viscosity', `${sim.dynamic_viscosity_pa_s.toExponential(2)} Pa s`],
  ];
  const dl = document.createElement('dl');
  for (const [label, value] of settings) {
    const div = document.createElement('div');
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = label;
    dd.textContent = value;
    div.append(dt, dd);
    dl.append(div);
  }
  document.querySelector('#preset-settings')!.replaceChildren(dl);
  document.querySelector('#burst-explanation')!.textContent =
    `${burst.injection.agi_concentration_per_m3 / 1e6} AgI particles/cm³ × ` +
    `${burst.injection.seeded_volume_m3 * 1000} litre of air = ${burst.agi_particle_count.toLocaleString()} AgI particles. ` +
    `The air volume is shared equally across ${burst.layers.length} layers. Local temperature and ice saturation determine ` +
    `the fraction activated in each layer; rounding each layer gives ${burst.crystal_count} crystals in total. This is a chosen demo dose.`;
  const rows = burst.layers.map(layer => {
    const row = document.createElement('tr');
    for (const value of [layer.injection.height_m.toLocaleString(), layer.temperature_k.toFixed(3),
      layer.ice_saturation_ratio.toFixed(5), layer.nucleation_fraction.toFixed(8),
      layer.expected_crystal_count.toFixed(4), String(layer.crystal_count)]) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    }
    return row;
  });
  document.querySelector('#seeding-layers')!.replaceChildren(...rows);
  document.querySelector<HTMLAnchorElement>('#download-data')!.href = `${import.meta.env.BASE_URL}data/cloud.json`;
}
