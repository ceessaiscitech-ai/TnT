"""
ml_spatial_pipeline.py -- pre-built ML and spatial layers (v20.23) + RUN_PREBUILT_PY orchestrator.

ML models on the LONG DIFFERENCE: for every pixel, dY = mean(outcome | post) - mean(outcome | pre), treatment = core
indicator, X = pre-period covariate means (+ site). That is the DiD-consistent cross-section on which CATE
estimators are defined (a treatment effect on the *change*), and it is what the custom M39-M45 do.

    M40  LinearDML            econml.dml.LinearDML                (double / debiased ML)      alt: doubleml.DoubleMLPLR
    M41  meta-learners        econml.metalearners S/T/XLearner
    M42  DR-learner           econml.dr.DRLearner
    M43  causal forest        econml.dml.CausalForestDML (honest, Athey-Tibshirani-Wager)
    M39  ML CATE summary      the same forest, CATE by covariate quantile
    M44  BART                 no maintained Python implementation -> R dbarts / bartCause (see R pipeline)
    M45  ML synthetic control mlsynth (single treated unit) -- site-level only; documented, not wired
    M17  Moran's I            esda.Moran on pixel effects, libpysal KNN weights
    M18  LISA                 esda.Moran_Local

    pip install econml doubleml esda libpysal
"""
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from pf_pipeline import package_input, out_dir, _engine


def long_difference(df, outcome, covariates=("Rain", "Tmax", "Tmean", "Tmin"), min_pre=2, min_post=1, by=None):
    covs = [c for c in covariates if c in df.columns]
    by = by or ("unit" if "unit" in df.columns else "pixel_id")     # v20.29: one long difference per series
    if "Season" in df.columns and df["Season"].nunique() > 1 and by != "pixel_id":   # v20.58: a season series against the control
        try:                                                                         #   rings' mean of the SAME season and year (as R's
            import _common as _C                                                     #   season_net): its own split, its own season's shocks
            df = df.copy(); df[outcome] = _C.season_net(df, outcome, treat_col="treat"); df = df[np.isfinite(df[outcome].values)]
        except Exception as e:
            print("season-matching skipped:", e)
    pre = df[df.post == 0].groupby(by).agg(y_pre=(outcome, "mean"), n_pre=(outcome, "size"), **{c: (c, "mean") for c in covs},
                                                  treat=("treat", "max"), cluster=("cluster_id", "first"), site=("site_id", "first"))
    post = df[df.post == 1].groupby(by).agg(y_post=(outcome, "mean"), n_post=(outcome, "size"))
    ld = pre.join(post, how="inner"); ld = ld[(ld.n_pre >= min_pre) & (ld.n_post >= min_post)]
    ld["dY"] = ld.y_post - ld.y_pre
    return ld.reset_index(), covs


def _save(C, model, name, obj, outcome):
    d = out_dir(f"ml_{model}", C); (obj if isinstance(obj, pd.DataFrame) else pd.DataFrame([obj])).to_csv(os.path.join(d, f"{name}_{outcome}.csv"), index=False)


