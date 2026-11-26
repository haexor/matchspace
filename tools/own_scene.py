"""Szenenauswertung ohne Veo: eigene Spuren mit Mannschaft, Rückennummer oder Name, eigener Ball.

Wird von tools/veo_scene.py aufgerufen, wenn statt Veo-Angaben "-" übergeben wird. Grundlage sind das eigene
Spielertracking (tools/track_players.py), die selbst gelesenen Rückennummern (tools/jersey_reader.py,
tools/jersey_identity.py), das Verbinden von Spurstücken derselben Person (tools/identity_link.py, mit dem
Aussehen aus tools/appearance.py) und die eigene Ballspur (tools/veo_ball.py).
"""
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import identity_link  # noqa: E402
import jersey_identity  # noqa: E402
import track_players  # noqa: E402

BALL_GAP = 2.0        # s: so lange Lücken der eigenen Ballspur werden gerade überbrückt
BALL_REACH = 0.9      # m: so nah an einer Fußspitze gilt der Ball als am Fuß
MAX_LATERAL = 0.12    # m: so weit zieht der Ball höchstens quer zur Blickrichtung an einen Fuß (dort stimmt sein Pixel)
MAX_RADIAL = 0.6      # m: und in Blickrichtung (dort ist die Tiefe ungenau)
BALL_AT_FOOT = 0.13   # m: Abstand Ballmitte zur Fußspitze bei Ballkontakt
TEAM_OF_COLOUR = {0: "own", 1: "opponent", 2: "referee"}   # Trikotfarben des Heimspiels (tools/veo_colors.py): rot = wir
KEEPER_INSIDE = 1.5   # m: so weit innerhalb der Linien muss eine solche Spur im Mittel liegen (Trainer, Betreuer stehen an der Linie)
KEEPER_MIN = 5.0      # s: so lange muss eine Spur in unbekannter Farbe auf dem Platz sein, um als Torwart zu gelten
MIN_APPEARANCE = 0.5  # s: kürzere Auftritte einer Figur entfallen
OWN_SAME = 0.6        # m: zwei eigene Spuren derselben Mannschaft näher als das sind dieselbe Person
OWN_GAP = 1.0         # s: so lange Lücken einer eigenen Spur werden überbrückt
OWN_ID = 1000         # Spuren ohne Rückennummer: Nummern ab hier (nur intern, nicht auf dem Trikot)


def _nan_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Zusammenhängende wahre Abschnitte [a, b) einer Bool-Folge."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def own_ball(out: np.ndarray, max_gap: float) -> np.ndarray:
    """Ballspur aus dem Video im Takt der Ausgabe (NaN = nicht gefunden). Lücken bis max_gap Bilder werden
    gerade überbrückt (der Ball rollt zwischen zwei Berührungen geradeaus; am Fuß zieht ihn später
    attach_ball heran), längere Lücken und Anfang und Ende halten die nächste bekannte Lage."""
    n_out = len(out)
    seen = np.flatnonzero(~np.isnan(out[:, 0]))
    if not len(seen):
        return out
    idx = np.arange(n_out)
    filled = np.column_stack([np.interp(idx, seen, out[seen, a]) for a in range(2)])
    for a, b in _nan_runs(np.isnan(out[:, 0])):
        inner = a > 0 and b < n_out
        if inner and b - a <= max_gap:
            continue
        # lange Lücke: in der ersten Hälfte die letzte, in der zweiten die nächste Lage halten
        before = out[a - 1] if a > 0 else out[b] if b < n_out else filled[a]
        after = out[b] if b < n_out else before
        mid = (a + b) // 2
        filled[a:mid], filled[mid:b] = before, after
    return filled


