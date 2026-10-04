# Kaggle CPU kernel: calibrate Module B's loan-book credit parameters from
# the real Lending Club corpus (~2.7M loans, 2007-2018, with grades, interest
# rates and default outcomes).
#
# Computes per grade: loan count, mean interest rate, realized default rate.
# Output: /kaggle/working/lc_calibration.csv + lc_calibration.json

import glob
import json
import os

os.environ.setdefault("USE_TF", "0")

import pandas as pd

USECOLS = ["grade", "int_rate", "loan_status"]


def find_source() -> str:
    hits = glob.glob("/kaggle/input/**/accepted*2007*.csv*", recursive=True)
    big = [h for h in hits if os.path.getsize(h) > 1e8]
    if big:
        return sorted(big)[0]
    raise SystemExit(f"lending club csv not found: {glob.glob('/kaggle/input/**/*', recursive=True)[:20]}")


def default_flag(status: str) -> int | None:
    s = (status or "").strip().lower()
    if s in ("charged off", "default", "does not meet the credit policy. status:charged off",
             "does not meet the credit policy. status:default"):
        return 1
    if s in ("fully paid", "does not meet the credit policy. status:fully paid"):
        return 0
    return None  # current / late / grace / other: excluded from the default-rate math


def parse_rate(x) -> float | None:
    try:
        return float(str(x).strip().rstrip("%"))
    except (ValueError, TypeError):
        return None


def main():
    src = find_source()
    print("source:", src, flush=True)

    stats = {}  # grade -> {n, defaulted, paid, rate_sum}
    for chunk in pd.read_csv(src, usecols=USECOLS, chunksize=500_000):
        chunk = chunk.dropna(subset=["grade", "int_rate", "loan_status"])
        for r in chunk.itertuples():
            g = str(r.grade).strip().upper()
            if g not in "ABCDEFG" or len(g) != 1:
                continue
            rate = parse_rate(r.int_rate)
            d = default_flag(r.loan_status)
            if rate is None or d is None:
                continue
            st = stats.setdefault(g, {"n": 0, "defaulted": 0, "paid": 0, "rate_sum": 0.0})
            st["n"] += 1
            st["defaulted"] += d
            st["paid"] += 1 - d
            st["rate_sum"] += rate
        print(f"  processed {sum(s['n'] for s in stats.values()):,} scored loans", flush=True)

    rows = []
    for g in sorted(stats):
        st = stats[g]
        rows.append({
            "grade": g,
            "loans": st["n"],
            "mean_int_rate_pct": round(st["rate_sum"] / st["n"], 3),
            "default_rate_pct": round(st["defaulted"] / max(st["paid"] + st["defaulted"], 1) * 100, 3),
        })
    out = pd.DataFrame(rows)
    out.to_csv("/kaggle/working/lc_calibration.csv", index=False)
    print(out.to_string(index=False), flush=True)

    # map LC grades (A-G) onto the platform's rating scale for the loan book
    mapping = {"A": "AA", "B": "A", "C": "BBB", "D": "BB", "E": "B", "F": "CCC", "G": "CCC"}
    RISK_FREE_PCT = 1.5  # approx 3Y treasury mean over the 2012-2018 loan window
    calibration = {}
    for r in rows:
        calibration[mapping[r["grade"]]] = {
            "lc_grade": r["grade"],
            "loans": r["loans"],
            "mean_int_rate_pct": r["mean_int_rate_pct"],
            "spread_bps_est": round((r["mean_int_rate_pct"] - RISK_FREE_PCT) * 100),
            "realized_default_rate_pct": r["default_rate_pct"],
            "pd_est": round(r["default_rate_pct"] / 100, 4),
        }
    with open("/kaggle/working/lc_calibration.json", "w") as f:
        json.dump({
            "source": "Lending Club corpus (wordsforthewise/lending-club), 2007-2018",
            "risk_free_assumption_pct": RISK_FREE_PCT,
            "grade_to_rating_mapping": mapping,
            "calibration": calibration,
        }, f, indent=2)
    print("saved lc_calibration.csv + lc_calibration.json", flush=True)


if __name__ == "__main__":
    main()
