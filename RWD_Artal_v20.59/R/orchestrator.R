# Spec 3 -- the R orchestrator: the same configuration file as orchestrator.py (config/analysis_config.yaml | .json) -> the design set on the R
# library, the PRE-FLIGHT checks (panel integrity, the singleton pre-flight, range safety), the estimators, the comparison report
# (SPEC_COMPARISON_<outcome>_R.csv).      Rscript orchestrator.R [config/analysis_config.yaml] [only=canonical,donut] [dry_run]
args <- commandArgs(trailingOnly = TRUE)
R_HOME_DIR <- normalizePath(if (nzchar(Sys.getenv("REWARD_R_HOME"))) Sys.getenv("REWARD_R_HOME") else { a <- grep("^--file=", commandArgs(), value = TRUE); if (length(a)) dirname(sub("^--file=", "", a)) else "." }, winslash = "/")
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
suppressPackageStartupMessages(library(data.table))
CFG_PATH <- { p <- args[!grepl("^(only=|dry_run)", args)]; if (length(p)) p[1] else file.path(R_HOME_DIR, "config", "analysis_config.yaml") }
ONLY <- { o <- grep("^only=", args, value = TRUE); if (length(o)) strsplit(sub("^only=", "", o), ",")[[1]] else NULL }
DRY <- "dry_run" %in% args
CFG_DEFAULTS <- list(ANALYSIS_VARIABLE = "NDVI", SEASON_FILTER = "Rabi", DONUT_RINGS = 1L, CONTROL_RINGS = "data", CONTROL_SELECTION_METHOD = "pre_bias_min", CONTROL_SELECT_ON = "level",
                     PRECISION_TOLERANCE = 1e-6, MIN_PIXEL_COVERAGE_PCT = 0.70, CLUSTER_VAR = "subwshed_id", ESTIMATOR = "SURROGATE_DID", LANDUSE_KEEP = "all", BASELINE_NDVI_MIN = NA,
                     SAME_PIXELS = "pre_post", DROP_SINGLETONS = TRUE, TREATMENT_TIMING = "fixed", TREATMENT_YEAR = 2022L, DESIGN_SOURCE = "model", EXCLUDE_TRANSITION_YEAR = FALSE,
                     OUTCOME_SCREEN = "drop", EXCLUDE_GAPFILLED = TRUE, COVARIATES = c("Rain", "Tmax", "Tmean", "Tmin"), SURROGATES = c("NDWI", "LSWI", "NDMI", "Rain"), SURROGATE_SEASON = 1L,
                     OUTCOME_SEASONS = c(2L, 3L), REPORT_SPECS = c("canonical", "donut", "matched", "synthetic_did", "surrogate_index"))