def attach_ball(ball_xy: np.ndarray, feet: np.ndarray, fps: float, active: np.ndarray | None = None, eye: np.ndarray | None = None) -> np.ndarray:
    """Zieht den Ball an den Fuß, wenn er in Reichweite liegt: Die Ballspur ist in Blickrichtung auf rund einen halben Meter
    genau, ein geführter Ball lag deshalb oft neben dem Spieler. feet: (T, F, 2) Fußspitzen aller Spieler (NaN = keiner).
    active: Bilder, in denen herangezogen wird (rund um erkannte Kontakte, tools/ball_events.py); None = überall.
    eye: Kamera (x, y). Mit ihr wird das Heranziehen begrenzt: Quer zur Blickrichtung ist der Ball auf wenige Zentimeter genau (sein Pixel), nur in der Tiefe
    ungenau; deshalb höchstens MAX_LATERAL quer und MAX_RADIAL in Blickrichtung. Ohne diese Grenze zog der Ball im Gedränge zum falschen Fuß (ein Meter daneben)."""
    T = len(ball_xy)
    shift = np.zeros((T, 2))
    for t in range(T):
        if np.isnan(ball_xy[t, 0]) or (active is not None and not active[t]):
            continue
        d = np.linalg.norm(feet[t] - ball_xy[t], axis=1)
        if np.isnan(d).all():
            continue
        k = int(np.nanargmin(d))
        if d[k] >= BALL_REACH:
            continue
        toward = (ball_xy[t] - feet[t, k]) / max(d[k], 1e-6)
        target = feet[t, k] + toward * BALL_AT_FOOT
        w = np.clip((BALL_REACH - d[k]) / (BALL_REACH - BALL_AT_FOOT), 0, 1)
        shift[t] = (target - ball_xy[t]) * (w * w * (3 - 2 * w))
        if eye is not None:
            radial = ball_xy[t] - eye
            radial = radial / max(float(np.linalg.norm(radial)), 1e-6)
            along = float(shift[t] @ radial)
            side = shift[t] - along * radial
            n_side = float(np.linalg.norm(side))
            if n_side > MAX_LATERAL:
                side = side * (MAX_LATERAL / n_side)
            shift[t] = float(np.clip(along, -MAX_RADIAL, MAX_RADIAL)) * radial + side
    kernel = np.hanning(7)[1:-1]
    kernel /= kernel.sum()
    shift = np.column_stack([np.convolve(shift[:, a], kernel, "same") for a in range(2)])   # nicht von Bild zu Bild springen
    return ball_xy + shift


def own_identities(det, cam, n, video):
    """Eigenes Tracking statt Veo (tools/track_players.py): Spuren auf dem Platz mit Mannschaft und Name.

    Personen, die meist außerhalb der Linien stehen (Auswechselspieler, Trainer, Zuschauer), zählen nicht, ebenso
    Spuren in Leibchen, die im Farbton deutlich vom Trikot ihrer Farbklasse abweichen (tools/track_players.split_bibs).
    Eine Spur in unbekannter Farbe, die lange auf dem Platz ist, gilt als Torwart; er gehört zu der Mannschaft,
    deren Feldspieler im Mittel näher an seinem Tor stehen. Rückgabe: {(Mannschaft, Nummer): (Farbe, Torwart,
    {Bild: Zeile})}."""
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    fps = det["fps"]
    kept, centre = [], {}
    result = track_players.track(det, cam)
    team = track_players.split_bibs(result, track_players.track_hues(video, result), fps)   # Leibchen der Auswechselspieler zählen nicht
    for tr in (t for t, ok in zip(result, team) if ok):
        fs = sorted(tr["frames"])
        pts = np.array([tr["frames"][f][:2] for f in fs])
        mid = np.median(pts, axis=0)
        inside = KEEPER_INSIDE if tr["colour"] < 0 else 0.0   # ohne Trikotfarbe: nicht die Leute an der Seitenlinie
        if abs(mid[0]) > L / 2 - inside or abs(mid[1]) > W / 2 - inside:
            continue
        if tr["colour"] < 0 and (fs[-1] - fs[0]) / fps < KEEPER_MIN:
            continue
        kept.append((fs[0], tr, mid))
        if tr["colour"] in (0, 1):
            centre.setdefault(tr["colour"], []).append(pts[:, 0])
    mean_x = {c: float(np.mean(np.concatenate(v))) for c, v in centre.items()}
    out, count = {}, Counter()
    for _, tr, mid in sorted(kept, key=lambda k: k[0]):
        colour, keeper = tr["colour"], tr["colour"] < 0
        if keeper:   # Torwart: Mannschaft, die im Mittel näher an seinem Tor steht
            goal = math.copysign(L / 2, mid[0])
            colour = min(mean_x, key=lambda c: abs(mean_x[c] - goal)) if mean_x else 0
        team = TEAM_OF_COLOUR.get(colour, "opponent")
        count[team] += 1
        out[(team, OWN_ID + count[team])] = (colour, keeper, tr["frames"])
    return out


