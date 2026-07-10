from pathlib import Path
from face_verification import verify_face

EVAL_DIR = Path(__file__).resolve().parent / "eval_data" / "genuine_pairs"

results = []
for pair_dir in sorted(EVAL_DIR.iterdir()):
    selfie = pair_dir / "selfie.jpg"
    id_photo = pair_dir / "id_photo.jpg"
    result = verify_face(str(selfie), str(id_photo))
    results.append((pair_dir.name, result))
    print(pair_dir.name, result)

# quick pass-rate summary at your current approve/flag/reject thresholds
scores = [r["match_score"] for _, r in results]
print(f"\n{len(scores)} genuine pairs evaluated")
print(f"Mean score: {sum(scores)/len(scores):.3f}")
print(f"Min score: {min(scores):.3f}")