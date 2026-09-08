"""
Clinical Trial Enrollment & Matching Analysis
---------------------------------------------
Pulls interventional trials for ANY condition(s) from the public
ClinicalTrials.gov v2 API, structures the messy eligibility/enrollment data
into a clean table, surfaces enrollment bottlenecks, and does a simple
rules-based match of a mock patient profile to eligible trials.

Turns raw, unstructured trial records into decision-ready output:
which trials are at recruitment risk, where demand concentrates, and which
trials a given patient could plausibly join.

Run:  python analyze_trials.py --conditions "depression,anxiety"
      python analyze_trials.py --conditions "glaucoma,macular degeneration"
      python analyze_trials.py --conditions "asthma"
Outputs: trials_clean.csv  (presentation-ready)
"""

import argparse
import requests
import pandas as pd
import re
import time

API = "https://clinicaltrials.gov/api/v2/studies"


def fetch_trials(condition, max_pages=5, page_size=100):
    """Page through the API for one condition, return a list of raw study dicts."""
    studies, token = [], None
    for _ in range(max_pages):
        params = {
            "query.cond": condition,
            "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION",
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "pageSize": page_size,
        }
        if token:
            params["pageToken"] = token
        r = requests.get(API, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        studies.extend(data.get("studies", []))
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(0.3)
    return studies


def parse_study(s):
    """Pull the fields we care about out of the deeply nested study JSON."""
    proto = s.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    elig = proto.get("eligibilityModule", {})
    cond = proto.get("conditionsModule", {})
    contacts = proto.get("contactsLocationsModule", {})

    enroll = design.get("enrollmentInfo", {}) or {}
    locations = contacts.get("locations", []) or []

    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "start_date": (status.get("startDateStruct") or {}).get("date"),
        "enrollment_target": enroll.get("count"),
        "enrollment_type": enroll.get("type"),
        "phase": ", ".join(design.get("phases", []) or []),
        "conditions": ", ".join(cond.get("conditions", []) or []),
        "min_age": elig.get("minimumAge"),
        "max_age": elig.get("maximumAge"),
        "sex": elig.get("sex"),
        "healthy_volunteers": elig.get("healthyVolunteers"),
        "eligibility_text": elig.get("eligibilityCriteria", ""),
        "n_sites": len(locations),
        "states": ", ".join(sorted({(l.get("state") or "") for l in locations if l.get("state")})),
    }


def age_to_years(age_str):
    """'18 Years' -> 18.0 ; '6 Months' -> 0.5 ; None -> None"""
    if not age_str or not isinstance(age_str, str):
        return None
    m = re.match(r"(\d+)\s*(Year|Month|Week|Day)", age_str)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {"Year": n, "Month": n / 12, "Week": n / 52, "Day": n / 365}[unit]


def clean_snip(t):
    """Turn the raw eligibility wall-of-text into a short, readable snippet."""
    t = str(t).replace("\\", "").replace("*", "")
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:120] + "...") if len(t) > 120 else t


def matches_patient(row, patient):
    """Return True if a mock patient could plausibly be eligible."""
    lo = row["min_age_years"]
    hi = row["max_age_years"]
    if lo is not None and patient["age"] < lo:
        return False
    if hi is not None and patient["age"] > hi:
        return False
    if row["sex"] and row["sex"] != "ALL" and row["sex"] != patient["sex"]:
        return False
    if patient["state"] and row["states"] and patient["state"] not in str(row["states"]):
        return False
    if patient["condition"].lower() not in str(row["conditions"]).lower():
        return False
    return True