def run_ml(outcome, C=None, models=("M40", "M41", "M42", "M43", "M39"), n_jobs=None, n_max=None, _ld=None):   # None = the 98 % RAM rule
    C = C or _engine()
    try:
        import _hardware as _Hw; _cores = _Hw.cpu_budget()                  # v20.47: this pipeline's share of the cores
    except Exception:
        _cores = os.cpu_count() or 1                                      # v20.57: every core
    n_jobs = n_jobs or max(1, _cores)                                      # v20.52: every core (no cap, your instruction)
    ld, covs = _ld if _ld is not None else long_difference(package_input(outcome, C), outcome)
    n_max = n_max or (C.rows_that_fit(2500.0) if hasattr(C, "rows_that_fit") else None) or len(ld)   # forests ~2.5 KB / pixel
    if len(ld) > n_max:                                                   # v20.58 YOUR RULE: every pixel -- beyond 98 % of the RAM the
        return _run_ml_batches(outcome, C, models, n_jobs, ld, covs, int(n_max))   #   models run on BATCHES (v20.57 sampled pixels)
    if not covs: raise SystemExit("no covariates in the package input")
    X = ld[covs].values; T = ld["treat"].values.astype(int); Y = ld["dY"].values
    print(f"long difference: {len(ld):,} pixels ({int(T.sum()):,} treated), covariates {covs}")
    res = {}
    try:
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
    except ImportError as e:
        raise SystemExit("scikit-learn missing") from e
    rf_y = lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=20, n_jobs=n_jobs, random_state=0)
    rf_t = lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=20, n_jobs=n_jobs, random_state=0)
    npx = f"{len(ld):,} " + ("pixel x season series" if "unit" in ld.columns else "pixels")   # v20.58: the long-difference units (as R)
    if "M40" in models:
        try:
            from econml.dml import LinearDML
            # v20.58 (second pass): the PARTIALLY LINEAR model of R's DoubleML PLR -- ONE effect, the covariates as controls (W), the SE of
            # the partialling-out score (HC0, as DoubleML's). With X = the covariates LinearDML fitted a linear CATE theta(X) and averaged
            # it: another estimator (1.2 SE from R's on the parity panel; its SE 15 % below). Checked: on the same folds and forests the two
            # packages give the same estimate to 1e-8 and the same SE.
            try:
                from econml.inference import StatsModelsInference
                _inf = StatsModelsInference(cov_type="HC0")
            except ImportError:
                _inf = "auto"
            m = LinearDML(model_y=rf_y(), model_t=rf_t(), discrete_treatment=True, cv=3, random_state=0).fit(Y, T, X=None, W=X, inference=_inf)
            inf = m.ate_inference(); ate_ = float(np.ravel(m.ate())[0])
            res["M40"] = _with_p({"outcome": outcome, "target": "ATE", "estimate": ate_, "ate": ate_, "se": float(np.ravel(inf.stderr_mean)[0]),
                                  "se_how": f"econml LinearDML, the partially linear model (DoubleML PLR's; 3-fold cross-fitting): its asymptotic SE "
                                            f"(HC0, as DoubleML), each of the {npx} one draw (not clustered)",
                                  "engine": "econml LinearDML (partially linear)"})
            _save(C, "M40", "double_ml", res["M40"], outcome); print("M40", res["M40"])
        except ImportError:
            try:
                import doubleml as dml
                data = dml.DoubleMLData(pd.concat([ld[covs], pd.Series(Y, name="dY"), pd.Series(T, name="treat")], axis=1), y_col="dY", d_cols="treat", x_cols=covs)
                m = dml.DoubleMLPLR(data, rf_y(), rf_t(), n_folds=3).fit()
                res["M40"] = _with_p({"outcome": outcome, "target": "ATE", "estimate": float(m.coef[0]), "ate": float(m.coef[0]), "se": float(m.se[0]),
                                      "se_how": f"DoubleML PLR (3-fold cross-fitting): its asymptotic SE, each of the {npx} one draw (not clustered)",
                                      "engine": "DoubleML PLR"})
                _save(C, "M40", "double_ml", res["M40"], outcome); print("M40", res["M40"])
            except ImportError:
                print("M40 needs econml or doubleml")
    if "M41" in models:
        try:
            from econml.metalearners import SLearner, TLearner, XLearner
            rows = []
            for name, L in (("S", SLearner(overall_model=rf_y())), ("T", TLearner(models=rf_y())), ("X", XLearner(models=rf_y(), propensity_model=rf_t()))):
                L.fit(Y, T, X=X); cate = L.effect(X)
                rows.append({"outcome": outcome, "learner": name, "att": float(np.mean(cate[T == 1])), "ate": float(np.mean(cate)), "cate_sd": float(np.std(cate)),
                             "n": int(len(Y)), "engine": "econml"})
            tab = pd.DataFrame(rows); _save(C, "M41", "meta_learners", tab, outcome); print("M41", rows)
            # v20.58 (as R's M41): the headline is the mean of the learners' ATEs (S, T and X in both languages); the learners give no SE
            res["M41"] = {"outcome": outcome, "target": "ATE", "estimate": float(tab["ate"].mean()), "ate": float(tab["ate"].mean()),
                          "att": float(tab["att"].mean()), "se_note": "S / T / X learners give no standard error", "engine": "econml meta-learners (S / T / X)",
                          "meta_learners": tab}
        except ImportError:
            print("M41 needs econml")
    if "M42" in models:
        try:
            from econml.dr import DRLearner
            m = DRLearner(model_propensity=rf_t(), model_regression=rf_y(), model_final=GradientBoostingRegressor(random_state=0), cv=3,
                          random_state=0).fit(Y, T, X=X, cache_values=True)
            cate = m.effect(X)
            # v20.58 (as R's grf AIPW): the headline is the ATE of the doubly robust (AIPW) scores the learner cross-fitted -- its mean IS
            # econml's ate() -- with the SE of those scores (v20.57 took the mean CATE of the TREATED pixels, without an SE: another estimand)
            phi = _dr_scores(m)
            ate = float(np.mean(phi)) if phi is not None else float(np.mean(cate))
            se = float(np.std(phi, ddof=1) / np.sqrt(len(phi))) if phi is not None and len(phi) > 1 else float("nan")
            res["M42"] = _with_p({"outcome": outcome, "target": "ATE", "estimate": ate, "se": se, "ate": ate, "att": float(np.mean(cate[T == 1])),
                                  "cate_sd": float(np.std(cate)), "se_how": (f"econml DRLearner: the SE of its cross-fitted doubly robust (AIPW) scores, each of the "
                                                                              f"{npx} one draw (not clustered) -- as R's grf AIPW" if phi is not None else
                                                                              "econml DRLearner: its AIPW scores were not readable in this econml version"),
                                  "engine": "econml DRLearner"})
            _save(C, "M42", "dr_learner", res["M42"], outcome); print("M42", res["M42"])
        except ImportError:
            print("M42 needs econml")
    if "M43" in models or "M39" in models:
        try:
            from econml.dml import CausalForestDML
            _mk = lambda: CausalForestDML(model_y=rf_y(), model_t=rf_t(), discrete_treatment=True, n_estimators=500, min_samples_leaf=20,
                                          honest=True, cv=3, random_state=0, n_jobs=n_jobs)
            m = _mk().fit(Y, T, X=X, cache_values=True)
            cate = m.effect(X); lo, hi = m.effect_interval(X, alpha=0.05)
            # v20.58 (as R's grf::average_treatment_effect(target.sample = "treated", method = "AIPW")): grf's doubly robust ATT, ported from the
            # grf source, on THIS forest's out-of-bag effects and its cross-fitted E[Y | X] and propensity -- the same estimator and SE as R's route.
            # econml's own att_ (the mean of its doubly robust scores over the treated: another estimator of the ATT, ~3.7 x the SE on the poison
            # panel) stays beside it
            try:
                tau_cf = _econml_crossfit_tau(_mk, Y, T, X)                         # v20.58: out-of-sample effects (see _econml_crossfit_tau)
            except Exception as e_:
                print("cross-fitted effects not computed:", e_); tau_cf = None
            g_ = _grf_att_from_econml(m, Y, T, clusters=(ld["site"].values if "site" in ld.columns and ld["site"].nunique() >= getattr(C, "MIN_SWS_CLUSTERS", 6) else None),
                                      tau=tau_cf)
            att_e = float(np.ravel(m.att_(T=1))[0]); att_e_se = float(np.ravel(m.att_stderr_(T=1))[0])
            att, att_se = (g_["estimate"], g_["se"]) if g_ is not None else (att_e, att_e_se)
            head = {"outcome": outcome, "target": "ATT", "estimate": att, "se": att_se, "att": att, "ate": float(np.ravel(m.ate_)[0]),
                    "att_econml_dr_scores": att_e, "se_att_econml_dr_scores": att_e_se,
                    "mean_cate_treated": float(np.mean(cate[T == 1])), "cate_sd": float(np.std(cate)),
                    "share_significant_positive": float(np.mean(lo > 0)), "share_significant_negative": float(np.mean(hi < 0)),
                    "se_how": ((f"grf's doubly robust ATT (average_treatment_effect, target.sample = 'treated', AIPW; ported) on econml CausalForestDML "
                                f"(honest; each series' effect cross-fitted out of sample): its SE, " + (g_["cluster_text"] if g_["cluster_text"] != "not clustered" else f"each of the {npx} one draw (not clustered)"))
                               if g_ is not None else f"econml CausalForestDML (honest): the SE of its doubly robust ATT scores, each of the {npx} one draw (not clustered)"),
                    "engine": "econml CausalForestDML (honest) + grf's ATT formula"}
            res["M43"] = _with_p(dict(head))
            _save(C, "M43", "causal_forest", res["M43"], outcome); print("M43", res["M43"])
            if "M39" in models:
                rows = []
                for c in covs:
                    q = pd.qcut(ld[c], 4, labels=False, duplicates="drop")
                    for qq in sorted(pd.unique(q.dropna())):
                        mm = (q == qq).values; rows.append({"outcome": outcome, "covariate": c, "quartile": int(qq) + 1, "cate_mean": float(np.mean(cate[mm])), "n": int(mm.sum())})
                tab = pd.DataFrame(rows); _save(C, "M39", "cate_by_covariate_quartile", tab, outcome)
                # v20.58 (as R's M39): the headline is the same forest's ATT and SE; the CATE by covariate quartile is its table
                res["M39"] = _with_p({**head, "engine": "econml CausalForestDML (CATE by covariate quartile)", "cate_by_covariate_quartile": tab})
        except ImportError:
            print("M43/M39 need econml")
    return res


