# models_prebuilt.R -- the model library of the pre-built R pipeline (v20.23). Sourced by RUN_ALL.R.
# Every function takes the package-input data.table `dt` (read_input(outcome)) and the outcome name; writes the
# same results layout as the Python engine under results/prebuilt_R/<model>/<scenario>/. `need()` names the
# package to install when one is missing. Not executed in the environment that produced this bundle.
#
#  M03 DRDID::drdid                M04 qte::cic                  M06 contdid                    M09 fixest::sunab
#  M10 fixest triple interaction   M13 DIDmultiplegtDYN          M14 MatchIt + fixest           M17/M18 spdep
#  M19 lme4 ICC                    M20 metafor::rma (Q, I2)      M22 bacondecomp                M24/M26/M29 fixest variants
#  M25 ritest                      M27 didimputation             M28 did2s                      M30 did::aggte(group)
#  M31 stacked (fixest)            M32 etwfe                     M33 WeightIt ebal + fixest     M35 quantreg / qte::QDiD
#  M36 fect (ife)                  M37 fect (mc)                 M38 gsynth                     M39/M43 grf::causal_forest
#  M40 DoubleML                    M41 grf S/T/X                 M42 grf DR                     M44 dbarts / bartCause
#  M45 synthdid / augsynth (site level)

# v20.43: sample sizes for the estimators that cannot take ~2 million pixels (overridable before sourcing)
if (!exists("N_MAX_UNITS")) N_MAX_UNITS <- NULL; if (!exists("N_MAX_PIXELS_MIXED")) N_MAX_PIXELS_MIXED <- NULL   # v20.57: the 98 % rule
if (!exists("N_MAX_ML")) N_MAX_ML <- NULL                                                                        # (reward_paths.R decides)
if (!exists("units_that_fit")) units_that_fit <- function(bytes_per_unit, manual = NULL) {   # the bridge (run_one.R): the same 98 % rule
  if (!is.null(manual) && is.finite(manual)) return(as.numeric(manual))
  m <- if (requireNamespace("ps", quietly = TRUE)) tryCatch(ps::ps_system_memory(), error = function(e) NULL) else NULL
  if (is.null(m)) return(Inf); max(1, floor(max(0, m$avail - 0.02 * m$total) / bytes_per_unit))
}
if (!exists("info")) info <- function(...) cat("[INFO]    ", ..., "\n", sep = "")
# v20.58 YOUR RULE: every row / unit in RAM at once -- ONLY beyond 98 % of the RAM does a model fall back to BATCHES: every unit used exactly
# once, never a sample (v20.57 SAMPLED there: M04, M17 / M18, M19, M35 and the ML models). FORCE_BATCH_UNITS (tests only) forces the batch
# path with a given batch size, to prove it gives the all-at-once answer.
if (!exists("FORCE_BATCH_UNITS")) FORCE_BATCH_UNITS <- NULL
unit_cap <- function(bytes_per_unit, manual = NULL) {
  cap <- units_that_fit(bytes_per_unit, manual)
  f <- get0("FORCE_BATCH_UNITS", ifnotfound = NULL); if (!is.null(f) && is.finite(f)) cap <- min(cap, f)
  max(1, cap)
}
batch_split <- function(units, cap, strata = NULL, seed = 1L) {
  # ceiling(n / cap) batches of <= cap units, every unit in exactly one; a stratum (treated / control) is spread evenly over them
  n <- length(units); k <- max(1L, as.integer(ceiling(n / cap))); if (k == 1L) return(list(units))
  set.seed(seed); b <- integer(n)
  if (is.null(strata)) b <- sample(rep_len(seq_len(k), n)) else for (s_ in unique(strata)) { i <- which(strata == s_); b[i] <- sample(rep_len(seq_len(k), length(i))) }
  unname(split(units, b))
}
say_batches <- function(what, n, k, cap) info(sprintf("%s: %s units in %d batches of <= %s -- all of them at once would pass 98 %% of the RAM; every unit is used, none is sampled",
                                                   what, format(n, big.mark = ","), k, format(cap, big.mark = ",")))
if (!exists("N_MAX_SPATIAL")) N_MAX_SPATIAL <- NULL      # v20.57 YOUR 98 % RULE: NULL = every pixel whose k-NN weights fit below 98 % of
                                                          #   the RAM (units_that_fit); a number caps it by hand (v20.55: 3,000,000 fixed)
if (!exists("MIN_SWS_CLUSTERS")) MIN_SWS_CLUSTERS <- 6    # v20.49: the Python bridge (run_one.R) sources this file alone
if (!exists("cluster_col_for", mode = "function")) cluster_col_for <- function(dt) {   # v20.58: the bridge (run_one.R) -- as reward_design.R
  if (uniqueN(dt$site_id[dt$site_id > 0]) >= MIN_SWS_CLUSTERS) "site_id" else "Year" }