SEASONS_MAP <- c(rabi = "Rabi", kharif = "Kharif", zaid = "Zaid", yearly = "yearly", all = "all")
METHODS <- list(all = list("rings", 2L), pre_bias_min = list("pre_rings", 2L), closest_1 = list("pre_rings", 1L), closest_2 = list("pre_rings", 2L))
CLUSTERS <- c(subwshed_id = "auto", site = "auto", year = "auto", block = "block")
load_config_R <- function(path) {
  cfg <- if (grepl("\\.json$", path, ignore.case = TRUE)) jsonlite::fromJSON(path) else { need("yaml"); yaml::read_yaml(path) }
  out <- CFG_DEFAULTS; for (k in names(cfg)) out[[k]] <- if (is.null(cfg[[k]])) NA else cfg[[k]]
  validate_config_R(out)
}
validate_config_R <- function(cfg) {
  bad <- c()
  if (!tolower(cfg$SEASON_FILTER) %in% names(SEASONS_MAP)) bad <- c(bad, sprintf("SEASON_FILTER '%s': Rabi | Kharif | Zaid | Yearly | All", cfg$SEASON_FILTER))
  if (!tolower(cfg$CONTROL_SELECTION_METHOD) %in% names(METHODS)) bad <- c(bad, sprintf("CONTROL_SELECTION_METHOD '%s': all | pre_bias_min | closest_1 | closest_2", cfg$CONTROL_SELECTION_METHOD))
  if (!tolower(cfg$CLUSTER_VAR) %in% names(CLUSTERS)) bad <- c(bad, sprintf("CLUSTER_VAR '%s': subwshed_id | year | block", cfg$CLUSTER_VAR))
  if (!toupper(cfg$ESTIMATOR) %in% c("TWFE_CANONICAL", "SYNTHETIC_DID", "SURROGATE_INDEX", "SURROGATE_DID")) bad <- c(bad, sprintf("ESTIMATOR '%s'", cfg$ESTIMATOR))
  if (!(cfg$PRECISION_TOLERANCE >= 0 && cfg$PRECISION_TOLERANCE <= 1e-2)) bad <- c(bad, "PRECISION_TOLERANCE must be in [0, 1e-2]")
  if (!(cfg$MIN_PIXEL_COVERAGE_PCT >= 0 && cfg$MIN_PIXEL_COVERAGE_PCT < 1)) bad <- c(bad, "MIN_PIXEL_COVERAGE_PCT must be in [0, 1)")
  dn <- suppressWarnings(as.integer(unlist(cfg$DONUT_RINGS))); dn <- dn[is.finite(dn)]; if (length(dn) && any(!dn %in% 1:5)) bad <- c(bad, "DONUT_RINGS must name rings 1..5")
  if (!tolower(cfg$CONTROL_SELECT_ON) %in% c("level", "rmse", "trend", "both")) bad <- c(bad, "CONTROL_SELECT_ON: level | rmse | trend | both")
  if (!tolower(cfg$SAME_PIXELS) %in% c("pre_post", "all", "off")) bad <- c(bad, "SAME_PIXELS: pre_post | all | off")
  unknown <- setdiff(cfg$REPORT_SPECS, c("canonical", "donut", "matched", "synthetic_did", "surrogate_index")); if (length(unknown)) bad <- c(bad, paste("REPORT_SPECS unknown:", paste(unknown, collapse = ",")))
  if (length(bad)) stop("configuration refused: ", paste(bad, collapse = "; "))
  cfg
}
apply_config_R <- function(cfg, spec = "config") {
  for (k in names(DESIGN_DEFAULTS)) assign(k, DESIGN_DEFAULTS[[k]], envir = globalenv())
  m <- METHODS[[tolower(cfg$CONTROL_SELECTION_METHOD)]]
  g <- list(TREATMENT_TIMING = cfg$TREATMENT_TIMING, TREATMENT_YEAR = as.integer(cfg$TREATMENT_YEAR), DESIGN_SOURCE = cfg$DESIGN_SOURCE, EXCLUDE_TRANSITION_YEAR = isTRUE(cfg$EXCLUDE_TRANSITION_YEAR),
            OUTCOME_SCREEN = cfg$OUTCOME_SCREEN, EXCLUDE_GAPFILLED = isTRUE(cfg$EXCLUDE_GAPFILLED), COVARIATES = if (length(cfg$COVARIATES)) as.character(cfg$COVARIATES) else character(0),
            CONTROL_RINGS = if (is.character(cfg$CONTROL_RINGS)) cfg$CONTROL_RINGS else as.integer(unlist(cfg$CONTROL_RINGS)), SEASONS = SEASONS_MAP[[tolower(cfg$SEASON_FILTER)]],
            DONUT_RINGS = { dn <- suppressWarnings(as.integer(unlist(cfg$DONUT_RINGS))); dn[is.finite(dn)] }, CONTROL_SELECTION = m[[1]], CONTROL_SELECT_K = m[[2]], CONTROL_SELECT_ON = cfg$CONTROL_SELECT_ON,
            CLUSTER = CLUSTERS[[tolower(cfg$CLUSTER_VAR)]], LANDUSE_KEEP = cfg$LANDUSE_KEEP, BASELINE_NDVI_MIN = cfg$BASELINE_NDVI_MIN, MIN_PIXEL_COVERAGE_PCT = cfg$MIN_PIXEL_COVERAGE_PCT,
            DROP_SINGLETONS = isTRUE(cfg$DROP_SINGLETONS), PRECISION_TOLERANCE = cfg$PRECISION_TOLERANCE, SAME_PIXELS = cfg$SAME_PIXELS, PRE_YEARS = "data", POST_YEARS = "data")
  if (spec == "canonical") { g$SEASONS <- "all"; g$DONUT_RINGS <- integer(0); g$CONTROL_SELECTION <- "rings" }
  else if (spec == "donut") g$CONTROL_SELECTION <- "rings"
  else if (spec == "matched") g$CONTROL_SELECTION <- if (m[[1]] != "rings") m[[1]] else "pre_rings"
  for (k in names(g)) assign(k, g[[k]], envir = globalenv())
  model_design(verbose = FALSE, force = TRUE)
}
preflight_R <- function(x, outcome, cfg) {
  pre <- x$post == 0L; tr <- x$treat == 1L; rows <- list()
  for (lab in c("treated", "control")) { m <- if (lab == "treated") tr else !tr; a <- unique(x$pixel_id[m & pre]); b <- unique(x$pixel_id[m & !pre])
    rows[[length(rows) + 1]] <- data.table(check = sprintf("panel integrity: the %s pixels are the same in pre and post", lab), ok = setequal(a, b), detail = sprintf("%s pre / %s post pixels, %s differ", format(length(a), big.mark = ","), format(length(b), big.mark = ","), format(length(union(setdiff(a, b), setdiff(b, a))), big.mark = ",")), strict = TRUE) }
  cnt <- x[, .N, by = unit]; n1 <- sum(cnt$N == 1L)
  rows[[length(rows) + 1]] <- data.table(check = "singleton pre-flight: series seen once", ok = n1 == 0 || isTRUE(cfg$DROP_SINGLETONS), detail = sprintf("%s of %s series seen once%s", format(n1, big.mark = ","), format(nrow(cnt), big.mark = ","), if (n1 && isTRUE(cfg$DROP_SINGLETONS)) " -- dropped before the demeaning (DROP_SINGLETONS)" else ""), strict = FALSE)
  rc <- outcome_range_check_R(x, outcome, say = FALSE)
  rows[[length(rows) + 1]] <- data.table(check = "range safety: the outcome within its bounds, no no-data code", ok = isTRUE(rc$ok), detail = sprintf("[%s, %s] against %s; %d outside, %d no-data codes, %d within the tolerance of zero", format(rc$vmin), format(rc$vmax), paste(rc$bounds, collapse = ","), rc$n_outside_bounds, rc$n_nodata_codes, rc$n_zero_padding), strict = TRUE)
  tab <- rbindlist(rows); tab[, outcome := outcome]
  for (i in seq_len(nrow(tab))) (if (tab$ok[i]) ok else warn)(sprintf("pre-flight -- %s: %s", tab$check[i], tab$detail[i]))
  bad <- tab[ok == FALSE & strict == TRUE]; if (nrow(bad)) stop("PRE-FLIGHT FAILED: ", paste(sprintf("%s (%s)", bad$check, bad$detail), collapse = " | "))
  tab
}
pretrend_p_R <- function(x, outcome) {
  pre <- x[post == 0L]; if (uniqueN(pre$Year) < 3 || !any(pre$treat == 1L)) return(NA_real_)
  pre <- copy(pre); pre[, pretrend_term := as.numeric(treat == 1L) * (Year - mean(Year))]
  f <- tryCatch(fe_fit(pre, outcome, "pretrend_term"), error = function(e) NULL); if (is.null(f) || !"pretrend_term" %in% names(f$p)) NA_real_ else unname(f$p["pretrend_term"])
}
run_spec_R <- function(spec, cfg) {
  outcome <- cfg$ANALYSIS_VARIABLE; t0 <- Sys.time()
  d <- apply_config_R(cfg, if (spec %in% c("canonical", "donut", "matched")) spec else "config"); tag <- scenario_tag(d)
  extra <- if (spec == "surrogate_index") intersect(setdiff(as.character(cfg$SURROGATES), outcome), panel_names()) else character(0)
  x <- load_panel_R(outcome, d, extra = extra); pf <- preflight_R(x, outcome, cfg)
  row <- data.table(spec = spec, outcome = outcome, tag = tag, n = nrow(x), pixels = uniqueN(x$pixel_id), rings = paste(sort(unique(x[treat == 0L, buff_km])), collapse = "+"),
                    seasons = paste(SEASON_LABEL[as.character(sort(unique(x$Season)))], collapse = "+"), pretrend_p = pretrend_p_R(x, outcome))
  if (spec %in% c("canonical", "donut", "matched")) { f <- fe_fit(x, outcome, "did"); row[, `:=`(estimator = "TWFE (two-way FE, CR1)", beta = unname(f$coef["did"]), se = unname(f$se["did"]), p_value = unname(f$p["did"]), clusters = f$G, cluster = cluster_col_for(x))] }
  else if (spec == "synthetic_did") { r <- synthetic_did_two_level_R(x, outcome, pixel_level = TRUE, cluster_col = "cluster_id"); save_outputs_R(r, RESULTS_DIR, outcome)
    row[, `:=`(estimator = "synthetic DiD (two-level; pixel WLS beside)", beta = r$att, se = r$se, p_value = r$p_value, pre_rmspe = r$pre_rmspe, clusters = r$pixel_wls$n_clusters, cluster = r$pixel_wls$cluster, pixel_wls_beta = r$pixel_wls$beta, pixel_wls_se = r$pixel_wls$se)] }
  else if (spec == "surrogate_index") { r <- surrogate_index_did_R(x, outcome, as.character(cfg$SURROGATES), outcome_seasons = as.integer(unlist(cfg$OUTCOME_SEASONS)), surrogate_season = as.integer(cfg$SURROGATE_SEASON), cluster_col = "cluster_id"); save_outputs_R(r, RESULTS_DIR, outcome)
    row[, `:=`(estimator = sprintf("surrogate index (%s)", paste(r$surrogates, collapse = "+")), beta = r$att, se = r$se, p_value = r$p_value, pre_rmspe = r$pre_rmspe, clusters = r$n_clusters, cluster = r$cluster)] }
  row[, `:=`(seconds = round(as.numeric(difftime(Sys.time(), t0, units = "secs")), 1), preflight = if (all(pf$ok)) "ok" else "warned")]
  info(sprintf("spec %s: beta %+.6f se %.6f p %.3g | pre-trend p %.3g | n %s | %s", spec, row$beta, row$se, row$p_value, row$pretrend_p, format(row$n, big.mark = ","), tag))
  row
}
run_report_R <- function(cfg, only = NULL) {
  est <- toupper(cfg$ESTIMATOR); specs <- as.character(cfg$REPORT_SPECS); if (!is.null(only)) specs <- intersect(specs, only)
  if (est == "TWFE_CANONICAL") specs <- intersect(specs, c("canonical", "donut", "matched")) else if (est == "SYNTHETIC_DID") specs <- setdiff(specs, "surrogate_index") else if (est == "SURROGATE_INDEX") specs <- setdiff(specs, "synthetic_did")
  rows <- lapply(specs, function(s) tryCatch(run_spec_R(s, cfg), error = function(e) { warn(sprintf("spec %s: not estimated -- %s", s, substr(conditionMessage(e), 1, 300))); data.table(spec = s, outcome = cfg$ANALYSIS_VARIABLE, estimator = "not estimated", note = substr(conditionMessage(e), 1, 300)) }))
  t <- rbindlist(rows, fill = TRUE); cols <- intersect(c("spec", "estimator", "beta", "se", "p_value", "pretrend_p", "pre_rmspe", "n", "pixels", "clusters", "cluster", "rings", "seasons", "tag", "note"), names(t))
  setcolorder(t, c(cols, setdiff(names(t), cols))); dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
  p <- file.path(RESULTS_DIR, sprintf("SPEC_COMPARISON_%s_R.csv", cfg$ANALYSIS_VARIABLE)); fwrite(t, p)
  cat("\n", strrep("=", 100), "\nSPEC COMPARISON -- ", cfg$ANALYSIS_VARIABLE, sprintf(" (config: season %s, donut %s, controls %s, cluster %s)", cfg$SEASON_FILTER, paste(unlist(cfg$DONUT_RINGS), collapse = ","), cfg$CONTROL_SELECTION_METHOD, cfg$CLUSTER_VAR), "\n", strrep("=", 100), "\n", sep = "")
  print(t[, intersect(c("spec", "estimator", "beta", "se", "p_value", "pretrend_p", "n", "clusters"), names(t)), with = FALSE]); cat("-> ", p, "\n")
  invisible(t)
}
if (sys.nframe() == 0 && !interactive()) {
  cfg <- load_config_R(CFG_PATH)
  cat(sprintf("[INFO]    configuration %s: variable %s, season %s, donut %s, controls %s, cluster %s, estimator %s, same pixels %s, singletons dropped %s\n", CFG_PATH, cfg$ANALYSIS_VARIABLE, cfg$SEASON_FILTER, paste(unlist(cfg$DONUT_RINGS), collapse = ","), cfg$CONTROL_SELECTION_METHOD, cfg$CLUSTER_VAR, cfg$ESTIMATOR, cfg$SAME_PIXELS, cfg$DROP_SINGLETONS))
  if (DRY) { for (s in cfg$REPORT_SPECS) cat(sprintf("[INFO]    %s: %s\n", s, scenario_tag(apply_config_R(cfg, if (s %in% c("canonical", "donut", "matched")) s else "config")))) } else { t <- run_report_R(cfg, ONLY); quit(status = if (nrow(t) && any(t$estimator != "not estimated")) 0L else 1L) }
}
