"""
Spec 2 -- Synthetic DiD (two-level) and Surrogate-Index DiD on the engine's estimation samples.

Two-level synthetic DiD
    Level 1 (aggregated): the sample is aggregated to cells (sub-watershed x ring x season, one mean per year -- the series the engine's M11
    uses). Unit weights w (donor cells) and time weights lambda (pre years) solve the regularised simplex problems
        min_w  || Ybar_treat,pre - sum_i w_i Y_i,pre ||_2^2 + zeta^2 T0 ||w||_2^2   s.t. sum w = 1, w >= 0
        min_l  || Ybar_donor,post - sum_t l_t Y_donor,t ||_2^2                      s.t. sum l = 1, l >= 0
    (Arkhangelsky et al. 2021; zeta from the donors' first differences as in the engine); ATT = the doubly weighted DiD; pre-RMSPE = the
    fit of the weighted donors to the treated pre trajectory; SE = leave-one-donor-out jackknife (deterministic, the same in R).
    Level 2 (pixel-level weighted TWFE, optional): every pixel takes its cell's unit weight (spread over the cell's pixels) and its year's
    time weight; the pixel x season and year x season fixed effects are removed by WEIGHTED alternating projections and the ATT is the
    weighted least-squares coefficient of the DiD term with a CR1 sandwich clustered at the sub-watershed (or the design's cluster).
Surrogate-index DiD (Athey, Chetty, Imbens, Kang 2019)
    Short-term proxies S (e.g. the Kharif NDWI / LSWI and the rain of the same year) predict the dry-season outcome Y. The link
    E[Y | S, year] is fitted by ridge on the CONTROL pool (every year), Y(0) is predicted for every treated pixel-year, and the ATT is
    the DiD of Y - Yhat(0): (treated post - treated pre) -- the treated pre residual removes the fit bias. SE = leave-one-cluster-out
    jackknife over the design's clusters (deterministic, the same in R).
Both return the standardised dictionary: att, se, p_value, pre_rmspe, unit weights per cell, time weights, n.
"""
import numpy as np, pandas as pd
from scipy import optimize as _opt, stats as _st
import _common as C

# ---------------------------------------------------------------- the simplex solvers
def _project_simplex(v):
    """Euclidean projection on {w >= 0, sum w = 1} (Duchi et al. 2008)."""
    u = np.sort(v)[::-1]; css = np.cumsum(u); k = np.arange(1, len(v) + 1)
    rho = np.nonzero(u * k > (css - 1))[0][-1]; theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0.0)

def _clean_weights(w):
    """Weights below 1e-9 are numerical residue of the solver (1e-30-sized), not weight: set to 0 and renormalised -- the same rows carry weight in R."""
    w = np.where(w < 1e-9, 0.0, w); s = w.sum(); return w / s if s > 0 else w

def simplex_ridge_weights(A, b, zeta=0.0, max_iter=5000, tol=1e-12):
    """min_w ||b - A' w||^2 + zeta^2 T0 ||w||^2  s.t. sum w = 1, w >= 0.  A: N0 x T0 (rows = units), b: T0.  SLSQP for small problems, projected
    gradient (the same objective) beyond 400 units -- the CPU memory fall-back of the spec (no N0 x N0 matrix is ever formed there)."""
    A = np.asarray(A, float); b = np.asarray(b, float); N0, T0 = A.shape; reg = float(zeta) ** 2 * T0
    def f(w): r = A.T @ w - b; return float(r @ r + reg * (w @ w))
    def grad(w): return 2.0 * (A @ (A.T @ w - b)) + 2.0 * reg * w
    w0 = np.full(N0, 1.0 / N0)
    if N0 <= 400:
        res = _opt.minimize(f, w0, jac=grad, method="SLSQP", bounds=[(0.0, 1.0)] * N0, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(N0)}],
                            options={"maxiter": 2000, "ftol": 1e-14})
        w = _clean_weights(_project_simplex(res.x))
        if f(w) <= f(w0) + 1e-12: return w
    w = w0.copy(); L = 2.0 * (np.linalg.norm(A, 2) ** 2 + reg); step = 1.0 / max(L, 1e-12)
    for _ in range(max_iter):
        w_new = _project_simplex(w - step * grad(w))
        if np.abs(w_new - w).max() < tol: w = w_new; break
        w = w_new
    return _clean_weights(w)