if (!exists("design_se_event", mode = "function")) {   # v20.58: the bridge (run_one.R) -- the same function as reward_design.R
design_se_event <- function(dt, outcome, estimate = NA_real_) {
  d <- dt[is.finite(get(outcome))]; if ("site_id" %in% names(d) && any(d$site_id > 0L)) d <- d[site_id > 0L]
  d <- d[, .(site_id, Year, Season, treat, post, unit, y = get(outcome))]; d[, y := y - mean(y), by = unit]
  g <- dcast(d[, .(m = mean(y)), by = .(site_id, Year, Season, treat)], site_id + Year + Season ~ treat, value.var = "m")
  if (!all(c("0", "1") %in% names(g))) return(list(se = NA_real_, df = NA_real_, p = NA_real_, how = "not identified"))
  g[, gap := `1` - `0`]; g <- merge(g, d[, .(post = max(post)), by = .(site_id, Year, Season)], by = c("site_id", "Year", "Season"))
  wy <- g[is.finite(gap), .(gap = mean(gap), post = max(post)), by = .(site_id, Year)]
  v <- wy[, .(s2 = if (sum(post == 0L) > 1) var(gap[post == 0L]) else NA_real_, n0 = sum(post == 0L), n1 = sum(post == 1L)), by = site_id][is.finite(s2) & n1 > 0]
  if (!nrow(v)) return(list(se = NA_real_, df = NA_real_, p = NA_real_, how = "not identified (fewer than 2 pre-period years)"))
  S <- nrow(v); se <- sqrt(sum(v$s2 * (1 + 1 / v$n1))) / S; df <- sum(v$n0 - 1)
  list(se = se, df = df, p = if (is.finite(estimate) && se > 0) 2 * pt(abs(estimate / se), df, lower.tail = FALSE) else NA_real_,
       how = sprintf("design-based: years as the draws (the year-to-year spread of the %d pre-period gap(s) x sqrt(1 + 1/%d post years)%s)", sum(v$n0), round(mean(v$n1)),
                     if (S > 1) sprintf(", %d sub-watersheds", S) else ""))
}
}
if (!exists("design_se", mode = "function")) {   # v20.58: the bridge (run_one.R) -- the same functions as reward_design.R (M20 needs them)
.draws <- function(w) {                                                        # w: site_id, gap, post -> per-site DiD and variance
  w[is.finite(gap), { a <- gap[post == 0L]; b <- gap[post == 1L]
    sa <- if (length(a) > 1) var(a) else NA_real_; sb <- if (length(b) > 1) var(b) else NA_real_
    .(did = if (length(a) && length(b)) mean(b) - mean(a) else NA_real_,
      va = if (length(a)) (if (is.finite(sa)) sa else sb) / length(a) else NA_real_, vb = if (length(b)) (if (is.finite(sb)) sb else sa) / length(b) else NA_real_,
      n0 = length(a), n1 = length(b)) }, by = site_id][is.finite(did)]
}
.combine <- function(per) {                                                    # the sub-watersheds' DiDs -> one DiD, SE, df
  S <- nrow(per); if (!S) return(list(did = NA_real_, se = NA_real_, df = NA_real_, S = 0L))
  if (S >= MIN_SWS_CLUSTERS) return(list(did = mean(per$did), se = sd(per$did) / sqrt(S), df = S - 1, S = S, by = "sub-watersheds"))
  v <- per$va + per$vb
  list(did = mean(per$did), se = if (any(is.finite(v))) sqrt(sum(v, na.rm = TRUE)) / S else NA_real_, df = sum(per$n0 + per$n1 - 2), S = S, by = "years")
}
design_se <- function(dt, outcome, estimate = NA_real_) {
  d <- dt[is.finite(get(outcome))]
  if ("site_id" %in% names(d) && any(d$site_id > 0L)) d <- d[site_id > 0L]  # v20.58: rows without a sub-watershed are no sub-watershed
  if (!nrow(d) || !all(c("treat", "post", "unit", "Year", "Season") %in% names(d))) return(list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified"))
  d <- d[, .(site_id, Year, Season, treat, post, unit, y = get(outcome))]
  d[, y := y - mean(y), by = unit]                                             # the within transformation (each unit's own level removed)
  g <- d[, .(m = mean(y)), by = .(site_id, Year, Season, treat)]
  w <- dcast(g, site_id + Year + Season ~ treat, value.var = "m")
  if (!all(c("0", "1") %in% names(w))) return(list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified (no year-season with both treated and control rows)"))
  w[, gap := `1` - `0`]
  w <- merge(w, d[, .(post = max(post), pmin = min(post)), by = .(site_id, Year, Season)], by = c("site_id", "Year", "Season"))
  wy <- w[is.finite(gap), .(gap = mean(gap), post = max(post), pmin = min(pmin)), by = .(site_id, Year)]
  wy <- wy[!(post == 1L & pmin == 0L)]                                         # a year whose seasons are partly treated is no YEAR draw
  per <- .draws(wy); cy <- .combine(per)
  if (!cy$S) return(list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified (no sub-watershed with pre AND post years)"))
  pt2 <- function(t, df) if (is.finite(t) && is.finite(df) && df > 0) 2 * pt(abs(t), df, lower.tail = FALSE) else NA_real_
  unit <- if (cy$by == "sub-watersheds") sprintf("%d sub-watersheds as the draws", cy$S) else if (cy$S == 1)
    sprintf("years as the draws: %d pre, %d post; one sub-watershed", per$n0, per$n1) else sprintf("years within each of %d sub-watersheds as the draws", cy$S)
  out <- list(did_design = cy$did, se_design = cy$se, df_design = cy$df, p_design = pt2(cy$did / cy$se, cy$df), se_design_unit = unit,
              n_pre_design = sum(per$n0), n_post_design = sum(per$n1), n_sites_design = cy$S,
              p_estimate_design = pt2(estimate / cy$se, cy$df))
  if (cy$by == "years" && uniqueN(d$Season) > 1) {                              # each year x season a draw (seasons of a year may share a shock:
    per2 <- .draws(w[, .(site_id, gap, post)]); c2 <- .combine(per2)            # the year-level pair above is the conservative one)
    if (c2$S) out <- c(out, list(did_design_period = c2$did, se_design_period = c2$se, df_design_period = c2$df, p_design_period = pt2(c2$did / c2$se, c2$df),
                                 n_periods_design = sum(per2$n0 + per2$n1), se_design_period_unit = "each year x season a draw",
                                 p_estimate_design_period = pt2(estimate / c2$se, c2$df)))
  }
  out
}
}
if (!exists("r_se_how", mode = "function")) {   # v20.58: the bridge (run_one.R) -- the SAME texts as reward_design.R's r_se_how: an R route's
                                                    #   SE described as R's own run describes it (Python printed "its own SE")
r_se_how <- function(model, dt, engine = "R") {
  # v20.58: what each model's OWN standard error is -- written into every result and printed with it (never a generic label)
  cc <- cluster_col_for(dt); G <- uniqueN(dt[[cc]]); cl <- sprintf("clustered by %s (%d clusters)", if (cc == "site_id") "sub-watershed" else "year", G)
  ns <- uniqueN(dt$site_id[dt$site_id > 0]); nu <- uniqueN(dt$unit); np <- uniqueN(dt$pixel_id)
  pkg_cl <- if (ns >= MIN_SWS_CLUSTERS) sprintf("clustered by sub-watershed (%d)", ns) else sprintf("each of the %s pixel x season series one draw (not clustered: the package clusters on groups, not on years)", format(nu, big.mark = ","))
  switch(model,
    M03 = sprintf("DRDID::drdid (improved doubly robust, Sant'Anna & Zhao 2020): the influence-function SE over the %s pixel x season series (each series one draw; not clustered)", format(nu, big.mark = ",")),
    M04 = sprintf("qte::CiC: the bootstrap over the %s pixel x season series (200 draws; not clustered)", format(nu, big.mark = ",")),
    M10 = sprintf("fixest::feols, triple differences (the did row; did x land use beside it), %s", cl),
    M12 = sprintf("fixest::feols on the first differences between consecutive observations (chained DiD), %s", cl),
    M13 = sprintf("DIDmultiplegtDYN: its analytic SE, %s", pkg_cl),
    M14 = sprintf("MatchIt 1:1 nearest-neighbour matching (caliper 0.2) + fixest::feols on the matched pixels, %s", cl),
    M17 = , M18 = "spdep::moran.test: the variance of Moran's I under randomisation",
    M20 = "metafor::rma (REML): the SE of the pooled effect across the sub-watersheds",
    M26 = sprintf("fixest::feols, the did row (the effect at the mean Rain; did x centred Rain beside it), %s", cl),
    M27 = sprintf("didimputation (Borusyak, Jaravel & Spiess 2024): its conservative analytic SE, %s", pkg_cl),
    M29 = sprintf("fixest::feols, one effect per exposure year -- their mean and its SE by the delta method, %s", cl),
    M31 = sprintf("fixest::feols on the stacked data (unit x stack and year x stack effects), %s", cl),
    M33 = sprintf("WeightIt entropy-balancing weights + weighted fixest::feols, %s", cl),
    M35 = sprintf("quantreg::rq at the median: the cluster-robust kernel sandwich (Parente & Santos Silva 2016), %s", cl),
    M39 = , M43 = sprintf("grf::causal_forest (honest): the SE of its average effect on the treated, %s", if (ns >= MIN_SWS_CLUSTERS) sprintf("clustered by sub-watershed (%d)", ns) else sprintf("each of the %s pixels one draw (not clustered)", format(np, big.mark = ","))),
    M40 = sprintf("DoubleML PLR (3-fold cross-fitting): its asymptotic SE, each of the %s pixels one draw (not clustered)", format(np, big.mark = ",")),
    M42 = sprintf("grf AIPW (doubly robust): its SE, each of the %s pixels one draw (not clustered)", format(np, big.mark = ",")),
    M44 = "bartCause: the posterior standard deviation of the ATT (500 draws)",
    sprintf("%s, %s", engine, cl))
}
}
if (!exists("N_THREADS")) N_THREADS <- max(1L, parallel::detectCores())
if (!exists("covs_in", mode = "function")) covs_in <- function(dt) {    # v20.58: the bridge (run_one.R) -- the same rule as reward_models_core.R:
  cv <- attr(dt, "covariates_used")                                       #   the covariates of the design in effect (COVARIATES), never a fixed list
  if (is.null(cv)) cv <- get0("DEFAULT_COVS", ifnotfound = c("Rain", "Tmax", "Tmean", "Tmin"))
  if (length(cv) == 1 && tolower(cv) == "all") cv <- c("Rain", "Tmax", "Tmean", "Tmin")
  intersect(cv, names(dt))
}
if (!exists("need", mode = "function")) need <- function(p, where = "CRAN") {   # v20.55: reward_packages.R's need() installs first when loaded
  if (!requireNamespace(p, quietly = TRUE) && exists("install_package_chain", mode = "function") && isTRUE(get0("AUTO_INSTALL_PACKAGES", ifnotfound = FALSE))) install_package_chain(p)
  if (!requireNamespace(p, quietly = TRUE)) stop(sprintf("install '%s' (%s)", p, where))
}
wr <- function(model, tag, name, x) fwrite(as.data.table(x), file.path(out_dir(model, tag), paste0(name, ".csv")))
# v20.58: the headline of an event-type model (the mean of its post-period coefficients) ALWAYS with an SE and a p-value: the delta method on
# the fit's cluster-robust covariance when the clusters are sub-watersheds; the design-based SE (years as the draws) when they are years --
# one coefficient per year makes that covariance degenerate (v20.57 left these SEs NA)
event_headline <- function(fit, terms, dt, outcome) {
  est <- mean(coef(fit)[terms]); yr <- identical(get0("cluster_col_for", ifnotfound = function(d) "Year")(dt), "Year")
  if (!yr) { w <- rep(1 / length(terms), length(terms)); V <- vcov(fit)[terms, terms, drop = FALSE]; se <- sqrt(drop(t(w) %*% V %*% w))
             G <- uniqueN(dt$cluster_id); return(list(estimate = est, se = se, p_value = 2 * pt(abs(est / se), max(1, G - 1), lower.tail = FALSE),
                                                      se_how = sprintf("delta method on the cluster-robust covariance (%d clusters)", G), p_how = sprintf("t with %d df", max(1, G - 1)))) }
  if (!exists("design_se_event", mode = "function")) return(list(estimate = est, se = NA_real_, p_value = NA_real_, se_how = "the year clusters make this SE degenerate"))
  de <- design_se_event(dt, outcome, est); list(estimate = est, se = de$se, p_value = de$p, se_how = de$how, p_how = sprintf("t with %g df", de$df))
}
# v20.49 (first real run of the R library): several packages require a NUMERIC unit id (DRDID, did) and a cluster that
# is constant within a unit (did, DIDmultiplegtDYN, grf). The sub-watershed is such a cluster; with fewer than
# MIN_SWS_CLUSTERS of them there is no valid cluster for these packages and they use their unit-level default.
num_id <- function(x) as.integer(factor(x))
# v20.58: every bootstrap on EVERY core, and reproducible: the parallel-safe random generator (L'Ecuyer-CMRG) seeded before each resampling
# model -- qte::CiC bootstrapped on 2 cores with unseeded streams (its SE changed between two runs of the same data), did::att_gt on 1
seeded <- function(expr) { old <- RNGkind()[1]; RNGkind("L'Ecuyer-CMRG"); set.seed(12345); on.exit(RNGkind(old), add = TRUE); force(expr) }
# v20.58: fect's / gsynth's cross-validation draws its folds (which series, which years are held out) from R's generator -- unseeded, the
# chosen number of factors (lambda) and so the estimate could change from one run to the next. Seeded with R's default generator
# (Mersenne-Twister, set.seed(12345)); the generator's state before is restored after. The Python engine replicates this generator and draws
# the same folds (_common._RRandom / fect_fit).
with_mt_seed <- function(expr, seed = 12345L) {
  had <- exists(".Random.seed", envir = globalenv(), inherits = FALSE)
  old_seed <- if (had) get(".Random.seed", envir = globalenv(), inherits = FALSE) else NULL
  old_kind <- RNGkind()
  on.exit({ suppressWarnings(RNGkind(old_kind[1], old_kind[2], old_kind[3]))
            if (had) assign(".Random.seed", old_seed, envir = globalenv()) else if (exists(".Random.seed", envir = globalenv(), inherits = FALSE)) rm(".Random.seed", envir = globalenv()) }, add = TRUE)
  suppressWarnings(set.seed(seed, kind = "Mersenne-Twister", normal.kind = "Inversion", sample.kind = "Rejection"))
  force(expr)
}
# v20.54: the event time in a coefficient name ("event_time::-3", "Year::2"); NA -- without the "NAs introduced by
# coercion" warning your runs printed -- for a covariate row such as "Rain"
term_event_time <- function(term) { out <- rep(NA_integer_, length(term)); k <- grepl("::-?[0-9]+", term)
  out[k] <- as.integer(sub(".*::(-?[0-9]+).*", "\\1", term[k])); out }
site_cluster <- function(dt) if (uniqueN(dt$site_id[dt$site_id > 0]) >= MIN_SWS_CLUSTERS) "site_id" else NULL
# v20.58 -- SEASON-MATCHED: these packages have ONE time effect per YEAR, but your design has one per year x season (a Kharif shock is not a
# Rabi shock). With the fund timing a cohort can be ONE season's series (Rabi 2024) while the never-treated rings hold every season -- the
# seasons' shocks then did not cancel (M27 0.0517 for a true 0.05 in the known-answer test). The outcome enters net of the control rings'
# mean in the same season and year (and sub-watershed: POOLED_FE "site_period" / one sub-watershed) -- the design's own year x season
# effect, estimated on the untreated rows: every series is compared with its own season's controls, as the two-way FE models do.
season_net <- function(dt, outcome) {
  pf <- tryCatch(load_design()$pooled_fe, error = function(e) NULL) %||% "site_period"
  by <- if (uniqueN(dt$site_id[dt$site_id > 0]) > 1 && identical(pf, "period")) c("Season", "Year") else c("site_id", "Season", "Year")
  v <- dt[[outcome]]; m <- dt[, .(cm = mean(get(outcome)[treat == 0L])), by = by]
  cm <- m[dt[, ..by], on = by, cm]
  out <- v - cm; out[!is.finite(out)] <- NA_real_; out
}
unit_year <- function(dt, outcome, covs = DEFAULT_COVS) {           # one row per pixel-year (staggered packages)
  cv <- covs[covs %in% names(dt)]; d <- copy(dt); d[, y_sn := season_net(dt, outcome)]; d <- d[is.finite(y_sn)]
  d[, c(list(y = mean(y_sn), treat = max(treat), post = max(post)), lapply(.SD, mean)),
    by = .(unit, Year, cluster_id, site_id, gvar = ifelse(is.finite(cohort), cohort, 0)), .SDcols = cv]   # v20.29: one series per pixel x season
}

# ---------------------------------------------------------------- M03 doubly-robust 2x2 (Sant'Anna & Zhao)
m03_drdid <- function(dt, outcome, covs = covs_in(dt)) {   # v20.58: the design's COVARIATES (was a fixed list: COVARIATES <- "none" did not reach it)   # v20.43: rewritten (grouping column was duplicated)
  need("DRDID"); cv <- covs[covs %in% names(dt)]
  uy <- unit_year(dt, outcome, cv)
  two <- uy[, .(y = mean(y), treat = max(treat)), by = .(unit, post)]                 # the 2-period panel DRDID wants
  if (length(cv)) two <- merge(two, uy[post == 0, lapply(.SD, mean), by = unit, .SDcols = cv], by = "unit")
  two <- two[unit %in% two[, .N, by = unit][N == 2, unit]]                           # units seen before AND after
  two[, id := num_id(unit)]                                                          # v20.49: DRDID needs a numeric id
  d <- DRDID::drdid(yname = "y", tname = "post", idname = "id", dname = "treat",
                    xformla = if (length(cv)) as.formula(paste("~", paste(cv, collapse = "+"))) else NULL,
                    data = as.data.frame(two), panel = TRUE, estMethod = "imp")
  r <- data.frame(outcome = outcome, att = d$ATT, se = d$se, engine = "DRDID::drdid"); wr("drdid", attr(dt, "scenario"), paste0("aipw_did_", outcome), r); r
}

# ---------------------------------------------------------------- M04 changes-in-changes
m04_cic <- function(dt, outcome) {
  need("qte"); uy <- unit_year(dt, outcome, character(0))
  two <- uy[, .(y = mean(y), treat = max(treat)), by = .(unit, post)]
  # v20.58 (second pass): integer series ids in (pixel, season) order -- qte's bootstrap draws the ids with sample(unique(ids), n, TRUE), so
  # the order of the ids decides which series each draw picks; the character ids came in the order of the data (and num_id() sorts them by
  # the locale's collation). The Python engine (_common.cic_qte) takes the same order and R's own draws.
  um <- dt[, .(p = min(pixel_id), s = min(Season)), by = unit]; setorder(um, p, s)
  two[, uid := match(unit, um$unit)]; setorder(two, uid, post)
  cic_one <- function(tw) {
    if (exists("CiC", envir = asNamespace("qte"), inherits = FALSE)) {
      # v20.54: qte 2.0 prints two notes on every call that do not apply here -- "CiC() is deprecated" (it still computes the
      # same estimate as before) and "covariates appear to vary over time" (qte compares the row names of two empty covariate
      # frames; this model has no covariates). They are silenced, the result is unchanged.
      # v20.58 (second pass): cores = 1 -- qte's bootstrap (pbapply) forks on Linux / macOS with draws that depend on the NUMBER of cores
      # (another machine, another SE) and runs sequentially on Windows whatever `cores` says; sequential everywhere gives your Windows SE on
      # every machine (200 CiC fits of one pre and one post mean per series: seconds), reproducible, and the Python engine's
      r <- withCallingHandlers(seeded(
        qte::CiC(y ~ treat, t = 1, tmin1 = 0, tname = "post", idname = "uid", panel = TRUE, data = as.data.frame(tw[, .(uid, post, y, treat)]),
                 probs = seq(0.1, 0.9, 0.1), se = TRUE, iters = 200, pl = FALSE, cores = 1L)),
        warning = function(w) if (grepl("is deprecated|covariates appear to vary over time", conditionMessage(w))) invokeRestart("muffleWarning"))
      return(list(att = r$ate, se = r$ate.se, eng = "qte::CiC"))
    }
    tw <- copy(tw); tw[, `:=`(id = uid, period = post + 1L, g = fifelse(treat == 1L, 2L, 0L))]   # v20.54: qte's successor cic()
    r <- seeded(qte::cic(yname = "y", gname = "g", tname = "period", idname = "id", data = as.data.frame(tw), gt_type = "att", biters = 200))
    list(att = r$overall_results$att, se = r$overall_results$se, eng = "qte::cic")
  }
  tr <- two[, .(treat = max(treat)), by = unit]
  bs <- batch_split(tr$unit, unit_cap(2 * 5 * 8 * 12, N_MAX_UNITS), tr$treat)                # v20.58: batches beyond 98 % of the RAM (was a sample)
  if (length(bs) == 1L) { r <- cic_one(two); att <- r$att; se <- r$se; eng <- r$eng; nb <- 1L }
  else {
    say_batches("M04 CiC", nrow(tr), length(bs), max(lengths(bs)))
    rs <- lapply(bs, function(u) cic_one(two[unit %in% u])); n1 <- vapply(bs, function(u) sum(tr[unit %in% u, treat]), numeric(1)); w <- n1 / sum(n1)
    att <- sum(w * vapply(rs, `[[`, numeric(1), "att")); se <- sqrt(sum(w^2 * vapply(rs, `[[`, numeric(1), "se")^2))
    eng <- paste0(rs[[1]]$eng, sprintf(" on %d batches of series (the treated spread evenly; ATT = their treated-weighted mean, SE from the independent batches)", length(bs))); nb <- length(bs)
  }
  out <- data.frame(outcome = outcome, att = att, se = se, batches = nb, engine = eng); wr("cic", attr(dt, "scenario"), paste0("cic_", outcome), out); out
}

# ---------------------------------------------------------------- M09 Sun-Abraham (fixest::sunab)
m09_sunab <- function(dt, outcome, covs = covs_in(dt)) {    # v20.58: the design's COVARIATES (DEFAULT_COVS was fixed when the library loaded)
  cv <- covs[covs %in% names(dt)]; d <- copy(dt); d[, cohort_g := ifelse(is.finite(cohort), cohort, 10000)]
  fit <- feols(as.formula(paste0(outcome, " ~ sunab(cohort_g, Year)", if (length(cv)) paste0(" + ", paste(cv, collapse = "+")) else "", " | unit + period")), data = d, cluster = ~cluster_id)
  ct <- as.data.table(coeftable(fit), keep.rownames = "term"); ct[, event_time := term_event_time(term)]
  out <- ct[, .(event_time, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "fixest::sunab")]
  wr("sun_abraham", attr(dt, "scenario"), paste0("sun_abraham_", outcome), out)
  # v20.58: the headline (the mean of the post-period event-time effects, as every event model) and ITS SE from the COHORT x PERIOD
  # coefficients. coef(fit) are fixest's per-period aggregates, but vcov(fit) is the covariance of the cohort x period ones -- with two or
  # more cohorts v20.57 indexed one by the other ('subscript out of bounds', scenario B). Each period's aggregate is fixest's own: the
  # cohorts weighted by their observations in the estimation sample (reproduces coef(fit) exactly); the headline is a linear combination
  # of the cohort x period coefficients, its SE the delta method on their cluster-robust covariance.
  cf <- coef(fit, agg = FALSE); cf <- cf[grepl("^Year::-?[0-9]+:cohort::", names(cf))]
  if (!length(cf)) stop("sunab returned no cohort x period coefficient")
  X <- model.matrix(fit, type = "rhs"); nob <- colSums(X[, names(cf), drop = FALSE] != 0)
  kk <- as.integer(sub("^Year::(-?[0-9]+):.*", "\\1", names(cf))); pk <- sort(unique(kk[kk >= 0]))
  if (!length(pk)) stop("sunab returned no post-period coefficient")
  L <- numeric(length(cf)); for (k in pk) { ix <- which(kk == k); L[ix] <- nob[ix] / sum(nob[ix]) / length(pk) }
  agg_chk <- vapply(pk, function(k) { ix <- which(kk == k); sum(nob[ix] * cf[ix]) / sum(nob[ix]) }, 0)
  agg_fx <- coef(fit)[paste0("Year::", pk)]
  if (any(is.finite(agg_fx)) && max(abs(agg_chk - agg_fx), na.rm = TRUE) > 1e-8 * max(1, abs(agg_fx), na.rm = TRUE))
    stop("the cohort weights do not reproduce fixest's period aggregates -- the headline would not be fixest's")
  est <- sum(L * cf)
  h <- if (!identical(cluster_col_for(dt), "Year")) {
    V <- vcov(fit)[names(cf), names(cf), drop = FALSE]; se <- sqrt(drop(t(L) %*% V %*% L)); G <- uniqueN(dt$cluster_id)
    list(estimate = est, se = se, p_value = 2 * pt(abs(est / se), max(1, G - 1), lower.tail = FALSE),
         se_how = sprintf("delta method on the cluster-robust covariance of the cohort x period coefficients (%d clusters)", G), p_how = sprintf("t with %d df", max(1, G - 1)))
  } else { de <- design_se_event(dt, outcome, est); list(estimate = est, se = de$se, p_value = de$p, se_how = de$how, p_how = sprintf("t with %g df", de$df)) }
  list(result = data.frame(estimate = h$estimate, se = h$se, p_value = h$p_value, se_how = h$se_how), se_how = h$se_how, p_how = h$p_how, table = out, fit = fit)
}

# ---------------------------------------------------------------- M10 triple differences (land use)
m10_ddd <- function(dt, outcome, group = "LandUse", level = 2L) {
  # v20.58 -- the SAME triple difference as Python's M10 (ddd_regression): the third dimension is land use 2 against the rest (g3), the
  # regression y ~ did + did x g3 | unit + period x g3, clustered on the design cluster; the HEADLINE is did x g3 = the DiD in land use 2 minus
  # the DiD in the rest (0 without heterogeneity) -- v20.57 R used every land-use class and reported the did row (the base class's DiD, ~0.05)
  # while Python reported the triple difference: the same model, two different numbers
  if (!group %in% names(dt)) stop("no ", group, " column"); d <- copy(dt); d[, g3 := as.integer(get(group) == level)]
  if (uniqueN(d$g3) < 2) stop(sprintf("%s == %d holds for all or none of the rows -- no triple difference", group, level))
  d[, did_g3 := did * g3]
  fit <- feols(as.formula(paste0(outcome, " ~ did_g3 + did | unit + period^g3")), data = d, cluster = ~cluster_id)
  ct <- as.data.table(coeftable(fit), keep.rownames = "term")
  out <- ct[, .(term, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "fixest DDD")]; wr("ddd", attr(dt, "scenario"), paste0("ddd_", outcome), out)
  h <- out[term == "did_g3"]; r <- out[term == "did"]
  list(result = data.frame(estimate = h$beta, se = h$se, p_value = h$p_value, did_rest = if (nrow(r)) r$beta else NA_real_, third_dim = sprintf("%s == %d", group, level),
                           se_how = sprintf("fixest::feols, the triple difference (did x [%s == %d]; the DiD of the rest beside it), clustered by %s", group, level,
                                            if (identical(cluster_col_for(dt), "Year")) "year" else "sub-watershed")), table = out)
}

# ---------------------------------------------------------------- M13 switchers (de Chaisemartin & D'Haultfoeuille)
m13_switchers <- function(dt, outcome) {
  need("DIDmultiplegtDYN"); uy <- unit_year(dt, outcome, character(0)); uy[, D := as.integer(post == 1 & treat == 1)]
  need("polars", "r-universe: install.packages('polars', repos = 'https://rpolars.r-universe.dev')")
  suppressPackageStartupMessages(library(polars))                        # v20.49: the package calls pl$... from the search path
  if (exists("pl", envir = .GlobalEnv, inherits = FALSE)) {              # v20.58: a variable named `pl` in YOUR session masked polars' `pl`
    .pl_saved <- get("pl", envir = .GlobalEnv); rm("pl", envir = .GlobalEnv)   # ("attempt to apply non-function" in the test run) --
    on.exit(assign("pl", .pl_saved, envir = .GlobalEnv), add = TRUE)       # set aside for the call, restored after it
  }
  uy[, gid := num_id(unit)]; cl <- site_cluster(dt)                                                 # v20.49
  r <- DIDmultiplegtDYN::did_multiplegt_dyn(df = as.data.frame(uy), outcome = "y", group = "gid", time = "Year", treatment = "D", effects = 3, placebo = 2,
                                            cluster = cl, graph_off = TRUE)
  ate <- r$results$ATE
  out <- data.frame(outcome = outcome, att_avg = unname(ate[1, 1]), se = unname(ate[1, 2]), engine = "DIDmultiplegtDYN"); wr("switchers", attr(dt, "scenario"), paste0("switchers_", outcome), out); out
}

# ---------------------------------------------------------------- M14 PSM-DiD, M33 entropy balancing
m14_psm <- function(dt, outcome, covs = covs_in(dt)) {     # v20.58: the design's COVARIATES
  need("MatchIt"); cv <- covs[covs %in% names(dt)]
  base <- dt[post == 0, c(list(treat = max(treat), cluster_id = cluster_id[1]), lapply(.SD, mean)), .SDcols = cv, by = pixel_id]
  # v20.58: matched on the LOGIT of the propensity score, caliper 0.2 SD of it (Austin 2011) -- the rule of Python's engine (v20.57 R matched on
  # the raw score); the highest propensity first (MatchIt's m.order = "largest")
  if (!length(cv)) stop("PSM needs covariates to match on (COVARIATES is empty)")
  m <- MatchIt::matchit(as.formula(paste("treat ~", paste(cv, collapse = "+"))), data = as.data.frame(base), method = "nearest", ratio = 1, caliper = 0.2,
                        distance = "glm", link = "linear.logit", m.order = "largest")
  keep <- MatchIt::match.data(m)$pixel_id; d <- dt[pixel_id %in% keep]
  fit <- feols(as.formula(paste0(outcome, " ~ did | unit + period")), data = d, cluster = ~cluster_id)
  out <- data.frame(outcome = outcome, beta = coef(fit)["did"], se = se(fit)["did"], n_matched_pixels = length(keep), engine = "MatchIt + fixest"); wr("psm_did", attr(dt, "scenario"), paste0("psm_did_", outcome), out); out
}
m33_ebal <- function(dt, outcome, covs = covs_in(dt)) {    # v20.58: the design's COVARIATES
  need("WeightIt"); cv <- covs[covs %in% names(dt)]
  base <- dt[post == 0, c(list(treat = max(treat)), lapply(.SD, mean)), .SDcols = cv, by = pixel_id]
  w <- WeightIt::weightit(as.formula(paste("treat ~", paste(cv, collapse = "+"))), data = as.data.frame(base), method = "ebal", estimand = "ATT")
  base[, w := w$weights]; d <- merge(dt, base[, .(pixel_id, w)], by = "pixel_id")
  fit <- feols(as.formula(paste0(outcome, " ~ did | unit + period")), data = d, weights = ~w, cluster = ~cluster_id)
  out <- data.frame(outcome = outcome, beta = coef(fit)["did"], se = se(fit)["did"], engine = "WeightIt ebal + fixest"); wr("entropy_balancing", attr(dt, "scenario"), paste0("ebal_did_", outcome), out); out
}

# ---------------------------------------------------------------- M17 / M18 spatial autocorrelation
knn_xy <- function(lat, lon) {                          # v20.58: metres on a local plane -- as Python's build_knn_spatial_weights
  R <- 6371000; lat0 <- mean(lat) * pi / 180; cbind(lon * pi / 180 * R * cos(lat0), lat * pi / 180 * R)
}
knn_index <- function(xy, k) {
  # v20.58: the k nearest neighbours of every pixel (n x k), an exact kd-tree (RANN, eps 0) -- spdep's own search without dbscan compares every
  # pair (n^2: days for your 3 million pixels). The queries run in batches only beyond 98 % of the RAM.
  need("RANN"); n <- nrow(xy); if (n <= k) stop(sprintf("k-NN weights need more than k = %d pixels (have %d)", k, n))
  cap <- unit_cap(16 * (k + 1) + 96); qs <- if (n <= cap) list(seq_len(n)) else split(seq_len(n), ceiling(seq_len(n) / cap))
  if (length(qs) > 1L) say_batches("k-NN search", n, length(qs), cap)
  nn <- matrix(0L, n, k)
  for (q in qs) {
    r <- RANN::nn2(xy, xy[q, , drop = FALSE], k = k + 1L, searchtype = "standard", eps = 0)$nn.idx
    is_self <- r == q; is_self[rowSums(is_self) == 0L, k + 1L] <- TRUE                 # the pixel itself leaves its own list
    nn[q, ] <- matrix(t(r)[!t(is_self)], ncol = k, byrow = TRUE)
  }
  nn
}
moran_knn <- function(v, nn, k) {
  # v20.58: Moran's I and the local Moran's I from row-standardised k-NN weights -- EXACTLY spdep's moran.test (randomisation) and
  # localmoran (conditional, mlvar) formulas, computed from the n x k index matrix (no neighbour lists: a few numbers per pixel).
  # Proven equal to spdep to 1e-10 by tests/run_all_tests.R. p-values two-sided.
  n <- length(v); z <- v - mean(v); lag <- numeric(n)
  cap <- unit_cap(8 * 4 * k + 64); rb <- if (n <= cap) list(seq_len(n)) else split(seq_len(n), ceiling(seq_len(n) / cap))
  mutual <- 0
  for (i in rb) { J <- nn[i, , drop = FALSE]; lag[i] <- rowMeans(matrix(z[J], nrow = length(i)))
    for (m in seq_len(k)) mutual <- mutual + sum(rowSums(nn[J[, m], , drop = FALSE] == i) > 0L) }   # directed edges whose reverse exists
  S0 <- n; S1 <- (n * k + mutual) / k^2; S2 <- sum((1 + tabulate(nn, nbins = n) / k)^2)
  m2 <- sum(z^2) / n; I <- sum(z * lag) / sum(z^2); K <- n * sum(z^4) / sum(z^2)^2; EI <- -1 / (n - 1)
  VI <- n * (S1 * (n^2 - 3 * n + 3) - n * S2 + 3 * S0^2) - K * (S1 * (n^2 - n) - 2 * n * S2 + 6 * S0^2)
  VI <- VI / ((n - 1) * (n - 2) * (n - 3) * S0^2) - EI^2; Z <- (I - EI) / sqrt(VI)
  Ii <- z * lag / m2; E.Ii <- -(z^2) / ((n - 1) * m2); V.Ii <- (z / m2)^2 * (n / (n - 2)) * (1 / k - 1 / (n - 1)) * (m2 - z^2 / (n - 1))
  Z.Ii <- (Ii - E.Ii) / sqrt(V.Ii)
  list(I = I, EI = EI, VI = VI, Z = Z, p = 2 * pnorm(-abs(Z)), local = cbind(Ii = Ii, E.Ii = E.Ii, Var.Ii = V.Ii, Z.Ii = Z.Ii, p = 2 * pnorm(-abs(Z.Ii))), z = z, lag = lag)
}
m17_18_spatial <- function(dt, outcome, k = 8, n_max = N_MAX_SPATIAL) {
  # v20.58: ONE point per pixel of the estimation sample (the location rule, your rings, years and seasons) -- its change post minus pre --
  # k-NN weights on metres; Moran's I with its SE (randomisation) and a TWO-sided p. spdep computes it while its neighbour lists fit below
  # 98 % of the RAM; beyond that the same formulas run on the index matrix (exact, in batches) -- v20.57 sampled pixels there.
  if (!all(c("latitude", "longitude") %in% names(dt))) stop("package input lacks latitude/longitude -- export with C.export_for_packages(covariates=[..., 'latitude', 'longitude'])")
  ld <- dt[, .(dY = mean(get(outcome)[post == 1]) - mean(get(outcome)[post == 0]), treat = max(treat), lat = latitude[1], lon = longitude[1]), by = pixel_id][is.finite(dY)]
  n <- nrow(ld); nn <- knn_index(knn_xy(ld$lat, ld$lon), k)
  use_spdep <- n <= unit_cap(2 * (400 + 16 * k), n_max) && requireNamespace("spdep", quietly = TRUE)
  if (use_spdep) {
    lw <- spdep::nb2listw(spdep::knn2nb(structure(list(nn = nn, np = n, k = k, dimension = 2L, x = knn_xy(ld$lat, ld$lon)), class = "knn")), style = "W")
    mi <- spdep::moran.test(ld$dY, lw, alternative = "two.sided"); loc <- spdep::localmoran(ld$dY, lw)
    I <- unname(mi$estimate[1]); EI <- unname(mi$estimate[2]); VI <- unname(mi$estimate[3]); p <- mi$p.value; L <- unclass(loc)[, 1:5]
    z <- ld$dY - mean(ld$dY); lagz <- as.numeric(spdep::lag.listw(lw, z)); eng <- "spdep::moran.test / localmoran (k-NN weights from an exact kd-tree)"
  } else {
    mo <- moran_knn(ld$dY, nn, k); I <- mo$I; EI <- mo$EI; VI <- mo$VI; p <- mo$p; L <- mo$local; z <- mo$z; lagz <- mo$lag
    eng <- "spdep's moran.test / localmoran formulas on the k-NN index (exact; spdep's neighbour lists would pass 98 % of the RAM)"
    info(sprintf("M17/M18: %s pixels -- %s", format(n, big.mark = ","), eng))
  }
  g <- data.frame(outcome = outcome, moran_I = I, expectation = EI, variance = VI, se_moran = sqrt(VI), z = (I - EI) / sqrt(VI), p_value = p, alternative = "two.sided",
                  k = k, n = n, engine = eng)
  wr("global_moran", attr(dt, "scenario"), paste0("global_moran_", outcome), g)
  q <- ifelse(z > 0 & lagz > 0, "High-High (hot spot)", ifelse(z <= 0 & lagz <= 0, "Low-Low (cold spot)", ifelse(z > 0, "High-Low (spatial outlier)", "Low-High (spatial outlier)")))
  lisa <- data.table(pixel_id = ld$pixel_id, local_I = L[, 1], expectation = L[, 2], variance = L[, 3], z = L[, 4], p_value = L[, 5], treat = ld$treat,
                     quadrant = ifelse(L[, 5] < 0.05, q, "Not significant (p >= 0.05)"))
  wr("lisa", attr(dt, "scenario"), paste0("lisa_", outcome), lisa); list(global = g, lisa = lisa)                   # v20.43: M18 needs the LISA table
}

# ---------------------------------------------------------------- M19 ICC, M20 heterogeneity Q / I2
m19_icc <- function(dt, outcome) {
  need("lme4"); px <- unique(dt$pixel_id)
  grp <- if (uniqueN(dt$site_id[dt$site_id > 0]) >= 2) "site_id" else "Year"        # v20.49: among sub-watersheds (else years)
  bs <- batch_split(px, unit_cap(300 * max(1, nrow(dt) / max(1, length(px))), N_MAX_PIXELS_MIXED))   # v20.58: batches beyond 98 % of the RAM (was a sample)
  if (length(bs) > 1L) say_batches("M19 lmer", length(px), length(bs), max(lengths(bs)))
  vcs <- rbindlist(lapply(bs, function(u) { d <- if (length(bs) == 1L) dt else dt[pixel_id %in% u]
    m <- lme4::lmer(as.formula(paste0(outcome, " ~ did + (1 | ", grp, ") + (1 | pixel_id)")), data = d)
    as.data.table(as.data.frame(lme4::VarCorr(m)))[, .(group = grp, variance = vcov, rows = nrow(d))] }))
  vc <- vcs[, .(variance = sum(variance * rows) / sum(rows)), by = group]; tot <- sum(vc$variance)   # the components averaged over the batches
  ic <- data.table(group = vc$group, variance = vc$variance, share = vc$variance / tot, batches = length(bs))   # (performance::icc gave NA when one is 0)
  wr("icc", attr(dt, "scenario"), paste0("icc_", outcome), ic)
  list(result = data.frame(ICC = ic[group == grp, share], grouping = grp, engine = sprintf("lme4::lmer (REML variance components%s)", if (length(bs) > 1L) sprintf(", averaged over %d batches of pixels", length(bs)) else ""),
                           se_note = sprintf("the share of the outcome's variance between %s (lme4 variance components): descriptive, it has no sampling SE", if (grp == "site_id") "sub-watersheds" else "years")), table = ic)
}
m20_heterogeneity <- function(dt, outcome) {
  # v20.58 -- the SAME in R and Python (Python's M20 notebook): the headline is the TEST (Cochran's Q against chi-square with k - 1 df, the
  # question the model asks); beside it the random-effects pooled effect (DerSimonian-Laird), its SE, Higgins' I2 = (Q - df) / Q and tau2.
  # Each sub-watershed's DiD (unit + period effects) carries its DESIGN-BASED SE -- within one sub-watershed the years are the draws (a
  # year's shock is shared by all its pixels); v20.57 clustered on the years here (a handful of clusters) while Python clustered on the
  # pixels (every pixel-year a draw), so their Q differed; REML (R) and the fixed-effect mean (Python) differed too.
  need("metafor")
  if (uniqueN(dt$site_id[dt$site_id > 0]) < 2) stop("heterogeneity across sub-watersheds needs >= 2 sub-watersheds in the panel (the pooled run)")
  per <- dt[site_id > 0, { why <- ""; f <- tryCatch(feols(as.formula(paste0(outcome, " ~ did | unit + period")), data = .SD), error = function(e) { why <<- conditionMessage(e); NULL })
               b <- if (is.null(f)) NA_real_ else unname(coef(f)["did"]); ds <- if (is.finite(b)) tryCatch(design_se(copy(.SD)[, site_id := .BY$site_id], outcome, b), error = function(e) { why <<- conditionMessage(e); NULL }) else NULL
               s_ <- if (is.null(ds)) NA_real_ else ds$se_design %||% NA_real_
               if (!nzchar(why) && !is.finite(s_)) why <- if (is.null(ds)) "no DiD" else (ds$se_design_unit %||% "no design-based SE")
               .(beta = b, se = s_, why = why) }, by = site_id]
  bad_ <- per[!(is.finite(beta) & is.finite(se) & se > 0)]
  if (nrow(bad_)) info("M20: sub-watersheds without a usable DiD: ", paste(sprintf("%s (%s)", bad_$site_id, substr(bad_$why, 1, 80)), collapse = "; "))   # v20.58: said
  per <- per[is.finite(beta) & is.finite(se) & se > 0, .(site_id, beta, se)]
  if (nrow(per) < 2) stop("fewer than 2 sub-watersheds have an estimable DiD with a design-based SE")
  r <- metafor::rma(yi = per$beta, sei = per$se, method = "DL"); k <- nrow(per); Q <- r$QE
  out <- data.frame(outcome = outcome, estimate = Q, p_value = r$QEp, Q_df = k - 1L, pooled_effect = r$b[1], pooled_se = r$se,
                    I2 = if (Q > 0) max(0, (Q - (k - 1)) / Q) * 100 else 0, tau2 = r$tau2, n_sub_watersheds = k,
                    se_how = "each sub-watershed's DiD with its design-based SE (years as the draws); Q with inverse-variance weights",
                    engine = "metafor::rma (DerSimonian-Laird)")
  wr("heterogeneity", attr(dt, "scenario"), paste0("heterogeneity_Q_I2_", outcome), out)
  list(result = out, table = cbind(per, outcome = outcome), se_how = out$se_how, p_how = sprintf("chi-square with %d df", k - 1L))
}

# ---------------------------------------------------------------- M22 Goodman-Bacon
m22_bacon <- function(dt, outcome) {
  # v20.49: on sub-watershed x ring units. bacondecomp fits every 2x2 with DENSE unit dummies: on pixel units (3,840 in the
  # test, ~2 million in your panel) that is a 38,400 x 3,850 matrix per fit -- the test process was killed for memory.
  # The decomposition depends on the timing groups, which the sub-watershed x ring means keep (as M11 / M36-M38 do).
  need("bacondecomp")
  # v20.58: series of ONE season (sub-watershed x ring x season x cohort), net of the rings' mean in the same season and year (the year x season
  # effect the design absorbs -- bacon's own two-way FE has one effect per YEAR only, so the seasons' shocks would enter the 2 x 2s)
  uy <- dt[, .(y = mean(get(outcome)), D = as.integer(max(did) == 1L)), by = .(unit = paste(site_id, buff_km, Season, cohort, sep = "_"), site_id, Season, Year, ctl = treat == 0L)]
  uy[, y := y - mean(y[ctl]), by = .(site_id, Season, Year)]; uy <- uy[is.finite(y), .(unit, site_id, Year, y, D)]
  n_all <- uniqueN(uy$unit); uy <- uy[unit %in% uy[, .N, by = unit][N == uniqueN(uy$Year), unit]]   # the balanced panel bacon() requires
  if (uniqueN(uy$unit) < n_all) info(sprintf("M22: %d series left out of the decomposition: not present in every year (it needs the balanced panel)", n_all - uniqueN(uy$unit)))
  b <- bacondecomp::bacon(y ~ D, data = as.data.frame(uy[, .(unit, Year, y, D)]), id_var = "unit", time_var = "Year", quietly = TRUE)
  out <- as.data.table(b); out[, engine := "bacondecomp"]; wr("bacon", attr(dt, "scenario"), paste0("bacon_decomposition_", outcome), out)
  print(out[, .(weight = sum(weight), estimate = weighted.mean(estimate, weight)), by = type])
  # v20.58: the decomposition adds up to THIS two-way FE -- its SE clustered as every model (by sub-watershed with >= MIN_SWS_CLUSTERS of them,
  # else by year; v20.58's first version always by year) -- the same numbers as Python's bacon_twfe_inference
  by_site <- uniqueN(uy$site_id[uy$site_id > 0]) >= MIN_SWS_CLUSTERS
  f <- feols(y ~ D | unit + Year, data = as.data.frame(uy), cluster = if (by_site) ~site_id else ~Year)
  G <- if (by_site) uniqueN(uy$site_id) else uniqueN(uy$Year)
  list(result = data.frame(estimate = sum(out$weight * out$estimate) / sum(out$weight), se = unname(se(f)["D"]), p_value = unname(pvalue(f)["D"]),
                           se_how = sprintf("the two-way FE the decomposition adds up to (%d series x %d years), cluster-robust (CR1) by %s (%d clusters); p: t with %d df",
                                            uniqueN(uy$unit), uniqueN(uy$Year), if (by_site) "sub-watershed" else "year", G, G - 1L)), table = out)
}

# ---------------------------------------------------------------- M24 spillover gradient, M26 covariate interaction, M29 exposure
m24_spillover <- function(dt, outcome) {
  d <- copy(dt); far <- max(d$buff_km); d[, ring := as.factor(buff_km)]                  # v20.43: the farthest ring PRESENT is the reference
  fit <- feols(as.formula(paste0(outcome, " ~ i(ring, post, ref = ", far, ") | unit + period")), data = d, cluster = ~cluster_id)
  ct <- as.data.table(coeftable(fit), keep.rownames = "term"); out <- ct[, .(term, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "fixest")]
  wr("spillover", attr(dt, "scenario"), paste0("spillover_gradient_", outcome), out)
  # v20.58 (as Python): the headline is the SPILLOVER -- the nearest control ring against the farthest one (truth 0 without spillover); the
  # core's own row (its effect against the farthest ring) stays in the table
  near <- min(d$buff_km[d$buff_km > 0]); hr <- out[term == sprintf("ring::%d:post", near)]
  list(result = data.frame(estimate = if (nrow(hr)) hr$beta else NA_real_, se = if (nrow(hr)) hr$se else NA_real_, p_value = if (nrow(hr)) hr$p_value else NA_real_,
                           ring = near, reference_ring = far, se_how = sprintf("ring %d against ring %d, clustered by %s", near, far, if (uniqueN(d$site_id[d$site_id > 0]) >= MIN_SWS_CLUSTERS) "sub-watershed" else "year")), table = out)
}
m26_interaction <- function(dt, outcome, covariate = "Rain") {
  if (!covariate %in% names(dt)) stop("no ", covariate, " column")
  mu <- mean(dt[[covariate]], na.rm = TRUE); dt <- copy(dt); set(dt, j = covariate, value = dt[[covariate]] - mu)   # v20.49: centred
  fit <- feols(as.formula(paste0(outcome, " ~ did + did:", covariate, " + ", covariate, " | unit + period")), data = dt, cluster = ~cluster_id)
  ct <- as.data.table(coeftable(fit), keep.rownames = "term"); out <- ct[, .(term, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "fixest")]
  wr("treatment_x_covariate", attr(dt, "scenario"), paste0("treatment_x_", covariate, "_", outcome), out)
  # v20.58 (as Python's M26): the headline = the effect at the covariate's mean (the did row); beside it the change of the effect per unit of
  # the covariate (did x covariate) with its SE and p
  h <- out[term == "did"]; ix <- out[term %in% c(paste0("did:", covariate), paste0(covariate, ":did"))]
  list(result = data.frame(estimate = h$beta, se = h$se, p_value = h$p_value, beta_interaction = if (nrow(ix)) ix$beta[1] else NA_real_,
                           se_interaction = if (nrow(ix)) ix$se[1] else NA_real_, p_interaction = if (nrow(ix)) ix$p_value[1] else NA_real_,
                           covariate = covariate, covariate_mean = mu), table = out)
}
m29_exposure <- function(dt, outcome) {
  d <- copy(dt); d[, exposure := ifelse(treat == 1 & post == 1, pmax(event_time, 0) + 1, 0)]; d[, exposure := as.factor(exposure)]
  fit <- feols(as.formula(paste0(outcome, " ~ i(exposure, ref = 0) | unit + period")), data = d, cluster = ~cluster_id)
  ct <- as.data.table(coeftable(fit), keep.rownames = "term"); out <- ct[, .(term, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "fixest")]
  wr("exposure", attr(dt, "scenario"), paste0("exposure_duration_", outcome), out)
  ex <- grep("^exposure::", names(coef(fit)), value = TRUE); w <- rep(1 / length(ex), length(ex))   # v20.49: headline + its SE
  list(result = data.frame(estimate = sum(w * coef(fit)[ex]), se = sqrt(drop(t(w) %*% vcov(fit)[ex, ex] %*% w)), n_exposure_years = length(ex)), table = out)
}

# ---------------------------------------------------------------- M25 randomisation inference
m25_ritest <- function(dt, outcome, reps = 999, batch = NULL) {
  # v20.49: randomisation inference AS THE PYTHON ENGINE DOES IT -- the treated status permuted across the units (pixel x
  # season series; the number of treated units kept), the DiD refitted with the same fixed effects (Frisch-Waugh: y and
  # each permuted did demeaned once per batch); p = (1 + #|beta_perm| >= |beta|) / (1 + reps). v20.47 called ritest,
  # which cannot permute an interaction, looked its data up by name ("Could not find cluster_id"), and in its stacked
  # mode ran this test's process out of memory (killed); its cluster permutation also mixed pre- and post-period rows.
  # v20.58 (second pass): the units in (pixel, season) order and the draws from R's default generator set explicitly (with_mt_seed:
  # Mersenne-Twister, set.seed(12345), the session's generator restored after) -- the Python engine draws the SAME permutations
  # (_common._permutation_inference_impl), so both give the same permuted estimates, SD and p (the order of first appearance in the
  # data and the session's generator kind could differ between the pipelines and runs)
  oc <- intersect(c("pixel_id", "Season"), names(dt))
  un <- if (length(oc)) unique(dt[do.call(order, unname(as.list(dt[, oc, with = FALSE]))), unit]) else unique(dt$unit)
  tu <- unique(dt[treat == 1L, unit]); n1 <- length(tu)
  if (n1 == 0L || n1 == length(un)) stop("randomisation inference needs treated AND control units")
  need("fixest"); fe <- dt[, .(unit, period)]; dm <- function(M) fixest::demean(M, f = fe)   # v20.49: works in the bridge too
  yd <- drop(dm(dt[[outcome]])); dd <- drop(dm(as.numeric(dt$did))); b0 <- sum(dd * yd) / sum(dd * dd)
  ui <- match(dt$unit, un); post <- as.numeric(dt$post)
  # v20.58 YOUR RULE: every permutation at once when they fit below 98 % of the RAM; else the largest batch that fits -- v20.57 always ran
  # batches of 50. SIX n-vectors per permutation (the permuted column, its demeaned copy, fixest's working copy, the two products before R's
  # garbage collector frees them; 2 of margin) -- 3 were counted while the peak is ~5 (as the Python engine, whose chain run was killed for memory)
  if (is.null(batch)) batch <- as.integer(max(1, min(reps, unit_cap(8 * 6 * nrow(dt)))))
  if (batch < reps) info(sprintf("M25: %d permutations in batches of %d (all at once would pass 98 %% of the RAM)", reps, batch))
  bs <- with_mt_seed({
    bs <- numeric(0)
    for (s0 in seq(1L, reps, by = batch)) {
      k <- min(batch, reps - s0 + 1L)
      M <- vapply(seq_len(k), function(i) { t <- numeric(length(un)); t[sample.int(length(un), n1)] <- 1; t[ui] * post }, numeric(nrow(dt)))
      Md <- dm(M); rm(M); bs <- c(bs, colSums(Md * yd) / colSums(Md * Md)); rm(Md)
    }
    bs
  })
  p <- (1 + sum(abs(bs) >= abs(b0))) / (1 + reps)
  out <- data.frame(outcome = outcome, beta = b0, se = sd(bs), p_ri = p, reps = reps, permuted = "treated status across pixel x season series (as the Python engine)",
                    se_how = sprintf("the standard deviation of the %d permuted estimates (randomisation inference)", reps),
                    engine = "Fisher randomisation inference (fixest demeaning)")
  wr("permutation", attr(dt, "scenario"), paste0("permutation_", outcome), out); out
}

# ---------------------------------------------------------------- M27 BJS imputation, M28 Gardner did2s, M30 cohorts, M31 stacked, M32 ETWFE
m27_imputation <- function(dt, outcome) {
  # v20.58: the design's COVARIATES in the first stage (the untreated unit + year model), as Python's diff-diff ImputationDiD (v20.57 R had none:
  # 0.0507664 against Python's 0.0507714 on the poison test)
  need("didimputation"); cv <- covs_in(dt); uy <- unit_year(dt, outcome, cv); cv <- cv[vapply(cv, function(c_) is.finite(stats::var(uy[[c_]])) && stats::var(uy[[c_]]) > 0, TRUE)]
  uy[, unit := as.integer(factor(unit))]      # v20.57: didimputation indexes its sparse design BY the id value -- pixel x season ids of
                                              #   ~1e6 or more gave an almost empty matrix and "LU factorization failed" (the route never
                                              #   verified, in v20.56 too); consecutive ids 1..N fix it (the estimate is unchanged)
  cl <- site_cluster(dt)                      # v20.49: year clusters made the variance singular ("LU factorization failed")
  args <- list(data = as.data.frame(uy), yname = "y", gname = "gvar", tname = "Year", idname = "unit")
  if (length(cv)) args$first_stage <- as.formula(paste("~", paste(cv, collapse = " + "), "| unit + Year"))
  if (!is.null(cl)) args$cluster_var <- "site_id"
  r <- do.call(didimputation::did_imputation, args)
  out <- as.data.table(r); out[, engine := "didimputation"]; wr("bjs_imputation", attr(dt, "scenario"), paste0("bjs_imputation_", outcome), out); out
}
m28_did2s <- function(dt, outcome) {
  need("did2s"); d <- copy(dt); d[, treatment_dyn := as.integer(did == 1)]
  d[!is.finite(event_time), event_time := -1000]         # v20.43: never-treated units need a code, or fixest drops them
  fit <- did2s::did2s(data = as.data.frame(d), yname = outcome, first_stage = ~ 0 | unit + period, second_stage = ~ i(event_time, ref = c(-1, -1000)),
                      treatment = "treatment_dyn", cluster_var = "cluster_id")
  ct <- as.data.table(coeftable(fit), keep.rownames = "term"); ct[, event_time := term_event_time(term)]
  out <- ct[, .(event_time, beta = Estimate, se = `Std. Error`, p_value = `Pr(>|t|)`, engine = "did2s")]; wr("gardner_did2s", attr(dt, "scenario"), paste0("gardner_did2s_", outcome), out)
  h <- event_headline(fit, ct[is.finite(event_time) & event_time >= 0, term], dt, outcome)          # v20.58: the headline and ITS SE
  list(result = data.frame(estimate = h$estimate, se = h$se, p_value = h$p_value, se_how = h$se_how), se_how = h$se_how, p_how = h$p_how, table = out)
}
m30_cohorts <- function(dt, outcome) {
  # v20.58: Callaway-Sant'Anna's GROUP aggregation -- each cohort's effect, and their average weighted by cohort size -- on M05's design
  # (the series, the season-matched outcome, never-treated comparisons, no covariates) and M05's SE rule (analytical influence function;
  # the multiplier bootstrap clustered by sub-watershed with >= MIN_SWS_CLUSTERS of them). v20.57 added the four weather covariates here
  # only (not in M05) and Python's engine estimated another estimand (a two-stage imputation per cohort): 0.0522 against 0.0507
  need("did"); uy <- unit_year(dt, outcome, character(0))
  uy[, id := num_id(unit)]                                                           # v20.49: did needs a numeric id
  cl <- site_cluster(dt)
  res <- seeded(did::att_gt(yname = "y", tname = "Year", idname = "id", gname = "gvar", data = as.data.frame(uy), control_group = "nevertreated",
                     clustervars = cl, bstrap = !is.null(cl), biters = 999, cband = FALSE, allow_unbalanced_panel = TRUE, pl = TRUE, cores = N_THREADS))
  g <- seeded(did::aggte(res, type = "group")); out <- data.table(cohort = g$egt, att = g$att.egt, se = g$se.egt, engine = "did::aggte(group)")
  wr("cohort_heterogeneity", attr(dt, "scenario"), paste0("cohort_att_", outcome), out)
  list(result = data.frame(estimate = g$overall.att, se = g$overall.se,
                           se_how = if (is.null(cl)) "did::aggte(type = 'group'): the cohort effects averaged; the analytical influence-function SE (each series a draw)"
                                    else sprintf("did::aggte(type = 'group'): the cohort effects averaged; the multiplier bootstrap (999) clustered by sub-watershed (%d)", uniqueN(uy$site_id))),
       table = out)
}
m31_stacked <- function(dt, outcome, window = c(-3, 3)) {
  uy <- unit_year(dt, outcome, character(0)); cohorts <- sort(unique(uy[gvar > 0, gvar])); stacks <- list()
  for (g in cohorts) {                                     # clean controls: never treated or treated after the window
    sub <- uy[gvar == g | gvar == 0 | gvar > g + window[2]]; sub <- sub[Year >= g + window[1] & Year <= g + window[2]]
    sub[, `:=`(stack = g, D = as.integer(gvar == g & Year >= g), rel = Year - g)]; stacks[[as.character(g)]] <- sub
  }
  st <- rbindlist(stacks); fit <- feols(y ~ D | unit^stack + Year^stack, data = st, cluster = ~cluster_id)
  out <- data.frame(outcome = outcome, att = coef(fit)["D"], se = se(fit)["D"], n_stacks = length(cohorts), engine = "stacked DiD (fixest)"); wr("stacked_did", attr(dt, "scenario"), paste0("stacked_did_", outcome), out); out
}
m32_etwfe <- function(dt, outcome) {
  need("etwfe"); uy <- unit_year(dt, outcome, character(0))
  m <- etwfe::etwfe(fml = y ~ 0, tvar = Year, gvar = gvar, data = as.data.frame(uy), vcov = ~cluster_id)
  e <- etwfe::emfx(m, type = "event"); out <- as.data.table(e); out[, engine := "etwfe"]; wr("etwfe", attr(dt, "scenario"), paste0("etwfe_", outcome), out)
  s1 <- as.data.frame(etwfe::emfx(m, type = "simple"))                                # v20.49: the headline ATT and its SE
  # v20.58: etwfe / marginaleffects give a NORMAL p-value (your v20.57 log: "p < 1e-300" on 6 year clusters) -- the p is taken from t with
  # G - 1 df on the same clustered SE, as every other model of the design; etwfe's own p stays in the table
  G <- uniqueN(uy$cluster_id); dfp <- max(1L, G - 1L); est <- s1$estimate[1]; se_ <- s1$std.error[1]
  list(result = data.frame(estimate = est, se = se_, p_value = 2 * pt(abs(est / se_), dfp, lower.tail = FALSE), p_value_etwfe_normal = s1$p.value[1],
                           se_how = sprintf("etwfe::emfx: the delta method on the covariance clustered by %s (%d clusters)", cluster_col_for(dt), G)),
       se_how = sprintf("etwfe::emfx: the delta method on the covariance clustered by %s (%d clusters)", cluster_col_for(dt), G),
       p_how = sprintf("t with %d df (etwfe's own p-value, %s, uses the normal distribution: too small with %d clusters)", dfp, format(signif(s1$p.value[1], 3)), G), table = out)
}

# ---------------------------------------------------------------- M35 quantile DiD
rq_cluster_se <- function(f, cl) {
  # v20.58: the cluster-robust covariance of a quantile regression (Parente & Santos Silva 2016, J. Econometric Methods 5(1)):
  # V = A^-1 B A^-1 * G / (G - 1), A = sum_i f_i x_i x_i' (the Gaussian-kernel density of the residuals at 0 with quantreg's Hall-Sheather
  # bandwidth -- exactly its summary(se = "ker")), B = sum_g s_g s_g', s_g = sum_(i in g) (tau - 1[r_i < 0]) x_i. One row per cluster gives
  # quantreg's own "ker" SE (up to G / (G - 1)).
  X <- if (!is.null(f$model)) model.matrix(terms(f), f$model) else model.matrix(f); r <- as.numeric(residuals(f)); tau <- f$tau; n <- length(r)   # the stored model frame
  h <- quantreg::bandwidth.rq(tau, n, hs = TRUE); while ((tau - h < 0) || (tau + h > 1)) h <- h / 2
  h <- (qnorm(tau + h) - qnorm(tau - h)) * min(sqrt(var(r)), (quantile(r, 0.75) - quantile(r, 0.25)) / 1.34)
  A <- crossprod(X * sqrt(dnorm(r / h) / h)); S <- rowsum(X * (tau - as.numeric(r < 0)), as.character(cl)); G <- nrow(S)
  if (G < 2) stop("one cluster: no cluster-robust SE")
  Ai <- solve(A); setNames(sqrt(pmax(diag(Ai %*% crossprod(S) %*% Ai) * G / (G - 1), 0)), colnames(X))
}
m35_batches <- function(dd, outcome, taus, bs, dt) {
  # divide and conquer (Volgushev, Chao & Cheng 2019): each batch of pixels fitted on all its rows, the batch coefficients averaged (weights =
  # rows); the batches share the year shocks, so the SE is the mean of the batch SEs (the upper bound for correlated batches: conservative)
  G <- uniqueN(dd$cluster_id); rows <- list()
  for (tau in taus) {
    r <- rbindlist(lapply(bs, function(u) { d <- dd[pixel_id %in% u]; f <- quantreg::rq(y_w ~ did + period, data = d, tau = tau, method = "fn")
      data.table(b = unname(coef(f)["did"]), se = tryCatch(unname(rq_cluster_se(f, d$cluster_id)["did"]), error = function(e) NA_real_), n = nrow(d)) }))
    b_ <- sum(r$b * r$n) / sum(r$n); se_ <- mean(r$se)
    rows[[length(rows) + 1]] <- data.frame(outcome = outcome, tau = tau, beta = b_, se = se_, p_value = 2 * pt(abs(b_ / se_), max(1L, G - 1L), lower.tail = FALSE),
                                           batches = length(bs), clusters = G, cluster_by = cluster_col_for(dt),
                                           engine = sprintf("quantreg::rq on %d batches of pixels (coefficients averaged; SE: the mean batch cluster-robust SE, conservative)", length(bs)))
  }
  out <- rbindlist(rows); wr("quantile_did", attr(dt, "scenario"), paste0("quantile_did_", outcome), out); out
}
m35_qdid <- function(dt, outcome, taus = c(0.1, 0.25, 0.5, 0.75, 0.9)) {
  need("quantreg"); rows <- list(); px <- unique(dt$pixel_id)
  dd <- copy(dt); dd[, y_pre := mean(get(outcome)[post == 0L]), by = unit]  # v20.49: minus the series' PRE-period level
  dd <- dd[is.finite(y_pre)]; dd[, y_w := get(outcome) - y_pre]           # (the whole-period mean absorbed part of the effect)
  cap_q <- unit_cap(8 * 6 * (2 + uniqueN(dt$period)) * max(1, nrow(dt) / max(1, length(px))), N_MAX_PIXELS_MIXED)   # rq's dense design
  bs <- batch_split(px, cap_q)                                            # v20.58: batches beyond 98 % of the RAM (was a sample)
  if (length(bs) > 1L) { say_batches("M35 quantile regression", length(px), length(bs), max(lengths(bs)))
    return(m35_batches(dd, outcome, taus, bs, dt)) }
  d <- dd
  for (tau in taus) {
    f <- quantreg::rq(y_w ~ did + period, data = d, tau = tau, method = "fn")
    sm <- tryCatch(summary(f, se = "nid")$coefficients, error = function(e) NULL)
    # v20.58: the SE of each quantile effect CLUSTERED as the design is (Parente & Santos Silva 2016: the kernel sandwich of quantreg's "ker" SE
    # with the per-cluster score sums in the middle). The v20.57 "nid" SE took every row as independent -- rows of one year share its shock --
    # and was printed as "clustered by Year": "p < 1e-300" in your log. nid stays in the table beside it.
    b_ <- unname(coef(f)["did"]); G <- uniqueN(d$cluster_id)
    # v20.58: with the YEARS as the clusters (fewer than MIN_SWS_CLUSTERS sub-watersheds) the did term is 0 in every pre year, so only the
    # post years' score sums enter the sandwich -- and the did condition forces them to cancel: 3.3e-05 for a design SE of 0.0012 on the
    # poison panel. Not a valid SE: left out here, and the headline takes the design-based SE (years as the draws), said as such.
    yr_ <- identical(cluster_col_for(dt), "Year")
    se_c <- if (yr_) NA_real_ else tryCatch(unname(rq_cluster_se(f, d$cluster_id)["did"]), error = function(e) { info("M35 tau ", tau, ": the cluster-robust SE failed -- ", conditionMessage(e)); NA_real_ })
    rows[[length(rows) + 1]] <- data.frame(outcome = outcome, tau = tau, beta = b_, se = se_c, p_value = if (is.finite(se_c)) 2 * pt(abs(b_ / se_c), max(1L, G - 1L), lower.tail = FALSE) else NA_real_,
                                           se_note = if (yr_) "the years are the clusters: the quantile regression's cluster-robust SE rests on the post years only (the did scores of the pre years are 0) -- not valid; the design-based SE is used" else "",
                                           se_nid_unclustered = if (!is.null(sm) && "did" %in% rownames(sm)) sm["did", 2] else NA_real_,
                                           clusters = G, cluster_by = cluster_col_for(dt), engine = "quantreg::rq (within-transformed; SE: cluster-robust kernel sandwich)")
  }
  out <- rbindlist(rows); wr("quantile_did", attr(dt, "scenario"), paste0("quantile_did_", outcome), out); out
}

# ---------------------------------------------------------------- M36 / M37 / M38 factor models: fect, gsynth
m36_38_factor <- function(dt, outcome, method = c("ife", "mc", "gsynth")) {
  # v20.58: one fit per cohort x season on series of ONE season (season_series above); the number of factors (lambda for "mc") is chosen by
  # cross-validation on the treated series' pre periods -- fect / gsynth need min.T0 + cv.nobs of them (5 + 3 by default): with your
  # PRE_YEARS <- 4 every v20.57 run was a data gap ("no eligible units have enough observations"). The CV is now fitted to the pre periods
  # there are and run ONCE (fect re-ran it inside every bootstrap draw with its defaults); with fewer than 3 pre years r = 0 (said).
  a <- season_series(dt, outcome)
  fit_one <- function(sub, g) {
    s <- copy(sub); s[, D := as.integer(treat == 1L & Year >= g)]
    # v20.58: fect's series as INTEGER ids -- the core series first, then the ring series, each by (sub-watershed, ring). The character ids
    # sorted by the locale's collation (fect orders its units), so the series order -- which fect's cross-validation samples from -- could
    # differ between machines; and fect's bootstrap draws the treated series with sample(tr, Ntr, TRUE), which for ONE treated series that
    # is not the first unit samples from 1:tr (any series). The Python engine (_common.fect_ring_series) takes the same order.
    uo <- unique(s[order(-treat, site_id, buff_km), unit]); s[, uid := match(unit, uo)]
    n_pre <- uniqueN(s[Year < g, Year]); cv_nobs <- min(3L, max(1L, n_pre - 2L)); min_t0 <- max(1L, min(5L, n_pre - cv_nobs)); do_cv <- n_pre >= 3L
    rmax <- min(4L, max(0L, n_pre - 2L), max(0L, uniqueN(s[treat == 0L, unit]) - 1L)); if (rmax == 0L) do_cv <- FALSE
    if (method[1] == "gsynth") { need("gsynth")
      r0 <- if (do_cv) tryCatch(with_mt_seed(gsynth::gsynth(y ~ D, data = as.data.frame(s), index = c("uid", "Year"), force = "two-way", CV = TRUE, r = c(0, rmax), min.T0 = min_t0, se = FALSE))$r.cv,
                                error = function(e) { info(sprintf("gsynth cohort %s: the cross-validation failed (%s) -- r = 0 factors used", g, conditionMessage(e))); 0 })
            else { info(sprintf("gsynth cohort %s: %d pre-period years / %d control series -- no cross-validation possible, r = 0 factors", g, n_pre, uniqueN(s[treat == 0L, unit]))); 0 }
      r <- seeded(gsynth::gsynth(y ~ D, data = as.data.frame(s), index = c("uid", "Year"), force = "two-way", CV = FALSE, r = r0, min.T0 = min_t0, se = TRUE, nboots = 200,
                                 inference = "parametric", parallel = FALSE))    # one core: its parallel bootstrap is not reproducible, and this panel is tiny
      return(list(estimate = unname(r$est.avg[1]), se = unname(r$est.avg[2]), r = r0, tuning = r0))
    }
    need("fect")
    # v20.58: without a lambda fect fits its FE model (fect: "No lambda is supplied. FEct is applied") -- said as such (was "fect's default lambda")
    nocv_txt <- if (method[1] == "mc") "no lambda: fect fits its FE model (no factors)" else "r = 0 factors"
    cvfit <- if (do_cv) tryCatch(with_mt_seed(fect::fect(y ~ D, data = as.data.frame(s), index = c("uid", "Year"), method = method[1], force = "two-way", CV = TRUE, r = c(0, rmax),
                                            min.T0 = min_t0, cv.nobs = cv_nobs, se = FALSE)), error = function(e) { info(sprintf("fect %s cohort %s: the cross-validation failed (%s) -- %s", method[1], g, conditionMessage(e), nocv_txt)); NULL })
             else { info(sprintf("fect %s cohort %s: %d pre-period years / %d control series -- no cross-validation possible, %s", method[1], g, n_pre, uniqueN(s[treat == 0L, unit]), nocv_txt)); NULL }
    tune <- if (method[1] == "mc") list(lambda = cvfit$lambda.cv) else list(r = if (!is.null(cvfit$r.cv)) cvfit$r.cv else 0)
    r <- seeded(do.call(fect::fect, c(list(formula = y ~ D, data = as.data.frame(s), index = c("uid", "Year"), method = method[1], force = "two-way", CV = FALSE,
                                           min.T0 = min_t0, se = TRUE, nboots = 200, parallel = TRUE, cores = N_THREADS, seed = 12345), Filter(Negate(is.null), tune))))   # every core
    ea <- r$est.avg
    list(estimate = if (!is.null(ea)) unname(ea[1, 1]) else r$att.avg, se = if (!is.null(ea) && ncol(ea) >= 2) unname(ea[1, 2]) else NA_real_,
         tuning = if (method[1] == "mc") (tune$lambda %||% NA_real_) else (tune$r %||% 0))
  }
  e <- by_cohort_season(a, fit_one, method[1])
  eng <- if (method[1] == "gsynth") "gsynth" else "fect"
  # v20.58: the tuning the cross-validation chose, said -- with few control series it picks r = 0 factors (the largest lambda for matrix
  # completion): each fit IS then the two-way FE DiD of that cohort x season, and M36 / M37 / M38 give the same estimate (their SEs differ).
  # That is a property of these data (a few ring series per season), not a copy.
  tn <- e$table$tuning
  if (length(tn) && all(is.finite(tn)) && ((method[1] != "mc" && all(tn == 0)) || (method[1] == "mc" && length(unique(round(tn, 12))) == 1)))
    info(sprintf("%s: the cross-validation chose %s in all %d fit(s) -- with %s control series per fit the factor model reduces to the two-way FE DiD of each cohort x season, so M36 / M37 / M38 share this estimate (their SEs differ)",
                 method[1], if (method[1] == "mc") sprintf("lambda = %.3g", tn[1]) else "r = 0 factors", length(tn), paste(unique(e$table$n_control), collapse = "/")))
  out <- data.frame(outcome = outcome, att_avg = e$estimate, se = e$se, method = method[1], fits = nrow(e$table),
                    tuning = if (method[1] == "mc") paste("lambda", paste(signif(tn, 3), collapse = ",")) else paste("r", paste(tn, collapse = ",")),
                    se_how = e$se_how, engine = paste(eng, "(one fit per cohort x season)"))
  wr(if (method[1] == "gsynth") "gsynth" else paste0("fect_", method[1]), attr(dt, "scenario"), paste0(if (method[1] == "gsynth") "gsynth" else paste0("fect_", method[1]), "_", outcome), out)
  list(result = out, table = e$table)
}

# ---------------------------------------------------------------- M39-M44 machine learning on the long difference
long_difference <- function(dt, outcome, covs = c("Rain", "Tmax", "Tmean", "Tmin")) {
  # v20.58 -- as the Python pipeline (python_prebuilt/ml_spatial_pipeline.long_difference): one long difference per SERIES, the design's unit
  # (pixel x season under UNIT_FE "pixel_season", the pixel under "pixel"); a season series is taken net of its own season's control rings in
  # the same year (season_net), so its pre / post split meets its own season's shocks; a series needs >= 2 pre and >= 1 post observation.
  # v20.57 R took one long difference per PIXEL of the raw outcome (seasons mixed) -- not the unit the Python ML models and every other model use.
  cv <- covs[covs %in% names(dt)]; by_ <- if ("unit" %in% names(dt)) "unit" else "pixel_id"
  d <- copy(dt)
  if (by_ != "pixel_id" && "Season" %in% names(d) && uniqueN(d$Season) > 1L) { d[, y_ld := season_net(dt, outcome)]; d <- d[is.finite(y_ld)] } else d[, y_ld := get(outcome)]
  pre <- d[post == 0, c(list(y_pre = mean(y_ld), n_pre = .N, treat = max(treat), site_id = site_id[1]), lapply(.SD, mean)), .SDcols = cv, by = by_]   # v20.49: site, not the Year cluster
  post <- d[post == 1, .(y_post = mean(y_ld), n_post = .N), by = by_]
  ld <- merge(pre, post, by = by_); ld <- ld[n_pre >= 2L & n_post >= 1L]; ld[, dY := y_post - y_pre]
  bs <- batch_split(seq_len(nrow(ld)), unit_cap(2500, N_MAX_ML), ld$treat)                # v20.58: forests ~2.5 KB / unit; batches beyond 98 % (was a sample)
  if (length(bs) > 1L) say_batches("ML (long difference)", nrow(ld), length(bs), max(lengths(bs)))
  list(ld = ld, cv = cv, batches = bs, what = if (by_ == "unit") "pixel x season series" else "pixels")
}
ml_over_batches <- function(L, fit, clustered = FALSE) {
  # fit(ld_batch) -> list(est, se, w): one batch = the whole data when it fits. Batches: the estimates averaged (weights w: the treated pixels for
  # an ATT, all pixels for an ATE); SE from independent batches -- or, clustered on sub-watersheds (the batches share them), the mean batch SE
  if (length(L$batches) == 1L) return(c(fit(L$ld), list(batches = 1L)))
  rs <- lapply(L$batches, function(i) fit(L$ld[i])); w <- vapply(rs, `[[`, numeric(1), "w"); w <- w / sum(w)
  e <- vapply(rs, `[[`, numeric(1), "est"); se <- vapply(rs, function(r) r$se %||% NA_real_, numeric(1))
  list(est = sum(w * e), se = if (clustered) mean(se) else sqrt(sum(w^2 * se^2)), batches = length(rs), per_batch = rs)
}
m43_causal_forest <- function(dt, outcome, num_trees = 2000) {
  need("grf"); L <- long_difference(dt, outcome); ld <- L$ld
  clustered <- uniqueN(ld$site_id) >= MIN_SWS_CLUSTERS                                 # v20.49: one pixel row has one year -> cluster on sub-watersheds
  fit <- function(b) { X <- as.matrix(b[, L$cv, with = FALSE]); cl <- if (clustered) num_id(b$site_id) else NULL
    cf <- grf::causal_forest(X, b$dY, b$treat, clusters = cl, num.trees = num_trees, honesty = TRUE, seed = 1)
    att <- grf::average_treatment_effect(cf, target.sample = "treated"); list(est = att[[1]], se = att[[2]], w = sum(b$treat), cate = predict(cf)$predictions) }
  r <- ml_over_batches(L, fit, clustered)
  cate <- if (r$batches == 1L) r$cate else { cc <- numeric(nrow(ld)); for (j in seq_along(L$batches)) cc[L$batches[[j]]] <- r$per_batch[[j]]$cate; cc }
  out <- data.frame(outcome = outcome, target = "ATT", att = r$est, se = r$se, p_value = ml_p(r$est, r$se), cate_sd = sd(cate), batches = r$batches,
                    se_how = sprintf("grf::causal_forest (honest): the SE of its doubly robust ATT, %s%s", if (clustered) sprintf("clustered by sub-watershed (%d)", uniqueN(ld$site_id))
                                     else sprintf("each of the %s %s one draw (not clustered)", format(nrow(ld), big.mark = ","), L$what), if (r$batches > 1L) sprintf("; %d batches of pixels combined", r$batches) else ""),
                    p_how = ML_P_HOW,
                    engine = paste0(if (clustered) "grf::causal_forest (honest, clustered on sub-watersheds)" else "grf::causal_forest (honest)", if (r$batches > 1L) sprintf(", %d batches of pixels", r$batches) else ""))
  wr("causal_forest", attr(dt, "scenario"), paste0("causal_forest_", outcome), out)
  q <- rbindlist(lapply(L$cv, function(v) { qq <- cut(ld[[v]], unique(quantile(ld[[v]], 0:4 / 4)), include.lowest = TRUE, labels = FALSE); data.table(outcome = outcome, covariate = v, quartile = seq_along(tapply(cate, qq, mean)), cate_mean = as.numeric(tapply(cate, qq, mean))) }))
  wr("cate_by_covariate", attr(dt, "scenario"), paste0("cate_by_covariate_quartile_", outcome), q); list(result = out, cate_by_covariate = q)
}
m40_doubleml <- function(dt, outcome) {
  need("DoubleML"); need("mlr3"); need("mlr3learners"); need("ranger"); L <- long_difference(dt, outcome)
  # v20.58: the forests as the Python primary's (econml LinearDML: scikit-learn forests of 300 trees, leaves of >= 20 series, every covariate
  # tried at each split of the outcome forest, sqrt(p) for the propensity) -- with ranger's defaults (500 trees, nodes of 5) R's estimate sat
  # 1.5-1.8 SE above Python's on the parity panel; aligned, the two differ by the forests' randomness only. v20.58 (second pass): the Python
  # primary is the same PARTIALLY LINEAR model (econml LinearDML with the covariates as controls, DoubleML's HC0 score SE) -- it fitted a
  # linear CATE averaged over the series before (another estimator)
  fit <- function(b) { obj <- DoubleML::DoubleMLData$new(as.data.frame(b), y_col = "dY", d_cols = "treat", x_cols = L$cv)
    set.seed(1); m <- DoubleML::DoubleMLPLR$new(obj, ml_l = mlr3::lrn("regr.ranger", num.threads = N_THREADS, num.trees = 300L, min.bucket = 20L, mtry = length(L$cv)),
                                                ml_m = mlr3::lrn("classif.ranger", num.threads = N_THREADS, num.trees = 300L, min.bucket = 20L), n_folds = 3); m$fit()
    list(est = unname(m$coef), se = unname(m$se), w = nrow(b)) }
  r <- ml_over_batches(L, fit)
  out <- data.frame(outcome = outcome, target = "ATE", ate = r$est, se = r$se, p_value = ml_p(r$est, r$se), batches = r$batches,
                    se_how = sprintf("DoubleML PLR (3-fold cross-fitting): its asymptotic SE, each of the %s %s one draw (not clustered)%s", format(nrow(L$ld), big.mark = ","), L$what,
                                     if (r$batches > 1L) sprintf("; %d batches of pixels combined", r$batches) else ""), p_how = ML_P_HOW,
                    engine = paste0("DoubleML PLR", if (r$batches > 1L) sprintf(", %d batches of pixels", r$batches) else ""))
  wr("double_ml", attr(dt, "scenario"), paste0("double_ml_", outcome), out); out
}
# v20.58: the p of an ML headline -- normal, from the estimate and the package's asymptotic SE (the same rule in the Python pipeline)
ML_P_HOW <- "normal, from the estimate and the package's asymptotic SE"
ml_p <- function(est, se) if (is.finite(est) && is.finite(se) && se > 0) 2 * pnorm(-abs(est / se)) else NA_real_
m44_bart <- function(dt, outcome) {
  need("bartCause"); L <- long_difference(dt, outcome)
  fit <- function(b) { bb <- bartCause::bartc(response = b$dY, treatment = b$treat, confounders = as.matrix(b[, L$cv, with = FALSE]), estimand = "att", n.samples = 500, n.burn = 200, seed = 1)
    s <- summary(bb)$estimates; list(est = s$estimate[1], se = s$sd[1], w = sum(b$treat)) }
  r <- ml_over_batches(L, fit)
  out <- data.frame(outcome = outcome, target = "ATT", att = r$est, se = r$se, p_value = ml_p(r$est, r$se), batches = r$batches,
                    se_how = sprintf("bartCause: the posterior standard deviation of the ATT (500 draws), each of the %s %s one draw%s", format(nrow(L$ld), big.mark = ","), L$what,
                                     if (r$batches > 1L) sprintf("; %d batches of pixels combined", r$batches) else ""),
                    p_how = "normal approximation of the posterior (estimate / posterior SD)",
                    engine = paste0("bartCause", if (r$batches > 1L) sprintf(", %d batches of pixels", r$batches) else ""))
  wr("bart", attr(dt, "scenario"), paste0("bart_", outcome), out); out
}

# ---------------------------------------------------------------- v20.58: SERIES OF ONE SEASON (M11, M22, M36-M38, M45)
# Your panel holds the annual composite AND Kharif / Rabi / Zaid, each with its own year-to-year shocks (the design absorbs them with year x
# season effects). v20.49-v20.57 averaged each sub-watershed x ring over its seasons -- the core of a Rabi-start cohort (Rabi rows only) then
# faced rings averaged over every season, so the season shocks did not cancel (0.0536 for a true 0.05 in the known-answer test). Now each
# unit is ONE season's series (sub-watershed x ring x season x cohort) and every fit compares a core series with ring series of the SAME
# season; the fits are averaged, weighted by their treated series x post years (SE: the fits taken as independent).
season_series <- function(dt, outcome) {
  a <- dt[, .(y = mean(get(outcome))), by = .(site_id, buff_km, Season, Year, treat, cohort)]
  a[treat == 0L, cohort := Inf]; a[, unit := paste(site_id, buff_km, Season, cohort, sep = "_")]; a[]
}
by_cohort_season <- function(a, fit_one, what) {
  rows <- list()
  for (s_ in sort(unique(a$Season))) for (g in sort(unique(a[treat == 1L & is.finite(cohort) & Season == s_, cohort]))) {
    sub <- a[Season == s_ & ((treat == 1L & cohort == g) | treat == 0L)]
    sub <- sub[unit %in% sub[, .N, by = unit][N == uniqueN(sub$Year), unit]]                 # the balanced panel these estimators need
    n1 <- uniqueN(sub[treat == 1L, unit]); n0 <- uniqueN(sub[treat == 0L, unit]); npost <- uniqueN(sub[Year >= g, Year])
    if (!n1 || n0 < 2 || !npost || uniqueN(sub[Year < g, Year]) < 2) next
    r <- tryCatch(fit_one(sub, g), error = function(e) { info(sprintf("%s: the fit of season %s, cohort %s failed -- %s (left out of the average)", what, s_, g, conditionMessage(e))); NULL })
    if (is.null(r) || !is.finite(r$estimate)) { if (!is.null(r)) info(sprintf("%s: season %s, cohort %s gave no finite estimate (left out of the average)", what, s_, g)); next }
    rows[[length(rows) + 1L]] <- data.table(Season = s_, cohort = g, n_treated = n1, n_control = n0, post_years = npost, estimate = r$estimate, se = r$se %||% NA_real_,
                                            tuning = if (is.null(r$tuning)) NA_real_ else as.numeric(r$tuning)[1])   # v20.58: r / lambda chosen
  }
  if (!length(rows)) stop(sprintf("%s: no cohort x season with a treated series, >= 2 same-season control series and >= 2 pre-period years", what))
  e <- rbindlist(rows); w <- e$n_treated * e$post_years; w <- w / sum(w)
  list(estimate = sum(w * e$estimate), se = if (all(is.finite(e$se))) sqrt(sum(w^2 * e$se^2)) else NA_real_, table = e[, weight := w][],
       se_how = sprintf("%d cohort x season fit(s), each a core series against the same season's ring series; their SEs combined as independent", nrow(e)))
}

# ---------------------------------------------------------------- v20.49: synthetic DiD, one fit per cohort (M11, M45)
sdid_fit <- function(sub, g) {                                                # v20.58: one synthdid fit (a cohort x season block)
  need("synthdid"); s <- copy(sub); s[, D := as.integer(treat == 1L & Year >= g)]
  # v20.58 (second pass): INTEGER series ids -- the treated first, then the ring series, each by sub-watershed and ring (as fect's). panel.matrices
  # sorts the units by their ids in the session's collation: the character ids "site_ring_season_cohort" could come in another order on another
  # machine, and the order decides which ring series each placebo replication draws (the SE). The Python engine takes the same order.
  uo <- unique(s[order(-treat, site_id, buff_km), unit]); s[, uid := match(unit, uo)]
  pm <- synthdid::panel.matrices(as.data.frame(s[, .(uid, Year, y, D)]), unit = "uid", time = "Year", outcome = "y", treatment = "D")
  tau <- synthdid::synthdid_estimate(pm$Y, pm$N0, pm$T0)
  v <- tryCatch(seeded(as.numeric(vcov(tau, method = "placebo"))), error = function(e) NA_real_)
  list(estimate = as.numeric(tau), se = sqrt(v))
}
sdid_by_cohort <- function(a) {
  # synthdid needs ONE adoption time. v20.47 dated every treated unit from the EARLIEST cohort, so with the pooled
  # sub-watersheds (2020 and 2022) the 2022 cohort counted 2020-21 as treated: 0.042 for a true 0.050. One fit per cohort
  # (its treated units vs the never-treated units), averaged with weights = treated units; SE from the placebo variances.
  # `a`: unit, Year, y, treat, cohort (Inf = never treated).
  need("synthdid"); cohorts <- sort(unique(a[treat == 1L & is.finite(cohort), cohort])); rows <- list()
  for (g in cohorts) {
    s <- a[(treat == 1L & cohort == g) | treat == 0L]; s[, D := as.integer(treat == 1L & Year >= g)]
    s <- s[unit %in% s[, .N, by = unit][N == uniqueN(s$Year), unit]]                    # the balanced panel synthdid needs
    pm <- synthdid::panel.matrices(as.data.frame(s[, .(unit, Year, y, D)]), unit = "unit", time = "Year", outcome = "y", treatment = "D")
    tau <- synthdid::synthdid_estimate(pm$Y, pm$N0, pm$T0)
    v <- tryCatch(as.numeric(vcov(tau, method = "placebo")), error = function(e) NA_real_)
    rows[[as.character(g)]] <- data.table(cohort = g, n_treated = nrow(pm$Y) - pm$N0, n_control = pm$N0, estimate = as.numeric(tau), se = sqrt(v))
  }
  e <- rbindlist(rows); w <- e$n_treated / sum(e$n_treated)
  list(estimate = sum(w * e$estimate), se = sqrt(sum(w^2 * e$se^2)), table = e)
}

# ---------------------------------------------------------------- M45 synthetic control at the SITE level (one treated unit per site)
# ---------------------------------------------------------------- v20.58: scikit-learn's ElasticNetCV on glmnet's solver (M45, as Python)
# The objective 1/(2n) ||y - b0 - Xw||^2 + a l1 ||w||_1 + a (1 - l1)/2 ||w||^2 (sklearn's), its alpha grid (100 values from the full data per l1 ratio,
# down to 1e-3 of the largest), its contiguous folds (min(5, n)), the fold-averaged MSE and its choice (the first minimum). glmnet standardises y and
# penalises on that scale, so y is standardised here (ys) and the penalties mapped back: lambda' = a (l1/ys + 1 - l1), alpha' = (l1/ys) / (l1/ys + 1 - l1).
# Every fit is converged tightly (thresh 1e-20, both here and in Python: tol 1e-12) -- sklearn's default tolerance moved the CV choice and the
# effect by up to 0.005 on test problems; converged, R and Python agree to 1e-9 (60 test problems, the same alpha and l1 ratio in all).
.sk_alpha_grid <- function(X, y, l1, K = 100L, eps = 1e-3) {
  Xy <- as.numeric(crossprod(sweep(X, 2, colMeans(X)), y - mean(y))); amax <- max(abs(Xy)) / (nrow(X) * l1)
  if (!is.finite(amax) || amax <= 1e-15) return(rep(1e-15, K))
  g <- 10^seq(log10(amax), log10(amax * eps), length.out = K); g[1] <- amax; g[K] <- amax * eps; g
}
.sk_glmnet <- function(X, y, alpha, lambda) {
  if ("control" %in% names(formals(glmnet::glmnet)))
    return(glmnet::glmnet(X, y, family = "gaussian", alpha = alpha, lambda = lambda, standardize = FALSE, intercept = TRUE,
                          control = list(thresh = 1e-20, maxit = 1e7, fdev = 0, devmax = 1)))
  old <- glmnet::glmnet.control(); on.exit(glmnet::glmnet.control(fdev = old$fdev, devmax = old$devmax), add = TRUE)
  glmnet::glmnet.control(fdev = 0, devmax = 1)          # glmnet < 5: no early end of the path (deviance ratio / change)
  glmnet::glmnet(X, y, family = "gaussian", alpha = alpha, lambda = lambda, standardize = FALSE, intercept = TRUE, thresh = 1e-20, maxit = 1e7)
}
.sk_enet_path <- function(X, y, alphas, l1) {
  ym <- mean(y); ys <- sqrt(mean((y - ym)^2)); p <- ncol(X)
  if (!(ys > 0)) return(list(n = length(alphas), pred = function(Xn, i) rep(ym, nrow(Xn)), coef = function(i) numeric(p), b0 = function(i) ym))
  c1 <- l1 / ys; c2 <- 1 - l1
  f <- suppressWarnings(.sk_glmnet(X, (y - ym) / ys, c1 / (c1 + c2), alphas * (c1 + c2)))
  list(n = length(f$lambda), pred = function(Xn, i) ym + ys * as.numeric(f$a0[i] + Xn %*% f$beta[, i]), coef = function(i) ys * as.numeric(f$beta[, i]),
       b0 = function(i) ym + ys * as.numeric(f$a0[i]))
}
enet_cv_sk <- function(X, y, l1s = c(0.3, 0.5, 0.7, 0.9, 1.0)) {
  need("glmnet"); n <- nrow(X); p <- ncol(X); k <- min(5L, n)
  fid <- rep(seq_len(k), rep(n %/% k, k) + c(rep(1L, n %% k), rep(0L, k - n %% k)))      # sklearn KFold: contiguous, the first n %% k folds one larger
  best <- Inf; ba <- NA_real_; bl <- NA_real_; short <- 0L
  for (l1 in l1s) {
    al <- .sk_alpha_grid(X, y, l1); mse <- matrix(NA_real_, k, length(al))
    for (f in seq_len(k)) {
      tr <- fid != f; fit <- .sk_enet_path(X[tr, , drop = FALSE], y[tr], al, l1); if (fit$n < length(al)) short <- short + 1L
      for (i in seq_len(fit$n)) mse[f, i] <- mean((fit$pred(X[!tr, , drop = FALSE], i) - y[!tr])^2)
    }
    mm <- colMeans(mse); if (!any(is.finite(mm))) next
    ib <- which.min(mm); if (mm[ib] < best) { best <- mm[ib]; ba <- al[ib]; bl <- l1 }
  }
  if (!is.finite(ba)) stop("the elastic net's cross-validation gave no finite error")
  fit <- .sk_enet_path(X, y, ba, bl); if (fit$n < 1L) stop("the elastic net did not fit at the chosen penalty")
  list(pred = function(Xn) fit$pred(Xn, 1L), coef = fit$coef(1L), intercept = fit$b0(1L), alpha = ba, l1_ratio = bl, cv_mse = best, n_paths_cut = short)
}

m45_synth_site <- function(dt, outcome) {
  # v20.58 -- the SAME model as Python's M45 (lasso_sc_ring_series): the ELASTIC-NET synthetic control on the core-vs-ring SERIES. Each treated
  # series (sub-watershed x season: the core, ring 0) is fitted on the SAME season's ring series (all ring series when fewer than 3), both net
  # of the donors' common year effect (their mean per year), the donor weights chosen by scikit-learn's cross-validated elastic net (above);
  # the effect = the mean post-period gap; the series' effects averaged with weights = post years. v20.57 R ran synthdid at the SITE level
  # (a data gap with one sub-watershed) while Python ran this elastic net: two estimators under one model name.
  need("glmnet"); a <- season_series(dt, outcome)
  U <- unique(a[, .(unit, site_id, buff_km, Season, treat, cohort)]); setorder(U, site_id, buff_km, Season, cohort)   # Python's series order
  yrs <- sort(unique(a$Year)); W <- dcast(a, unit ~ Year, value.var = "y"); Ym <- as.matrix(W[, -1, with = FALSE]); rownames(Ym) <- W$unit
  Ym <- Ym[U$unit, , drop = FALSE]
  rows <- list(); wts <- list(); nfail <- 0L; ncut <- 0L
  for (g in sort(unique(U[treat == 1L & is.finite(cohort), cohort]))) {
    pre <- yrs[yrs < g]; post <- yrs[yrs >= g]; if (length(pre) < 3L || !length(post)) next
    cp <- as.character(pre); cq <- as.character(post); win <- c(cp, cq)
    di <- which(U$treat == 0L & rowSums(!is.finite(Ym[, win, drop = FALSE])) == 0L)
    ti <- which(U$treat == 1L & U$cohort == g & rowSums(is.finite(Ym[, cp, drop = FALSE])) >= 3L & rowSums(is.finite(Ym[, cq, drop = FALSE])) > 0L)
    if (!length(ti) || length(di) < 2L) next
    for (i in ti) {
      dj <- di[U$Season[di] == U$Season[i]]; if (length(dj) < 3L) dj <- di        # too few same-season donors: every ring series
      mu <- colMeans(Ym[dj, , drop = FALSE])                                      # the donors' common year effect
      pre_i <- cp[is.finite(Ym[i, cp])]; post_i <- cq[is.finite(Ym[i, cq])]; if (length(pre_i) < 3L || !length(post_i)) next
      X <- t(sweep(Ym[dj, pre_i, drop = FALSE], 2, mu[pre_i])); y <- Ym[i, pre_i] - mu[pre_i]
      Xp <- t(sweep(Ym[dj, post_i, drop = FALSE], 2, mu[post_i]))
      f <- tryCatch(enet_cv_sk(X, y), error = function(e) { info(sprintf("M45: series %s -- %s (left out of the average)", U$unit[i], conditionMessage(e))); NULL })
      if (is.null(f)) { nfail <- nfail + 1L; next }
      ncut <- ncut + f$n_paths_cut
      att_i <- mean(Ym[i, post_i] - mu[post_i] - f$pred(Xp))
      rows[[length(rows) + 1L]] <- data.table(cohort = g, site_id = U$site_id[i], Season = U$Season[i], ATT = att_i, n_nonzero_donors = sum(f$coef != 0),
                                              n_donors_available = length(dj), pre_years = length(pre_i), post_years = length(post_i), alpha = f$alpha, l1_ratio = f$l1_ratio)
      wts[[length(wts) + 1L]] <- data.table(cohort = g, treated = sprintf("site %d season %d", U$site_id[i], U$Season[i]),
                                            donor = sprintf("site %d ring %d season %d", U$site_id[dj], as.integer(U$buff_km[dj]), U$Season[dj]), weight = f$coef)
    }
  }
  if (nfail) info(sprintf("M45: %d treated series could not be fitted -- left out of the average (see above)", nfail))
  if (ncut) info(sprintf("M45: %d cross-validation path(s) ended before the smallest penalty (glmnet did not converge there) -- their remaining penalties were not candidates", ncut))
  if (!length(rows)) stop("no treated series with >= 3 pre-years, a post-year and >= 2 complete ring series as donors")
  t <- rbindlist(rows); att <- sum(t$ATT * t$post_years) / sum(t$post_years)
  out <- data.frame(outcome = outcome, estimate = att, se = NA_real_, ATT_lasso_sc = att, n_cohorts = uniqueN(t$cohort), n_treated_series = nrow(t),
                    n_nonzero_donors = sum(t$n_nonzero_donors), n_donors_available = max(t$n_donors_available),
                    design = "each core series (site x season) on the same-season ring series, net of their common year effect",
                    se_note = "the elastic-net synthetic control gives no SE of its own", engine = "scikit-learn's ElasticNetCV (glmnet solver) -- core vs ring series, as Python")
  tag <- attr(dt, "scenario")
  wr("lasso_sc", tag, paste0("lasso_sc_", outcome), out); wr("lasso_sc", tag, paste0("lasso_sc_by_cohort_", outcome), t)
  wr("lasso_sc", tag, paste0("lasso_sc_weights_", outcome), rbindlist(wts))
  list(result = out, table = t)
}


# ---------------------------------------------------------------- v20.43: M12 chained, M15 placebo, M41 meta-learners, M42 DR
m12_chained <- function(dt, outcome) {                   # first differences between consecutive observations of each series
  d <- dt[order(unit, Year, Season)]
  d[, `:=`(dy = get(outcome) - shift(get(outcome)), ddid = did - shift(did), pair = paste(shift(period), period, sep = ">")), by = unit]
  fd <- d[is.finite(dy) & is.finite(ddid)]
  fit <- feols(dy ~ ddid | pair, data = fd, cluster = ~cluster_id)
  n_cl <- uniqueN(fd[ddid != 0, cluster_id])            # v20.49: the treatment switches inside ONE cluster (one year) with a
  out <- data.frame(outcome = outcome, beta = unname(coef(fit)["ddid"]),                 # single sub-watershed: its cluster SE is 0
                    se = if (n_cl >= 2) unname(se(fit)["ddid"]) else NA_real_,          # by construction -> not reported
                    p_value = if (n_cl >= 2) unname(pvalue(fit)["ddid"]) else NA_real_,   # v20.58: its p (t with G - 1 df), as Python
                    se_note = if (n_cl >= 2) "" else "cluster-robust SE not identified (the switch lies in one cluster); read the design-based SE",
                    engine = "fixest first differences (chained)")
  wr("chained_did", attr(dt, "scenario"), paste0("chained_did_", outcome), out); out
}
m15_placebo <- function(dt, outcome) {                   # fake treatment years inside the pre-period: effects should be ~0
  pre <- dt[post == 0]; yrs <- sort(unique(pre$Year)); yrs <- yrs[yrs > min(yrs)]; rows <- list(); psi <- list()
  # v20.58: with the YEARS as the clusters (one sub-watershed) a placebo's cluster SE rests on a handful of pre years and is too small
  # (false alarms); its SE is then the design-based one -- the year-to-year spread of the pre-period treated-minus-control gaps (within
  # each unit, a year's seasons averaged) x sqrt(1/n_before + 1/n_after), t with n_pre - 2 df
  yr_cl <- identical(get0("cluster_col_for", ifnotfound = function(d) "site_id")(dt), "Year"); gy <- NULL
  if (yr_cl) { q <- pre[, .(site_id, Year, Season, treat, unit, y = get(outcome))]; q[, y := y - mean(y), by = unit]
    gg <- dcast(q[, .(m = mean(y)), by = .(site_id, Year, Season, treat)], site_id + Year + Season ~ treat, value.var = "m")
    if (all(c("0", "1") %in% names(gg))) gy <- gg[, .(gap = `1` - `0`), by = .(site_id, Year, Season)][is.finite(gap), .(gap = mean(gap)), by = .(site_id, Year)] }
  need("fixest"); fe <- pre[, .(unit, period)]; yd <- drop(fixest::demean(as.numeric(pre[[outcome]]), f = fe)); cl <- pre$cluster_id
  for (fy in yrs) {
    d <- copy(pre); d[, fake_did := as.integer(treat == 1 & Year >= fy)]
    fit <- tryCatch(feols(as.formula(paste0(outcome, " ~ fake_did | unit + period")), data = d, cluster = ~cluster_id),
                    error = function(e) { info(sprintf("M15: the placebo start %d cannot be fitted (%s) -- left out", fy, conditionMessage(e))); NULL })
    if (!is.null(fit) && "fake_did" %in% names(coef(fit))) {
      b <- unname(coef(fit)["fake_did"]); se_ <- unname(se(fit)["fake_did"]); p_ <- unname(pvalue(fit)["fake_did"]); how <- "cluster-robust (fixest)"
      if (!is.null(gy) && nrow(gy) >= 3) { a <- gy[Year < fy, gap]; z <- gy[Year >= fy, gap]
        if (length(a) && length(z) && length(c(a, z)) >= 3) { s2 <- var(c(a - mean(a), z - mean(z))) * (length(c(a, z)) - 1) / max(1, length(c(a, z)) - 2)
          se_ <- sqrt(s2 * (1 / length(a) + 1 / length(z))); p_ <- 2 * pt(abs(b / se_), max(1, length(c(a, z)) - 2), lower.tail = FALSE); how <- "design-based (years as the draws)" } }
      xd <- drop(fixest::demean(as.numeric(d$fake_did), f = fe))                  # v20.58: each cluster's influence on this placebo (FWL) --
      psi[[as.character(fy)]] <- tapply(xd * (yd - b * xd), cl, sum) / sum(xd * xd)  # the covariance of the placebo years' estimates
      rows[[length(rows) + 1]] <- data.frame(outcome = outcome, placebo_year = fy, beta = b, se = se_, p_value = p_, se_how = how)
    }
  }
  if (!length(rows)) stop("no pre-period year can carry a placebo")
  out <- rbindlist(rows); out[, engine := "fixest placebo timing"]
  # v20.58: the headline is the MEAN placebo effect WITH ITS OWN SE AND p (v20.57 printed the mean effect, the typical SE of ONE placebo and a
  # Bonferroni p of the most significant year in one row: an estimate 0.0004, SE 0.0007 and p 0.076 that did not belong together).
  # Design-based (years as the clusters): each placebo is a difference of the yearly treated-minus-control gaps after and before its start,
  # so their mean is a fixed combination of the gaps -- SE = SD of the gaps x the norm of that combination, t with n - 1 df. Cluster-robust
  # (>= MIN_SWS_CLUSTERS sub-watersheds): the placebo years' estimates are correlated (the same pre rows) -- their joint covariance from each
  # cluster's influence on every placebo (CR1), t with G - 1 df. Whether ANY single year looks like an effect: p_any_placebo_bonferroni.
  k <- nrow(out); est <- mean(out$beta)
  if (!is.null(gy) && nrow(gy) >= 3) {
    g <- gy$gap; Yr <- gy$Year; cb <- numeric(length(g))
    for (fy in out$placebo_year) { a <- Yr < fy; z <- Yr >= fy; if (any(a) && any(z)) cb <- cb + (z / sum(z) - a / sum(a)) / k }
    se_m <- sqrt(stats::var(g) * sum(cb^2)); df_m <- length(g) - 1L
    how_m <- sprintf("design-based: the mean of the %d placebo effects as a combination of the %d yearly treated-minus-control gaps (years as the draws)", k, length(g))
  } else {
    P <- do.call(cbind, psi[as.character(out$placebo_year)]); G <- nrow(P); sc <- drop(P %*% rep(1 / k, k))
    se_m <- sqrt(sum(sc^2) * G / (G - 1)); df_m <- G - 1L
    how_m <- sprintf("cluster-robust (CR1) over the %d placebo years jointly -- their covariance from each of the %d clusters' influence", k, G)
  }
  p_m <- 2 * pt(abs(est / se_m), max(1, df_m), lower.tail = FALSE); pb <- min(1, k * min(out$p_value, na.rm = TRUE))
  out[, `:=`(mean_placebo_beta = est, mean_placebo_se = se_m, mean_placebo_p = p_m, p_any_placebo_bonferroni = pb)]
  wr("placebo_timing", attr(dt, "scenario"), paste0("placebo_timing_", outcome), out)
  p_how <- sprintf("t with %d df on the mean placebo effect; p_any_placebo_bonferroni = %.3g (the smallest of the %d placebo p-values x %d)", df_m, pb, k, k)
  list(result = data.frame(estimate = est, se = se_m, p_value = p_m, p_any_placebo_bonferroni = pb, n_placebo_years = k, se_how = how_m, p_how = p_how),
       se_how = how_m, p_how = p_how, table = out)
}
m41_learners <- function(dt, outcome) {
  need("grf"); L <- long_difference(dt, outcome)
  fit <- function(b) { X <- as.matrix(b[, L$cv, with = FALSE]); y <- b$dY; w <- b$treat
    s <- grf::regression_forest(cbind(X, w = w), y, num.trees = 500, seed = 1)
    cS <- predict(s, cbind(X, w = 1))$predictions - predict(s, cbind(X, w = 0))$predictions
    f1 <- grf::regression_forest(X[w == 1, , drop = FALSE], y[w == 1], num.trees = 500, seed = 1)
    f0 <- grf::regression_forest(X[w == 0, , drop = FALSE], y[w == 0], num.trees = 500, seed = 1)
    cT <- predict(f1, X)$predictions - predict(f0, X)$predictions
    # v20.58: the X-learner too (Kunzel et al. 2019) -- as the Python pipeline (econml S / T / X): each arm's imputed effects (the other arm's
    # model), a forest of each, blended by the propensity score (a grf regression forest of the treatment)
    d1 <- y[w == 1] - predict(f0, X[w == 1, , drop = FALSE])$predictions; d0 <- predict(f1, X[w == 0, , drop = FALSE])$predictions - y[w == 0]
    g1 <- grf::regression_forest(X[w == 1, , drop = FALSE], d1, num.trees = 500, seed = 1); g0 <- grf::regression_forest(X[w == 0, , drop = FALSE], d0, num.trees = 500, seed = 1)
    e <- pmin(pmax(predict(grf::regression_forest(X, w, num.trees = 500, seed = 1))$predictions, 0.01), 0.99)
    cX <- e * predict(g0, X)$predictions + (1 - e) * predict(g1, X)$predictions
    list(est = mean(c(mean(cS), mean(cT), mean(cX))), se = NA_real_, w = nrow(b),
         tab = data.table(learner = c("S", "T", "X"), att = c(mean(cS[w == 1]), mean(cT[w == 1]), mean(cX[w == 1])), ate = c(mean(cS), mean(cT), mean(cX)),
                          cate_sd = c(sd(cS), sd(cT), sd(cX)), n = nrow(b))) }
  r <- ml_over_batches(L, fit)
  tabs <- if (r$batches == 1L) list(r$tab) else lapply(r$per_batch, `[[`, "tab")
  out <- rbindlist(tabs)[, .(att = sum(att * n) / sum(n), ate = sum(ate * n) / sum(n), cate_sd = sqrt(sum(cate_sd^2 * n) / sum(n))), by = learner]
  out <- data.table(outcome = outcome, out, batches = r$batches, engine = "grf S / T / X learners")
  wr("meta_learners", attr(dt, "scenario"), paste0("meta_learners_", outcome), out)
  list(result = data.frame(estimate = mean(out$ate), target = "ATE", se_note = "S / T / X learners give no standard error (grf regression forests)"), table = out)
}
m42_dr <- function(dt, outcome) {
  need("grf"); L <- long_difference(dt, outcome)
  fit <- function(b) { X <- as.matrix(b[, L$cv, with = FALSE]); cf <- grf::causal_forest(X, b$dY, b$treat, num.trees = 1000, seed = 1)
    a <- grf::average_treatment_effect(cf, target.sample = "all", method = "AIPW"); list(est = a[[1]], se = a[[2]], w = nrow(b)) }
  r <- ml_over_batches(L, fit)
  out <- data.frame(outcome = outcome, target = "ATE", ate = r$est, se = r$se, p_value = ml_p(r$est, r$se), batches = r$batches,
                    se_how = sprintf("grf AIPW (doubly robust): the SE of its doubly robust (AIPW) scores, each of the %s %s one draw (not clustered)%s", format(nrow(L$ld), big.mark = ","), L$what,
                                     if (r$batches > 1L) sprintf("; %d batches of pixels combined", r$batches) else ""), p_how = ML_P_HOW,
                    engine = paste0("grf AIPW (doubly robust)", if (r$batches > 1L) sprintf(", %d batches of pixels", r$batches) else ""))
  wr("dr_learner", attr(dt, "scenario"), paste0("dr_learner_", outcome), out); out
}

# v20.43: the bridge needs the ERROR, not a swallowed NULL -- run_model_strict lets it through; run_model keeps RUN_ALL's behaviour
run_model_strict <- function(id, dt, outcome) {
  f <- switch(id, M03 = m03_drdid, M04 = m04_cic, M09 = m09_sunab, M10 = m10_ddd, M12 = m12_chained, M13 = m13_switchers, M14 = m14_psm,
              M15 = m15_placebo, M17 = m17_18_spatial, M18 = m17_18_spatial, M19 = m19_icc, M20 = m20_heterogeneity, M22 = m22_bacon,
              M24 = m24_spillover, M25 = m25_ritest, M26 = m26_interaction, M27 = m27_imputation, M28 = m28_did2s, M29 = m29_exposure,
              M30 = m30_cohorts, M31 = m31_stacked, M32 = m32_etwfe, M33 = m33_ebal, M35 = m35_qdid,
              M36 = function(d, o) m36_38_factor(d, o, "ife"), M37 = function(d, o) m36_38_factor(d, o, "mc"), M38 = function(d, o) m36_38_factor(d, o, "gsynth"),
              M39 = m43_causal_forest, M40 = m40_doubleml, M41 = m41_learners, M42 = m42_dr, M43 = m43_causal_forest, M44 = m44_bart, M45 = m45_synth_site, NULL)
  if (is.null(f)) stop("no pre-built R implementation registered for ", id)
  f(dt, outcome)
}

run_model <- function(id, dt, outcome) {
  f <- switch(id, M03 = m03_drdid, M04 = m04_cic, M09 = m09_sunab, M10 = m10_ddd, M13 = m13_switchers, M14 = m14_psm, M17 = m17_18_spatial, M18 = m17_18_spatial,
              M19 = m19_icc, M20 = m20_heterogeneity, M22 = m22_bacon, M24 = m24_spillover, M25 = m25_ritest, M26 = m26_interaction, M27 = m27_imputation, M28 = m28_did2s,
              M29 = m29_exposure, M30 = m30_cohorts, M31 = m31_stacked, M32 = m32_etwfe, M33 = m33_ebal, M35 = m35_qdid,
              M36 = function(d, o) m36_38_factor(d, o, "ife"), M37 = function(d, o) m36_38_factor(d, o, "mc"), M38 = function(d, o) m36_38_factor(d, o, "gsynth"),
              M39 = m43_causal_forest, M40 = m40_doubleml, M43 = m43_causal_forest, M44 = m44_bart, M45 = m45_synth_site, NULL)
  if (is.null(f)) stop("no pre-built R implementation registered for ", id, " (M01/M02/M05/M16/M23/M34 are in RUN_ALL.R; M07/M08 need external files)")
  tryCatch(run_model_strict(id, dt, outcome), error = function(e) { cat(sprintf("[WARNING] %s: %s\n", id, conditionMessage(e))); NULL })
}
