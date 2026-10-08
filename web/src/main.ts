import './style.css';
import { samplePopulation, type SimulationData, type Trajectory } from './trajectory';

// These are drawing settings, not inputs to the Python model yet.
const scene = {
  groundHeightM: 0,
  axisTopM: 3000,
  cloudBaseM: 2000,
  cloudTopM: 3000,
  tickSpacingM: 500,
  cloudWidthPx: 420,
  cloudFontSize: 16,
  cloudColor: '#dbe5de',
  axisColor: '#647e72',
  labelColor: '#91a39a',
};

// The original artwork. Resize the whole drawing proportionally below.
const cloudArt = String.raw`
                        .------.
                   .---' . : .  '---.
            .-----'  . : . : . : .   '---.
         .-'  . : . : . : . : . : . : .  '-.
        / . : . : . : . : . : . : . : . :  \
    .--' . : . : . : . : . : . : . : . : . '--.
  .'  . : . : . : . : . : . : . : . : . : . :  '.
 / . : . : . : . : . : . : . : . : . : . : . : . \
( . : . : . : . : . : . : . : . : . : . : . : . : )
 \ . : . : . : . : . : . : . : . : . : . : . : . /
  '.  . : . : . : . : . : . : . : . : . : . :  .'
    '--. . : . : . : . : . : . : . : . : . .--'
        '---. . : . : . : . : . : . : .---'
             '-----------------------'
`.trimEnd().split('\n').slice(1);

const canvas = document.querySelector<HTMLCanvasElement>('#cloud-scene')!;
const context = canvas.getContext('2d');
if (!context) throw new Error('This browser does not support Canvas 2D.');
const ctx = context;
const toggle = document.querySelector<HTMLButtonElement>('#toggle')!;
const restart = document.querySelector<HTMLButtonElement>('#restart')!;
const readout = document.querySelector<HTMLOutputElement>('#readout')!;
const status = document.querySelector<HTMLParagraphElement>('#status')!;
const waterMass = document.querySelector<HTMLOutputElement>('#water-mass')!;

// 280 simulated seconds per real second; each crystal has its own journey time.
const playbackSpeed = 280;
// Preserve the original two-group timing when jumping ahead to minute 450.
const firstBatchSize = 10;
const secondBatchDelaySeconds = 8;
const initialSimulationTime = 450 * 60; // model seconds, not real seconds
document.querySelector('#speed')!.textContent = `${playbackSpeed}× speed`;
let trajectories: Trajectory[] = [];
let particleStartTimes: number[] = [];
let initialWaterMassKg = 0;
// This clock is elapsed time since opening/restarting, separate from model time.
let simulationTime = 0;
let playing = false;
let previousFrame: number | null = null;

function setPlaying(value: boolean) {
  playing = value;
  previousFrame = null;
  toggle.textContent = playing ? 'Pause' : 'Play';
}

