"""
Measures real-world accuracy of ml.kyc.face_verification.verify_face against
the LFW (Labeled Faces in the Wild) dataset, using the match/mismatch pair
CSVs that ship with LFW (matchpairsDevTest.csv, matchpairsDevTrain.csv,
mismatchpairsDevTest.csv, mismatchpairsDevTrain.csv, or the combined
pairs.csv / people.csv views).

This only measures FACE-MATCHING accuracy (same person vs different person).
It does NOT measure liveness/anti-spoofing accuracy - LFW has no spoof
samples (printed photos, screen replays, etc), so _run_liveness_check
cannot be evaluated with this dataset.

Usage:
    python backend/scripts/eval_face_accuracy.py \\
        --images-dir /path/to/lfw-deepfunneled \\
        --match-csv /path/to/matchpairsDevTest.csv \\
        --mismatch-csv /path/to/mismatchpairsDevTest.csv \\
        [--match-csv /path/to/matchpairsDevTrain.csv] \\
        [--mismatch-csv /path/to/mismatchpairsDevTrain.csv] \\
        [--limit 500] \\
        [--verbose]

Expects the standard LFW image layout:
    <images-dir>/<Name>/<Name>_<imagenum padded to 4 digits>.jpg
"""

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.kyc.face_verification import verify_face  # noqa: E402

# The real approve/flag/reject cutoff used in production
# (backend/app/tasks/kyc_tasks.py). Duplicated here rather than imported,
# because importing kyc_tasks pulls in celery/db/storage config just to
# read one float - not worth it for a standalone eval script. If you
# change MATCH_CONFIDENT_RATIO in kyc_tasks.py, update this too.
MATCH_CONFIDENT_RATIO = 0.85


def image_path(images_dir: Path, name: str, imagenum: str) -> Path:
    filename = f"{name}_{int(imagenum):04d}.jpg"
    return images_dir / name / filename


def load_match_pairs(csv_path: Path) -> list[tuple[str, str, str]]:
    pairs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if not row or not row[0]:
                continue
            name, n1, n2 = row[0], row[1], row[2]
            pairs.append((name, n1, n2))
    return pairs


def load_mismatch_pairs(csv_path: Path) -> list[tuple[str, str, str, str]]:
    pairs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if not row or not row[0]:
                continue
            name1, n1, name2, n2 = row[0], row[1], row[2], row[3]
            pairs.append((name1, n1, name2, n2))
    return pairs


def _score_pair(img1: Path, img2: Path) -> dict | None:
    if not img1.exists() or not img2.exists():
        print(f"[skip missing file] {img1} / {img2}")
        return None
    try:
        result = verify_face(str(img1), str(img2))
        return {
            "match_score": float(result["match_score"]),
            "verified": bool(result["verified"]),
            "raw_distance": float(result["raw_distance"]),
            "threshold": float(result["threshold"]),
        }
    except Exception as exc:
        print(f"[error pair {img1.name} vs {img2.name}] {exc}")
        return None


def _decision(r: dict) -> str:
    """Mirrors the exact branch order in backend/app/tasks/kyc_tasks.py."""
    ratio = r["raw_distance"] / r["threshold"]
    if r["verified"] and ratio <= MATCH_CONFIDENT_RATIO:
        return "approved"
    if r["verified"]:
        return "flagged"
    return "rejected"


def evaluate(
    images_dir: Path,
    match_csvs: list[Path],
    mismatch_csvs: list[Path],
    limit: int | None,
    verbose: bool = False,
):
    genuine_pairs: list[tuple[Path, Path]] = []
    for csv_path in match_csvs:
        for name, n1, n2 in load_match_pairs(csv_path):
            genuine_pairs.append((image_path(images_dir, name, n1), image_path(images_dir, name, n2)))

    impostor_pairs: list[tuple[Path, Path]] = []
    for csv_path in mismatch_csvs:
        for name1, n1, name2, n2 in load_mismatch_pairs(csv_path):
            impostor_pairs.append((image_path(images_dir, name1, n1), image_path(images_dir, name2, n2)))

    if limit:
        genuine_pairs = genuine_pairs[:limit]
        impostor_pairs = impostor_pairs[:limit]

    total = len(genuine_pairs) + len(impostor_pairs)
    done = 0
    genuine_results = []
    impostor_results = []
    errors = 0

    for img1, img2 in genuine_pairs:
        done += 1
        r = _score_pair(img1, img2)
        if r is None:
            errors += 1
        else:
            genuine_results.append(r)
            if verbose:
                d = _decision(r)
                ratio = r["raw_distance"] / r["threshold"]
                flag = "  <-- WRONG" if d == "rejected" else ""
                print(f"[genuine] {img1.name:30s} vs {img2.name:30s} "
                      f"dist={r['raw_distance']:.3f} ratio={ratio:.3f} "
                      f"verified={r['verified']} -> {d}{flag}")
        if done % 25 == 0:
            print(f"progress: {done}/{total}")

    for img1, img2 in impostor_pairs:
        done += 1
        r = _score_pair(img1, img2)
        if r is None:
            errors += 1
        else:
            impostor_results.append(r)
            if verbose:
                d = _decision(r)
                ratio = r["raw_distance"] / r["threshold"]
                flag = "  <-- FALSE ACCEPT" if d != "rejected" else ""
                print(f"[impostor] {img1.name:30s} vs {img2.name:30s} "
                      f"dist={r['raw_distance']:.3f} ratio={ratio:.3f} "
                      f"verified={r['verified']} -> {d}{flag}")
        if done % 25 == 0:
            print(f"progress: {done}/{total}")

    return genuine_results, impostor_results, errors


