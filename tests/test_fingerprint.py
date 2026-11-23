import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import appearance


def scene_of(groups: int, per: int, dim: int = 24, seed: int = 0):
    """Merkmale mit großem gemeinsamen Anteil (Trikot) und kleinem Anteil je Gruppe, dazu Rauschen."""
    rng = np.random.default_rng(seed)
    common = rng.normal(size=dim) * 4
    own = rng.normal(size=(groups, dim))
    rows, frames = [], {}
    for g in range(groups):
        frames[f"g{g}"] = {}
        for k in range(per):
            rows.append(common + own[g] + rng.normal(size=dim) * 1.5)
            frames[f"g{g}"][k] = np.array([0, 0, 0, 0, 0, 0, 0, 0, len(rows) - 1], float)
    n = len(rows)
    emb = np.array(rows, np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    scene = appearance.SceneLooks(np.arange(n, dtype=np.int32) % per, np.zeros(n, np.int8), np.arange(n, dtype=np.int32),
                                  emb, np.ones(n, np.float32))
    # frames: Bild k, Linse 0, Boxnummer = Zeilennummer; die Zeile je Erkennung steht in where
    where = {(int(f), 0, int(b)): i for i, (f, b) in enumerate(zip(scene.frame, scene.box))}
    return scene, where, frames


def separation(scene, frames, groups: int, per: int) -> float:
    """Mittlerer Kosinus gleicher Gruppe minus mittlerer Kosinus verschiedener Gruppen."""
    e = scene.embedding.astype(np.float32).reshape(groups, per, -1)
    same = np.mean([float((e[g, 0:per // 2].mean(0) / np.linalg.norm(e[g, 0:per // 2].mean(0)))
                          @ (e[g, per // 2:].mean(0) / np.linalg.norm(e[g, per // 2:].mean(0)))) for g in range(groups)])
    diff = np.mean([float((e[a].mean(0) / np.linalg.norm(e[a].mean(0))) @ (e[b].mean(0) / np.linalg.norm(e[b].mean(0))))
                    for a in range(groups) for b in range(groups) if a != b])
    return same - diff


class FingerprintTest(unittest.TestCase):
    def test_learning_separates_groups_that_share_a_kit(self):
        scene, where, frames = scene_of(6, 60)
        learned = appearance.learn_fingerprint(scene, where, frames)
        self.assertGreater(separation(learned, frames, 6, 60), separation(scene, frames, 6, 60) + 0.3)
        self.assertEqual(learned.embedding.shape[0], scene.embedding.shape[0])
        norms = np.linalg.norm(learned.embedding, axis=1)
        self.assertTrue(np.allclose(norms, 1.0, atol=1e-4))

    def test_too_few_long_groups_keep_the_features(self):
        scene, where, frames = scene_of(3, 60)
        self.assertIs(appearance.learn_fingerprint(scene, where, frames), scene)
        scene, where, frames = scene_of(6, 10)          # alle zu kurz
        self.assertIs(appearance.learn_fingerprint(scene, where, frames), scene)


if __name__ == "__main__":
    unittest.main()
