"""
dd_pipeline.py -- the diff-diff layer of the pre-built Python pipeline (v20.23).

diff-diff (Gerber 2026, https://github.com/igerber/diff-diff) gives one scikit-learn-style API for the DiD
estimators, validated against their R counterparts:

    DifferenceInDifferences   2x2                                  <-> M01
    MultiPeriodDiD            leads/lags event study               <-> M02 / M16 (its pre-period table)
    CallawaySantAnna          ATT(g,t) + aggregations, covariates  <-> M05
    SunAbraham                interaction-weighted event study     <-> M09
    StackedDiD                stacked / clean-control DiD          <-> M31
    ImputationDiD             Borusyak-Jaravel-Spiess imputation   <-> M27
    SyntheticDiD              Arkhangelsky et al.                  <-> M11
    ContinuousDiD             dose-response DiD                    <-> M06
    BaconDecomposition        Goodman-Bacon                         <-> M22
    HonestDiD                 relative magnitudes / smoothness     <-> M34
    check_parallel_trends     pre-trend slope test                 <-> M16 (1-df linear-trend version)

INPUT SHAPE. These estimators want ONE ROW PER UNIT AND PERIOD. The panel is pixel x Year x Season, so
`to_unit_period()` collapses it to pixel x Year means (outcome and covariates averaged over the seasons kept by
the scenario), with `first_treat` = the site's treatment year (0 = never treated, the diff-diff convention) --
the same aggregation the R did:: script uses. State it in the paper. The staggered estimators need >= 2
cohorts: pooled multi-site input with site years (P11 CELL 4) provides them.

    pip install diff-diff
    python dd_pipeline.py NDVI            # everything that applies to the input
Not executed in the environment that produced this bundle; the first call compares the 2x2 with the engine.
"""
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from pf_pipeline import package_input, out_dir, _engine


def _dd():
    try:
        import diff_diff as dd
    except ImportError as e:
        raise SystemExit("diff-diff is not installed: pip install diff-diff") from e
    return dd


def to_unit_period(df, outcome, covariates=("Rain", "Tmax", "Tmean", "Tmin")):
    """one row per unit (pixel x season series, v20.29) and Year; columns: unit, period, treated, post, first_treat,
    cluster, site, <outcome>, covariates."""
    covs = [c for c in covariates if c in df.columns]
    ukey = "unit" if "unit" in df.columns else "pixel_id"          # v20.29: each pixel x season series is a unit
    if "Season" in df.columns and df["Season"].nunique() > 1:     # v20.58: diff-diff works on YEARS -- the outcome net of the control rings'
        try:                                                       #   mean in the same season and year (as R's unit_year / season_net), or a
            import _common as _C                                   #   Rabi series meets rings of every season (their shocks differ)
            df = df.copy(); df[outcome] = _C.season_net(df, outcome, treat_col="treat"); df = df[np.isfinite(df[outcome].values)]
        except Exception as e:
            print("season-matching skipped:", e)
    g = df.groupby([ukey, "Year"], as_index=False).agg(
        **{outcome: (outcome, "mean")}, **{c: (c, "mean") for c in covs},
        treated=("treat", "max"), post=("post", "max"), cohort=("cohort", "first"),
        cluster=("cluster_id", "first"), site=("site_id", "first"))
    g = g.rename(columns={ukey: "unit", "Year": "period"})
    g["first_treat"] = np.where(np.isfinite(g["cohort"]), g["cohort"], 0).astype(int)
    g["period"] = g["period"].astype(int)
    return g, covs


def _cluster_arg(up):
    """v20.49: diff-diff needs a cluster column that is CONSTANT within each unit (the sub-watershed). The Year clusters
    of a single-sub-watershed run are not -- CallawaySantAnna then refused ("varies within units") and M34 never ran on
    the package. None = diff-diff's default (the unit)."""
    try:
        return "cluster" if int(up.groupby("unit")["cluster"].nunique(dropna=False).max()) <= 1 else None
    except Exception:
        return None


