import os
from pathlib import Path
from sklearn.datasets import fetch_lfw_pairs
from PIL import Image

OUTPUT_DIR = Path(__file__).resolve().parent / "eval_data" / "genuine_pairs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pairs = fetch_lfw_pairs(subset="test", color=True, resize=1.0)

saved = 0
for i, (img1, img2) in enumerate(pairs.pairs):
    if pairs.target[i] != 1:  # 1 = same person; skip the "different person" pairs
        continue
    pair_dir = OUTPUT_DIR / f"pair_{i:03d}"
    pair_dir.mkdir(exist_ok=True)
    Image.fromarray(img1.astype("uint8")).save(pair_dir / "selfie.jpg")
    Image.fromarray(img2.astype("uint8")).save(pair_dir / "id_photo.jpg")
    saved += 1

print(f"Saved {saved} genuine same-person pairs to {OUTPUT_DIR}")