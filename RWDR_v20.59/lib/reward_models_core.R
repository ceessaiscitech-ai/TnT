# reward_models_core.R -- every model in R (v20.47): the core models below + the package library models_prebuilt.R,
# one registry of all 45, and run_model_R(id, outcome): load the screened panel, estimate, save (with the design SE).
# PACKAGE FIRST, WITH A FALL-BACK: fixest when installed; otherwise an exact two-way fixed-effects engine (alternating
# projections + rank-revealing QR + cluster-robust SE, t with G-1 df) -- so the core models run even without fixest.
suppressPackageStartupMessages(library(data.table))
if (!requireNamespace("fixest", quietly = TRUE) && exists("install_package_chain", mode = "function") && isTRUE(get0("AUTO_INSTALL_PACKAGES", ifnotfound = FALSE)))
  install_package_chain("fixest")                              # v20.55: the pre-built package first -- fetched now when it is missing
HAS_FIXEST <- requireNamespace("fixest", quietly = TRUE)
if (HAS_FIXEST) { suppressPackageStartupMessages(library(fixest)); setFixest_nthreads(N_THREADS)
} else info("fixest is not installed: the core models use the built-in fixed-effects engine (install fixest for speed and the full library)")
DEFAULT_COVS <- COVARIATES                                       # the four weather covariates; LandUse is never one
out_dir <- function(model, tag) { d <- file.path(RESULTS_DIR, "package_tables", model, tag %||% "run"); dir.create(d, recursive = TRUE, showWarnings = FALSE); d }
source(file.path(R_HOME_DIR, "lib", "models_prebuilt.R"), local = environment())
covs_in <- function(dt) {                                         # v20.57: the covariates of the DESIGN IN EFFECT (COVARIATES <- "all"
  cv <- attr(dt, "covariates_used")                               #   gave none before: intersect("all", names) was empty)
  if (is.null(cv)) cv <- tryCatch(load_design()$covariates, error = function(e) NULL)
  if (is.null(cv)) cv <- COVARIATES
  if (length(cv) == 1 && tolower(cv) == "all") cv <- c("Rain", "Tmax", "Tmean", "Tmin")
  intersect(cv, names(dt))
}

# ---------------------------------------------------------------- the fall-back fixed-effects engine
fe_demean <- function(X, f1, f2 = NULL, tol = 1e-10, maxit = 5000) {
  X <- as.matrix(X); g1 <- as.integer(factor(f1)); n1 <- tabulate(g1)
  if (is.null(f2)) return(X - (rowsum(X, g1, reorder = TRUE) / n1)[g1, , drop = FALSE])
  g2 <- as.integer(factor(f2)); n2 <- tabulate(g2); sc <- max(1, max(abs(X)))
  for (it in seq_len(maxit)) {                                    # alternating projections: exact at convergence
    m1 <- rowsum(X, g1, reorder = TRUE) / n1; X <- X - m1[g1, , drop = FALSE]
    m2 <- rowsum(X, g2, reorder = TRUE) / n2; X <- X - m2[g2, , drop = FALSE]
    if (max(abs(m1)) < tol * sc && max(abs(m2)) < tol * sc) break
  }
  X
}
fe_fit <- function(dt, y, x, fe = c("unit", "period"), cluster = "cluster_id") {
  x <- unique(x[x %in% names(dt)])
  if (HAS_FIXEST) {
    f <- as.formula(paste0("`", y, "` ~ ", paste(sprintf("`%s`", x), collapse = " + "), " | ", paste(fe, collapse = " + ")))
    fit <- fixest::feols(f, data = dt, cluster = as.formula(paste0("~", cluster)), notes = FALSE, warn = FALSE)
    b <- coef(fit); V <- vcov(fit); names(b) <- gsub("`", "", names(b)); dimnames(V) <- list(names(b), names(b))
    return(list(coef = b, se = sqrt(diag(V)), p = setNames(fixest::pvalue(fit), names(b)), vcov = V, n = nobs(fit), G = uniqueN(dt[[cluster]]), engine = "fixest::feols"))
  }
  M <- fe_demean(cbind(dt[[y]], as.matrix(dt[, x, with = FALSE])), dt[[fe[1]]], if (length(fe) > 1) dt[[fe[2]]] else NULL)
  yd <- M[, 1]; Xd <- M[, -1, drop = FALSE]; colnames(Xd) <- x
  q <- qr(Xd, tol = 1e-9); keep <- sort(q$pivot[seq_len(q$rank)])      # collinear regressors dropped, as fixest does
  if (!length(keep)) stop("no regressor varies within units and periods")
  Xd <- Xd[, keep, drop = FALSE]; XtX <- crossprod(Xd); Bi <- solve(XtX)
  b <- drop(Bi %*% crossprod(Xd, yd)); e <- drop(yd - Xd %*% b)
  cl <- dt[[cluster]]; G <- uniqueN(cl); N <- length(yd); K <- ncol(Xd)
  # v20.58: the fixed-effect parameters in (N - 1) / (N - K) by fixest's own default (fixef.K = "nested") -- as the fixest path above and
  # Python's engine / pyfixest: each FE dimension's levels, one less per dimension beyond the first, a dimension nested in the clusters as one
  fe_ <- fe[fe %in% names(dt)]; L <- vapply(fe_, function(f) uniqueN(dt[[f]]), 0)
  nest <- vapply(fe_, function(f) all(dt[, uniqueN(get(cluster)), by = f]$V1 == 1L), TRUE)
  k_fe <- if (!length(L)) 0 else { ka <- sum(L) - (length(L) - 1); if (any(nest)) ka - sum(L[nest]) + sum(nest) else ka }
  S <- rowsum(Xd * e, cl)                                          # per-cluster scores
  V <- Bi %*% crossprod(S) %*% Bi * (G / (G - 1)) * ((N - 1) / max(1, N - K - k_fe))
  se <- sqrt(diag(V)); p <- 2 * pt(abs(b / se), max(1, G - 1), lower.tail = FALSE)
  names(b) <- names(se) <- names(p) <- colnames(Xd); dimnames(V) <- list(colnames(Xd), colnames(Xd))
  list(coef = b, se = se, p = p, vcov = V, n = N, G = G, dropped = setdiff(x, colnames(Xd)), engine = "built-in fixed-effects engine")
}
pick <- function(f, k) { if (!k %in% names(f$coef)) stop("'", k, "' is not identified (collinear with the fixed effects)"); list(estimate = unname(f$coef[k]), se = unname(f$se[k]), p_value = unname(f$p[k])) }

