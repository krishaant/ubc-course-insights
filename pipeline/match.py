"""Step 4 (MATCH) — build the professor identity crosswalk across sources.

Builds data/clean/prof_crosswalk.csv: one row per (source, raw_name), with
a normalized match_key and a resolved legacy_id (RMP's professor id) where
possible, labeled per the spec:
  - exact: match_key maps to exactly one RMP professor
  - unverified: match_key maps to 2+ RMP professors and nothing resolves it
    (see note below — proper "dept" disambiguation needs a subject-code ->
    RMP-department-name mapping that doesn't exist yet, so this is scoped
    down from the spec's 3-way exact/dept/unverified split to exact/unverified
    for now; data/overrides.csv is exactly the mechanism for a human to
    resolve these by hand)
  - no_rmp: grades/schedule/salary person with no RMP page at all

Review-to-course fuzzy matching is NOT done here — reviews haven't been
pulled yet (holding off per the user).
"""

import re
from pathlib import Path

import pandas as pd

CLEAN_DIR = Path("data/clean")
OVERRIDES_PATH = Path("data/overrides.csv")


def _token(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return re.sub(r"[^a-z]", "", str(s).lower())


def match_key_from_parts(first_name, last_name) -> str | None:
    first = _token(str(first_name).split()[0]) if first_name and str(first_name).strip() else ""
    last = _token(str(last_name).split()[-1]) if last_name and str(last_name).strip() else ""
    if not first or not last:
        return None
    return f"{last}_{first}"


def match_key_from_fullname(full_name) -> str | None:
    if not isinstance(full_name, str) or not full_name.strip():
        return None
    parts = full_name.strip().split()
    if len(parts) < 2:
        return None
    return match_key_from_parts(parts[0], parts[-1])


def load_overrides() -> dict[str, int]:
    """match_key -> legacy_id, hand-edited, always wins."""
    if not OVERRIDES_PATH.exists():
        return {}
    df = pd.read_csv(OVERRIDES_PATH)
    return dict(zip(df["match_key"], df["legacy_id"]))


def build_crosswalk() -> pd.DataFrame:
    rmp = pd.read_csv(CLEAN_DIR / "rmp_professors.csv")
    grades = pd.read_csv(CLEAN_DIR / "grade_sections.csv")
    sections = pd.read_csv(CLEAN_DIR / "upcoming_sections.csv")
    salaries = pd.read_csv(CLEAN_DIR / "salaries.csv")

    rmp["match_key"] = [
        match_key_from_parts(f, l) for f, l in zip(rmp["first_name"], rmp["last_name"])
    ]
    # candidates: match_key -> list of legacy_ids (1 = unambiguous within RMP itself)
    candidates = rmp.dropna(subset=["match_key"]).groupby("match_key")["legacy_id"].apply(list).to_dict()

    overrides = load_overrides()

    def resolve(match_key: str | None) -> tuple[object, str]:
        if match_key is None:
            return None, "no_rmp"
        if match_key in overrides:
            return overrides[match_key], "override"
        ids = candidates.get(match_key)
        if not ids:
            return None, "no_rmp"
        if len(ids) == 1:
            return ids[0], "exact"
        return None, "unverified"

    rows = []

    # Non-RMP sources: dedupe to distinct raw names per source before
    # resolving, so the crosswalk is one row per distinct name, not one row
    # per section/term occurrence.
    for source, df, name_col in [
        ("grades", grades, "instructor"),
        ("sections", sections, "instructor"),
        ("salaries", salaries, None),  # built below from first/last
    ]:
        if source == "salaries":
            names = (df["first_name"].fillna("") + " " + df["last_name"].fillna("")).str.strip()
        else:
            names = df[name_col]

        for raw_name in sorted(names.dropna().unique()):
            key = match_key_from_fullname(raw_name)
            legacy_id, label = resolve(key)
            rows.append({
                "source": source, "raw_name": raw_name, "match_key": key,
                "legacy_id": legacy_id, "match_label": label,
            })

    # RMP itself: always "exact" to its own legacy_id, flag internal
    # ambiguity (same key, multiple RMP profiles) so it's visible.
    for _, r in rmp.iterrows():
        n_candidates = len(candidates.get(r["match_key"], []))
        rows.append({
            "source": "rmp",
            "raw_name": f"{r['first_name']} {r['last_name']}",
            "match_key": r["match_key"],
            "legacy_id": r["legacy_id"],
            "match_label": "exact" if n_candidates == 1 else "ambiguous_within_rmp",
        })

    crosswalk = pd.DataFrame(rows)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "prof_crosswalk.csv"
    crosswalk.to_csv(out_path, index=False)

    counts = crosswalk["match_label"].value_counts()
    print(f"prof_crosswalk: {len(crosswalk)} rows -> {out_path}")
    print(counts.to_string())
    return crosswalk


def write_hand_check_sample(crosswalk: pd.DataFrame, n: int = 100) -> Path:
    """Random sample for a human to eyeball, per the spec's VALIDATE step."""
    non_rmp = crosswalk[crosswalk["source"] != "rmp"]
    sample = non_rmp.sample(n=min(n, len(non_rmp)), random_state=42)
    out_path = CLEAN_DIR / "match_hand_check_sample.csv"
    sample.sort_values(["match_label", "source"]).to_csv(out_path, index=False)
    print(f"hand-check sample: {len(sample)} rows -> {out_path}")
    return out_path


if __name__ == "__main__":
    crosswalk = build_crosswalk()
    write_hand_check_sample(crosswalk)