def _with_p(r):
    """v20.58: the p of an ML headline -- normal, from the estimate and the package's asymptotic SE (as R's ML routes)."""
    try:
        from scipy import stats as _st
        e, s = float(r.get("estimate", np.nan)), float(r.get("se", np.nan))
        if np.isfinite(e) and np.isfinite(s) and s > 0:
            r["p_value"] = float(2 * _st.norm.sf(abs(e / s))); r["p_how"] = "normal, from the estimate and the package's asymptotic SE"
    except Exception:
        pass
    return r


def _econml_crossfit_tau(make, Y, T, X, seed=0):
    """v20.58: every series' effect OUT OF SAMPLE from the same econml causal forest (two halves, each predicted by the forest grown on the
    other). econml's own out-of-bag effects (_oob_preds) were ~25 x as dispersed as grf's on the parity panel (sd 0.020 against grf's 0.0008,
    unchanged with 4,000 trees) and made the ATT's SE 4.3 x R's; the cross-fitted effects are as dispersed as grf's (sd 0.0011)."""
    n = len(Y); rng = np.random.default_rng(seed); idx = rng.permutation(n); h = n // 2; A, B = idx[:h], idx[h:]
    tau = np.full(n, np.nan)
    for a, b in ((A, B), (B, A)):
        tau[b] = np.ravel(make().fit(Y[a], T[a], X=X[a]).effect(X[b]))
    return tau


