import './style.css';

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
}

function drawScene() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const pixelRatio = window.devicePixelRatio || 1;

  // Keep text sharp on high-resolution displays; draw in CSS pixels below.
  canvas.width = Math.round(width * pixelRatio);
  canvas.height = Math.round(height * pixelRatio);
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const axisX = 64;
  const axisTop = 32;
  const axisBottom = height - 32;
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

  drawCloud(cloudX, cloudTop, cloudWidth, cloudHeight, fontFamily);
}

// The first scene is static, so only redraw when the window or canvas changes.
new ResizeObserver(drawScene).observe(canvas);
window.addEventListener('resize', drawScene);