def drop_same_place(obs: dict, where: list[dict]) -> int:
    """Zwei Spuren derselben Mannschaft an derselben Stelle sind eine Person: In dem Bild weicht die nur
    überbrückte Spur, sind beide gemessen, die kürzere. Ändert obs und where; gibt die Zahl entfernter
    Spieler-Bilder zurück."""
    removed = 0
    length = {key: int((~np.isnan(rows[:, 0])).sum()) for key, rows in obs.items()}
    for fi in range(len(where)):
        keys = list(where[fi])
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                ka, kb = keys[a], keys[b]
                if ka[0] != kb[0] or ka not in where[fi] or kb not in where[fi]:
                    continue
                if np.linalg.norm(where[fi][ka] - where[fi][kb]) >= OWN_SAME:
                    continue
                measured_a, measured_b = not np.isnan(obs[ka][fi, 0]), not np.isnan(obs[kb][fi, 0])
                loser = kb if (measured_a, length[ka]) >= (measured_b, length[kb]) else ka
                del where[fi][loser]
                obs[loser][fi] = np.nan
                removed += 1
    return removed


def _piece_looks(video, det_path, tracks: dict, cam, groups: dict | None = None) -> dict[str, identity_link.Look]:
    """Aussehen je Spur aus dem Zwischenspeicher (tools/appearance.py); ohne Bildmodell leer. Mit groups (Name ->
    Bild -> Zeile, etwa die Ketten des ersten Durchgangs) wird zuvor das Spielmerkmal gelernt (learn_fingerprint)."""
    import appearance   # erst hier: lädt Torch
    scene = appearance.read_scene(video, det_path)
    if scene is None:
        return {}
    where = scene.index()
    if groups:
        scene = appearance.learn_fingerprint(scene, where, groups)
    return {name: identity_link.Look(*appearance.piece_features(scene, where, frames, cam)) for name, frames in tracks.items()}


def _key(r) -> tuple[int, int]:
    return int(r[3]), int(r[8])


def write_identity(path: str | Path, players: dict, events: list[dict], numbers: dict, fps: float) -> None:
    """Zuordnung der Auswertung (specs/003-eigene-referenz/data-model.md): je Spieler seine Erkennungen als
    [Bild, Linse, Box], dazu Trennungen und Verbindungen und die besten Nummern. Keine Lagen, keine Bilder.
    players: Name -> (Mannschaft, Torwart, Nummer oder None, {Bild: Zeile}); events: mit "detections" als Anker."""
    owner, out = {}, {}
    for name, (team, keeper, number, frames) in players.items():
        dets = [[int(f), *_key(frames[f])] for f in sorted(frames)]
        for d in dets:
            owner[tuple(d)] = name
        out[name] = {"team": team, "keeper": bool(keeper), "number": number, "detections": dets}
    marked = [{**e, "players": [owner.get(tuple(d)) for d in e["detections"]]} for e in events]
    stamp = hashlib.sha1(json.dumps({n: v["detections"] for n, v in sorted(out.items())}).encode()).hexdigest()[:16]
    data = {"fps": fps, "players": out, "events": marked, "numbers": numbers, "stamp": stamp}
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _first_last(frames: dict) -> tuple[list[int], list[int]]:
    a, b = min(frames), max(frames)
    return [int(a), *_key(frames[a])], [int(b), *_key(frames[b])]