def _grf_att_from_econml(m, Y, T, clusters=None, tau=None):
    """grf::average_treatment_effect(forest, target.sample = "treated", method = "AIPW") -- ported line by line from the grf source -- on a fitted
    econml CausalForestDML (fit with cache_values=True): tau = the forest's out-of-bag effects, Y.hat = Y - Y_res and W.hat = T - T_res (the
    cross-fitted first stage). mu0 = Y.hat - W.hat tau, mu1 = Y.hat + (1 - W.hat) tau; gamma = 1 on the treated and W.hat / (1 - W.hat) on the
    controls, each normalised to sum n; the estimate = mean(tau | treated) + mean(W gamma (Y - mu1) - (1 - W) gamma (Y - mu0)); the SE =
    sqrt(var of the plug-in mean + the correction's variance x n / (n - 1)) -- per cluster when clusters are given (grf's cluster.se).
    None when this econml version does not keep the nuisances."""
    try:
        Yv = np.asarray(Y, float).ravel(); W = np.asarray(T, float).ravel(); n = len(Yv)
        nu = m._cached_values.nuisances
        Yres = np.asarray(nu[0], float).reshape(n, -1)[:, 0]; Tres = np.asarray(nu[1], float).reshape(n, -1)[:, 0]
        tau = (np.asarray(m.rlearner_model_final_._oob_preds, float).reshape(n, -1)[:, 0] if tau is None
               else np.asarray(tau, float).ravel())                                 # v20.58: the cross-fitted effects when given
    except Exception:
        return None
    ok = np.isfinite(tau) & np.isfinite(Yres) & np.isfinite(Tres)
    if ok.sum() < 3: return None
    Yv, W, Yres, Tres, tau = Yv[ok], W[ok], Yres[ok], Tres[ok], tau[ok]; n = len(Yv)
    Yhat = Yv - Yres; What = W - Tres
    tr = W == 1; co = ~tr
    if tr.sum() < 2 or co.sum() < 2: return None
    mu0 = Yhat - What * tau; mu1 = Yhat + (1 - What) * tau
    raw = float(np.mean(tau[tr])); var_raw = float(np.sum((tau[tr] - raw) ** 2) / tr.sum() ** 2)
    g = np.zeros(n); gc = What[co] / (1 - What[co]); g[co] = gc / gc.sum() * n; g[tr] = n / tr.sum()
    dr = W * g * (Yv - mu1) - (1 - W) * g * (Yv - mu0)
    corr = float(np.mean(dr))
    if clusters is not None:
        cl = pd.factorize(pd.Series(np.asarray(clusters)[ok]).astype(str))[0]; G = int(cl.max()) + 1
        s2 = float(np.sum(np.bincount(cl, weights=dr) ** 2) / n ** 2 * G / (G - 1)); ctext = f"clustered by sub-watershed ({G})"
    else:
        s2 = float(np.sum(dr ** 2) / n ** 2 * n / (n - 1)); ctext = "not clustered"
    return {"estimate": raw + corr, "se": float(np.sqrt(var_raw + s2)), "cluster_text": ctext}