def _sdid_by_cohort(dd, up, outcome):
    """v20.49: diff-diff 3.x SyntheticDiD (fit(..., post_periods=[...])); ONE adoption time per fit, so one fit per cohort
    (its treated units vs the never-treated), averaged with weights = treated units. The placebo variance needs more
    control than treated units -- otherwise the bootstrap (v20.47 got SE = 0.0 there). diff-diff < 3: fit(post=)."""
    rows = []
    for g in sorted(up.loc[up.first_treat > 0, "first_treat"].unique()):
        sub = up[(up.first_treat == g) | (up.first_treat == 0)].copy(); sub["treated"] = (sub.first_treat == g).astype(int)
        n1 = sub.loc[sub.treated == 1, "unit"].nunique(); n0 = sub.loc[sub.treated == 0, "unit"].nunique()
        try:
            r = dd.SyntheticDiD(variance_method="placebo" if n0 > n1 else "bootstrap", seed=1).fit(
                sub, outcome=outcome, treatment="treated", unit="unit", time="period", post_periods=sorted(p for p in sub.period.unique() if p >= g))
        except TypeError:
            sub["post"] = (sub.period >= g).astype(int)
            r = dd.SyntheticDiD().fit(sub, outcome=outcome, unit="unit", time="period", treatment="treated", post="post")
        se_ = float(r.se) if r.se is not None and float(r.se) > 0 else float("nan")
        rows.append({"cohort": int(g), "n_treated": int(n1), "n_control": int(n0), "att": float(r.att), "se": se_})
    if not rows: raise RuntimeError("no treated cohort")
    w = np.array([r_["n_treated"] for r_ in rows], float); w /= w.sum()
    return (float(np.dot(w, [r_["att"] for r_ in rows])), float(np.sqrt(np.dot(w ** 2, [r_["se"] ** 2 for r_ in rows]))), pd.DataFrame(rows))


def season_series(df, outcome):
    """v20.58 -- R's season_series (lib/models_prebuilt.R): one series per sub-watershed x ring x season (x cohort), its mean per Year; the
    rings' cohort is Inf (never treated). The unit of M11 / M36-M38 / M45 in BOTH languages."""
    a = df.groupby(["site_id", "buff_km", "Season", "Year", "treat", "cohort"], dropna=False, as_index=False)[outcome].mean().rename(columns={outcome: "y"})
    a.loc[a["treat"] == 0, "cohort"] = np.inf
    a["unit"] = a["site_id"].astype(str) + "_" + a["buff_km"].astype(str) + "_" + a["Season"].astype(str) + "_" + a["cohort"].astype(str)
    return a

def _synthdid_r_se(sub, g):
    """v20.58 (second pass): this fit's SE as R computes it -- synthdid's placebo variance (vcov(method = "placebo"), 200 replications) with
    R's OWN draws (L'Ecuyer-CMRG after set.seed(12345), as R's sdid_fit runs it), on the fit's matrix in R's order (the treated series first,
    then the ring series, each by sub-watershed and ring; synthdid's panel.matrices sorts the controls by those integer ids as text).
    diff-diff's placebo variance is the same algorithm with numpy's draws -- 200 random permutations differ by ~5 % between two generators,
    so R and Python gave different SEs for the same estimate. Returns (tau, se); tau checks that the matrix is diff-diff's."""
    import _common as _C
    key = sub.groupby("unit")[["site_id", "buff_km"]].first()
    k_ = lambda u: (int(key.loc[u, "site_id"]), int(key.loc[u, "buff_km"]))
    tr = sorted(sub.loc[sub.treated == 1, "unit"].unique(), key=k_); co = sorted(sub.loc[sub.treated == 0, "unit"].unique(), key=k_)
    uid = {u: len(tr) + 1 + k for k, u in enumerate(co)}; co = sorted(co, key=lambda u: str(uid[u]))
    W = sub.pivot_table(index="unit", columns="period", values="y", aggfunc="first").sort_index(axis=1)
    Ym = np.vstack([W.loc[co].values, W.loc[tr].values]).astype(np.float64); T0 = int((W.columns.values < g).sum())
    tau, om, lam = _C.synthdid_point(Ym, len(co), T0)
    return float(tau), float(_C.synthdid_placebo_se(Ym, len(co), T0, om, lam))


