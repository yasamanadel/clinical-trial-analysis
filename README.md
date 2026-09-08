# Clinical Trial Enrollment & Matching Analysis

A lightweight, reusable tool that pulls interventional trials from the public
**ClinicalTrials.gov** API for **any condition**, structures the messy
eligibility/enrollment data into a clean table, surfaces **enrollment
bottlenecks**, and runs a simple **rules-based patient-to-trial match**.

Over 86% of clinical trials are delayed because they can't enroll enough
patients. This turns raw, unstructured trial records into decision-ready output:
which trials are at recruitment risk, where demand concentrates, and which trials
a given patient could plausibly join.

## Quick start
```bash
pip install -r requirements.txt
python analyze_trials.py
```

Run it on **any** therapeutic area — nothing is hardcoded:
```bash
# default
python analyze_trials.py --conditions "depression,anxiety"

# any field you like
python analyze_trials.py --conditions "glaucoma,macular degeneration"
python analyze_trials.py --conditions "asthma,copd"

# optionally run the SAME pipeline on a second set to compare across areas
python analyze_trials.py --conditions "depression" --compare "glaucoma,dry eye"
```

## What you get
- `trials_clean.csv` — every trial, structured and readable
- `compare_trials_risk.csv` — recruitment-risk shortlist for the `--compare` set (if used)
- console views: recruitment-risk trials, enrollment demand by state, and a
  patient-match demo

## How it works
1. **Pull** — pages the ClinicalTrials.gov v2 API for recruiting interventional trials.
2. **Structure** — flattens deeply nested JSON; parses free-text ages
   ("18 Years" -> 18) and site/geography fields; trims the eligibility
   wall-of-text into a readable snippet.
3. **Surface bottlenecks** — flags high-target/low-site trials (a recruitment red
   flag) and totals enrollment demand by state.
4. **Match** — matches a mock patient (age, sex, state, condition) against
   structured eligibility to return plausibly-eligible trials.

## Configuring the patient match
The demo patient lives near the bottom of `analyze_trials.py`:
```python
patient = {"age": 34, "sex": "FEMALE", "state": "California", "condition": "Depression"}
```
Edit those values to match against a different profile.

## Honest scope
A scrappy v1 built to validate the idea, not a production matcher. Eligibility
matching is field-level (age / sex / geography / condition), not full free-text
criteria parsing — the obvious next step is NLP on the eligibility text.

## Data & license
All data is public, pulled live from ClinicalTrials.gov. Released under the MIT License.