function drawCloud(left: number, top: number, width: number, height: number, fontFamily: string) {
  ctx.font = `${scene.cloudFontSize}px ${fontFamily}`;
  const naturalWidth = Math.max(...cloudArt.map(line => ctx.measureText(line).width));
  const naturalRowHeight = scene.cloudFontSize * 1.3;
  const naturalHeight = cloudArt.length * naturalRowHeight;
  // One scale for both dimensions preserves the original cloud proportions.
  const scale = Math.min(1, width / naturalWidth, height / naturalHeight);
  const rowHeight = naturalRowHeight * scale;
  const artLeft = left + (width - naturalWidth * scale) / 2;
  const artTop = top + (height - naturalHeight * scale) / 2;

  ctx.font = `${scene.cloudFontSize * scale}px ${fontFamily}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = scene.cloudColor;
  cloudArt.forEach((line, row) => {
    ctx.fillText(line, artLeft, artTop + (row + 0.5) * rowHeight);
  });
  return { left: artLeft, top: artTop, rowHeight, cellWidth: ctx.measureText('M').width };
}

function drawScene() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const pixelRatio = window.devicePixelRatio || 1;

  // Keep text sharp on high-resolution displays; draw in CSS pixels below.
  const pixelWidth = Math.round(width * pixelRatio);
  const pixelHeight = Math.round(height * pixelRatio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const axisX = 64;
  const axisTop = 32;
  const axisBottom = height - 64; // room for the horizontal-axis ticks and label
  // Both the axis and the cloud use the same altitude-to-screen mapping.
  const heightToY = (metres: number) =>
    axisBottom - ((metres - scene.groundHeightM) /
      (scene.axisTopM - scene.groundHeightM)) * (axisBottom - axisTop);

  const cloudLeft = axisX + 30;
  const availableWidth = Math.max(1, width - cloudLeft - 12);
  const fontFamily = getComputedStyle(canvas).fontFamily;
  const cloudTop = heightToY(scene.cloudTopM);
  const cloudBottom = heightToY(scene.cloudBaseM);
  const cloudHeight = cloudBottom - cloudTop;
  const cloudWidth = Math.min(scene.cloudWidthPx, availableWidth * 0.9);
  const cloudX = cloudLeft + (availableWidth - cloudWidth) / 2;

  ctx.strokeStyle = scene.axisColor;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(axisX, axisTop);
  ctx.lineTo(axisX, axisBottom);
  ctx.font = `11px ${fontFamily}`;
  ctx.fillStyle = scene.labelColor;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let metres = scene.groundHeightM; metres <= scene.axisTopM; metres += scene.tickSpacingM) {
    const y = heightToY(metres);
    ctx.moveTo(axisX - 5, y);
    ctx.lineTo(axisX, y);
    ctx.fillText(`${metres} m`, axisX - 12, y);
  }
  ctx.stroke();

  // A dimensionless horizontal axis: the Python physics only models height.
  const axisRight = width - 16;
  ctx.beginPath();
  ctx.moveTo(axisX, axisBottom);
  ctx.lineTo(axisRight, axisBottom);
  ctx.textAlign = 'center';
  for (let fraction = 0; fraction <= 1; fraction += 0.25) {
    const x = axisX + fraction * (axisRight - axisX);
    ctx.moveTo(x, axisBottom);
    ctx.lineTo(x, axisBottom + 5);
    ctx.fillText(fraction.toFixed(2), x, axisBottom + 18);
  }
  ctx.stroke();
  ctx.fillText('Horizontal position (visual)', (axisX + axisRight) / 2, axisBottom + 42);

  const art = drawCloud(cloudX, cloudTop, cloudWidth, cloudHeight, fontFamily);

  if (trajectories.length) {
    const modelTime = initialSimulationTime + simulationTime;
    const population = samplePopulation(trajectories, modelTime, particleStartTimes);
    // Exclude every arrival before the scene opened, including on Restart.
    waterMass.textContent = `${((population.waterMassKg - initialWaterMassKg) * 1e9).toFixed(2)} µg`;
    let iceCount = 0;
    let liquidCount = 0;
    for (const particle of population.particles) {
      if (particle.phase === 'gone') continue;
      if (particle.phase === 'ice') iceCount++;
      else liquidCount++;

      // At its birth height, find the actual interior of the cloud's text row.
      // Keep that x position for the entire fall; only Python changes its height.
      const birthY = heightToY(particle.trajectory.height_m[0]);
      // Use all rows touched by the 16px glyph, so its edges also stay inside.
      const rowAt = (y: number) => Math.max(0, Math.min(cloudArt.length - 1,
        Math.floor((y - art.top) / art.rowHeight)));
      const birthRows = cloudArt.slice(rowAt(birthY - 8), rowAt(birthY + 8) + 1);
      const first = Math.max(...birthRows.map(line => line.search(/\S/)));
      const last = Math.min(...birthRows.map(line => line.trimEnd().length));
      const left = art.left + first * art.cellWidth + 12;
      const right = art.left + last * art.cellWidth - 12;
      const x = left + particle.trajectory.display_x_fraction * (right - left);
      ctx.font = `16px ${fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillStyle = particle.phase === 'ice' ? '#bcecff' : '#ffc58a';
      ctx.fillText(particle.phase === 'ice' ? '*' : 'o', x, heightToY(particle.height_m));
    }
    readout.textContent = `${(simulationTime / 60).toFixed(1)} min · ${iceCount + liquidCount} particles`;
    const waiting = particleStartTimes.filter(start => modelTime < start).length;
    const state = `${iceCount} ice · ${liquidCount} liquid` + (waiting ? ` · ${waiting} waiting` : '');
    if (status.textContent !== state) status.textContent = state;
  }
}

new ResizeObserver(drawScene).observe(canvas);
window.addEventListener('resize', drawScene);

toggle.addEventListener('click', () => setPlaying(!playing));
restart.addEventListener('click', () => {
  simulationTime = 0;
  toggle.disabled = false;
  setPlaying(true);
  drawScene();
});
// Returning to a hidden tab resumes from where the visitor left it.
document.addEventListener('visibilitychange', () => { previousFrame = null; });

function animate(timestamp: number) {
  if (playing && trajectories.length && !document.hidden) {
    if (previousFrame !== null) simulationTime += (timestamp - previousFrame) / 1000 * playbackSpeed;
    previousFrame = timestamp;
    drawScene();
  }
  requestAnimationFrame(animate);
}

async function loadSimulation() {
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}data/cloud.json`);
    if (!response.ok) throw new Error(`Could not load trajectory (${response.status}).`);
    const data: SimulationData = await response.json();
    if (data.schema_version !== 1 || !data.particles?.length ||
        data.particles.some(p => !(p.time_s[p.time_s.length - 1] > 0) ||
          !Number.isFinite(p.display_x_fraction) || p.display_x_fraction < 0 || p.display_x_fraction > 1)) {
      throw new Error('Unsupported or empty trajectory file.');
    }
    trajectories = data.particles;
    particleStartTimes = trajectories.map((_, index) =>
      index < firstBatchSize ? 0 : secondBatchDelaySeconds * playbackSpeed);
    initialWaterMassKg = samplePopulation(trajectories, initialSimulationTime, particleStartTimes).waterMassKg;
    // Draw the environment that actually produced the trajectory.
    scene.groundHeightM = data.environment.ground_height_m;
    scene.cloudBaseM = data.environment.cloud_base_height_m;
    scene.cloudTopM = data.environment.top_height_m;
    toggle.disabled = restart.disabled = false;
    setPlaying(!window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    drawScene();
    requestAnimationFrame(animate);
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'Could not load the simulation.';
  }
}

void loadSimulation();