# ---------------------------------------------------------------- level 1: the aggregated synthetic DiD
def aggregate_cells(df, outcome, cell=("site_id", "buff_km", "Season")):
    """One mean per cell and year, with the pixel count; the treated cells are the ring-0 cells."""
    d = df[np.isfinite(pd.to_numeric(df[outcome], errors="coerce").values)]
    keys = [c for c in cell if c in d.columns] + ["Year"]
    g = d.groupby(keys, observed=True).agg(y=(outcome, "mean"), n=(outcome, "size"), n_pix=("pixel_id", "nunique"), post=("post", "max")).reset_index()
    g["treated"] = (pd.to_numeric(g["buff_km"], errors="coerce") == 0).astype(int)
    g["cell"] = g[[c for c in cell if c in g.columns]].astype(str).agg("|".join, axis=1)
    return g

def _sdid_on_matrix(Y, treated, pre_mask, zeta=None):
    """Y: units x years (balanced), treated: bool per unit, pre_mask: bool per year. Returns tau, omega (donors), lam (pre years), pre_rmspe, zeta."""
    Yc = Y[~treated]; Yt = Y[treated]; N1 = int(treated.sum()); T1 = int((~pre_mask).sum())
    if zeta is None: zeta = C.compute_sdid_regularization(Yc[:, pre_mask], N1, T1)
    omega = simplex_ridge_weights(Yc[:, pre_mask], Yt[:, pre_mask].mean(axis=0), zeta)
    lam = simplex_ridge_weights(Yc[:, pre_mask].T, Yc[:, ~pre_mask].mean(axis=1), 1e-6)        # time weights: the donors' post mean from their pre years (a 1e-6 ridge: one optimum, the same in R)
    tr_post = Yt[:, ~pre_mask].mean(); tr_pre = float(lam @ Yt[:, pre_mask].mean(axis=0))
    do_post = float(omega @ Yc[:, ~pre_mask].mean(axis=1)); do_pre = float(omega @ (Yc[:, pre_mask] @ lam))
    tau = (tr_post - tr_pre) - (do_post - do_pre)
    fit = Yc[:, pre_mask].T @ omega; pre_rmspe = float(np.sqrt(np.mean((Yt[:, pre_mask].mean(axis=0) - fit) ** 2)))
    return float(tau), omega, lam, pre_rmspe, float(zeta)