# ---------------------------------------------------------------- the core models
m01_twfe <- function(dt, outcome) {
  cv <- covs_in(dt); f <- fe_fit(dt, outcome, c("did", cv)); out <- c(pick(f, "did"), engine = paste(f$engine, "(two-way FE)"))
  if (length(cv)) out$table <- covariate_response_R(dt, outcome, cv)     # v20.57: the bad-control check (as Python's M01)
  bs <- by_season_R(dt, outcome, cv)                                     # v20.58: the estimate of EACH season and its weight in the pooled one
  if (!is.null(bs)) { od <- file.path(RESULTS_DIR, "M01", attr(dt, "scenario") %||% "run"); dir.create(od, recursive = TRUE, showWarnings = FALSE)
                      fwrite(bs, file.path(od, sprintf("M01_%s_by_season.csv", outcome))) }
  out
}
# v20.58 -- WHY "all" and "seasonal" can differ (your v20.56 log: NDVI 0.00022 with the annual composite, 0.0107 without it). With one fixed
# effect per pixel x season series and per year x season, the pooled estimate is EXACTLY a weighted mean of the season-by-season estimates
# (without covariates; nearly so with them), each season weighted by how much treatment variation it holds (sum of the squared demeaned
# did). The table shows each season's own estimate, SE and weight: an annual composite whose effect differs from the seasons' pulls
# the pooled number toward it.
by_season_R <- function(dt, outcome, cv = character(0)) {
  ss <- sort(unique(dt$Season)); if (length(ss) < 2) return(NULL)
  parts <- lapply(ss, function(s_) {
    x <- dt[Season == s_]
    why <- ""                                                                    # v20.58: a season that cannot be fitted says why
    f <- tryCatch(fe_fit(x, outcome, c("did", cv)), error = function(e) { why <<- conditionMessage(e); NULL })
    dd <- tryCatch(if (HAS_FIXEST) fixest::demean(as.numeric(x$did), f = x[, .(unit, period)]) else fe_demean(as.numeric(x$did), x$unit, x$period), error = function(e) NULL)
    list(season = s_, f = f, why = why, rows = nrow(x), weight = if (!is.null(dd)) sum(as.numeric(dd)^2) else NA_real_)
  })
  by_season_core(outcome, parts)
}
# v20.58: the table from each season's fit (f or NULL + why), rows and weight (the squared two-way demeaned did) -- shared with the
# out-of-core path (reward_outofcore.R), whose seasons are fitted from the partitions' cross-products
by_season_core <- function(outcome, parts) {
  rows <- lapply(parts, function(p) {
    f <- p$f; why <- p$why
    ok_ <- !is.null(f) && "did" %in% names(f$coef)
    if (!ok_ && !nzchar(why)) why <- "the did term is absorbed by the fixed effects in this season"
    data.table(season = SEASON_LABEL[as.character(p$season)], estimate = if (ok_) f$coef[["did"]] else NA_real_, se = if (ok_) f$se[["did"]] else NA_real_,
               p_value = if (ok_) f$p[["did"]] else NA_real_, rows = p$rows, weight = p$weight,
               note = if (ok_) "" else substr(gsub("\\s+", " ", why), 1, 160))
  })
  tab <- rbindlist(rows); tab[, weight := weight / sum(weight, na.rm = TRUE)]
  tab[, outcome := outcome]
  info(sprintf("%s by season -- the pooled estimate is their weighted mean (weight = the treatment variation each season holds): %s", outcome,
               paste(sprintf("%s %.4g (SE %.2g, weight %.0f %%)", tab$season, tab$estimate, tab$se, 100 * tab$weight), collapse = "; ")))
  tab[]
}
# v20.57 -- THE BAD-CONTROL CHECK: each covariate as the OUTCOME of the same two-way FE DiD. Weather does not respond to a watershed
# programme; a covariate that does (|t| > 3) is moved by the treatment -- e.g. land-SURFACE temperature (MODIS LST, the exporter's
# fall-back when ERA5-Land air temperature is missing), which greener vegetation cools -- and as a covariate it absorbs part of the
# effect. The table also gives the estimate WITHOUT covariates: read that one when a covariate moves with the treatment.
covariate_response_R <- function(dt, outcome, cv, t_flag = 3)
  covariate_response_core(outcome, cv, function(y, x, c_ = NULL) fe_fit(if (is.null(c_)) dt else dt[is.finite(get(c_))], y, x), t_flag)
