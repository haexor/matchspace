// Spielerprofil: FIFA-artige Werte (0 bis 99) je Spieler und was daraus körperlich folgt (Tempo, Beschleunigung, Wendigkeit, Sprunghöhe, Ausdauer, Schusskraft, Ballbindung).
// Heute gilt für alle dasselbe Profil (DEFAULT_RATINGS); später stehen die Werte je Spieler in der Szene (`entity.profile.ratings`, errechnet aus gemessenen Spielen,
// tools/player_rating.py) und jeder bewegt sich anders. Die Umrechnung ist stetig und monoton: ein höherer Wert ist nie langsamer, springt nie niedriger.

export const ATTRIBUTES = [
  ['pace', 'Tempo'], ['acceleration', 'Beschleunigung'], ['agility', 'Wendigkeit'], ['jumping', 'Sprungkraft'], ['stamina', 'Ausdauer'],
  ['dribbling', 'Dribbling'], ['tackling', 'Zweikampf'], ['shooting', 'Schuss'], ['passing', 'Passspiel'],
];
export const DEFAULT_RATINGS = Object.fromEntries(ATTRIBUTES.map(([key]) => [key, 70]));
const GRAVITY = 9.81;

const lerp = (a, b, t) => a + (b - a) * Math.min(1, Math.max(0, t));

/** Werte eines Spielers: Voreinstellung, überschrieben von `entity.profile.ratings` (jeder Wert 0 bis 99). */
export function ratingsOf(entity) {
  return { ...DEFAULT_RATINGS, ...(entity?.profile?.ratings ?? {}) };
}

/** Körperliche Größen aus den Werten. Geschwindigkeiten in m/s, Beschleunigung in m/s², Drehrate in rad/s, Zeiten in s. */
export function physicsOf(ratings) {
  const r = (key) => (ratings[key] ?? 70) / 99;
  const sprintSpeed = lerp(4.6, 8.8, r('pace'));      // Jugend: Wert 70 etwa 26 km/h, 99 etwa 32 km/h
  const jumpHeight = lerp(0.3, 0.9, r('jumping'));
  return {
    sprintSpeed,
    jogSpeed: 0.62 * sprintSpeed,                       // Laufen ohne Umschalt-Taste
    acceleration: lerp(4.0, 9.5, r('acceleration')),
    braking: lerp(7.0, 13.0, r('agility')),
    turnRate: lerp(6.0, 15.0, r('agility')),
    jumpHeight,
    jumpSpeed: Math.sqrt(2 * GRAVITY * jumpHeight),     // Abfluggeschwindigkeit für diese Sprunghöhe
    gravity: GRAVITY,
    sprintSeconds: lerp(5.0, 22.0, r('stamina')),       // so lange hält ein voller Atem im Sprint
    recoverSeconds: lerp(14.0, 6.0, r('stamina')),      // so lange dauert das volle Erholen im Stehen/Traben
    shotSpeed: lerp(11.0, 26.0, r('shooting')),
    touch: lerp(0.35, 0.95, r('dribbling')),            // Ballbindung: wie eng der Ball am Fuß bleibt (0 = weit weg, 1 = am Fuß)
  };
}