def synthetic_did_two_level(df, outcome, season=None, cell=("site_id", "buff_km", "Season"), zeta=None, pixel_level=True, cluster_col="subwshed_id", verbose=True):
    """The two-level synthetic DiD on an estimation sample (build_treatment_columns rows with in_analysis_sample == 1). season: one season
    code (e.g. 2 = Rabi) or None (every season, the cell carries it). One fit per cohort x season block when the timing is staggered."""
    d = df if season is None else df[pd.to_numeric(df["Season"], errors="coerce") == int(season)]
    if not len(d): raise C.InsufficientDataError(f"synthetic DiD: no rows of {outcome}" + (f" in season {season}" if season is not None else ""))
    g = aggregate_cells(d, outcome, cell); rows = []; wrows = []; lrows = []
    for se_, gs in g.groupby("Season") if "Season" in g.columns else [(None, g)]:
        yrs = sorted(gs["Year"].unique()); piv = gs.pivot(index="cell", columns="Year", values="y")
        full = piv.dropna(axis=0, how="any")                                       # the balanced block the solver needs
        meta = gs.drop_duplicates("cell").set_index("cell").loc[full.index]
        meta["n_pix"] = gs.groupby("cell")["n_pix"].max().loc[full.index].values          # the cell's pixels = its largest year (row order plays no part: the same in R)
        treated = meta["treated"].values.astype(bool)
        post_year = gs.groupby("Year")["post"].max(); pre_mask = np.array([post_year.get(y, 0) == 0 for y in full.columns])
        if treated.sum() == 0 or (~treated).sum() < 2 or pre_mask.sum() < 2 or (~pre_mask).sum() < 1:
            rows.append({"Season": se_, "status": f"skipped: {int(treated.sum())} treated / {int((~treated).sum())} donor cells, {int(pre_mask.sum())} pre / {int((~pre_mask).sum())} post years"}); continue
        Y = full.values.astype(float)
        tau, omega, lam, rmspe, z = _sdid_on_matrix(Y, treated, pre_mask, zeta)
        donors = np.where(~treated)[0]
        jk = []                                                                     # leave-one-donor-out jackknife (deterministic)
        for j in range(len(donors)):
            keep = np.ones(len(Y), bool); keep[donors[j]] = False
            try: jk.append(_sdid_on_matrix(Y[keep], treated[keep], pre_mask, z)[0])
            except Exception: pass
        jk = np.asarray(jk); se = float(np.sqrt((len(jk) - 1) / len(jk) * np.sum((jk - jk.mean()) ** 2))) if len(jk) >= 2 else float("nan")
        rows.append({"Season": se_, "status": "fitted", "ATT": tau, "se": se, "pre_rmspe": rmspe, "zeta": z, "n_treated_cells": int(treated.sum()), "n_donor_cells": int(len(donors)),
                     "pre_years": int(pre_mask.sum()), "post_years": int((~pre_mask).sum()), "treated_pixels": int(meta.loc[treated, "n_pix"].sum()), "donor_pixels": int(meta.loc[~treated, "n_pix"].sum())})
        for j, w in zip(donors, omega): wrows.append({"Season": se_, "cell": full.index[j], "site_id": meta.iloc[j].get("site_id"), "buff_km": meta.iloc[j].get("buff_km"), "unit_weight": float(w), "n_pix": int(meta.iloc[j]["n_pix"])})
        for y, l in zip(np.array(full.columns)[pre_mask], lam): lrows.append({"Season": se_, "Year": int(y), "time_weight": float(l)})
    tab = pd.DataFrame(rows); fit = tab[tab.get("status", "") == "fitted"] if len(tab) else tab
    if not len(fit): raise C.InsufficientDataError("synthetic DiD: no season block with >= 1 treated cell, >= 2 donor cells, >= 2 pre and >= 1 post year -- " + "; ".join(tab.get("status", pd.Series(dtype=str)).tolist()))
    wgt = fit["treated_pixels"].values / fit["treated_pixels"].sum()
    att = float((wgt * fit["ATT"].values).sum()); se = float(np.sqrt(np.sum(wgt ** 2 * fit["se"].values ** 2))) if np.all(np.isfinite(fit["se"].values)) else float("nan")
    p = float(2 * _st.norm.sf(abs(att / se))) if np.isfinite(se) and se > 0 else float("nan")
    out = {"estimator": "synthetic_did_two_level", "outcome": outcome, "att": att, "se": se, "p_value": p, "pre_rmspe": float((wgt * fit["pre_rmspe"].values).sum()),
           "n_fits": int(len(fit)), "n_treated_cells": int(fit["n_treated_cells"].sum()), "n_donor_cells": int(fit["n_donor_cells"].sum()), "n_rows": int(len(d)),
           "se_how": "leave-one-donor-cell-out jackknife per season block, combined with the treated-pixel weights of the blocks",
           "unit_weights": pd.DataFrame(wrows), "time_weights": pd.DataFrame(lrows), "blocks": tab}
    if pixel_level:
        out["pixel_wls"] = weighted_twfe_from_weights(d, outcome, out["unit_weights"], out["time_weights"], cluster_col=cluster_col)
    if verbose:
        C.info(f"synthetic DiD (two-level, {outcome}{'' if season is None else ', season ' + str(season)}): ATT {att:+.6f} (jackknife se {se:.6f}, p {p:.3g}), pre-RMSPE {out['pre_rmspe']:.5f}, "
               f"{out['n_treated_cells']} treated / {out['n_donor_cells']} donor cells in {out['n_fits']} block(s)"
               + (f"; pixel-level weighted TWFE {out['pixel_wls']['beta']:+.6f} (se {out['pixel_wls']['se']:.6f}, {out['pixel_wls']['n_clusters']} clusters)" if pixel_level and out.get("pixel_wls") else ""))
    return out

