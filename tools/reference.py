"""Eigene Referenz einer Szene: Personen aus der Zuordnung der Auswertung und den Antworten an strittigen Stellen.

Reine Logik ohne Datei-, Video- oder Netzzugriff (specs/003-eigene-referenz/data-model.md, research.md R2):
  - Jede strittige Stelle schneidet ihre Beteiligten in Abschnitte (vorher, nachher). Stellen zur Nummer schneiden
    nicht.
  - Eine Antwort verknüpft Abschnitte: Der Abschnitt nach der Stelle gehört zur Person eines Abschnitts davor, ist
    eine andere Person oder ist unklar. Personen sind zusammenhängende Gruppen verknüpfter Abschnitte.
  - Abschnitte ohne Antwort gelten als richtig zugeordnet (die bewusste Annahme „unauffällig heißt richtig“); nach
    einer offenen oder unklaren Stelle zählt der folgende Abschnitt nicht.
  - Antworten hängen an Bild, Linse und Box ihrer Beteiligten und werden nach einer neuen Auswertung darüber
    wiedergefunden.
"""
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field

NO_CUT = ("number", "number-unsure")   # Stellen nur zur Nummer: kein Schnitt
REFIND_IOU = 0.5                       # Überlappung der Anker-Boxen beim Wiederfinden
REFIND_FRAMES = 15                     # so weit dürfen wiedergefundene Stellen zeitlich auseinanderliegen


@dataclass
class Participant:
    """Ein Spieler der Auswertung an einer Stelle; anchor: [Bild, Linse, Box, x1, y1, x2, y2] am Rand der Stelle."""
    player: str
    letter: str
    anchor: list
    boxes: dict = field(default_factory=dict)


@dataclass
class Spot:
    id: str
    kinds: list
    frame: int
    start: int
    end: int
    lens: int
    crop: list
    before: list
    after: list
    proposal: dict
    priority: float
    number: int | None = None


@dataclass
class Answer:
    spot: str
    choice: str          # proposed, swapped, mapped, unclear
    mapping: dict
    numbers: dict
    anchors: dict
    at: str
    repeat: bool = False


@dataclass
class Persons:
    of: dict             # (Bild, Linse, Box) -> Person
    number: dict         # Person -> Nummer (vom Nutzer)
    team: dict           # Person -> Mannschaft (Mehrheit der Erkennungen)
    open: int            # offene Stellen
    unclear: int         # Stellen mit mindestens einer unklaren Zuordnung


def mapping_of(spot: Spot, answer: Answer | None) -> dict:
    """Zuordnung Buchstabe nachher -> Buchstabe vorher, "other" oder "unclear"."""
    if answer is None or answer.choice == "unclear":
        return {p.letter: "unclear" for p in spot.after}
    if answer.choice == "proposed":
        return {k: (v if v is not None else "other") for k, v in spot.proposal.items()}
    if answer.choice == "swapped":
        letters = [p.letter for p in spot.before]
        if len(letters) != 2:
            raise ValueError("„vertauscht“ geht nur bei zwei Beteiligten")
        flip = {letters[0]: letters[1], letters[1]: letters[0]}
        return {k: flip.get(v, "other") if v is not None else "other" for k, v in spot.proposal.items()}
    return dict(answer.mapping)


def _latest(answers: Sequence[Answer]) -> dict[str, Answer]:
    out = {}
    for a in answers:
        if not a.repeat:
            out[a.spot] = a
    return out


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def persons(identity: Mapping, spots: Sequence[Spot], answers: Sequence[Answer]) -> Persons:
    """Personen je Erkennung aus Zuordnung, Stellen und Antworten."""
    cuts: dict[str, set[int]] = {}
    for s in spots:
        if any(k in NO_CUT for k in s.kinds):
            continue
        for p in s.before + s.after:
            cuts.setdefault(p.player, set()).add(s.frame)
    segment, team_of = {}, {}
    for name, p in identity["players"].items():
        edges = sorted(cuts.get(name, ()))
        for f, lens, box in p["detections"]:
            k = sum(1 for e in edges if f >= e)
            segment[(f, lens, box)] = (name, k)
            team_of[(f, lens, box)] = p["team"]
    union, excluded, numbers = _Union(), set(), {}
    latest = _latest(answers)
    open_, unclear = 0, 0

    def seg(p: Participant):
        return segment.get(tuple(p.anchor[:3]))
    for s in spots:
        a = latest.get(s.id)
        if any(k in NO_CUT for k in s.kinds):
            pass
        else:
            open_ += a is None
            m = mapping_of(s, a)
            unclear += a is not None and "unclear" in m.values()
            before = {p.letter: p for p in s.before}
            for p in s.after:
                target = m.get(p.letter, "unclear")
                after_seg = seg(p)
                if after_seg is None:
                    continue
                if target == "unclear":
                    excluded.add(after_seg)
                elif target in before and seg(before[target]) is not None:
                    union.join(after_seg, seg(before[target]))
        if a is not None:
            by_letter = {p.letter: p for p in s.before}
            by_letter.update({p.letter: p for p in s.after})
            for letter, number in a.numbers.items():
                if letter in by_letter and seg(by_letter[letter]) is not None:
                    numbers[seg(by_letter[letter])] = int(number)
    of, votes = {}, {}
    for det, sg in segment.items():
        if sg in excluded:
            continue
        person = union.find(sg)
        of[det] = person
        votes.setdefault(person, Counter())[team_of[det]] += 1
    number = {union.find(sg): n for sg, n in numbers.items()}
    team = {person: c.most_common(1)[0][0] for person, c in votes.items()}
    return Persons(of, number, team, open_, unclear)