def _sdid_by_cohort_season(dd, df, outcome):
    """v20.58 -- the SAME design as R's m11_sdid (by_cohort_season + synthdid): series of ONE season (season_series), one fit per cohort x
    season (its treated series against the same season's ring series, the balanced panel), averaged with weights = treated series x post
    years, their SEs combined as independent. v20.57 fitted pixel x season units of every season together (0.0507 against R's 0.0500)."""
    a = season_series(df, outcome); rows = []
    for s_ in sorted(a["Season"].unique()):
        for g in sorted(a.loc[(a.treat == 1) & np.isfinite(a.cohort) & (a.Season == s_), "cohort"].unique()):
            sub = a[(a.Season == s_) & (((a.treat == 1) & (a.cohort == g)) | (a.treat == 0))].copy()
            ny = sub["Year"].nunique(); nn = sub.groupby("unit")["Year"].nunique(); sub = sub[sub["unit"].isin(nn.index[nn == ny])]   # balanced
            n1 = sub.loc[sub.treat == 1, "unit"].nunique(); n0 = sub.loc[sub.treat == 0, "unit"].nunique()
            npost = sub.loc[sub.Year >= g, "Year"].nunique(); npre = sub.loc[sub.Year < g, "Year"].nunique()
            if not n1 or n0 < 2 or not npost or npre < 2: continue
            sub["treated"] = (sub.treat == 1).astype(int); sub["period"] = sub["Year"].astype(int)
            try:
                r = dd.SyntheticDiD(variance_method="placebo" if n0 > n1 else "bootstrap", seed=1).fit(
                    sub, outcome="y", treatment="treated", unit="unit", time="period", post_periods=sorted(int(p) for p in sub.period.unique() if p >= g))
            except Exception as e:
                print(f"M11 SyntheticDiD season {s_}, cohort {g}: not fitted ({type(e).__name__}: {str(e)[:100]}) -- left out of the average"); continue
            se_ = float(r.se) if r.se is not None and np.isfinite(float(r.se)) and float(r.se) > 0 else float("nan")
            se_dd = se_; se_src = "diff-diff"                                  # v20.58 (second pass): R's draws for the SE (see _synthdid_r_se)
            try:
                tau_r, se_r = _synthdid_r_se(sub, g)
                if np.isfinite(se_r) and se_r > 0 and abs(tau_r - float(r.att)) <= 1e-6 * max(1.0, abs(float(r.att))):
                    se_ = se_r; se_src = "synthdid placebo, R's draws"
                elif abs(tau_r - float(r.att)) > 1e-6 * max(1.0, abs(float(r.att))):
                    print(f"M11 season {s_}, cohort {g}: synthdid's estimate on this matrix {tau_r:.6g} differs from diff-diff's {float(r.att):.6g} -- diff-diff's SE kept")
            except Exception as e:
                print(f"M11 season {s_}, cohort {g}: the SE with R's draws not computed ({type(e).__name__}: {str(e)[:80]}) -- diff-diff's SE kept")
            rows.append({"Season": int(s_), "cohort": int(g), "n_treated": int(n1), "n_control": int(n0), "post_years": int(npost), "estimate": float(r.att), "se": se_,
                         "se_diffdiff": se_dd, "se_source": se_src})
    if not rows: raise RuntimeError("no cohort x season with a treated series, >= 2 same-season control series and >= 2 pre-period years")
    t = pd.DataFrame(rows); w = (t.n_treated * t.post_years).astype(float).values; w /= w.sum()
    se = float(np.sqrt(np.sum(w ** 2 * t.se.values ** 2))) if np.isfinite(t.se.values).all() else float("nan")
    t["weight"] = w
    return float(np.dot(w, t.estimate.values)), se, t