# ---------------------------------------------------------------- level 2: the pixel-level weighted TWFE
def weighted_demean_two_way(y, u, t, w, tol=1e-11, max_iter=500):
    """Weighted alternating projections: remove the weighted unit and period means until the change is below tol."""
    y = np.asarray(y, float).copy(); w = np.asarray(w, float)
    su = np.bincount(u, weights=w); st = np.bincount(t, weights=w)
    for _ in range(max_iter):
        y0 = y.copy()
        y -= (np.bincount(u, weights=w * y) / np.maximum(su, 1e-300))[u]
        y -= (np.bincount(t, weights=w * y) / np.maximum(st, 1e-300))[t]
        if np.abs(y - y0).max() < tol: break
    return y

def weighted_twfe(df, y_col, x_col, unit_col, time_col, w, cluster_col):
    """WLS of y on x with unit and period fixed effects and weights w; CR1 sandwich clustered on cluster_col, fixest's small-sample rule."""
    w = np.asarray(w, float); keep = np.isfinite(w) & (w > 0)
    d = df[keep]; w = w[keep]
    u = pd.factorize(d[unit_col].values)[0]; t = pd.factorize(d[time_col].values)[0]; cl = pd.factorize(d[cluster_col].values)[0]
    yd = weighted_demean_two_way(pd.to_numeric(d[y_col], errors="coerce").values, u, t, w); xd = weighted_demean_two_way(pd.to_numeric(d[x_col], errors="coerce").values, u, t, w)
    sxx = float(np.sum(w * xd * xd))
    if sxx <= 0: raise C.InsufficientDataError("weighted TWFE: the DiD term does not vary within the weighted units and periods")
    beta = float(np.sum(w * xd * yd) / sxx); e = yd - beta * xd
    S = np.bincount(cl, weights=w * xd * e); G = len(S); n = len(d)
    K = 1 + C._k_fe_nonnested([d[unit_col].values, d[time_col].values], cl)
    var = float(np.sum(S ** 2)) / sxx ** 2 * (G / max(G - 1, 1)) * ((n - 1) / max(n - K, 1))
    se = float(np.sqrt(var)); p = float(2 * _st.t.sf(abs(beta / se), max(G - 1, 1))) if se > 0 else float("nan")
    return {"beta": beta, "se": se, "p_value": p, "n": int(n), "n_clusters": int(G), "cluster": str(cluster_col), "sum_weights": float(w.sum())}

def weighted_twfe_from_weights(d, outcome, unit_weights, time_weights, cluster_col="subwshed_id"):
    """The pixel-level regression of level 2: every donor pixel carries its cell's unit weight spread over the cell's pixels, every treated pixel
    1 / n_treated (within the season block); every pre-year row its year's time weight, every post row 1 / T1."""
    d = d.copy(); d["_cell"] = d[["site_id", "buff_km", "Season"]].astype(str).agg("|".join, axis=1)
    uw = dict(zip(unit_weights["cell"], unit_weights["unit_weight"] / unit_weights["n_pix"])) if len(unit_weights) else {}
    tw = {(int(r.Season), int(r.Year)): float(r.time_weight) for r in time_weights.itertuples()} if len(time_weights) else {}
    tr = d["treatment"].values == 1; post = d["post"].values == 1
    n_tr = d.loc[tr].groupby("Season")["pixel_id"].nunique(); n_post = d.loc[post].groupby("Season")["Year"].nunique()
    wu = np.where(tr, 1.0 / d["Season"].map(n_tr).fillna(1).values, d["_cell"].map(uw).fillna(0.0).values)
    wt = np.where(post, 1.0 / d["Season"].map(n_post).fillna(1).values, [tw.get((int(s), int(y)), 0.0) for s, y in zip(d["Season"].values, d["Year"].values)])
    w = wu * wt
    ck = C._cluster_key(d, cluster_col)
    r = weighted_twfe(d, outcome, "did_term", C._unit_key(d, "pixel_id"), "time_fe_yearseason", w, ck)
    r["weights_how"] = "unit weight of the cell / pixels of the cell (donors), 1 / treated pixels (treated) x time weight of the year (pre), 1 / post years (post)"
    return r

