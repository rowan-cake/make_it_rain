// Visual timing is in real playback seconds, independent of the physics speed.
export const fairySettings = {
  flyInSeconds: 1.25,
  sprinkleSeconds: 1.5,
  flyOutSeconds: 1.25,
  widthPx: 200,
};

export const fairyDurationSeconds =
  fairySettings.flyInSeconds + fairySettings.sprinkleSeconds + fairySettings.flyOutSeconds;

export function fairyStage(seconds: number) {
  if (seconds < fairySettings.flyInSeconds) return 'Flying in…';
  if (seconds < fairySettings.flyInSeconds + fairySettings.sprinkleSeconds) return 'Sprinkling…';
  if (seconds < fairyDurationSeconds) return 'Flying away…';
  return 'Done';
}

interface FairyScene {
  width: number;
  cloudCenterX: number;
  cloudTopY: number;
  cloudWidth: number;
  cloudHeight: number;
  fontFamily: string;
}

export function drawFairy(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  seconds: number,
  scene: FairyScene,
) {
  if (seconds < 0 || seconds >= fairyDurationSeconds) return;
  const spriteWidth = Math.min(fairySettings.widthPx, scene.width * 0.45);
  const spriteHeight = spriteWidth * image.naturalHeight / image.naturalWidth;
  // Her outstretched hand is on the left. Position it over the cloud's centre.
  const hoverX = scene.cloudCenterX + spriteWidth * 0.25;
  const hoverY = scene.cloudTopY - spriteHeight / 2 - 12;
  const sprinkleStart = fairySettings.flyInSeconds;
  const exitStart = sprinkleStart + fairySettings.sprinkleSeconds;
  const mix = (a: number, b: number, fraction: number) => a + (b - a) * fraction;
  let x = hoverX;
  let y = hoverY;
  let tilt = 0;

  if (seconds < sprinkleStart) {
    const progress = seconds / sprinkleStart;
    const ease = 1 - (1 - progress) ** 3;
    x = mix(scene.width + spriteWidth, hoverX, ease);
    y = mix(hoverY - 25, hoverY, ease) - Math.sin(progress * Math.PI) * 12;
    tilt = -0.1 * (1 - ease);
  } else if (seconds < exitStart) {
    const shake = Math.sin((seconds - sprinkleStart) * Math.PI * 8);
    x += shake * 3;
    y += Math.sin((seconds - sprinkleStart) * Math.PI * 4) * 2;
    tilt = shake * 0.06;
  } else {
    const progress = (seconds - exitStart) / fairySettings.flyOutSeconds;
    const ease = progress * progress;
    x = mix(hoverX, -spriteWidth, ease);
    y = mix(hoverY, hoverY - 35, ease);
    tilt = -0.12 * progress;
  }

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(tilt);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(image, -spriteWidth / 2, -spriteHeight / 2, spriteWidth, spriteHeight);
  ctx.restore();

  // These falling dots illustrate AgI delivery; they do not add simulated ice.
  // The particle birth event happens once, after the entire animation finishes.
  ctx.save();
  ctx.font = `13px ${scene.fontFamily}`;
  ctx.textAlign = 'center';
  ctx.fillStyle = '#f5e4b9';
  const dotLifetime = 0.7;
  const dotCount = 30;
  for (let i = 0; i < dotCount; i++) {
    const birth = sprinkleStart + i / (dotCount - 1) * fairySettings.sprinkleSeconds;
    const age = seconds - birth;
    if (age < 0 || age > dotLifetime) continue;
    const progress = age / dotLifetime;
    const handX = hoverX - spriteWidth * 0.33;
    const handY = hoverY - spriteHeight * 0.15;
    const spread = Math.sin(i * 2.4) * scene.cloudWidth * 0.3;
    ctx.globalAlpha = 1 - progress * 0.65;
    ctx.fillText(i % 4 === 0 ? '+' : '.', handX + spread * progress,
      mix(handY, scene.cloudTopY + scene.cloudHeight * 0.35, progress * progress));
  }
  ctx.restore();
}