def split_and_link(identities: dict, video: str, det_path: str, cam, fps: float, scene=None,
                   squad: dict[str, frozenset[int]] | None = None, report: list[str] | None = None,
                   events: list[dict] | None = None) -> dict:
    """Eine Identität je Spieler (tools/identity_link.py): Spuren an Spurwechseln trennen (fremdes Trikot,
    verschiedene sichere Nummern an einem Kontakt), dann Stücke derselben Person verbinden. scene: gelesene
    Rücken (jersey_reader.read_scene) oder None; report: sammelt Zeilen zum Prüfen (tools/identity_link.py);
    events: sammelt Trennungen und Verbindungen mit ihren Anker-Erkennungen (für {det}.identity.json).
    Rückgabe in der Form von own_identities, neu durchnummeriert."""
    import jersey_reader   # erst hier: lädt Torch
    pieces = [identity_link.Piece(f"{key[0]}-{key[1]}", key[0], keeper, frames)
              for key, (_, keeper, frames) in identities.items()]
    colour_of = {f"{key[0]}-{key[1]}": colour for key, (colour, _, _) in identities.items()}
    team_colour = {team: c for c, team in TEAM_OF_COLOUR.items()}
    pieces = identity_link.split_by_colour(pieces, team_colour, fps)
    by_colour = len(pieces) - len(identities)
    after_colour = {p.id for p in pieces}
    found = identity_link.contacts(pieces, fps)

    def readings(ps):
        return jersey_reader.readings_for_tracks(scene, {p.id: p.frames for p in ps}) if scene is not None else []
    count = len(pieces)
    pieces = identity_link.split_by_numbers(pieces, found, readings(pieces), fps, squad)
    by_number = len(pieces) - count
    votes = jersey_identity.vote(readings(pieces), {p.id: p.team for p in pieces}, fps, squad)
    tracks = {p.id: p.frames for p in pieces}
    looks = _piece_looks(video, det_path, tracks, cam)
    log: list[identity_link.Link] = []
    numbers = {n: v.number for n, v in votes.items()}
    chains = identity_link.link(pieces, looks, numbers, fps)
    if looks:   # zweiter Durchgang: Spielmerkmal aus den Ketten des ersten lernen, dann noch einmal verbinden
        groups = {c[0]: {f: r for name in c for f, r in tracks[name].items()} for c in chains}
        looks = _piece_looks(video, det_path, tracks, cam, groups)
        chains = identity_link.link(pieces, looks, numbers, fps, log)
    else:
        chains = identity_link.link(pieces, looks, numbers, fps, log)
    by_id = {p.id: p for p in pieces}
    if events is not None:
        groups: dict[tuple[str, str], list] = {}
        for piece in pieces:   # Teile derselben Spur: an fremdem Trikot (erste Stufe) oder an Nummern getrennt
            if piece.id in after_colour:
                groups.setdefault(("colour", piece.id.split("/")[0]), []).append(piece)
            else:
                groups.setdefault(("number", piece.id.rsplit("/", 1)[0]), []).append(piece)
        for (reason, _), parts in groups.items():
            parts.sort(key=lambda q: q.start)
            for a, b in zip(parts, parts[1:]):
                events.append({"kind": "split", "frame": int(b.start), "reason": reason,
                               "detections": [_first_last(a.frames)[1], _first_last(b.frames)[0]]})
        for k in log:
            events.append({"kind": "link", "frame": int(by_id[k.start].start), "reason": "path",
                           "detections": [_first_last(by_id[k.end].frames)[1], _first_last(by_id[k.start].frames)[0]]})
    if report is not None:
        report.extend(f"Kontakt   {c.a:18s} mit {c.b:18s} Bild {c.frame:4d}, {c.distance:.2f} m" for c in found)
        report.extend(f"Stück     {p.id:18s} {p.team:8s} Bild {p.start:4d}-{p.end:4d}, Nummer {numbers.get(p.id)}"
                      for p in sorted(pieces, key=lambda p: p.id) if "/" in p.id)
        report.extend(f"verbunden {k.end:18s} -> {k.start:18s} Kosten {k.cost:5.2f}, Zweitbester {k.margin:4.1f}-mal so teuer"
                      for k in log)
        for end, best in identity_link.open_ends(chains, pieces, looks, numbers, fps):
            if best[0][0] <= identity_link.MAX_COST * identity_link.MIN_MARGIN:
                rival = f", Zweitbester {best[1][1]} {best[1][0]:.2f}" if len(best) > 1 else ""
                report.append(f"getrennt gelassen {end:18s}: bester Anfang {best[0][1]} Kosten {best[0][0]:.2f}{rival}")
    out, count_of = {}, Counter()
    for chain in sorted(chains, key=lambda c: by_id[c[0]].start):
        first = by_id[chain[0]]
        frames = {}
        for name in chain:   # bei kurzer Übergabe gilt im gemeinsamen Bild das spätere Stück
            frames.update(tracks[name])
        colour = colour_of[chain[0].split("/")[0]] if first.keeper else team_colour[first.team]
        count_of[first.team] += 1
        out[(first.team, OWN_ID + count_of[first.team])] = (colour, first.keeper, frames)
    print(f"Spurwechsel getrennt: {by_colour} an fremden Trikots, {by_number} an verschiedenen Nummern "
          f"({len(found)} Kontakte); Stücke verbunden: {len(log)}; {len(identities)} Spuren -> {len(out)} Spieler"
          f"{'' if looks else ' (ohne Aussehen)'}", flush=True)
    return out


