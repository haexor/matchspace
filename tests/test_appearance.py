import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np
import torch

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import appearance


class TinyNet(torch.nn.Module):
    """Ersatz für DINOv2: gleiche Ausgabeform (pooler_output, last_hidden_state), ohne Download."""

    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(3, appearance.WIDTH // 2)

    def forward(self, pixel_values):
        x = pixel_values.mean(dim=(2, 3))
        tokens = self.proj(x).unsqueeze(1).repeat(1, 5, 1)
        return SimpleNamespace(pooler_output=tokens[:, 0], last_hidden_state=tokens)


def tiny_model():
    torch.manual_seed(0)
    return TinyNet().eval(), torch.device("cpu")


def write_scene(folder: Path, frames: int = 4) -> tuple[Path, Path]:
    """Winziges Zwei-Linsen-Video mit einer Box je Linse, dazu Detektionen und Gelenkpunkte."""
    w, h = 64, 64
    video = folder / "scene.mp4"
    out = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 25, (w, 2 * h))
    for f in range(frames):
        image = np.full((2 * h, w, 3), 40, np.uint8)
        image[10:50, 20:36] = (0, 0, 200)          # rote Person oben (Linse links)
        image[h + 10:h + 50, 30:46] = (200, 0, 0)  # blaue Person unten (Linse rechts)
        out.write(image)
    out.release()
    boxes = {"left": [[20, 10, 36, 50, 0.9, 0]], "right": [[30, 10, 46, 50, 0.9, 1]]}
    det = {"video": "scene.mp4", "fps": 25, "lensSize": [w, h],
           "frames": [{"frame": f, "t": f / 25, **boxes} for f in range(frames)]}
    det_path = folder / "scene.det.json"
    det_path.write_text(json.dumps(det))
    kp = np.zeros((2 * frames, 17, 3), np.float32)
    kp[:, 5:7] = (28, 15, 0.9)    # Schultern
    kp[:, 15:17] = (28, 48, 0.9)  # Knöchel
    kp[1::2, :, 2] = 0.1          # zweite Person: unsicher, keine Größe
    index = np.array([[[2 * f, 2 * f + 1], [2 * f + 1, 2 * f + 2]] for f in range(frames)])
    np.savez(f"{det_path}.keypoints.npz", kp=kp, index=index, colour=np.zeros(2 * frames))
    return video, det_path


class DescribeTest(unittest.TestCase):
    def test_unit_vectors_of_full_width(self):
        net, device = tiny_model()
        crops = np.random.default_rng(0).integers(0, 255, (3, appearance.CROP_H, appearance.CROP_W, 3), np.uint8)
        e = appearance.describe(crops, net, device)
        self.assertEqual(e.shape, (3, appearance.WIDTH))
        np.testing.assert_allclose(np.linalg.norm(e, axis=1), 1.0, rtol=1e-5)

    def test_empty_input(self):
        net, device = tiny_model()
        self.assertEqual(appearance.describe(np.zeros((0, appearance.CROP_H, appearance.CROP_W, 3), np.uint8), net, device).shape,
                         (0, appearance.WIDTH))


class SceneCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video, self.det = write_scene(Path(self.tmp.name))
        patcher = mock.patch.object(appearance, "load_net", side_effect=tiny_model)
        self.load = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_every_second_frame_both_lenses(self):
        scene = appearance.read_scene(self.video, self.det)
        self.assertEqual(sorted(zip(scene.frame.tolist(), scene.lens.tolist())), [(0, 0), (0, 1), (2, 0), (2, 1)])
        self.assertEqual(scene.embedding.shape, (4, appearance.WIDTH))
        self.assertTrue(np.all(scene.height[scene.lens == 0] > 30))
        self.assertTrue(np.all(np.isnan(scene.height[scene.lens == 1])))

    def test_cache_holds_no_image_data_and_is_reused(self):
        appearance.read_scene(self.video, self.det)
        with np.load(f"{self.det}.appearance.npz") as c:
            self.assertEqual(set(c.files), {"frame", "lens", "box", "embedding", "height", "stamp"})
        appearance.read_scene(self.video, self.det)
        self.assertEqual(self.load.call_count, 1)

    def test_stale_stamp_recomputes(self):
        appearance.read_scene(self.video, self.det)
        with np.load(f"{self.det}.appearance.npz") as c:
            data = {k: c[k] for k in c.files}
        data["stamp"] = data["stamp"] + 1
        np.savez(f"{self.det}.appearance.npz", **data)
        appearance.read_scene(self.video, self.det)
        self.assertEqual(self.load.call_count, 2)

    def test_without_model_returns_none(self):
        self.load.side_effect = None
        self.load.return_value = None
        self.assertIsNone(appearance.read_scene(self.video, self.det))


if __name__ == "__main__":
    unittest.main()