def _dr_scores(m):
    """The cross-fitted doubly robust scores of a fitted econml DRLearner (fit with cache_values=True): Y(1)-hat minus Y(0)-hat per pixel,
    or None when this econml version does not keep them."""
    try:
        yp = np.asarray(m._cached_values.nuisances[0], dtype=float)
        if yp.ndim == 2 and yp.shape[1] >= 2: return yp[:, 1] - yp[:, 0]
    except Exception:
        pass
    return None


def _run_ml_batches(outcome, C, models, n_jobs, ld, covs, cap):
    """v20.58: the ML models on BATCHES of pixels (the treated spread evenly) -- every pixel used once; the batch estimates averaged (weights:
    the treated pixels for an ATT, all pixels for an ATE), the SE from independent batches. Divide and conquer, used only beyond 98 % of the RAM."""
    rng = np.random.default_rng(1); k = int(np.ceil(len(ld) / cap)); b = np.empty(len(ld), int)
    for tv in (0, 1):
        i = np.flatnonzero(ld["treat"].values == tv); b[i] = rng.permutation(np.resize(np.arange(k), len(i)))
    print(f"ML: {len(ld):,} pixels in {k} batches of <= {cap:,} -- all at once would pass 98 % of the RAM; every pixel is used, none is sampled")
    parts = [run_ml(outcome, C=C, models=models, n_jobs=n_jobs, n_max=len(ld) + 1, _ld=(ld[b == j].reset_index(drop=True), covs)) for j in range(k)]
    out = {}
    tr_ = ld["treat"].values == 1

    def _mean_table(t):                                                   # a batch table: rows of the same key averaged (weights n when present)
        keys = [c for c in t.columns if t[c].dtype == object and c not in ("engine",)] + [c for c in ("quartile",) if c in t.columns]
        num = [c for c in t.columns if c not in keys and c not in ("batch", "n") and pd.api.types.is_numeric_dtype(t[c])]
        if "n" in t.columns:
            tt = t.copy()
            for c in num: tt[c] = pd.to_numeric(tt[c], errors="coerce") * tt["n"]
            g = tt.groupby(keys, as_index=False)[num + ["n"]].sum()
            for c in num: g[c] = g[c] / g["n"]
            return g
        return t.groupby(keys, as_index=False).mean(numeric_only=True).drop(columns=["batch"], errors="ignore")

    for m in set().union(*[set(p_) for p_ in parts]):
        pairs = [(j, p_[m]) for j, p_ in enumerate(parts) if m in p_]      # v20.58: (batch, result) -- a batch that lacks the model keeps the weights aligned
        if all(isinstance(r_, dict) for _, r_ in pairs):
            tgt = str(pairs[0][1].get("target", "ATT"))
            w_att = np.array([float(tr_[b == j].sum()) for j, _ in pairs]); w_all = np.array([float((b == j).sum()) for j, _ in pairs])
            r0 = {k_: v for k_, v in pairs[0][1].items() if not isinstance(v, pd.DataFrame)}
            for key in ("estimate", "att", "ate"):                       # as R's ml_over_batches: treated pixels weigh an ATT, all pixels an ATE
                if all(key in r_ for _, r_ in pairs):
                    w = w_att if (key == "att" or (key == "estimate" and tgt == "ATT")) else w_all; w = w / w.sum()
                    r0[key] = float(np.dot(w, [float(r_[key]) for _, r_ in pairs]))
            if all(np.isfinite(float(r_.get("se", np.nan))) for _, r_ in pairs):
                w = (w_att if tgt == "ATT" else w_all); w = w / w.sum()
                r0["se"] = float(np.sqrt(np.dot(w ** 2, [float(r_["se"]) ** 2 for _, r_ in pairs])))   # independent batches
                r0["se_how"] = str(r0.get("se_how", "")) + f"; {len(pairs)} independent batches of pixels combined"
            for k_ in [k_ for k_, v in pairs[0][1].items() if isinstance(v, pd.DataFrame)]:
                r0[k_] = _mean_table(pd.concat([r_[k_].assign(batch=j) for j, r_ in pairs if isinstance(r_.get(k_), pd.DataFrame)], ignore_index=True))
            r0.pop("p_value", None); r0.pop("p_how", None)
            r0["batches"] = len(pairs); r0["engine"] = str(r0.get("engine", "")) + f" ({len(pairs)} batches of pixels)"; out[m] = _with_p(r0)
        else:
            t = pd.concat([r_.assign(batch=j) for j, r_ in pairs], ignore_index=True)
            out[m] = _mean_table(t)
    return out