def report(genuine_results: list[dict], impostor_results: list[dict], errors: int):
    print("\n" + "=" * 60)
    print(f"Genuine pairs scored:  {len(genuine_results)}")
    print(f"Impostor pairs scored: {len(impostor_results)}")
    print(f"Errors/skips:          {errors}")
    print("=" * 60)

    if not genuine_results or not impostor_results:
        print("Not enough scored pairs to compute metrics.")
        return

    print(f"\n--- Actual production decision logic (MATCH_CONFIDENT_RATIO = {MATCH_CONFIDENT_RATIO}) ---")
    genuine_decisions = [_decision(r) for r in genuine_results]
    impostor_decisions = [_decision(r) for r in impostor_results]

    def _rate(decisions, label):
        return sum(1 for d in decisions if d == label) / len(decisions)

    print("Genuine pairs (want: mostly approved, rest flagged, minimal rejected):")
    print(f"  approved: {_rate(genuine_decisions, 'approved'):.4f}")
    print(f"  flagged:  {_rate(genuine_decisions, 'flagged'):.4f}")
    print(f"  rejected: {_rate(genuine_decisions, 'rejected'):.4f}")

    print("Impostor pairs (want: mostly rejected, minimal flagged/approved):")
    print(f"  approved: {_rate(impostor_decisions, 'approved'):.4f}  <- false accept rate")
    print(f"  flagged:  {_rate(impostor_decisions, 'flagged'):.4f}")
    print(f"  rejected: {_rate(impostor_decisions, 'rejected'):.4f}")

    print("\n--- Diagnostic only: match_score distribution (NOT used for decisioning) ---")
    genuine_scores = [r["match_score"] for r in genuine_results]
    impostor_scores = [r["match_score"] for r in impostor_results]
    print(f"Genuine match_score:  min={min(genuine_scores):.3f} max={max(genuine_scores):.3f} "
          f"avg={sum(genuine_scores)/len(genuine_scores):.3f}")
    print(f"Impostor match_score: min={min(impostor_scores):.3f} max={max(impostor_scores):.3f} "
          f"avg={sum(impostor_scores)/len(impostor_scores):.3f}")
    print("(match_score is informational only - see ml/kyc/face_verification.py.")
    print(" The approve/flag/reject decision above uses verified + distance/threshold ratio.)")

    print("\nNOTE: this dataset (LFW) has no spoof/liveness samples, so")
    print("LIVENESS_THRESHOLD (anti-spoofing) cannot be tuned from this run.")
    print("That requires a separate dataset of real selfies vs. spoof attempts")
    print("(printed photo, screen replay, mask, etc).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images-dir", required=True, type=Path, help="Path to lfw-deepfunneled/ (or lfw/) folder")
    parser.add_argument("--match-csv", action="append", required=True, type=Path,
                         help="Path to a match-pairs CSV (name,imagenum1,imagenum2). Repeatable.")
    parser.add_argument("--mismatch-csv", action="append", required=True, type=Path,
                         help="Path to a mismatch-pairs CSV (name1,imagenum1,name2,imagenum2). Repeatable.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap number of genuine/impostor pairs each, for a quick smoke run")
    parser.add_argument("--verbose", action="store_true",
                         help="Print per-pair decisions, flagging wrong genuine rejections and false accepts")
    args = parser.parse_args()

    genuine_results, impostor_results, errors = evaluate(
        args.images_dir, args.match_csv, args.mismatch_csv, args.limit, verbose=args.verbose
    )
    report(genuine_results, impostor_results, errors)


if __name__ == "__main__":
    main()