def main(conditions, compare=None):
    print(f"Pulling trials for {list(conditions)} from ClinicalTrials.gov ...")
    raw = []
    for c in conditions:
        raw += fetch_trials(c)
    print(f"  pulled {len(raw)} raw study records")

    df = pd.DataFrame([parse_study(s) for s in raw]).drop_duplicates("nct_id")

    df["min_age_years"] = df["min_age"].map(age_to_years)
    df["max_age_years"] = df["max_age"].map(age_to_years)
    df["enrollment_target"] = pd.to_numeric(df["enrollment_target"], errors="coerce")
    print(f"  structured into {len(df)} unique trials\n")

    # ---- CLEAN UP for a presentation-ready CSV ----
    df["eligibility_snippet"] = df["eligibility_text"].map(clean_snip)
    df["phase"] = df["phase"].replace("", "Not specified").fillna("Not specified")
    df["max_age"] = df["max_age"].fillna("No upper limit")
    df["states"] = df["states"].replace("", "No US/listed site").fillna("No US/listed site")

    cols = ["nct_id", "title", "status", "phase", "enrollment_target",
            "enrollment_type", "n_sites", "states", "sex", "min_age",
            "max_age", "conditions", "eligibility_snippet"]
    (df[cols].sort_values("enrollment_target", ascending=False)
        .to_csv("trials_clean.csv", index=False))
    print("Saved -> trials_clean.csv\n")

    bottleneck = df[(df["n_sites"] <= 1) & (df["enrollment_target"] >= 100)]
    bottleneck = bottleneck.sort_values("enrollment_target", ascending=False)
    print("=" * 70)
    print("ENROLLMENT RISK: high target (>=100) but <=1 site  (recruitment risk)")
    print("=" * 70)
    print(bottleneck[["nct_id", "enrollment_target", "n_sites", "title"]]
          .head(10).to_string(index=False))

    print("\n" + "=" * 70)
    print("ENROLLMENT DEMAND BY STATE (sum of targets where a site exists)")
    print("=" * 70)
    rows = []
    for _, r in df.iterrows():
        for st in [x.strip() for x in str(r["states"]).split(",")
                   if x.strip() and x.strip() != "No US/listed site"]:
            rows.append({"state": st, "target": r["enrollment_target"] or 0})
    by_state = (pd.DataFrame(rows).groupby("state")["target"]
                .sum().sort_values(ascending=False).head(10))
    print(by_state.to_string())

    patient = {"age": 34, "sex": "FEMALE", "state": "California", "condition": "Depression"}
    print("\n" + "=" * 70)
    print(f"PATIENT MATCH DEMO -> {patient}")
    print("=" * 70)
    eligible = df[df.apply(lambda r: matches_patient(r, patient), axis=1)]
    print(f"{len(eligible)} plausibly-eligible recruiting trials found. Top 10:")
    print(eligible[["nct_id", "phase", "n_sites", "title"]].head(10).to_string(index=False))

    # ---- OPTIONAL: run the SAME pipeline on a second set of conditions ----
    # Proves the framework is condition-agnostic. Enable with --compare.
    if compare:
        print("\n" + "=" * 70)
        print(f"CROSS-DOMAIN: same pipeline on {list(compare)}")
        print("=" * 70)
        c_raw = []
        for c in compare:
            c_raw += fetch_trials(c)
        cdf = pd.DataFrame([parse_study(s) for s in c_raw]).drop_duplicates("nct_id")
        cdf["enrollment_target"] = pd.to_numeric(cdf["enrollment_target"], errors="coerce")
        c_risk = cdf[(cdf["n_sites"] <= 1) & (cdf["enrollment_target"] >= 100)]
        c_risk = c_risk.sort_values("enrollment_target", ascending=False)
        c_risk.to_csv("compare_trials_risk.csv", index=False)
        print(f"{len(cdf)} trials pulled; "
              f"{len(c_risk)} flagged at recruitment risk -> compare_trials_risk.csv")
        print(c_risk[["nct_id", "enrollment_target", "n_sites", "title"]]
              .head(5).to_string(index=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Pull, structure & analyze ClinicalTrials.gov trials for any condition.")
    p.add_argument("--conditions", default="depression,anxiety",
                   help='comma-separated conditions, e.g. "asthma,copd" (default: depression,anxiety)')
    p.add_argument("--compare", default=None,
                   help='optional second set of conditions to run the same pipeline on, '
                        'e.g. "glaucoma,macular degeneration"')
    args = p.parse_args()
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    compare = [c.strip() for c in args.compare.split(",") if c.strip()] if args.compare else None
    main(conditions, compare)
