// Bewegung eines gesteuerten Spielers auf dem Platz: Beschleunigung, Drehung, Sprint mit Ausdauer, Sprung und ein einfacher Ball.
// Reine Rechnung (keine Grafik): Zustand rein, Eingabe rein, neuer Zustand. Die Werte kommen aus web/profile.js (je Spieler verschieden einstellbar).

export function createMover(x = 0, z = 0, heading = Math.PI / 2) {
  return { x, z, vx: 0, vz: 0, heading, y: 0, vy: 0, grounded: true, phase: 0, air: 0, stamina: 1, sprinting: false, landed: 0 };
}

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

/**
 * Ein Zeitschritt. input: { dx, dz } Wunschrichtung in Weltkoordinaten (Länge 0 bis 1), sprint, jump (bool). ph: physicsOf(). bounds: { x, z } Halbmaße des begehbaren Bereichs (m).
 * Läuft in der Luft nur mit einem Drittel der Beschleunigung weiter (der Absprung legt die Richtung fest).
 */
export function stepMover(m, input, ph, dt, bounds) {
  const want = Math.min(1, Math.hypot(input.dx, input.dz));
  const sprint = input.sprint && m.stamina > 0.02 && want > 0.1;
  const top = want * (sprint ? ph.sprintSpeed : ph.jogSpeed);
  const ux = want > 0 ? input.dx / Math.hypot(input.dx, input.dz) : 0, uz = want > 0 ? input.dz / Math.hypot(input.dx, input.dz) : 0;
  const tx = ux * top, tz = uz * top;
  const speedUp = (tx * tx + tz * tz) > (m.vx * m.vx + m.vz * m.vz) ? ph.acceleration : ph.braking;
  const control = m.grounded ? 1 : 0.33;
  const dvx = tx - m.vx, dvz = tz - m.vz, dv = Math.hypot(dvx, dvz), step = Math.min(dv, speedUp * control * dt);
  if (dv > 1e-6) { m.vx += dvx / dv * step; m.vz += dvz / dv * step; }
  m.x = Math.min(bounds.x, Math.max(-bounds.x, m.x + m.vx * dt));
  m.z = Math.min(bounds.z, Math.max(-bounds.z, m.z + m.vz * dt));
  const speed = Math.hypot(m.vx, m.vz);
  if (speed > 0.4) {
    const turn = wrap(Math.atan2(m.vx, m.vz) - m.heading);
    m.heading = wrap(m.heading + Math.sign(turn) * Math.min(Math.abs(turn), ph.turnRate * dt));
  }
  // Sprung
  if (input.jump && m.grounded) { m.vy = ph.jumpSpeed; m.grounded = false; }
  if (!m.grounded) {
    m.vy -= ph.gravity * dt;
    m.y += m.vy * dt;
    if (m.y <= 0) { m.y = 0; m.landed = Math.min(1, -m.vy / 4); m.vy = 0; m.grounded = true; }
  } else {
    m.landed = Math.max(0, m.landed - dt * 4);
  }
  m.air += ((m.grounded ? 0 : 1) - m.air) * Math.min(1, dt * 12);
  // Ausdauer
  m.sprinting = sprint;
  m.stamina = Math.min(1, Math.max(0, m.stamina + (sprint ? -dt / ph.sprintSeconds : dt / ph.recoverSeconds * (speed < ph.jogSpeed * 1.1 ? 1 : 0.4))));
  // Schrittphase: schneller laufen, schneller wechseln
  const norm = Math.min(1.25, speed / ph.sprintSpeed);
  m.phase = (m.phase + dt * 2 * Math.PI * (speed < 0.2 ? 0 : 0.8 + 1.3 * norm)) % (2 * Math.PI);
  return m;
}

export function createBall(x = 0, z = 0) {
  return { x, z, y: 0.11, vx: 0, vz: 0, vy: 0, roll: 0 };
}

/** Ball: rollt und bremst, prallt am Boden, wird beim Laufen vor dem Fuß mitgenommen (Ballbindung `ph.touch`) und mit `shoot` in Blickrichtung geschossen. */
export function stepBall(b, m, ph, dt, shoot, bounds) {
  const dx = b.x - m.x, dz = b.z - m.z, dist = Math.hypot(dx, dz);
  const fx = Math.sin(m.heading), fz = Math.cos(m.heading);
  const ahead = dist > 1e-6 ? (dx * fx + dz * fz) / dist : 0;
  const speed = Math.hypot(m.vx, m.vz);
  if (shoot && dist < 1.1 && m.y < 0.5) {
    b.vx = fx * ph.shotSpeed; b.vz = fz * ph.shotSpeed; b.vy = 0.12 * ph.shotSpeed;
  } else if (dist < 0.75 && ahead > 0.2 && speed > 0.5 && m.y < 0.4) {
    // Ball vor dem Fuß: Er läuft mit, bei hoher Ballbindung dicht davor (0,45 m), bei niedriger weiter weg und springt vor
    const stick = ph.touch, target = 0.45 + (1 - stick) * 0.5;
    const gx = m.x + fx * target, gz = m.z + fz * target;
    b.vx += (gx - b.x) * 9 * dt * stick + (m.vx - b.vx) * Math.min(1, 6 * dt * stick);
    b.vz += (gz - b.z) * 9 * dt * stick + (m.vz - b.vz) * Math.min(1, 6 * dt * stick);
  } else if (dist < 0.42 && speed < 0.5) {
    const push = (0.42 - dist) * 6;
    b.vx += (dx / Math.max(dist, 1e-3)) * push * dt * 10; b.vz += (dz / Math.max(dist, 1e-3)) * push * dt * 10;
  }
  b.vy -= 9.81 * dt;
  b.y += b.vy * dt;
  if (b.y <= 0.11) { b.y = 0.11; b.vy = b.vy < -1 ? -b.vy * 0.5 : 0; }
  const grounded = b.y <= 0.115, drag = grounded ? 0.55 : 0.05;
  b.vx -= b.vx * drag * dt; b.vz -= b.vz * drag * dt;
  b.x += b.vx * dt; b.z += b.vz * dt;
  if (Math.abs(b.x) > bounds.x) { b.x = Math.sign(b.x) * bounds.x; b.vx *= -0.4; }
  if (Math.abs(b.z) > bounds.z) { b.z = Math.sign(b.z) * bounds.z; b.vz *= -0.4; }
  b.roll = Math.hypot(b.vx, b.vz);
  return b;
}