# v20.58: the table from a fitter fit(y, x, c_) -- in memory fe_fit on the sample; out of core the partitions' exact two-way FE fits
covariate_response_core <- function(outcome, cv, fit, t_flag = 3) {
  f0 <- tryCatch(pick(fit(outcome, "did"), "did"), error = function(e) NULL)
  rows <- lapply(cv, function(c_) {
    why <- ""
    r <- tryCatch(pick(fit(c_, "did", c_), "did"), error = function(e) { why <<- conditionMessage(e); NULL })
    if (is.null(r)) return(data.table(covariate = c_, did_on_covariate = NA_real_, se = NA_real_, t = NA_real_, p_value = NA_real_, moves_with_treatment = NA,
                                      note = paste("not fitted:", substr(gsub("\\s+", " ", why), 1, 160))))   # v20.58: said, never a bare NA
    tt <- r$estimate / r$se
    data.table(covariate = c_, did_on_covariate = r$estimate, se = r$se, t = tt, p_value = r$p_value, moves_with_treatment = is.finite(tt) && abs(tt) > t_flag)
  })
  tab <- rbindlist(rows, fill = TRUE)   # v20.58: a covariate that cannot be fitted (constant within the fixed effects) has a note -- M01 stopped
  tab[, `:=`(outcome = outcome, estimate_without_covariates = if (is.null(f0)) NA_real_ else f0$estimate, se_without_covariates = if (is.null(f0)) NA_real_ else f0$se)]
  bad <- tab[moves_with_treatment %in% TRUE]
  if (nrow(bad)) warn(sprintf("BAD-CONTROL CHECK: %s move(s) with the treatment (%s) -- a covariate the programme changes (e.g. land-SURFACE temperature, MODIS LST) absorbs part of the effect; the estimate WITHOUT covariates is %.5g (SE %.3g)",
                              paste(bad$covariate, collapse = ", "), paste(sprintf("%s t = %.1f", bad$covariate, bad$t), collapse = "; "), tab$estimate_without_covariates[1], tab$se_without_covariates[1]))
  else info(sprintf("bad-control check: no covariate moves with the treatment (|t| <= %g for %s)", t_flag, paste(cv, collapse = ", ")))
  tab[]
}
m02_event <- function(dt, outcome) {
  d <- copy(dt); ks <- sort(unique(d[treat == 1L & is.finite(event_time), event_time])); ks <- ks[ks != -1L]
  if (!length(ks)) stop("no event time other than the reference year -1")
  for (k in ks) set(d, j = paste0("et::", k), value = as.integer(d$treat == 1L & d$event_time %in% k))
  f <- fe_fit(d, outcome, c(paste0("et::", ks), covs_in(d)))
  m02_finish(f, cluster_col_for(dt) == "Year", function(est) design_se_event(dt, outcome, est))
}
# v20.58: the event study's table and headline from its fit -- shared with the out-of-core path (is_year: the clusters are years;
# dse(estimate): the design-based SE of the headline)
m02_finish <- function(f, is_year, dse) {
  et <- grep("^et::", names(f$coef), value = TRUE)
  tab <- data.table(event_time = as.integer(sub("^et::", "", et)), estimate = f$coef[et], se = f$se[et], p_value = f$p[et])[order(event_time)]
  if (is_year && sum(tab$event_time < -1) >= 2) {                                # v20.49: clusters = years -> each coefficient
    tab[, se_design := sd(tab[event_time < -1, estimate])]                       # rests on one year; the spread of the leads
    tab[, se_note := "cluster = Year: per-year cluster SEs are not valid; se_design = SD of the pre-period leads"]   # is its SE
  }
  # v20.58: the headline = the mean of the post-period coefficients -- ALWAYS with an SE and a p-value. Clusters = sub-watersheds: the delta
  # method on their cluster-robust covariance. Clusters = years (one sub-watershed, or fewer than 6): each coefficient rests on ONE year,
  # so its cluster covariance is degenerate (v20.55-v20.57 left the SE NA -- your "SE NA" on every M02 line); the SE is then the
  # design-based one of this headline: years as the draws (design_se_event, reward_design.R).
  post_k <- paste0("et::", tab[event_time >= 0, event_time]); est_h <- mean(tab[event_time >= 0, estimate])
  if (length(post_k) && !is_year && all(post_k %in% rownames(f$vcov))) {
    w <- rep(1 / length(post_k), length(post_k)); se_h <- sqrt(drop(t(w) %*% f$vcov[post_k, post_k, drop = FALSE] %*% w))
    p_h <- 2 * pt(abs(est_h / se_h), max(1, f$G - 1), lower.tail = FALSE)
    how <- sprintf("delta method on the cluster-robust covariance (%d sub-watersheds)", f$G); p_how <- sprintf("t with %d df", max(1, f$G - 1))
  } else {
    de <- dse(est_h); se_h <- de$se; p_h <- de$p; how <- de$how; p_how <- sprintf("t with %g df", de$df)
  }
  list(estimate = est_h, se = se_h, p_value = p_h, se_how = how, p_how = p_how, table = tab, b = f$coef[et], V = f$vcov[et, et, drop = FALSE], G = f$G,
       engine = paste(f$engine, "(event study, reference year -1; headline = the mean of the post-period coefficients)"))
}
m05_cs <- function(dt, outcome) {
  need("did")
  d <- copy(dt); d[, y_sn := season_net(dt, outcome)]; d <- d[is.finite(y_sn)]          # v20.58: season-matched (models_prebuilt.R season_net)
  uy <- d[, .(y = mean(y_sn), gvar = if (is.finite(cohort[1])) cohort[1] else 0, site_id = site_id[1]), by = .(unit, Year)]
  uy[, id := as.integer(factor(unit))]
  # v20.58: the SE -- ANALYTICAL (the influence function, each series a draw: exactly diff-diff's, Python's M05) unless the sub-watersheds are
  # the clusters (>= MIN_SWS_CLUSTERS): then did's multiplier bootstrap clustered on them (999 draws; did has no analytical clustered SE).
  # v20.57: a 200-draw bootstrap for every panel (~5 % Monte Carlo error in the SE; 0.00097 against Python's 0.00103 on the poison test)
  cl <- site_cluster(dt)
  r <- seeded(did::att_gt(yname = "y", tname = "Year", idname = "id", gname = "gvar", data = as.data.frame(uy), control_group = "nevertreated",
                   bstrap = !is.null(cl), biters = 999, clustervars = cl, cband = FALSE, allow_unbalanced_panel = TRUE, pl = TRUE, cores = N_THREADS))
  s <- seeded(did::aggte(r, type = "simple")); e <- seeded(did::aggte(r, type = "dynamic"))
  list(estimate = s$overall.att, se = s$overall.se, table = data.table(event_time = e$egt, estimate = e$att.egt, se = e$se.egt), engine = "did::att_gt (Callaway-Sant'Anna)",
       se_how = if (is.null(cl)) "did: the analytical influence-function SE of the simple aggregation (each series a draw)"
                else sprintf("did: the multiplier bootstrap (999 draws) clustered by sub-watershed (%d clusters)", uniqueN(uy$site_id)))
}
m06_dose <- function(dt, outcome) {
  # v20.57: `dose` = DOSE_VARIABLE from your fund workbook, attached when the model runs (load_panel_R): the amount released by the end
  # of the previous season / the treatment area (default), 0 on the control rings and in untreated periods, NaN where the file cannot say
  tp <- dt[treat == 1L & post == 1L]
  if (!"dose" %in% names(dt) || !any(is.finite(tp$dose) & tp$dose > 0))
    stop("no dose on the treatment area (the fund file did not load, or it does not cover these seasons)")
  d <- dt[is.finite(dose)]
  f <- fe_fit(d, outcome, c("dose", covs_in(d))); r <- pick(f, "dose")
  sd_d <- sd(d[treat == 1L & post == 1L, dose]); m_d <- mean(d[treat == 1L & post == 1L, dose])
  c(r, list(table = data.table(per = c(sprintf("unit of %s", DOSE_VARIABLE), "1 SD of the treated dose", "the mean treated dose"),
                               effect = c(r$estimate, r$estimate * sd_d, r$estimate * m_d)),
            engine = paste(f$engine, "(continuous-dose DiD, fund-file dose)")))
}
m07_surrogate <- function(dt, outcome) {
  pn <- panel_names(); bm <- grep("^BM_", pn, value = TRUE)
  if (!length(bm)) stop("no BM (benchmark-site) sub-watershed means in the panel -- the BM table was not found")
  need("glmnet")
  sat <- intersect(c("NDVI", "EVI", "SAVI", "LAI", "SMDI", "VCI", "TCI", "VHI"), pn)
  core <- panel_read(intersect(c("pixel_id", "site_id", "site_check", "Year", "Season", "buff_km", sat, bm), pn))[buff_km == 0]
  dz <- load_design(); loc <- location_table_R()                                        # v20.58: the LOCATION rule -- the surrogate is
  S <- dz$processed %||% processing_set_R(loc, dz$sub_watersheds %||% "data", dz$fragment_min_share %||% 0.05)$sites   # trained on the processed
  dc <- c(if (identical(dz$fragment_rule %||% "drop", "drop")) 1:2, if (identical(dz$overlap_rows %||% "drop", "drop")) 3:4)   # sub-watershed(s)' core only
  if (length(dc)) core <- core[!location_codes_R(core, loc, S) %in% dc]
  agg <- core[, lapply(.SD, function(v) mean(v, na.rm = TRUE)), by = .(site_id, Year, Season), .SDcols = c(sat, bm)]
  # v20.55: the panel now carries every outcome column (an index the exports lack is NaN throughout, as in Python) -- only the
  # indices with data are predictors, otherwise complete.cases() would leave no row
  sat <- sat[vapply(sat, function(s_) any(is.finite(agg[[s_]])), logical(1))]
  if (!length(sat)) stop("no satellite index with data in the treatment area")
  rows <- list()
  for (v in bm) {
    tr <- agg[is.finite(get(v))]; tr <- tr[complete.cases(tr[, ..sat])]
    if (nrow(tr) < 6) { rows[[v]] <- data.table(ground = v, status = sprintf("not fitted: %d sub-watershed x season BM means (need >= 6) -- the pooled run provides them", nrow(tr))); next }
    if (length(sat) >= 2) { cvf <- glmnet::cv.glmnet(as.matrix(tr[, ..sat]), tr[[v]], alpha = 0, nfolds = min(5, nrow(tr)))
                            prd <- function(X) as.numeric(predict(cvf, X, s = "lambda.min"))
    } else { lf <- lm(tr[[v]] ~ tr[[sat]]); prd <- function(X) as.numeric(coef(lf)[1] + coef(lf)[2] * X[, 1]) }   # v20.49: one predictor
    d <- load_panel_R(DESIGN_OUTCOME, load_design(), extra = sat)
    X <- as.matrix(d[, ..sat]); ok_r <- complete.cases(X); d <- d[ok_r]
    d[, gnd := prd(X[ok_r, , drop = FALSE])]
    f <- fe_fit(d, "gnd", "did")
    rows[[v]] <- data.table(ground = v, status = "fitted", estimate = unname(f$coef["did"]), se = unname(f$se["did"]), n_means = nrow(tr))
  }
  tab <- rbindlist(rows, fill = TRUE); f1 <- tab[status == "fitted"]
  if (!nrow(f1)) stop(paste(tab$status, collapse = " | "))
  list(estimate = f1$estimate[1], se = f1$se[1], table = tab, engine = "glmnet ridge surrogate (BM sub-watershed means) + fixed effects")
}
m08_iv <- function(dt, outcome) stop("IV-DiD needs an instrument (a variable that shifts treatment but not the outcome) -- none exists in the data")
m11_sdid <- function(dt, outcome) {
  need("synthdid", "GitHub synth-inference/synthdid, or the skranz r-universe mirror")
  r <- by_cohort_season(season_series(dt, outcome), sdid_fit, "synthetic DiD")               # v20.58: series of ONE season, one fit per cohort x season
  c(r, engine = "synthdid (sub-watershed x ring x season series; one fit per cohort x season)")
}
m16_pretrends <- function(dt, outcome, pre_window = c(-4L, -2L), ref = -1L) {
  # v20.49 (found by the first real run: v20.47 reported F = 2.8e8 and "REJECT" on data WITHOUT a pre-trend). The rules
  # of the Python engine: the leads are tested against the reference year on the pre-period sample, and the
  # cluster-robust Wald test is used only when it is well conditioned (rank = number of leads <= G - 1, condition
  # number < 1e6). With one sub-watershed the clusters are years and each lead rests on ONE year, so that covariance is
  # degenerate -- the test is then the DESIGN-BASED one: the linear trend of the core-minus-control gap over the
  # pre-period years (sub-watershed fixed effects; the years are the draws), t with its residual degrees of freedom.
  d0 <- dt[post == 0L]
  tr_rows <- d0[treat == 1L & is.finite(event_time) & event_time >= pre_window[1] & event_time <= ref]
  ks <- sort(unique(tr_rows$event_time)); ks <- ks[ks != ref]
  is_year <- cluster_col_for(dt) == "Year"
  # clusters = years: every lead is ONE year's dummy, its cluster scores are 0 by construction and the Wald F explodes
  # (the Python engine gave F ~ 1e28 and "REJECT" on panels without a pre-trend) -- never used then
  f <- NULL
  if (length(ks) && any(tr_rows$event_time == ref) && !is_year) {
    d <- d0[(treat == 1L & is.finite(event_time) & event_time >= pre_window[1] & event_time <= ref) | (treat == 0L & Year %in% unique(tr_rows$Year))]
    for (k in ks) set(d, j = paste0("lead::", k), value = as.integer(d$treat == 1L & d$event_time %in% k))
    f <- tryCatch(fe_fit(d, outcome, c(paste0("lead::", ks), covs_in(d))), error = function(e) { info("M16: the cluster-robust leads fit failed (", conditionMessage(e), ") -- the design-based test is used"); NULL })
  }
  m16_core(ks, f, function() d0[, .(m = mean(get(outcome))), by = .(site_id, Year, treat)], is_year)
}
# v20.58: the test from the leads' fit (NULL: not fitted) and the pre-period cell means (g(): site_id, Year, treat, m) -- shared with the
# out-of-core path
m16_core <- function(ks, f, g_fun, is_year) {
  cw <- list(F = NA_real_, p = NA_real_, rank = 0L, q = length(ks), G = NA_integer_, cond = NA_real_, reliable = FALSE)
  if (!is.null(f)) {
    ld <- intersect(paste0("lead::", ks), names(f$coef)); b <- f$coef[ld]; V <- f$vcov[ld, ld, drop = FALSE]; V <- (V + t(V)) / 2
    ev <- eigen(V, symmetric = TRUE); keep <- ev$values > max(1e-7 * max(ev$values), 1e-300)
    z <- crossprod(ev$vectors[, keep, drop = FALSE], b); rk <- sum(keep)
    cond <- if (rk) max(ev$values) / min(ev$values[keep]) else Inf
    Fcw <- if (rk) sum(z^2 / ev$values[keep]) / rk else NA_real_
    cw <- list(F = Fcw, p = if (rk) pf(Fcw, rk, max(1, f$G - 1), lower.tail = FALSE) else NA_real_, rank = rk, q = length(ld), G = f$G, cond = cond,
               reliable = rk > 0 && rk == length(ld) && length(ld) <= f$G - 1 && cond < 1e6)
  }
  if (isTRUE(cw$reliable)) {
    verdict <- if (cw$p < 0.05) "REJECT parallel pre-trends" else "no evidence against parallel pre-trends"
    return(list(estimate = cw$F, se = NA_real_, p_value = cw$p,
                table = data.table(test = "joint Wald on the event-study leads (cluster-robust)", leads = cw$q, clusters = cw$G, F = cw$F, df1 = cw$rank,
                                   df2 = cw$G - 1, p_value = cw$p, condition_number = cw$cond, verdict = verdict),
                engine = "event-study leads + joint Wald test (well conditioned)"))
  }
  g <- g_fun()                                                                       # the design-based linear pre-trend test
  w <- dcast(g, site_id + Year ~ treat, value.var = "m")
  if (!all(c("0", "1") %in% names(w))) stop("no pre-period year has both core and control pixels")
  w[, gap := `1` - `0`]; w <- w[is.finite(gap)]
  S <- uniqueN(w$site_id); dfree <- nrow(w) - S - 1L
  if (dfree < 1L) stop(sprintf("the pre-trend test needs >= %d pre-period years per sub-watershed (have %d rows for %d sub-watershed(s))", 3L, nrow(w), S))
  fit <- if (S > 1) lm(gap ~ Year + factor(site_id), data = w) else lm(gap ~ Year, data = w)
  ct <- summary(fit)$coefficients; tt <- ct["Year", "t value"]; p <- 2 * pt(-abs(tt), dfree)
  verdict <- if (p < 0.05) "REJECT: the core-minus-control gap trends before implementation" else "no evidence against parallel pre-trends"
  list(estimate = tt^2, se = NA_real_, p_value = p,
       table = data.table(test = "design-based linear pre-trend of the core-minus-control gap (years as draws)", slope_per_year = ct["Year", "Estimate"],
                          slope_se = ct["Year", "Std. Error"], t = tt, F = tt^2, df1 = 1L, df2 = dfree, p_value = p, sub_watersheds = S, pre_years = uniqueN(w$Year),
                          cluster_wald_F = cw$F, cluster_wald_reliable = FALSE,
                          cluster_wald_why = if (is_year) "not applicable: the clusters are years (one lead per year)" else
                            sprintf("rank %d of %d leads, %s clusters, condition number %.2g", cw$rank, cw$q, cw$G, cw$cond), verdict = verdict),
       engine = "design-based linear pre-trend test (the cluster-robust Wald test was ill-conditioned here)")
}
m21_annual <- function(dt, outcome) {
  # v20.58: the season-averaged ANNUAL panel. A year whose seasons are only partly treated (a season start: Rabi 2024 treated, Kharif / Zaid
  # 2024 not) is treated with the SHARE of its treated seasons (the dose of that year); v20.57 counted it as fully treated (max) -- on a
  # Rabi start that shrank the effect by a third of a year (0.033 for 0.05). The naive (max) estimate stays in the table: the gap between
  # the two IS the season-to-annual aggregation bias this model reports.
  a <- dt[, .(y = mean(get(outcome)), did_share = mean(did), did_max = max(did), cluster_id = cluster_id[1]), by = .(pixel_id, Year)]
  f <- fe_fit(a, "y", "did_share", fe = c("pixel_id", "Year")); fn <- tryCatch(fe_fit(a, "y", "did_max", fe = c("pixel_id", "Year")), error = function(e) { info("M21: the naive (any season treated) fit failed: ", conditionMessage(e)); NULL })
  out <- pick(f, "did_share")
  out$table <- data.table(estimate = c("share of treated seasons (headline)", "any season treated (naive)"), beta = c(out$estimate, if (is.null(fn)) NA_real_ else unname(fn$coef["did_max"])),
                          se = c(out$se, if (is.null(fn)) NA_real_ else unname(fn$se["did_max"])))
  c(out, engine = paste(f$engine, "on the season-averaged annual panel (treatment = the share of the year's treated seasons)"))
}
m23_wild <- function(dt, outcome, B = 9999) {
  # Frisch-Waugh: demean on unit + period, partial out the covariates; then the restricted (null-imposed) wild cluster
  # bootstrap-t with Webb weights, computed EXACTLY from per-cluster sums (O(clusters) per replicate).
  cv <- covs_in(dt); X <- as.matrix(dt[, c("did", cv), with = FALSE])
  dm <- if (HAS_FIXEST) fixest::demean(cbind(y = dt[[outcome]], X), f = dt[, .(unit, period)]) else fe_demean(cbind(dt[[outcome]], X), dt$unit, dt$period)
  y <- dm[, 1]; x <- dm[, 2]
  if (length(cv)) { W <- dm[, -(1:2), drop = FALSE]; Q <- qr(W, tol = 1e-9); if (Q$rank > 0) { y <- qr.resid(Q, y); x <- qr.resid(Q, x) } }
  cl <- as.integer(factor(dt$cluster_id)); G <- max(cl); xx <- sum(x * x)
  S <- as.numeric(tapply(x * y, cl, sum)); Qg <- as.numeric(tapply(x * x, cl, sum))
  b <- sum(S) / xx; adj <- sqrt(G / (G - 1))
  se_of <- function(Sg, bb) sqrt(sum((Sg - bb * Qg)^2)) / xx * adj
  t0 <- b / se_of(S, b)
  # v20.58 (as Python): Webb's six-point weights with fewer than 12 clusters (Rademacher allows only 2^G distinct samples), Rademacher otherwise
  wts <- if (G < 12) "Webb" else "Rademacher"; set.seed(12345)
  vals <- if (wts == "Webb") c(-sqrt(1.5), -1, -sqrt(0.5), sqrt(0.5), 1, sqrt(1.5)) else c(-1, 1)
  W <- matrix(sample(vals, G * B, replace = TRUE), nrow = G)
  Sb <- S * W; bb <- colSums(Sb) / xx
  tb <- bb / (sqrt(colSums((Sb - outer(Qg, bb))^2)) / xx * adj)
  p <- (1 + sum(abs(tb) >= abs(t0))) / (1 + B)   # v20.58 (as Python): a bootstrap p is never 0 -- at least 1 / (B + 1); v20.57 printed "< 1e-300"
  info(sprintf("wild cluster bootstrap: %d clusters, %s weights, %s replicates (exact per-cluster sums)", G, wts, format(B, big.mark = ",")))
  list(estimate = b, se = se_of(S, b), p_value = p, table = data.table(t = t0, p_wild = p, clusters = G, reps = B, weights = wts),
       engine = sprintf("wild cluster bootstrap-t (%s weights, null imposed; exact per-cluster sums)", wts),
       se_how = sprintf("CR1 on %d clusters (sqrt(G / (G - 1)); the same SE in the observed and the bootstrap t)", G),
       p_how = sprintf("wild cluster bootstrap-t, %s replicates, %s weights, the null imposed", format(B, big.mark = ","), wts))
}
m34_honest <- function(dt, outcome) {
  need("HonestDiD", "GitHub asheshrambachan/HonestDiD")
  m34_from_event(m02_event(dt, outcome), cluster_col_for(dt) == "Year", function(est) design_se_event(dt, outcome, est))
}
# v20.58: HonestDiD on an event study's coefficients (e = m02_event / its out-of-core twin) -- shared by both paths
m34_from_event <- function(e, is_year, dse) {
  et <- as.integer(sub("^et::", "", names(e$b))); o <- order(et)
  b <- e$b[o]; V <- e$V[o, o]; nPre <- sum(et < -1); nPost <- sum(et >= 0)
  if (nPre < 1 || nPost < 1) stop("HonestDiD needs >= 1 pre-period lead and >= 1 post-period coefficient")
  # v20.52: with fewer than MIN_SWS_CLUSTERS sub-watersheds the event study's covariance is clustered on YEARS -- each
  # coefficient rests on one year, the covariance is ~0 (v20.49, M16) and HonestDiD's intervals built on it are not
  # valid. Then the covariance is the DESIGN one: independent years, each with the spread of the pre-period leads.
  cov_src <- "event-study covariance (clustered on sub-watersheds)"
  if (is_year) {
    lead <- b[et[o] < -1]
    if (length(lead) < 2) stop("HonestDiD with year clusters needs >= 2 pre-period leads for a design-based covariance")
    V <- diag(stats::var(lead), length(b)); cov_src <- sprintf("design-based: independent years, SD of the %d pre-period leads", length(lead))
  }
  # v20.58: the robust intervals are for the SAME parameter as the headline -- the equal-weight mean of the post-period effects (l_vec; the
  # package's default is the FIRST post period only, and Python's diff-diff HonestDiD targets the equal-weight mean) -- on the grid
  # Mbar = 0, 0.5, ..., 2 AND at the exact breakdown value (v20.57 reported the grid only; Python printed "> 5" and wrote 5).
  # The test grid is CENTRED on the estimate and scaled to its SE and to the bound (v20.57: +-50 x max|beta| with 2000 points -- a spacing of
  # 0.0025 on NDVI, WIDER than the interval itself: bounds rounded to the grid, or no grid point inside -> an "empty" interval), widened when
  # the interval reaches its edge (open), refined when no point is accepted.
  lv <- rep(1 / nPost, nPost); post_ <- et[o] >= 0
  th <- sum(lv * b[post_]); se_th <- sqrt(drop(t(lv) %*% V[post_, post_, drop = FALSE] %*% lv))
  maxd <- max(abs(diff(c(b[et[o] < -1], 0))), 1e-12)                          # the largest pre-period change (the reference year = 0)
  rm_at <- function(Mb, gp = 1000) {
    w <- 8 * se_th + 2 * Mb * maxd * (nPost + 1); r <- NULL
    for (k in 1:10) {
      r <- as.data.table(suppressWarnings(HonestDiD::createSensitivityResults_relativeMagnitudes(betahat = b, sigma = V, numPrePeriods = nPre,
             numPostPeriods = nPost, l_vec = lv, Mbarvec = Mb, grid.lb = th - w, grid.ub = th + w, gridPoints = gp)))
      sp <- 2 * w / (gp - 1); empty_ <- !is.finite(r$lb[1]) || !is.finite(r$ub[1]) || r$lb[1] > r$ub[1]
      open_ <- !empty_ && (r$lb[1] <= th - w + sp || r$ub[1] >= th + w - sp)
      if (!open_ && !empty_) break
      if (open_) w <- 4 * w else if (k <= 4) w <- w / 4 else break           # open -> wider; empty -> a finer grid (then accepted as empty)
    }
    r[, `:=`(ci_open = open_, ci_empty = empty_, grid_halfwidth = w, grid_points = gp)][]
  }
  covers0 <- function(Mb) {                                                   # the search: 300 points; an edge = unbounded that side
    r <- rm_at(Mb, 300); if (r$ci_empty[1]) return(FALSE)
    w <- r$grid_halfwidth[1]; sp <- 2 * w / 299
    lb_ <- if (r$lb[1] <= th - w + sp) -Inf else r$lb[1]; ub_ <- if (r$ub[1] >= th + w - sp) Inf else r$ub[1]
    lb_ <= 0 && ub_ >= 0 }
  bd <- if (covers0(0)) 0 else {                                              # the breakdown: the smallest Mbar whose interval covers 0 --
    lo <- 0; hi <- 2; while (!covers0(hi) && hi < 4096) { lo <- hi; hi <- 2 * hi }   # bracketed by doubling (no cap below 4096), then
    if (!covers0(hi)) Inf else { for (i in 1:30) { if (hi - lo <= 5e-3 * max(1, lo)) break   # bisection to 0.5 %
      mid <- (lo + hi) / 2; if (covers0(mid)) hi <- mid else lo <- mid }; hi } }
  bd_how <- if (is.infinite(bd)) "no Mbar up to 4096 makes the robust interval cover 0 (the largest pre-period change is ~0)" else
            if (bd == 0) "the effect is not significant even under exact parallel trends (Mbar = 0)" else
            sprintf("the smallest Mbar whose robust interval covers 0 (bisection to 0.5 %%): the effect survives a post-period violation up to %.3g x the largest pre-period one", bd)
  tab <- rbindlist(lapply(sort(unique(c(seq(0, 2, 0.5), if (is.finite(bd) && bd > 0) bd))), rm_at, gp = 1000), fill = TRUE)
  tab[ci_open == TRUE & lb <= th - grid_halfwidth + 2 * grid_halfwidth / 999, lb := -Inf]   # an OPEN interval is written as -Inf / Inf,
  tab[ci_open == TRUE & ub >= th + grid_halfwidth - 2 * grid_halfwidth / 999, ub := Inf]    # never as the grid edge
  tab[, `:=`(covariance = cov_src, target = "the equal-weight mean of the post-period effects", breakdown_row = is.finite(bd) & abs(Mbar - bd) < 1e-12)]
  if (any(tab$ci_open)) info(sprintf("M34: %d of %d robust intervals are unbounded (lb -Inf or ub Inf): the data cannot rule out a violation of that size", sum(tab$ci_open), nrow(tab)))
  if (any(tab$ci_empty)) info(sprintf("M34: %d of %d robust sets are EMPTY (every value rejected): the pre-period changes are inconsistent with that restriction", sum(tab$ci_empty), nrow(tab)))
  pw <- as.numeric(et[o] >= 0); pw <- pw / sum(pw); se_h <- sqrt(drop(t(pw) %*% V %*% pw))          # v20.58: the headline's SE from the SAME
  # v20.58: the p of the SAME rule as M02's headline (the effect M34 assesses): with year clusters the design-based event SE and ITS df (v20.58's
  # first version left the p to save_result: t with G - 1 = 5 df against a design SE of 3 df -- a p different from M02's for the same number)
  if (is_year) { de <- dse(sum(pw * b)); se_h <- de$se; how <- de$how; p_h <- de$p; p_how <- sprintf("t with %g df", de$df) } else {
    how <- cov_src; p_h <- 2 * pt(abs(sum(pw * b) / se_h), max(1, e$G - 1), lower.tail = FALSE); p_how <- sprintf("t with %d df", max(1, e$G - 1)) }
  info(sprintf("M34: breakdown Mbar = %s -- %s", if (is.finite(bd)) format(signif(bd, 4)) else "Inf", bd_how))
  list(estimate = sum(pw * b), se = se_h, p_value = p_h, se_how = how, p_how = p_how, breakdown_Mbar = bd, breakdown_how = bd_how, table = tab,
       engine = paste("HonestDiD relative magnitudes |", cov_src, "| headline = the mean of the post-period coefficients; breakdown Mbar", if (is.finite(bd)) format(signif(bd, 4)) else "Inf"))
}