# ---------------------------------------------------------------- the surrogate-index DiD
def surrogate_index_did(df, outcome, surrogates, outcome_seasons=(2, 3), surrogate_season=1, ridge=1e-3, cluster_col="subwshed_id", verbose=True):
    """Y = the pixel-year mean of `outcome` over outcome_seasons (the dry seasons); S = the pixel-year values of `surrogates` in
    surrogate_season (Kharif) plus that year's rain if present. Ridge of Y on S + year dummies on the CONTROL pool (every year); Yhat(0) for
    every pixel-year; ATT = (mean treated post residual) - (mean treated pre residual); SE = leave-one-cluster-out jackknife."""
    sur = [s for s in surrogates if s in df.columns]
    if not sur: raise C.InsufficientDataError(f"surrogate index: none of the surrogates {list(surrogates)} is in the sample (columns: {[c for c in df.columns if c.isupper()][:12]})")
    df = df.copy(); cluster_col = C._cluster_key(df, cluster_col)                      # the design's cluster (site -> years when few sub-watersheds; 'block' = ~1 km blocks)
    se_ = pd.to_numeric(df["Season"], errors="coerce").values
    yo = df[np.isin(se_, list(outcome_seasons)) & np.isfinite(pd.to_numeric(df[outcome], errors="coerce").values)]
    Y = yo.groupby(["pixel_id", "Year"], observed=True).agg(y=(outcome, "mean"), treated=("treatment", "max"), post=("post", "max"), cl=(cluster_col, "first")).reset_index()
    xs = df[se_ == int(surrogate_season)].groupby(["pixel_id", "Year"], observed=True)[sur].mean().reset_index()
    D = Y.merge(xs, on=["pixel_id", "Year"], how="inner").dropna(subset=sur + ["y"])
    if len(D) < 30: raise C.InsufficientDataError(f"surrogate index: only {len(D)} pixel-years carry both the dry-season {outcome} and the {surrogate_season}-season surrogates")
    yrs = sorted(D["Year"].unique()); Xy = np.column_stack([(D["Year"].values == y).astype(float) for y in yrs])
    def design(frame): return np.column_stack([frame[sur].values.astype(float), np.column_stack([(frame["Year"].values == y).astype(float) for y in yrs])])
    def fit_predict(train, pred):
        X = design(train); y = train["y"].values.astype(float); mu = X[:, :len(sur)].mean(axis=0); sd = X[:, :len(sur)].std(axis=0) + 1e-12
        Xs = X.copy(); Xs[:, :len(sur)] = (Xs[:, :len(sur)] - mu) / sd
        P = np.full(X.shape[1], 1e-8 * len(train)); P[:len(sur)] = ridge * len(train)   # ridge on the surrogates; a 1e-8 ridge on the year dummies (a year absent from a jackknife fold never makes the solve singular)
        beta = np.linalg.solve(Xs.T @ Xs + np.diag(P), Xs.T @ y)
        Xp = design(pred).copy(); Xp[:, :len(sur)] = (Xp[:, :len(sur)] - mu) / sd
        return Xp @ beta, beta
    ctrl = D[D.treated == 0]; trt = D[D.treated == 1]
    if not len(trt) or not len(ctrl): raise C.InsufficientDataError("surrogate index: the sample lacks treated or control pixel-years")
    yhat, beta = fit_predict(ctrl, trt); res = trt["y"].values - yhat
    pre = trt["post"].values == 0; post = ~pre
    if not pre.any() or not post.any(): raise C.InsufficientDataError("surrogate index: the treated pixel-years lack a pre or a post period")
    att = float(res[post].mean() - res[pre].mean()); pre_rmspe = float(np.sqrt(np.mean(res[pre] ** 2)))
    cls = sorted(D["cl"].astype(str).unique()); jk = []
    for c in cls:                                                                    # leave-one-cluster-out: the fit AND the treated means without the cluster
        m_c = D["cl"].astype(str).values != c; Dc = D[m_c]; cc = Dc[Dc.treated == 0]; tt = Dc[Dc.treated == 1]
        if len(cc) < 10 or not len(tt): continue
        yh, _ = fit_predict(cc, tt); r_ = tt["y"].values - yh; pr = tt["post"].values == 0
        if pr.any() and (~pr).any(): jk.append(float(r_[~pr].mean() - r_[pr].mean()))
    jk = np.asarray(jk); se = float(np.sqrt((len(jk) - 1) / len(jk) * np.sum((jk - jk.mean()) ** 2))) if len(jk) >= 2 else float("nan")
    p = float(2 * _st.t.sf(abs(att / se), max(len(jk) - 1, 1))) if np.isfinite(se) and se > 0 else float("nan")
    ctrl_fit = fit_predict(ctrl, ctrl)[0]; r2 = float(1 - np.sum((ctrl["y"].values - ctrl_fit) ** 2) / max(np.sum((ctrl["y"].values - ctrl["y"].values.mean()) ** 2), 1e-300))
    out = {"estimator": "surrogate_index_did", "outcome": outcome, "surrogates": sur, "outcome_seasons": list(outcome_seasons), "surrogate_season": int(surrogate_season),
           "att": att, "se": se, "p_value": p, "pre_rmspe": pre_rmspe, "surrogate_r2_control": r2, "n_pixel_years": int(len(D)), "n_treated_pixel_years": int(len(trt)),
           "n_control_pixel_years": int(len(ctrl)), "n_clusters": int(len(cls)), "cluster": str(cluster_col), "ridge": float(ridge),
           "coefficients": dict(zip(sur, [float(b) for b in beta[:len(sur)]])), "se_how": f"leave-one-cluster-out jackknife over {len(cls)} clusters ({cluster_col})"}
    if verbose:
        C.info(f"surrogate-index DiD ({outcome} in seasons {list(outcome_seasons)} from {sur} of season {surrogate_season}): ATT {att:+.6f} (jackknife se {se:.6f}, p {p:.3g}), "
               f"pre-RMSPE {pre_rmspe:.5f}, control-pool R2 {r2:.3f}, {len(D):,} pixel-years, {len(cls)} clusters")
    return out

