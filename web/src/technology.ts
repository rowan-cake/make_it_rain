import { mount } from 'ascii.rest';
import { python, typescript, html, css, vercel } from 'ascii.rest/pieces';

// Bundle the five pieces locally. The library pauses offscreen and honors reduced motion.
const pieces = { python, typescript, html, css, vercel };
const stops = Object.entries(pieces).map(([name, piece]) => {
  const canvas = document.querySelector<HTMLCanvasElement>(`#tech-${name}`)!;
  return mount(canvas, piece, { fps: 20 });
});

if (import.meta.hot) {
  import.meta.hot.dispose(() => stops.forEach(stop => stop()));
}