def run_spatial(outcome, C=None, k=8, n_max=None):
    """Moran's I and LISA with esda -- v20.58: on the SAME points and weights as the engine and R: one point per pixel of the estimation
    sample (its change post minus pre), k nearest neighbours on metres (an exact kd-tree, every pixel -- v20.57 sampled beyond 98 % of the
    RAM and used raw degrees), row-standardised. esda's analytical randomisation variance (spdep's) gives the SE and a two-sided p; its
    permutation p uses a fixed seed (v20.57: unseeded -- a rerun gave another p)."""
    C = C or _engine()
    df = package_input(outcome, C)
    if not {"latitude", "longitude"} <= set(df.columns):
        df = df.merge(C.load_panel(columns=["pixel_id", "latitude", "longitude"]).drop_duplicates("pixel_id"), on="pixel_id", how="left")
    g = C.pixel_change(df.rename(columns={"treat": "treatment"}), outcome)
    nn = C.knn_index(C.knn_xy(g["lat"].values, g["lon"].values), k)
    try:
        from libpysal.weights import W; from esda.moran import Moran, Moran_Local
    except ImportError as e:
        raise SystemExit("pip install esda libpysal") from e
    n = len(g); w = W({i: list(map(int, nn[i])) for i in range(n)}, {i: [1.0] * k for i in range(n)}, silence_warnings=True); w.transform = "r"
    np.random.seed(12345); mi = Moran(g["dY"].values, w, permutations=999, two_tailed=True)
    from scipy import stats as _st
    z = float(mi.z_rand); se = float(np.sqrt(mi.VI_rand))
    res = {"outcome": outcome, "moran_I": float(mi.I), "expected_I": float(mi.EI), "se_moran": se, "z_rand": z, "p_rand_two_sided": float(2 * _st.norm.sf(abs(z))),
           "p_sim": float(mi.p_sim), "z_sim": float(mi.z_sim), "k": k, "n": int(n), "points": "one per pixel (change post minus pre)",
           "se_how": "esda: the variance of Moran's I under randomisation (= spdep); p two-sided", "engine": "esda Moran"}
    _save(C, "M17", "global_moran", res, outcome); print("M17", res)
    np.random.seed(12345); ml = Moran_Local(g["dY"].values, w, permutations=999)
    lisa = pd.DataFrame({"pixel_id": g["pixel_id"].values, "local_I": ml.Is, "quadrant": ml.q, "p_sim": ml.p_sim, "treat": g["treat"].values})
    _save(C, "M18", "lisa", lisa, outcome)
    print("M18 LISA: significant clusters", int((lisa.p_sim < 0.05).sum()), "of", len(lisa))
    return res, lisa