def with_numbers(identities: dict, det: dict, video: str, det_path: str,
                 squad: dict[str, frozenset[int]] | None = None, model_path: str | Path | None = None,
                 cam=None) -> dict:
    """Rückennummern aus dem Video und eine Identität je Spieler.

    1. Spuren an Spurwechseln trennen und Stücke derselben Person verbinden (split_and_link); sichere Nummern
       je Stück helfen dabei.
    2. Je Spieler über die Lesungen aller seiner Stücke abstimmen; Spieler mit gestützter Nummer heißen
       (Mannschaft, Nummer), Spieler mit derselben Nummer werden einer.
    Ohne Nummernleser (models/jersey-digits.pt) wird nur über Trikotfarbe, Laufweg und Aussehen getrennt
    und verbunden."""
    import jersey_reader   # erst hier: lädt Torch
    fps = det["fps"]
    model_path = Path(model_path or jersey_reader.MODEL)
    scene = None
    if model_path.exists():
        scene = jersey_reader.read_scene(video, det_path, model_path)
    else:
        print(f"Hinweis: kein Nummernleser ({model_path.name}), alle Spieler ohne Rückennummer. "
              "Trainieren mit tools/jersey_reader.py train", flush=True)

    events: list[dict] = []
    identities = split_and_link(identities, video, det_path, cam, fps, scene, squad, events=events)
    if scene is None:
        _record(det_path, identities, events, {}, fps)
        return identities
    keys = {f"{key[0]}-{key[1]}": key for key in identities}
    tracks = {name: identities[key][2] for name, key in keys.items()}
    teams = {name: key[0] for name, key in keys.items()}
    votes = jersey_identity.vote(jersey_reader.readings_for_tracks(scene, tracks), teams, fps, squad)
    positions = {name: {f: r[:2] for f, r in fr.items()} for name, fr in tracks.items()}
    numbers = jersey_identity.assign(votes, {name: set(fr) for name, fr in tracks.items()}, fps)
    players = jersey_identity.merge_by_number(numbers, votes, positions, teams, fps)
    out = {}
    for p in players:
        if p.number is None:
            out[keys[p.id]] = identities[keys[p.id]]
            continue
        frames, keeper = {}, False
        for name in p.tracks:
            _, is_keeper, fr = identities[keys[name]]
            frames.update(fr)
            keeper |= is_keeper
        out[(p.team, p.number)] = (identities[keys[p.id]][0], keeper, frames)
        ordered = sorted(p.tracks, key=lambda t: min(tracks[t]))
        for a, b in zip(ordered, ordered[1:]):   # Stücke mit derselben Nummer zu einem Spieler
            events.append({"kind": "link", "frame": int(min(tracks[b])), "reason": "number",
                           "detections": [_first_last(tracks[a])[1], _first_last(tracks[b])[0]]})
    ranked = {}
    for p in players:
        v = votes.get(p.id)
        if v is not None and v.ranked:
            name = f"{p.team}-{p.number}" if p.number is not None else p.id
            ranked[name] = [[n, round(c, 4)] for n, c in v.ranked[:3]]
    _record(det_path, out, events, ranked, fps)
    numbered = Counter(p.team for p in players if p.number is not None)
    print(f"Rückennummern aus dem Video: {len(scene.frame)} Rücken gelesen; Spieler mit Nummer {dict(numbered)}, "
          f"aus {sum(len(p.tracks) for p in players if p.number is not None)} Spuren; "
          f"ohne Nummer {sum(1 for p in players if p.number is None)} Spuren", flush=True)
    return out


def _record(det_path, identities: dict, events: list[dict], ranked: dict, fps: float) -> None:
    players = {f"{key[0]}-{key[1]}": (key[0], keeper, key[1] if key[1] < OWN_ID else None, frames)
               for key, (_, keeper, frames) in identities.items()}
    write_identity(f"{det_path}.identity.json", players, events, ranked, fps)


def player_entity(key: tuple[str, int], keeper: bool, name_index: int) -> dict:
    """Spieler für den Viewer (specs/001-rueckennummern/contracts/viewer-entities.md): mit Nummer nur number,
    ohne Nummer der Spurname als label (S…, Torwart TW). Nummern 1–99 und interne Namen ab OWN_ID überschneiden
    sich nicht."""
    team, number = key
    entity = {"id": f"{team}-{number}", "kind": "player", "team": team}
    if number < OWN_ID:
        entity["number"] = number
    else:
        entity["label"] = "TW" if keeper else f"S{name_index}"
    if keeper:
        entity["role"] = "goalkeeper"
    return entity