# ---------------------------------------------------------------- the prebuilt-library models, standardised
standardise <- function(model, r) {
  tab <- NULL; head <- list(); note_row <- NULL
  if (is.list(r) && !is.data.frame(r)) {
    if (model == "M18" && !is.null(r$lisa)) tab <- r$lisa else if (model == "M39" && !is.null(r$cate_by_covariate)) tab <- r$cate_by_covariate else if (!is.null(r$table)) tab <- r$table
    r1 <- if (!is.null(r$global)) r$global else if (!is.null(r$result)) r$result else NULL
    if (!is.null(r1)) head <- as.list(as.data.frame(r1)[1, , drop = FALSE])          # v20.58: M39's headline too (its ATT and SE)
  } else if (is.data.frame(r)) { if (nrow(r) == 1) head <- as.list(as.data.frame(r)[1, , drop = FALSE]) else tab <- r }
  num <- function(k, src = head) { for (x in k) if (!is.null(src[[x]])) { v <- suppressWarnings(as.numeric(src[[x]][1])); if (is.finite(v)) return(v) }; NA_real_ }
  est <- num(c("att", "ate", "beta", "att_avg", "pooled", "moran_I", "estimate", "ICC")); se <- num(c("se", "std.error", "se_moran")); p <- num(c("p_value", "p.value", "p_ri", "p_moran"))
  if (!is.finite(est) && !is.null(tab)) { t <- as.data.table(tab); bcol <- intersect(c("beta", "estimate", "att"), names(t))[1]
    scol <- intersect(c("se", "std.error"), names(t))[1]; pcol <- intersect(c("p_value", "p.value"), names(t))[1]
    one <- function(rw) { est <<- rw[[bcol]][1]; if (!is.na(scol)) se <<- rw[[scol]][1]; if (!is.na(pcol)) p <<- rw[[pcol]][1]   # v20.58: the SE / p of the SAME row
      if ("se_note" %in% names(rw) && nzchar(rw$se_note[1] %||% "")) note_row <<- as.character(rw$se_note[1]) }                    #   (and why it has none)
    if ("event_time" %in% names(t)) est <- mean(t[event_time >= 0][[bcol]], na.rm = TRUE)
    else if ("term" %in% names(t) && any(t$term == "did")) one(t[term == "did"])
    else if ("tau" %in% names(t)) one(t[abs(tau - 0.5) < 1e-9])
    else if ("cohort" %in% names(t)) est <- mean(t$att, na.rm = TRUE)
    else if ("learner" %in% names(t)) est <- mean(t$ate, na.rm = TRUE)
    else if ("cate_mean" %in% names(t)) est <- mean(t$cate_mean, na.rm = TRUE)
    else if (all(c("weight", "estimate") %in% names(t))) est <- sum(t$weight * t$estimate) / sum(t$weight)
    else if ("local_I" %in% names(t)) est <- mean(t$local_I, na.rm = TRUE)
    else if ("placebo_year" %in% names(t)) est <- mean(t$beta, na.rm = TRUE) }
  s_how <- if (is.list(r) && !is.data.frame(r)) r$se_how else NULL
  if (is.null(s_how) && length(head) && !is.null(head$se_how)) s_how <- as.character(head$se_how)
  ex <- list(); for (k in HEADLINE_EXTRA) { v <- if (is.list(r) && !is.data.frame(r) && !is.null(r[[k]])) r[[k]] else if (length(head)) head[[k]] else NULL
    if (!is.null(v)) ex[[k]] <- v[1] }                                              # v20.58: the extra headline columns travel with it
  c(ex, list(estimate = est, se = se, p_value = p, table = tab, se_how = s_how,
             p_how = if (is.list(r) && !is.data.frame(r) && !is.null(r$p_how)) r$p_how else if (length(head) && !is.null(head$p_how)) as.character(head$p_how) else NULL,
       se_note = if (length(head) && !is.null(head$se_note)) as.character(head$se_note) else note_row,
       engine = if (length(head) && !is.null(head$engine)) paste0(as.character(head$engine[1]), " (R ", model, ")")
                else if (!is.null(tab) && "engine" %in% names(tab)) paste0(as.character(tab$engine[1]), " (R ", model, ")") else paste("R", model, "(models_prebuilt.R)")))
}
lib_model <- function(id) function(dt, outcome) standardise(id, run_model_strict(id, dt, outcome))