def standard_row(res):
    """The one-row summary the report prints: estimator, att, se, p, pre_rmspe, n."""
    return {"estimator": res.get("estimator"), "outcome": res.get("outcome"), "att": res.get("att"), "se": res.get("se"), "p_value": res.get("p_value"), "pre_rmspe": res.get("pre_rmspe"),
            "n": res.get("n_rows", res.get("n_pixel_years")), "se_how": res.get("se_how", "")}

def save_outputs(res, results_dir, outcome):
    """The standardised files beside the model's results."""
    tag = res["estimator"]
    C.save_results({k: v for k, v in res.items() if not isinstance(v, (pd.DataFrame, dict, list))} | {"surrogates": ";".join(res.get("surrogates", []))} if "surrogates" in res else
                   {k: v for k, v in res.items() if not isinstance(v, (pd.DataFrame, dict, list))}, results_dir, f"{tag}_{outcome}.csv")
    for k in ("unit_weights", "time_weights", "blocks"):
        if isinstance(res.get(k), pd.DataFrame) and len(res[k]): C.save_results(res[k], results_dir, f"{tag}_{k}_{outcome}.csv")
    if isinstance(res.get("pixel_wls"), dict): C.save_results({"outcome": outcome, **res["pixel_wls"]}, results_dir, f"{tag}_pixel_wls_{outcome}.csv")