# ------------------------------------------------------------------ orchestrator
MODEL_TO_PACKAGE = {
    "M01": ("pf_pipeline.twfe_2x2", "fixest::feols"), "M02": ("pf_pipeline.event_study", "fixest::feols i()"),
    "M03": ("csdid/drdid (drdid.drdid_dr)", "DRDID::drdid"), "M04": ("pycinc", "qte::cic"),
    "M05": ("dd_pipeline M05 (diff-diff CallawaySantAnna) | csdid", "did::att_gt"), "M06": ("dd_pipeline M06 (ContinuousDiD)", "contdid (Callaway-Goodman-Bacon-Sant'Anna)"),
    "M07": ("statsmodels/econml surrogate index -- needs ground truth file", "-"), "M08": ("pyfixest IV (feols 2SLS) -- needs instrument", "fixest::feols IV"),
    "M09": ("dd_pipeline M09 (SunAbraham) | pyfixest.did.event_study", "fixest::sunab"), "M10": ("pf_pipeline (feols with i(LandUse) x did)", "fixest triple interaction"),
    "M11": ("dd_pipeline M11 (SyntheticDiD)", "synthdid"), "M12": ("pyfixest (long-difference chain)", "fixest first differences"),
    "M13": ("-", "DIDmultiplegtDYN::did_multiplegt_dyn"), "M14": ("causalml / sklearn matching + pf_pipeline", "MatchIt + fixest"),
    "M15": ("pf_pipeline event_study with shifted years", "fixest"), "M16": ("pf_pipeline.pretrends_wald | dd check_parallel_trends", "fixest::wald / pretrends"),
    "M17": ("ml_spatial_pipeline.run_spatial (esda Moran)", "spdep::moran.test"), "M18": ("esda Moran_Local", "spdep::localmoran"),
    "M19": ("statsmodels MixedLM ICC", "lme4 / performance::icc"), "M20": ("statsmodels/scipy Q and I2", "metafor::rma"),
    "M21": ("pandas aggregation + pf_pipeline", "fixest"), "M22": ("dd_pipeline M22 (BaconDecomposition)", "bacondecomp"),
    "M23": ("pf_pipeline.wild_bootstrap (wildboottest, Webb)", "fwildclusterboot::boottest"), "M24": ("pf_pipeline feols with i(buff_km) x post", "fixest"),
    "M25": ("pyfixest ritest", "ritest / fixest"), "M26": ("pf_pipeline feols with covariate x did", "fixest"),
    "M27": ("dd_pipeline M27 (ImputationDiD)", "didimputation::did_imputation"), "M28": ("pyfixest.did.did2s", "did2s::did2s"),
    "M29": ("pf_pipeline feols with exposure bins", "fixest"), "M30": ("dd_pipeline M05 cohort aggregation", "did::aggte(type='group')"),
    "M31": ("dd_pipeline M31 (StackedDiD)", "stacked (fixest) / did2s"), "M32": ("pyfixest feols saturated (Wooldridge ETWFE)", "etwfe"),
    "M33": ("-", "WeightIt(method='ebal') + fixest"), "M34": ("dd_pipeline M34 (HonestDiD)", "HonestDiD"),
    "M35": ("pyfixest quantreg", "quantreg / qte::QDiD"), "M36": ("-", "fect (interactive FE)"),
    "M37": ("-", "fect (matrix completion, method='mc')"), "M38": ("-", "gsynth / fect"),
    "M39": ("ml_spatial_pipeline M39 (CausalForestDML CATE)", "grf::causal_forest"), "M40": ("econml LinearDML | DoubleML", "DoubleML"),
    "M41": ("econml S/T/X learners", "grf / SuperLearner"), "M42": ("econml DRLearner", "grf / drlearner"),
    "M43": ("econml CausalForestDML", "grf::causal_forest"), "M44": ("-", "dbarts / bartCause"),
    "M45": ("mlsynth (site level)", "synthdid / augsynth"),
}


def run_prebuilt(outcome, models=None):
    """Run every pre-built Python model that applies (the custom engine keeps the rest)."""
    import pf_pipeline as P, dd_pipeline as D
    models = set(models or MODEL_TO_PACKAGE)
    C = _engine(); out = {}
    P.compare(outcome, C)                                   # stop at the first disagreement with the engine
    if models & {"M01", "M02", "M16", "M23", "M24", "M26", "M29"}: out["pf"] = P.run_all(outcome, C=C)
    if models & {"M05", "M06", "M09", "M11", "M22", "M27", "M31", "M34"}: out["dd"] = D.run(outcome, C=C, models=sorted(models))
    if models & {"M39", "M40", "M41", "M42", "M43"}: out["ml"] = run_ml(outcome, C=C, models=tuple(sorted(models & {"M39", "M40", "M41", "M42", "M43"})))
    if models & {"M17", "M18"}: out["spatial"] = run_spatial(outcome, C=C)
    return out


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    run_prebuilt(a[0] if a else "NDVI", models=a[1:] or None)