# ---------------------------------------------------------------- the registry: all 45 models
source(file.path(R_HOME_DIR, "lib", "model_names.R"), local = environment())       # MODEL_NAMES (the same 45 as the Python pipeline)
MODEL_FUN <- c(list(M01 = m01_twfe, M02 = m02_event, M05 = m05_cs, M06 = m06_dose, M07 = m07_surrogate, M08 = m08_iv, M11 = m11_sdid,
                    M16 = m16_pretrends, M21 = m21_annual, M23 = m23_wild, M34 = m34_honest),
               setNames(lapply(c("M03", "M04", "M09", "M10", "M12", "M13", "M14", "M15", "M17", "M18", "M19", "M20", "M22", "M24", "M25", "M26",
                                 "M27", "M28", "M29", "M30", "M31", "M32", "M33", "M35", "M36", "M37", "M38", "M39", "M40", "M41", "M42", "M43",
                                 "M44", "M45"), lib_model),
                        c("M03", "M04", "M09", "M10", "M12", "M13", "M14", "M15", "M17", "M18", "M19", "M20", "M22", "M24", "M25", "M26",
                          "M27", "M28", "M29", "M30", "M31", "M32", "M33", "M35", "M36", "M37", "M38", "M39", "M40", "M41", "M42", "M43",
                          "M44", "M45")))