def conflicts(identity: Mapping, p: Persons) -> list[str]:
    """Widersprüche der Referenz (FR-015) als Hinweise."""
    out = []
    at: dict[tuple, int] = Counter((person, det[0]) for det, person in p.of.items())
    twice = sorted({person for (person, _), n in at.items() if n > 1}, key=str)
    out += [f"Person {person} steht zur selben Zeit an zwei Orten" for person in twice]
    holders: dict[tuple, list] = {}
    for person, number in p.number.items():
        holders.setdefault((p.team.get(person), number), []).append(person)
    out += [f"Nummer {number} trägt in {team} mehr als eine Person" for (team, number), ps in holders.items() if len(ps) > 1]
    team_of = {tuple(d): q["team"] for q in identity["players"].values() for d in q["detections"]}
    teams: dict = {}
    for det, person in p.of.items():
        teams.setdefault(person, set()).add(team_of.get(det, "?"))
    out += [f"Person {person} gehört zu zwei Mannschaften" for person, ts in teams.items() if len(ts) > 1]
    return out


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _same(a: Sequence, b: Sequence) -> bool:
    return a[0] == b[0] and a[1] == b[1] and _iou(a[3:7], b[3:7]) > REFIND_IOU


def _match(s: Spot, t: Spot) -> dict[str, str] | None:
    """Buchstaben von s -> Buchstaben von t, wenn jeder Beteiligte von s in t wiederzufinden ist."""
    letters = {}
    for side in ("before", "after"):
        for p in getattr(s, side):
            q = next((q for q in getattr(t, side) if _same(p.anchor, q.anchor)), None)
            if q is None:
                return None
            letters[p.letter] = q.letter
    return letters


def refind(old: Sequence[Spot], answers: Sequence[Answer], new: Sequence[Spot]) -> tuple[list[Answer], list[Answer]]:
    """Antworten zu Stellen einer neuen Auswertung: über die Anker der Beteiligten. Rückgabe (übernommen, verwaist)."""
    by_id = {s.id: s for s in old}
    kept, orphaned = [], []
    for a in answers:
        s = by_id.get(a.spot)
        found = None
        if s is not None:
            found = next(((t, m) for t in new if abs(t.frame - s.frame) <= REFIND_FRAMES
                          for m in [_match(s, t)] if m is not None), None)
        if found is None:
            orphaned.append(a)
            continue
        t, letters = found
        if a.choice == "unclear":
            mapping = {}
        else:
            mapping = {letters[k]: letters.get(v, v) for k, v in mapping_of(s, a).items()}
        kept.append(Answer(t.id, "unclear" if a.choice == "unclear" else "mapped", mapping,
                           {letters[k]: v for k, v in a.numbers.items() if k in letters}, a.anchors, a.at, a.repeat))
    return kept, orphaned


def to_json(scene: str, stamp: str, spots: Sequence[Spot], answers: Sequence[Answer], seed: int) -> dict:
    def spot(s: Spot) -> dict:
        d = asdict(s)
        d["from"], d["to"] = d.pop("start"), d.pop("end")
        return d
    return {"scene": scene, "identityStamp": stamp, "spots": [spot(s) for s in spots],
            "answers": [asdict(a) for a in answers], "seed": seed}


def from_json(data: Mapping) -> tuple[list[Spot], list[Answer], int]:
    spots = []
    for d in data["spots"]:
        d = dict(d)
        d["start"], d["end"] = d.pop("from"), d.pop("to")
        for side in ("before", "after"):
            d[side] = [Participant(p["player"], p["letter"], list(p["anchor"]), {int(k): v for k, v in p.get("boxes", {}).items()})
                       for p in d[side]]
        spots.append(Spot(**d))
    answers = [Answer(**a) for a in data["answers"]]
    return spots, answers, int(data.get("seed", 0))