def _cs_fit(est, data, **kw):
    """v20.44: diff-diff >= 3.x fits once and aggregates after; older versions take fit(aggregate=)."""
    import warnings
    r = est.fit(data, **kw)
    if hasattr(r, "aggregate"):
        try:
            return r, r.aggregate("event_study")
        except Exception:
            pass
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        r = est.fit(data, aggregate="event_study", **kw)
    return r, r

def _cs_table(r, agg):
    for obj, args in ((agg, ("event_study",)), (agg, ()), (r, ("event_study",))):
        try:
            if hasattr(obj, "to_dataframe"): return obj.to_dataframe(*args)
        except Exception:
            continue
    raise RuntimeError("diff-diff CallawaySantAnna: no event-study table")

def _cs_overall(r, agg):
    for obj in (r, agg):
        a = getattr(obj, "overall_att", None); s = getattr(obj, "overall_se", None)
        if a is not None and s is not None: return float(a), float(s)
    if hasattr(r, "aggregate"):
        s_ = r.aggregate("simple")
        return float(getattr(s_, "att", getattr(s_, "overall_att", np.nan))), float(getattr(s_, "se", getattr(s_, "overall_se", np.nan)))
    return np.nan, np.nan

def run(outcome, C=None, models=None, write=True):
    C = C or _engine(); dd = _dd()
    df = package_input(outcome, C); up, covs = to_unit_period(df, outcome)
    tag = C.scenario_tag(); res = {}
    n_cohorts = up.loc[up.first_treat > 0, "first_treat"].nunique(); never = int((up.first_treat == 0).sum())
    print(f"unit-period table: {len(up):,} rows, {up.unit.nunique():,} units, cohorts {sorted(up.loc[up.first_treat > 0, 'first_treat'].unique())}, never-treated rows {never:,}")
    want = set(models or ["M01", "M02", "M16", "M05", "M09", "M31", "M27", "M11", "M06", "M22", "M34"])
    def save(model, name, obj):
        if write:
            d = out_dir(f"dd_{model}", C); (obj if isinstance(obj, pd.DataFrame) else pd.DataFrame([obj])).to_csv(os.path.join(d, f"{name}_{outcome}.csv"), index=False)
    # ---- M01 2x2 ----
    if "M01" in want:
        r = dd.DifferenceInDifferences(cluster="cluster").fit(up, outcome=outcome, treatment="treated", time="post",
                                                              covariates=covs or None)
        res["M01"] = {"outcome": outcome, "att": float(r.att), "se": float(r.se), "p_value": float(r.p_value),
                      "ci_low": float(r.conf_int[0]), "ci_high": float(r.conf_int[1]), "engine": "diff-diff"}
        save("M01", "canonical_twfe", res["M01"]); print("M01", res["M01"])
    # ---- M02 event study + M16 pre-trend test ----
    if "M02" in want or "M16" in want:
        ty = int(C.ACTIVE["treatment_year"]); periods = sorted(up.period.unique())
        post_periods = [p for p in periods if p >= ty]; ref = ty - 1
        if post_periods and ref in periods:
            r = dd.MultiPeriodDiD(cluster="cluster").fit(up, outcome=outcome, treatment="treated", time="period",
                                                        post_periods=post_periods, reference_period=ref, covariates=covs or None)
            es = r.to_dataframe(); es["event_time"] = es["period"] - ty; es["engine"] = "diff-diff"
            res["M02"] = es; save("M02", "event_study", es); print("M02", es[["event_time", "effect", "se"]].round(5).to_dict("records"))
        pre = [p for p in periods if p < ty]
        if "M16" in want and len(pre) >= 2:
            pt = dd.check_parallel_trends(up, outcome=outcome, time="period", treatment_group="treated", pre_periods=pre)
            res["M16"] = {"outcome": outcome, "trend_difference": pt["trend_difference"], "se": pt["trend_difference_se"],
                          "t_statistic": pt["t_statistic"], "p_value": pt["p_value"], "plausible": pt["parallel_trends_plausible"], "engine": "diff-diff"}
            save("M16", "pretrends_linear", res["M16"]); print("M16", res["M16"])
    # ---- staggered family (needs >= 2 cohorts) ----
    if n_cohorts >= 2:
        cs_r = None
        if "M05" in want or "M34" in want:          # v20.42: M34 (HonestDiD) needs THIS result as its base
            _est = dd.CallawaySantAnna(control_group="never_treated" if never else "not_yet_treated", base_period="universal", cluster=_cluster_arg(up))
            r, _agg = _cs_fit(_est, up, outcome=outcome, unit="unit", time="period", first_treat="first_treat", covariates=covs or None)
            cs_r = _agg
            es = _cs_table(r, _agg); es["engine"] = "diff-diff CallawaySantAnna"
            res["_cs"] = cs_r
            if "M05" in want:
                _oa, _os = _cs_overall(r, _agg)
                res["M05"] = {"overall_att": _oa, "se": _os, "table": es}
            if "M05" in want:
                save("M05", "cs_event_time", es); save("M05", "cs_overall", {"outcome": outcome, "att": _oa, "se": _os}); print("M05 overall", _oa, _os)
        if "M09" in want:
            r = dd.SunAbraham(control_group="never_treated" if never else "not_yet_treated", cluster="cluster").fit(
                up, outcome=outcome, unit="unit", time="period", first_treat="first_treat", covariates=covs or None)
            es = r.to_dataframe(); es["engine"] = "diff-diff SunAbraham"; res["M09"] = es; save("M09", "sun_abraham", es)
        if "M31" in want:
            try:           # v20.49: diff-diff 3.x -- cluster is a mode ('unit'); covariates enter through entropy balancing
                r = (dd.StackedDiD(balance="entropy") if covs else dd.StackedDiD()).fit(up, outcome=outcome, unit="unit", time="period",
                                                                                       first_treat="first_treat", covariates=covs or None)
            except TypeError:                                     # diff-diff < 3
                r = dd.StackedDiD(cluster="cluster").fit(up, outcome=outcome, unit="unit", time="period", first_treat="first_treat", covariates=covs or None)
            res["M31"] = {"outcome": outcome, "att": float(r.att), "se": float(r.se), "engine": "diff-diff StackedDiD"}; save("M31", "stacked_did", res["M31"])
        if "M27" in want:
            # v20.58 (as R's m27 / didimputation): clustered by sub-watershed when it is constant within the series (>= MIN_SWS_CLUSTERS of
            # them), else at the series (unit) level -- the package defaults of both; the year clusters of a one-sub-watershed run vary
            # within a series (BJS's variance is not defined on them: didimputation's LU factorisation failed)
            _cl27 = _cluster_arg(up)
            r = dd.ImputationDiD(cluster=_cl27).fit(up, outcome=outcome, unit="unit", time="period", first_treat="first_treat", covariates=covs or None)
            _nu27 = int(up["unit"].nunique()); _ns27 = int(up["cluster"].nunique()) if "cluster" in up.columns else 0
            res["M27"] = {"outcome": outcome, "att": float(r.att), "se": float(r.se), "engine": "diff-diff ImputationDiD (BJS)",
                          "se_how": ("diff-diff ImputationDiD (Borusyak, Jaravel & Spiess 2024): its conservative analytic SE, "   # v20.58: as R's text
                                     + (f"clustered by sub-watershed ({_ns27})" if _cl27 else
                                        f"each of the {_nu27:,} pixel x season series one draw (not clustered: the package clusters on groups, not on years)"))}
            save("M27", "bjs_imputation", res["M27"])
        if "M22" in want:
            # v20.58 (as R's m22_bacon and the engine): series of ONE season, net of the control rings' mean in the same sub-watershed,
            # season and year, the balanced panel -- and the SE of the two-way FE the decomposition adds up to
            uy_b, _nu = C.bacon_series(df, outcome, d_col="did" if "did" in df.columns else "did_term")
            ub = uy_b.rename(columns={"Year": "period"}).copy()
            _ft = ub[ub["D"] == 1].groupby("unit")["period"].min(); ub["first_treat"] = ub["unit"].map(_ft).fillna(0).astype(int)
            r = dd.BaconDecomposition().fit(ub, outcome="y", unit="unit", time="period", first_treat="first_treat")
            bd = r.to_dataframe(); bd["engine"] = "diff-diff Bacon"
            _inf = C.bacon_twfe_inference(uy_b)
            bd["headline_se"] = _inf["se"]; bd["headline_p"] = _inf["p_value"]; bd["se_how"] = _inf["se_how"]; bd["twfe_beta"] = _inf["twfe_beta"]
            res["M22"] = bd; save("M22", "bacon_decomposition", bd)
            print(f"M22 TWFE {r.twfe_estimate:.5f}; forbidden-comparison weight {bd.loc[bd.comparison_type.str.contains('forbidden|later', case=False), 'weight'].sum():.3f}")
    else:
        print("staggered family (M05/M09/M31/M27/M22) needs >= 2 treatment cohorts: use the pooled multi-site input with site years")
    # ---- M11 synthetic DiD ----
    if "M11" in want:
        try:
            _a, _s, _tab = _sdid_by_cohort_season(dd, df, outcome)
            _nr = int((_tab["se_source"] == "synthdid placebo, R's draws").sum()) if "se_source" in _tab.columns else 0
            _w = _tab["weight"].values; _sdd = _tab["se_diffdiff"].values if "se_diffdiff" in _tab.columns else np.full(len(_tab), np.nan)
            res["M11"] = {"outcome": outcome, "att": _a, "se": _s, "fits": len(_tab), "engine": "diff-diff SyntheticDiD (sub-watershed x ring x season series; one fit per cohort x season, as R)",
                          "se_diffdiff": float(np.sqrt(np.sum(_w ** 2 * _sdd ** 2))) if np.isfinite(_sdd).all() else float("nan"),
                          "se_how": (f"{len(_tab)} cohort x season fit(s), each a core series against the same season's ring series; each fit's SE by synthdid's placebo "
                                     f"variance ({_nr} of {len(_tab)} with R's own draws -- 200 replications, L'Ecuyer-CMRG after set.seed(12345), as R's route; "
                                     f"diff-diff's own placebo SE, numpy's draws, in se_diffdiff); combined as independent")}
            save("M11", "synthetic_did", res["M11"]); save("M11", "synthetic_did_by_cohort_season", _tab)
        except Exception as e:
            print("M11 SyntheticDiD skipped:", e)
    # ---- M06 continuous dose ----
    if "M06" in want and "dose" in df.columns and df.dose.nunique() > 1:
        _uk = "unit" if "unit" in df.columns else "pixel_id"      # v20.49: the SAME unit as to_unit_period (pixel x season); the
        upd = up.merge(df.groupby(_uk)["dose"].max().rename("dose"), left_on="unit", right_index=True)   # pixel_id key matched nothing there
        if "first_treat" in upd.columns:                          # v20.54: a never-treated unit has no dose -- set here, as diff-diff
            upd.loc[upd["first_treat"] == 0, "dose"] = 0.0        # would do itself (with a warning per call); the result is identical
        try:                                                      # v20.49: diff-diff 3.x -- first_treat + dose, no cluster argument;
            cfit = dd.ContinuousDiD(degree=1).fit(upd, outcome=outcome, unit="unit", time="period", first_treat="first_treat", dose="dose")
            res["M06"] = {"outcome": outcome, "att_per_unit_dose": float(cfit.overall_acrt), "se": float(cfit.overall_acrt_se),   # linear response:
                          "att_at_observed_doses": float(cfit.overall_att), "att_at_observed_doses_se": float(cfit.overall_att_se),   # the slope IS
                          "engine": "diff-diff ContinuousDiD (linear dose response)"}                                        # the effect per unit dose
        except TypeError:                                         # diff-diff < 3
            r = dd.ContinuousDiD(cluster="cluster").fit(upd, outcome=outcome, unit="unit", time="period", dose="dose", post="post")
            res["M06"] = {"outcome": outcome, "att_per_unit_dose": float(r.att), "se": float(r.se), "engine": "diff-diff ContinuousDiD"}
        save("M06", "dose_response", res["M06"])
    # ---- M34 HonestDiD on the CS or the event study ----
    if "M34" in want and res.get("_cs") is not None:
        # v20.58 -- as R's m34_honest: the HEADLINE is the effect whose robustness is assessed (the equal-weight mean of the post-period
        # event-time effects -- diff-diff's default target, R's l_vec), with ITS SE and p; the robust intervals on Mbar = 0, 0.5, ..., 2 and
        # the EXACT breakdown value (the smallest Mbar whose interval covers 0: bracketed by doubling, then bisection to 0.5 %). v20.57 took
        # the grid 0..5 and, when every interval excluded 0, wrote 5 (printed "> 5.0") -- a capped value, not the breakdown.
        from scipy import stats as _st
        base = res["_cs"]                          # v20.42: was `r` -- whichever estimator happened to run last
        hd = lambda M: dd.HonestDiD(method="relative_magnitude", M=M).fit(base)
        covers0 = lambda h: (not (np.isfinite(h.ci_lb) and np.isfinite(h.ci_ub))) or (h.ci_lb <= 0 <= h.ci_ub)
        rows, h0 = [], None
        try:
            for M in (0, 0.5, 1, 1.5, 2):
                h = hd(M); h0 = h0 or h
                rows.append({"M": M, "ci_low": h.ci_lb, "ci_high": h.ci_ub, "significant": not covers0(h)})
        except Exception as e:
            print("HonestDiD skipped: %s" % e); rows = []
        if rows:
            if covers0(h0): bd = 0.0
            else:
                lo, hi = 0.0, 2.0
                while not covers0(hd(hi)) and hi < 4096: lo, hi = hi, 2 * hi
                if not covers0(hd(hi)): bd = float("inf")
                else:
                    for _ in range(30):
                        if hi - lo <= 5e-3 * max(1.0, lo): break
                        mid = (lo + hi) / 2
                        if covers0(hd(mid)): hi = mid
                        else: lo = mid
                    bd = hi
            if np.isfinite(bd) and bd > 0:
                hb = hd(bd); rows.append({"M": bd, "ci_low": hb.ci_lb, "ci_high": hb.ci_ub, "significant": not covers0(hb)})
            grid = pd.DataFrame(rows).sort_values("M").reset_index(drop=True); grid["engine"] = "diff-diff HonestDiD"
            grid["target"] = str(getattr(h0, "target_label", "equal-weight mean of the post-period effects")); grid["breakdown_row"] = np.isclose(grid["M"], bd) if np.isfinite(bd) else False
            est, se = float(h0.original_estimate), float(h0.original_se)
            pv = float(2 * _st.norm.sf(abs(est / se))) if np.isfinite(se) and se > 0 else np.nan
            bd_how = ("no Mbar up to 4096 makes the robust interval cover 0 (the largest pre-period change is ~0)" if not np.isfinite(bd) else
                      "the effect is not significant even under exact parallel trends (Mbar = 0)" if bd == 0 else
                      f"the smallest Mbar whose robust interval covers 0 (bisection to 0.5 %): the effect survives a post-period violation up to {bd:.3g} x the largest pre-period one")
            res["M34"] = {"outcome": outcome, "estimate": est, "se": se, "p_value": pv, "breakdown_Mbar": bd, "breakdown_how": bd_how,
                          "se_how": "diff-diff HonestDiD: the SE of its target (the equal-weight mean of the post-period effects) from the Callaway-Sant'Anna event-study covariance",
                          "p_how": "normal (the package's inference)", "grid": grid, "engine": "diff-diff HonestDiD"}
            save("M34", "honest_did_grid", grid)
            print(f"M34 effect {est:.5g} (SE {se:.3g}) | breakdown Mbar {bd:.4g} -- {bd_how}")
    return res


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    run(a[0] if a else "NDVI")