MODEL_FUN_ALL <- MODEL_FUN                                        # v20.58: every model the library implements
# v20.58: beyond 98 % of the RAM, M01 / M02 / M16 / M34 out of core (Dask -> Spark -> R batches; exact) -- run_model_R hands them there
source(file.path(R_HOME_DIR, "lib", "reward_outofcore.R"), local = environment())
if (exists("PIPELINE_MODELS") && length(PIPELINE_MODELS)) MODEL_FUN <- MODEL_FUN[intersect(names(MODEL_FUN), PIPELINE_MODELS)]   # the project's models

run_model_R <- function(id, outcome, d = load_design()) {
  cat(sprintf("\n===== %s  %s  x  %s  (%s)\n", id, MODEL_NAMES[[id]] %||% "", outcome, scenario_tag(d)))
  idt <- tryCatch(outcome_identities_R(verbose = FALSE), error = function(e) NULL)            # v20.58: said at every run of either one
  if (!is.null(idt) && nrow(idt)) for (k in which(idt$a == outcome | idt$b == outcome))
    info(sprintf("%s is an exact linear function of %s in this panel (%s = %.4g %+.4g x %s, r = %.7f): %s", outcome, if (idt$a[k] == outcome) idt$b[k] else idt$a[k],
                 idt$b[k], idt$intercept[k], idt$slope[k], idt$a[k], idt$r[k], if (abs(idt$slope[k] - 1) < 1e-6 && abs(idt$intercept[k]) < 1e-9) "the same variable -- identical results are expected, not a copy"
                 else "its estimate is that one's times the slope, with the same p-value"))
  # v20.58 -- YOUR 98 % RULE: M01, M02, M16 and M34 go OUT OF CORE when the sample would not fit (reward_outofcore.R: the pixel partitions
  # on Dask, Spark or R batches; exact, never sampled); below 98 % they run here, all rows at once, exactly as before
  rm_ <- run_mode_R(id, outcome, d)
  if (identical(rm_$mode, "out_of_core")) return(invisible(ooc_run_model_R(id, outcome, d, rm_$why)))
  dt <- tryCatch(load_panel_R(outcome, d), error = function(e) e)
  if (inherits(dt, "error") && id %in% OOC_MODELS_R && grepl("cannot allocate|memory exhausted|vector memory|std::bad_alloc", conditionMessage(dt), ignore.case = TRUE)) {
    warn(sprintf("%s x %s: the sample did not fit in RAM (%s) -- out of core instead", id, outcome, conditionMessage(dt)))
    invisible(gc()); return(invisible(ooc_run_model_R(id, outcome, d, "the in-memory load ran out of memory")))
  }
  if (inherits(dt, "error")) { save_result(id, outcome, list(error = conditionMessage(dt)), NULL, d); return(invisible(NULL)) }
  t0 <- Sys.time()
  res <- tryCatch(MODEL_FUN[[id]](dt, outcome), error = function(e) list(error = conditionMessage(e)))
  out <- save_result(id, outcome, res, dt, d)
  info(sprintf("%s x %s done in %.1f s", id, outcome, as.numeric(difftime(Sys.time(), t0, units = "secs"))))
  rm(dt); invisible(gc()); invisible(out)
}
