// Originalvideo unter der Szene (optional): läuft im Takt der Szene, damit man Bild für Bild vergleichen kann.
// Nur wenn meta.reference gesetzt ist (tools/scene_reference.py). Das Video bleibt lokal neben den Szenendaten.

const $ = (id) => document.getElementById(id);
const DRIFT_S = 0.12;     // so weit darf das Video von der Szene abweichen, bevor nachgestellt wird
const SHARE = 0.4;        // Anteil der Fensterhöhe für das Original

export function createReference(meta, base, query) {
  const ref = meta.reference;
  const box = $('ref');
  const video = $('refVideo');
  if (!ref || query.get('ref') === '0') return { height: () => 0, sync() {}, available: false, resized() {} };

  let on = true;
  video.src = base + ref.file;
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  document.body.classList.add('split');
  box.hidden = false;

  const toggle = $('refToggle');
  toggle.hidden = false;
  toggle.addEventListener('click', () => {
    on = !on;
    box.hidden = !on;
    document.body.classList.toggle('split', on);
    toggle.setAttribute('aria-pressed', String(on));
    window.dispatchEvent(new Event('resize'));
  });

  return {
    available: true,
    /** Höhe der Fläche, die das Original oben vom Fenster abzieht (ohne Leiste unten). */
    height: () => (on ? Math.round(innerHeight * SHARE) : 0),
    resized() { box.style.height = `${this.height()}px`; },
    /** Video auf Szenenbild `frame` bringen; `playing`/`speed` wie in der Szene. */
    sync(frame, playing, speed) {
      if (!on) return;
      const want = Math.max(0, frame - ref.startFrame) / ref.fps;
      if (playing) {
        if (video.playbackRate !== speed) video.playbackRate = Math.min(16, Math.max(0.0625, speed));
        if (video.paused) video.play().catch(() => {});
        if (Math.abs(video.currentTime - want) > DRIFT_S) video.currentTime = want;
      } else {
        if (!video.paused) video.pause();
        if (Math.abs(video.currentTime - want) > 0.5 / ref.fps) video.currentTime = want;
      }
    },
  };
}
