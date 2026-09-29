"""validate_inference.py -- v20.46: is the headline inference HONEST? A Monte Carlo test on the engine itself.

Panels with a KNOWN effect and realistic noise (pixel noise + year shocks shared by all pixels + year shocks specific to
each sub-watershed's core, the part that makes one sub-watershed hard) are estimated with M01 (two-way FE DiD) many
times. For each scenario: bias, the true spread of the estimate, the average reported SEs, how often each SE's 95 %
interval covers the truth, and how often each finds a "significant" effect when there is none.
    python validate_inference.py          (about 1-2 minutes)
"""
import os, sys, warnings
import numpy as np, pandas as pd
from scipy import stats
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
warnings.filterwarnings("ignore")
import _common as C

def panel(rng, n_sws, beta, core=60, ring=120, years=range(2018, 2025), T=2022, sd_pix=0.01, sd_year=0.006, sd_core_year=0.004):
    rows = []
    lam = {y: rng.normal(0, sd_year) for y in years}
    for s in range(1, n_sws + 1):
        dlt = {y: rng.normal(0, sd_core_year) for y in years}              # the core's own year shocks (the hard part)
        for p in range(core + ring):
            tr = p < core; a = rng.normal(0.3, 0.05)
            for y in years:
                rows.append((s * 100000 + p, y, 0, 0 if tr else 1 + p % 5, f"U{s}", s, a + lam[y] + (dlt[y] if tr else 0)
                             + (beta if tr and y >= T else 0) + rng.normal(0, sd_pix)))
    d = pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "y"])
    d["time_fe_yearseason"] = d.Year.astype(str) + "_0"
    return d

def run(name, n_sws, beta, reps, seed):
    rng = np.random.default_rng(seed); out = []
    C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False, seasons="all", covariates=[])
    for r in range(reps):
        d = C.build_treatment_columns(panel(rng, n_sws, beta)); d = d[d.in_analysis_sample == 1]
        b, se = C.estimate_twfe_did(d, "y", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        G = d["site_id"].nunique() if d["site_id"].nunique() >= C.MIN_SWS_CLUSTERS else d["Year"].nunique()
        ds = C.design_se("y", df=d) or {}
        sd, dfd = ds.get("se_design", np.nan), ds.get("df_design", ds.get("df", np.nan))
        bd = ds.get("did_collapsed", b)
        tm, td = stats.t.ppf(0.975, max(G - 1, 1)), stats.t.ppf(0.975, dfd if np.isfinite(dfd) and dfd > 0 else 1)
        out.append({"b": b, "se": se, "bd": bd, "sd": sd, "cov_m": abs(b - beta) <= tm * se, "cov_d": abs(bd - beta) <= td * sd,
                    "rej_m": abs(b) > tm * se, "rej_d": abs(bd) > td * sd})
    o = pd.DataFrame(out)
    return {"scenario": name, "true_effect": beta, "reps": reps, "bias": o.b.mean() - beta, "true_sd_of_estimate": o.b.std(),
            "mean_model_se": o.se.mean(), "mean_design_se": o.sd.mean(), "coverage_model_se": o.cov_m.mean(), "coverage_design_se": o.cov_d.mean(),
            "false_positive_model_se": o.rej_m.mean() if beta == 0 else np.nan, "false_positive_design_se": o.rej_d.mean() if beta == 0 else np.nan}

def main(reps=int(os.environ.get("REWARD_MC_REPS", "200"))):
    res = pd.DataFrame([run("one sub-watershed (like Haligeri)", 1, 0.03, reps, 1), run("eight sub-watersheds (pooled)", 8, 0.03, reps, 2),
                        run("one sub-watershed, NO effect", 1, 0.0, reps, 3)])
    pd.set_option("display.width", 200)
    print(res.round(4).to_string(index=False))
    problems = []
    for r in res.itertuples():
        if abs(r.bias) > 0.25 * r.true_sd_of_estimate + 1e-4: problems.append(f"{r.scenario}: biased ({r.bias:+.5f})")
        if not (0.88 <= r.coverage_design_se <= 0.995): problems.append(f"{r.scenario}: design-SE coverage {r.coverage_design_se:.1%} (expected ~95 %)")
    nul = res.iloc[2]
    if not nul.false_positive_design_se <= 0.10: problems.append(f"no-effect scenario: design SE finds an effect {nul.false_positive_design_se:.0%} of the time")
    os.makedirs(os.path.join(HERE, "06_Validation"), exist_ok=True)
    print("\nREAD: the estimate is unbiased; the DESIGN-BASED SE (se_design / p_design, on every result) is the calibrated one.")
    print("      Where the model SE's coverage is far below 95 %, its p-values overstate significance -- report p_design.")
    print(("CLEAN: inference validated -- no bias, design-based intervals cover the truth at the nominal rate." if not problems
           else "PROBLEMS:\n  - " + "\n  - ".join(problems)))
    return 0 if not problems else 1

if __name__ == "__main__":
    sys.exit(main())
