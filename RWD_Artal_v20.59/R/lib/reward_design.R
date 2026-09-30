# reward_design.R -- the rules every R model shares (v20.45; the same rules as the Python engine).
suppressPackageStartupMessages({ library(data.table); library(jsonlite) })
`%||%` <- function(a, b) if (is.null(a) || !length(a)) b else a      # (base R has it only from 4.4)
options(datatable.showProgress = FALSE)          # v20.52: no "Processed N groups out of N" lines
ok   <- function(...) cat("[OK]      ", ..., "\n", sep = "")
info <- function(...) cat("[INFO]    ", ..., "\n", sep = "")
warn <- function(...) cat("[WARNING] ", ..., "\n", sep = "")

# ---------------------------------------------------------------- v20.49: the 50 % split, shared with the Python pipelines
# Every running pipeline -- R or Python -- registers (process id, start time, data folder) in ONE machine-wide folder
# (the Python registry: <temp>/reward_instances). The cores this R session gives data.table / fixest, and the memory it
# plans with, are divided by the number of DISTINCT data folders being processed now: 50 % each for two, the whole
# machine again when the other ends. A dead or re-used process id (its start time differs) is ignored.
INSTANCE_DIR <- file.path(dirname(tempdir()), "reward_instances")
.root_key <- function(p) { r <- normalizePath(p, winslash = "\\", mustWork = FALSE); if (.Platform$OS.type == "windows") tolower(r) else normalizePath(p, mustWork = FALSE) }
.proc_alive <- function(pid, created = NULL) {
  if (!requireNamespace("ps", quietly = TRUE)) return(NA)                        # unknown: the heartbeat decides
  h <- tryCatch(ps::ps_handle(as.integer(pid)), error = function(e) NULL); if (is.null(h)) return(FALSE)
  if (!isTRUE(tryCatch(ps::ps_is_running(h), error = function(e) FALSE))) return(FALSE)
  if (!is.null(created) && is.finite(as.numeric(created))) {                     # a re-used pid is another process
    ct <- tryCatch(as.numeric(ps::ps_create_time(h)), error = function(e) NA_real_)
    if (is.finite(ct) && abs(ct - as.numeric(created)) > 2) return(FALSE)
  }
  TRUE
}
register_instance <- function() {
  try({ dir.create(INSTANCE_DIR, showWarnings = FALSE, recursive = TRUE)
        created <- if (requireNamespace("ps", quietly = TRUE)) as.numeric(ps::ps_create_time(ps::ps_handle())) else NA_real_
        writeLines(jsonlite::toJSON(list(pid = Sys.getpid(), root = .root_key(ROOT), heartbeat = as.numeric(Sys.time()), created = created, lang = "R"),
                                    auto_unbox = TRUE, digits = NA), file.path(INSTANCE_DIR, paste0(Sys.getpid(), ".json"))) }, silent = TRUE)
}
live_roots <- function() {
  roots <- .root_key(ROOT)
  for (f in list.files(INSTANCE_DIR, pattern = "\\.json$", full.names = TRUE)) {
    d <- tryCatch(jsonlite::fromJSON(f), error = function(e) NULL); if (is.null(d) || is.null(d$pid)) next
    a <- .proc_alive(d$pid, d$created)
    stale <- isFALSE(a) || (is.na(a) && as.numeric(Sys.time()) - as.numeric(d$heartbeat %||% 0) > 3600)
    if (stale) { unlink(f); next }
    roots <- c(roots, as.character(d$root))
  }
  unique(roots)
}
AUTO_SPLIT <- FALSE   # v20.52 (your instruction): NO cap -- the whole machine for every pipeline; TRUE = the v20.47 split
memory_share <- function(verbose = TRUE) {
  if (!AUTO_SPLIT) {                     # v20.54: MEMORY_SHARE (reward_paths.R, 1.0 = no cap) is honoured again -- v20.52 returned 1
    sh <- suppressWarnings(as.numeric(MEMORY_SHARE))    # whatever it said, so the documented manual setting did nothing
    sh <- if (length(sh) == 1 && is.finite(sh)) min(1, max(0.05, sh)) else 1                # an unreadable value = no cap (as Python)
    if (verbose) info(if (sh >= 1) paste0("using the whole machine: ", N_THREADS, " cores, all RAM (no split, no cap)")
                      else sprintf("MEMORY_SHARE = %.2f (your manual setting): %d of %d cores, %.0f %% of the RAM below 98 %%", sh, max(1L, floor(N_THREADS * sh)), N_THREADS, 100 * sh))
    return(sh)
  }
  register_instance(); n <- max(1L, length(live_roots())); v <- min(MEMORY_SHARE, 1 / n)
  if (verbose) info(if (n > 1) sprintf("%d REWARD pipelines on different data folders are running: this one uses %.0f %% of the cores and memory", n, 100 * v)
                    else "this is the only REWARD pipeline running: it uses the whole machine")
  v
}
apply_share <- function(verbose = TRUE) {
  sh <- memory_share(verbose); nt <- max(1L, floor(N_THREADS * sh))
  setDTthreads(nt); if (requireNamespace("fixest", quietly = TRUE)) fixest::setFixest_nthreads(nt)
  invisible(sh)
}
MEMORY_CEILING <- 0.98                                                          # v20.57 YOUR RULE: no limit until 98 % of the TOTAL RAM
ram_budget_bytes <- function() {                                                # this pipeline's share of the RAM below 98 % (v20.56: 95 %)
  # v20.58: REWARD_RAM_BUDGET_BYTES lowers the budget by hand (as Python's _hardware.ram_budget_bytes) -- the checks use it to prove that the
  # out-of-core path starts BY ITSELF when the data do not fit (tests/run_all_tests.R scenario H)
  env <- suppressWarnings(as.numeric(Sys.getenv("REWARD_RAM_BUDGET_BYTES", "")))
  if (!requireNamespace("ps", quietly = TRUE)) return(if (isTRUE(env > 0)) env else NA_real_)
  m <- tryCatch(ps::ps_system_memory(), error = function(e) NULL); if (is.null(m)) return(if (isTRUE(env > 0)) env else NA_real_)
  own <- tryCatch(as.numeric(ps::ps_memory_info(ps::ps_handle())[["rss"]]), error = function(e) 0)
  b <- max(0, min(m$avail - (1 - MEMORY_CEILING) * m$total, memory_share(FALSE) * MEMORY_CEILING * m$total - own))
  if (isTRUE(env > 0)) b <- min(b, env)
  b
}
units_that_fit <- function(bytes_per_unit, manual = NULL) {                    # v20.57: the 98 % rule instead of a fixed sample size
  if (!is.null(manual) && is.finite(manual)) return(as.numeric(manual))
  b <- ram_budget_bytes(); if (!is.finite(b)) return(Inf)
  max(1, floor(b / bytes_per_unit))
}
.unregister <- function(e) try(unlink(file.path(INSTANCE_DIR, paste0(Sys.getpid(), ".json"))), silent = TRUE)
reg.finalizer(environment(), .unregister, onexit = TRUE)
apply_share(verbose = TRUE)

# ---------------------------------------------------------------- the panel on disk: arrow first, CSV as the fall-back
HAS_ARROW <- requireNamespace("arrow", quietly = TRUE)
panel_file <- function() if (HAS_ARROW) PANEL_PATH else sub("\\.parquet$", if (requireNamespace("R.utils", quietly = TRUE)) ".csv.gz" else ".csv", PANEL_PATH)
# v20.58: the panel file carries the data and nothing of how one run built it. R attributes of the build (the dedup counts, the rows
# dropped without an outcome, a sort key) are stripped before writing -- in memory and out of core alike -- so both write the SAME file,
# schema and metadata (tests/run_all_tests.R H; they differed in a project without M07's benchmark means, where no merge dropped them).
# The counts are in panel_build_settings_R.csv and the run's log.
panel_plain_attrs <- function(x) {
  for (a in setdiff(names(attributes(x)), c("names", "row.names", "class", ".internal.selfref"))) setattr(x, a, NULL)
  invisible(x)
}
panel_write <- function(dt) {
  panel_plain_attrs(dt)
  if (HAS_ARROW) { arrow::write_parquet(dt, PANEL_PATH); return(invisible(PANEL_PATH)) }
  fwrite(dt, panel_file()); info("arrow is not installed: the panel is written as ", panel_file(), " (install arrow: faster and smaller)")
  invisible(panel_file())
}
panel_names <- function() if (HAS_ARROW) names(arrow::open_dataset(PANEL_PATH)) else names(fread(panel_file(), nrows = 0))
panel_read <- function(cols, rings = NULL) {
  cols <- intersect(unique(cols), panel_names())
  if (HAS_ARROW) {
    ds <- dplyr::select(arrow::open_dataset(PANEL_PATH), dplyr::all_of(cols))
    if (!is.null(rings)) ds <- dplyr::filter(ds, buff_km == 0 | buff_km %in% rings)
    return(as.data.table(dplyr::collect(ds)))
  }
  x <- fread(panel_file(), select = cols, colClasses = list(character = intersect(c("pixel_id", "unit", "period", "sws_name"), cols)))
  if (!is.null(rings)) x <- x[buff_km == 0 | buff_km %in% rings]
  x
}

# ---------------------------------------------------------------- the cluster: sub-watersheds (>= 6) else years
cluster_col_for <- function(dt) {
  n <- uniqueN(dt$site_id[dt$site_id > 0])
  if (n >= MIN_SWS_CLUSTERS) "site_id" else "Year"
}

# ---------------------------------------------------------------- the outcome screen: a year the export filled is not data
# v20.59: every decision comes with its EVIDENCE -- rows, pixels, mean, SD across pixels, min and max per year-season, written to
# OUTCOME_SCREEN_<outcome>.csv beside the results at every run -- and with a way out: OUTCOME_SCREEN <- "keep" (the model's settings) keeps the
# flagged year-seasons (said; the results are tagged _screenKept), "off" runs no screen; "drop" (the default) leaves them out as before. A
# refusal (fewer than 2 pre / 1 post years left) names the evidence file and the option -- your v20.58 log stopped at "Re-export it" with
# 41 of 44 year-seasons flagged and nothing to look at.
screen_rule_R <- function(v = .opt("OUTCOME_SCREEN", "drop")) {
  if (isTRUE(v)) return("drop"); if (is.null(v) || isFALSE(v)) return("off")
  v <- tolower(trimws(as.character(v)[1]))
  if (v %in% c("drop", "true", "on")) return("drop"); if (v %in% c("keep", "report", "warn")) return("keep"); if (v %in% c("off", "false", "none", "no")) return("off")
  stop("OUTCOME_SCREEN must be \"drop\", \"keep\" or \"off\" (got \"", v, "\")")
}
screen_outcome <- function(dt, outcome, treatment_year = TREATMENT_YEAR, refuse = TRUE, rule = screen_rule_R()) {
  if (identical(rule, "off")) return(list(dt = dt, report = NULL))
  y <- dt[[outcome]]; keep <- is.finite(y)
  s <- dt[keep, .(n = .N, sd = sd(get(outcome)), mean = mean(get(outcome)), min = min(get(outcome)), max = max(get(outcome)),
                  n_pixels = if ("pixel_id" %in% names(dt)) as.numeric(uniqueN(pixel_id)) else NA_real_,
                  n_treated = sum(buff_km == 0), n_control = sum(buff_km > 0)), by = .(Year, Season)]
  dec <- screen_decide(s, outcome, rule)
  bad <- dec$drop
  if (nrow(bad)) dt <- dt[!bad, on = .(Year, Season)]
  screen_refuse(sort(unique(dt$Year[is.finite(dt[[outcome]])])), outcome, treatment_year, refuse, dec)
  list(dt = dt, report = if (nrow(dec$bad)) dec$bad[, .(outcome = outcome, Year, Season, why)] else NULL)
}
# v20.58: the two decisions of the screen on its (Year, Season) table -- shared by the in-memory path above and the out-of-core path
# (reward_outofcore.R: the same table merged from the pixel partitions), so both leave out exactly the same year-seasons.
# v20.59: s carries min, max, n_pixels too; returns list(bad = the cells that are not pixel data, drop = the cells to leave out (none under
# "keep"), table = the evidence of every cell, path = the evidence file, n_cells)
screen_decide <- function(s, outcome, rule = screen_rule_R()) {
  s <- copy(s); s[is.na(sd), sd := 0]
  for (k in c("min", "max", "n_pixels")) if (!k %in% names(s)) set(s, j = k, value = NA_real_)
  mt <- median(s$n_treated); mc <- median(s$n_control)
  tol <- .opt("PRECISION_TOLERANCE", 1e-6); cov_ <- .opt("MIN_PIXEL_COVERAGE_PCT", SCREEN_MIN_COVERAGE)                  # spec 1 / 3 (as Python)
  s[, constant := sd <= pmax(tol, 1e-9 * pmax(1, abs(mean)))]
  s[, collapse := n_treated < cov_ * mt | n_control < cov_ * mc]
  s[, why := paste0(ifelse(constant, sprintf("constant across pixels (a fill value: %s rows%s, every value %s%s)", formatC(n, big.mark = ",", format = "d"),
                                             ifelse(is.finite(n_pixels), sprintf(" of %s pixels", formatC(n_pixels, big.mark = ",", format = "d")), ""),
                                             formatC(min, digits = 6, format = "g"), ifelse(is.finite(max) & max != min, paste0("..", formatC(max, digits = 6, format = "g")), "")), ""),
                    ifelse(constant & collapse, "; ", ""),
                    ifelse(collapse, sprintf("coverage collapsed (%s treated / %s control rows against typical %s / %s)", formatC(n_treated, big.mark = ",", format = "d"),
                                             formatC(n_control, big.mark = ",", format = "d"), formatC(round(mt), big.mark = ",", format = "d"), formatC(round(mc), big.mark = ",", format = "d")), ""))]
  s[, `:=`(usable = !(constant | collapse), outcome = outcome, rule = rule, left_out = (constant | collapse) & rule == "drop")]
  setorder(s, Year, Season)
  path <- file.path(RESULTS_DIR, sprintf("OUTCOME_SCREEN_%s.csv", outcome))
  try({ dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
        fwrite(s[, .(outcome, Year, Season, season = SEASON_LABEL[as.character(Season)], rows = n, pixels = n_pixels, mean, sd_across_pixels = sd, min, max,
                     treated_rows = n_treated, control_rows = n_control, constant, collapse, usable, rule, left_out, why)], path) }, silent = TRUE)
  bad <- s[constant | collapse]
  if (nrow(bad)) {
    warn(outcome, ": ", nrow(bad), " of ", nrow(s), " year-season(s) are NOT pixel data", if (rule == "drop") " and are left out" else " -- KEPT (OUTCOME_SCREEN = \"keep\": the model runs on them -- NOTE: in a fill year-season every pixel holds ONE value, so the treated-control difference there is exactly 0; kept, it dilutes the gap the DiD compares (a pre gap g over n real pre periods becomes g x n / (n + 1)) and the estimate moves by that dilution. Use \"keep\" only if these ARE pixel data)", " -- ",
         paste(sprintf("%s %s: %s", bad$Year, SEASON_LABEL[as.character(bad$Season)], bad$why), collapse = "; "),
         " -> the evidence of every year-season (rows, pixels, mean, SD, min, max): ", path)
  }
  list(bad = bad, drop = if (rule == "drop") bad else bad[0], table = s, path = path, n_cells = nrow(s))
}
screen_refuse <- function(yrs, outcome, treatment_year, refuse = TRUE, dec = NULL) {   # yrs: the years with a valid value after the screen
  pre <- yrs[yrs < treatment_year]; post <- yrs[yrs >= treatment_year]
  if (refuse && (length(pre) < 2 || length(post) < 1))
    stop(sprintf("'%s' is not usable: after the screen (%s of %s year-seasons left out as fill values / collapsed coverage) it has %d valid pre-period year(s) [%s] and %d post-period year(s) [%s] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in %s. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- \"keep\" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.",
                 outcome, if (is.null(dec)) "?" else nrow(dec$drop), if (is.null(dec)) "?" else dec$n_cells, length(pre), paste(pre, collapse = ", "), length(post), paste(post, collapse = ", "),
                 if (is.null(dec)) "OUTCOME_SCREEN_<outcome>.csv (beside the results)" else dec$path))
  invisible(TRUE)
}

# ---------------------------------------------------------------- the design-based SE (the honest benchmark for every model)
# v20.58 (your v20.56 log: "design SE 0.003 ... p 0.944" on an estimate of -0.0066): the p-value belonged to a DIFFERENT number -- the DiD
# of the collapsed gaps -- that was never printed; the gaps were RAW means (in an unbalanced panel the pixels present change from year to
# year, and a year's seasons were pooled with changing weights), and the rows WITHOUT a sub-watershed (site 0: pixels outside every
# polygon) were a second "sub-watershed" with half of the weight. Now: the outcome net of each unit's own level (the model's unit:
# pixel x season series or pixel -- the within transformation of the fixed-effects models), treated-minus-control gaps per year x
# season, a year's gap = the mean of its seasons' gaps (each season once), processed sub-watersheds only (site_id > 0). Returned and
# printed: the design DiD itself, its SE, df and p -- and the p of the MODEL's estimate against that SE.
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
  if (inherits(dt, "reward_ooc")) return(dt$design_se(estimate))            # v20.58: out of core -- the same cells, merged from the partitions
  d <- dt[is.finite(get(outcome))]
  if ("site_id" %in% names(d) && any(d$site_id > 0L)) d <- d[site_id > 0L]  # v20.58: rows without a sub-watershed are no sub-watershed
  if (!nrow(d) || !all(c("treat", "post", "unit", "Year", "Season") %in% names(d))) return(list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified"))
  d <- d[, .(site_id, Year, Season, treat, post, unit, y = get(outcome))]
  d[, y := y - mean(y), by = unit]                                             # the within transformation (each unit's own level removed)
  design_se_core(d[, .(m = mean(y)), by = .(site_id, Year, Season, treat)], d[, .(post = max(post), pmin = min(post)), by = .(site_id, Year, Season)],
                 uniqueN(d$Season), estimate)
}
# v20.58: the design SE from its cells -- g (site_id, Year, Season, treat, m = the mean of the unit-demeaned outcome) and pp (site_id, Year,
# Season, post = max, pmin = min) -- shared by the in-memory path above and the out-of-core path (the cells merged from the partitions)
design_se_core <- function(g, pp, n_seasons, estimate = NA_real_) {
  w <- dcast(g, site_id + Year + Season ~ treat, value.var = "m")
  if (!all(c("0", "1") %in% names(w))) return(list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified (no year-season with both treated and control rows)"))
  w[, gap := `1` - `0`]
  w <- merge(w, pp[, .(site_id, Year, Season, post, pmin)], by = c("site_id", "Year", "Season"))
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
  if (cy$by == "years" && n_seasons > 1) {                                       # each year x season a draw (seasons of a year may share a shock:
    per2 <- .draws(w[, .(site_id, gap, post)]); c2 <- .combine(per2)            # the year-level pair above is the conservative one)
    if (c2$S) out <- c(out, list(did_design_period = c2$did, se_design_period = c2$se, df_design_period = c2$df, p_design_period = pt2(c2$did / c2$se, c2$df),
                                 n_periods_design = sum(per2$n0 + per2$n1), se_design_period_unit = "each year x season a draw",
                                 p_estimate_design_period = pt2(estimate / c2$se, c2$df)))
  }
  out
}
# the design-based SE of an EVENT-STUDY headline (the mean of the post-period coefficients against the reference year -1): with the
# years as the draws (one sub-watershed, or too few to cluster on) each coefficient is a gap minus the reference year's gap, so the
# headline = mean(post gaps) - gap(-1) has variance s2 (1 + 1 / n_post), s2 = the year-to-year variance of the PRE-period gaps.
design_se_event <- function(dt, outcome, estimate = NA_real_) {
  if (inherits(dt, "reward_ooc")) return(dt$design_se_event(estimate))      # v20.58: out of core -- the same cells, merged from the partitions
  d <- dt[is.finite(get(outcome))]; if ("site_id" %in% names(d) && any(d$site_id > 0L)) d <- d[site_id > 0L]
  d <- d[, .(site_id, Year, Season, treat, post, unit, y = get(outcome))]; d[, y := y - mean(y), by = unit]
  design_event_core(d[, .(m = mean(y)), by = .(site_id, Year, Season, treat)], d[, .(post = max(post)), by = .(site_id, Year, Season)], estimate)
}
design_event_core <- function(g0, pp, estimate = NA_real_) {                  # v20.58: shared with the out-of-core path (as design_se_core)
  g <- dcast(g0, site_id + Year + Season ~ treat, value.var = "m")
  if (!all(c("0", "1") %in% names(g))) return(list(se = NA_real_, df = NA_real_, p = NA_real_, how = "not identified"))
  g[, gap := `1` - `0`]; g <- merge(g, pp[, .(site_id, Year, Season, post)], by = c("site_id", "Year", "Season"))
  wy <- g[is.finite(gap), .(gap = mean(gap), post = max(post)), by = .(site_id, Year)]
  v <- wy[, .(s2 = if (sum(post == 0L) > 1) var(gap[post == 0L]) else NA_real_, n0 = sum(post == 0L), n1 = sum(post == 1L)), by = site_id][is.finite(s2) & n1 > 0]
  if (!nrow(v)) return(list(se = NA_real_, df = NA_real_, p = NA_real_, how = "not identified (fewer than 2 pre-period years)"))
  S <- nrow(v); se <- sqrt(sum(v$s2 * (1 + 1 / v$n1))) / S; df <- sum(v$n0 - 1)
  list(se = se, df = df, p = if (is.finite(estimate) && se > 0) 2 * pt(abs(estimate / se), df, lower.tail = FALSE) else NA_real_,
       how = sprintf("design-based: years as the draws (the year-to-year spread of the %d pre-period gap(s) x sqrt(1 + 1/%d post years)%s)", sum(v$n0), round(mean(v$n1)),
                     if (S > 1) sprintf(", %d sub-watersheds", S) else ""))
}

# ---------------------------------------------------------------- v20.58: OUTCOMES THAT ARE THE SAME VARIABLE (said, never silent)
# Your v20.56 run gave LSWI exactly NDMI's result and WSSI exactly minus ESI's. That is not a copy: in your exports LSWI and NDMI are the
# same index (both (NIR - SWIR1) / (NIR + SWIR1)), and WSSI = 1 - ESI. Every pair of outcomes that is an exact linear function of the other
# on the rows they share (|r| > 0.999999) is found once per panel (OUTCOME_IDENTITIES.csv) and announced at every run of either one.
outcome_identities_R <- function(outcomes = OUTCOMES, verbose = TRUE) {
  key <- paste("ident", panel_identity()); if (!is.null(.DESIGN_CACHE[[key]])) return(.DESIGN_CACHE[[key]])
  cf <- file.path(dirname(panel_file()), "OUTCOME_IDENTITIES_R.rds")                     # once per panel, kept next to it
  j <- tryCatch(if (file.exists(cf)) readRDS(cf) else NULL, error = function(e) NULL)
  if (!is.null(j) && identical(j$panel, panel_identity())) { .DESIGN_CACHE[[key]] <- j$tab; return(j$tab) }
  oc <- intersect(outcomes, panel_names()); out <- data.table(a = character(0), b = character(0), r = numeric(0), slope = numeric(0), intercept = numeric(0), n = numeric(0))
  # v20.58: beyond 98 % of the RAM (or on the checks' switch) the same test row group by row group (reward_outofcore.R: exact co-moments)
  big <- length(oc) >= 2 && HAS_ARROW && !is.null(get0("ooc_forced", mode = "function")) && (!is.null(ooc_forced()) || isTRUE(panel_rows_R() * length(oc) * 8 * 3 > ram_budget_bytes()))
  if (big) { out <- outcome_identities_stream_R(oc); info("outcome identities: the panel read row group by row group (all at once would pass 98 % of the RAM) -- exact") }
  if (!big && length(oc) >= 2) {
    x <- panel_read(oc); keep <- vapply(oc, function(o) sum(is.finite(x[[o]])) > 2, logical(1)); oc <- oc[keep]
    first <- x[seq_len(min(nrow(x), 1e6))]                                                # a pair is SCREENED on the first rows ...
    for (i in seq_along(oc)) for (j in seq_along(oc)) if (i < j) {
      a <- first[[oc[i]]]; b <- first[[oc[j]]]; m <- is.finite(a) & is.finite(b); if (sum(m) < 3) next
      if (!isTRUE(abs(suppressWarnings(cor(a[m], b[m]))) > 0.99999)) next
      a <- x[[oc[i]]]; b <- x[[oc[j]]]; m <- is.finite(a) & is.finite(b)                  # ... and CONFIRMED on every row both have
      sa <- sd(a[m]); sb <- sd(b[m]); if (!is.finite(sa) || !is.finite(sb) || sa == 0 || sb == 0) next
      r <- cor(a[m], b[m]); if (is.finite(r) && abs(r) > 0.999999) { sl <- r * sb / sa
        out <- rbind(out, data.table(a = oc[i], b = oc[j], r = r, slope = sl, intercept = mean(b[m]) - sl * mean(a[m]), n = sum(m))) }
    }
    rm(x, first)
  }
  try(saveRDS(list(panel = panel_identity(), tab = out), cf), silent = TRUE)
  if (verbose && nrow(out)) for (k in seq_len(nrow(out))) info(sprintf("OUTCOME IDENTITY: %s = %.4g %+.4g x %s on all %s rows they share (r = %.7f) -- %s", out$b[k], out$intercept[k], out$slope[k], out$a[k],
                                                                  format(out$n[k], big.mark = ","), out$r[k], if (abs(out$slope[k] - 1) < 1e-6 && abs(out$intercept[k]) < 1e-9) "the SAME variable: identical results are expected"
                                                                  else sprintf("a linear transform: the estimate of %s = %.4g x that of %s (identical p-values)", out$b[k], out$slope[k], out$a[k])))
  try(if (nrow(out)) fwrite(out, file.path(RESULTS_DIR, "OUTCOME_IDENTITIES.csv")), silent = TRUE)
  .DESIGN_CACHE[[key]] <- out; out
}

# ---------------------------------------------------------------- the design, from the DATA -- never from the effect
recommend_design <- function(outcome = DESIGN_OUTCOME, treatment_year = TREATMENT_YEAR, write = TRUE, fragment_rule = "drop", min_share = 0.05, overlap_rows = "drop", sites = NULL) {
  cols <- intersect(c("pixel_id", "Year", "Season", "buff_km", outcome, "site_id", "site_check"), panel_names())
  # v20.58: the data summary the choice rests on -- all rows at once below 98 % of the RAM, else from the pixel partitions (out of core,
  # reward_outofcore.R: the same sums, counts and pixel sets)
  big <- !is.null(get0("ooc_forced", mode = "function")) && (!is.null(ooc_forced()) || isTRUE(panel_rows_R() * 8 * (length(cols) + 4) * 3 > ram_budget_bytes()))
  sm <- if (big) recommend_summary_ooc(outcome, treatment_year, fragment_rule, min_share, overlap_rows, sites, cols)
        else recommend_summary_mem(outcome, treatment_year, fragment_rule, min_share, overlap_rows, sites, cols)
  recommend_from_summary(sm, treatment_year, write)
}
recommend_summary_mem <- function(outcome, treatment_year, fragment_rule, min_share, overlap_rows, sites, cols) {
  a0 <- panel_read(cols)
  if ("site_id" %in% names(a0)) {                                          # v20.58: chosen on the rows the run estimates -- the LOCATION rule
    loc <- location_table_R(); S <- if (is.null(sites)) processing_set_R(loc, "data", min_share)$sites else sites   # (the current
    lc <- location_codes_R(a0, loc, S)                                     # sub-watershed's own data; no overlap, no repeated pixel)
    dc <- c(if (identical(fragment_rule, "drop")) 1:2, if (identical(overlap_rows, "drop")) 3:4)
    if (length(dc)) a0 <- a0[!lc %in% dc]
  }
  a <- a0[is.finite(get(outcome))]; s0 <- min(a$Season); ann <- a[Season == s0]
  g <- ann[, .(n = .N, mean = mean(get(outcome)), sd = sd(get(outcome))), by = .(Year, ring = buff_km)]
  yrs <- sort(unique(g$Year))
  core0 <- a0[Season == s0 & buff_km == 0]                                                   # pixels PRESENT (not: with a finite outcome)
  ref <- unique(core0[Year == treatment_year - 1, pixel_id])
  link <- sapply(yrs, function(y) { p <- unique(core0[Year == y, pixel_id]); if (length(p)) mean(p %in% ref) else NA })
  names(link) <- yrs
  list(g = g, s0 = s0, link = link, sn_all = a[Season != s0, .N, by = .(Season, Year)])
}
# the choice itself, from the summary (g: Year, ring, n, mean, sd of the first season; link: the core's pixels linked to the year before
# the start; sn_all: rows per season x year of the other seasons) -- the same in memory and out of core
recommend_from_summary <- function(sm, treatment_year, write) {
  g <- sm$g; s0 <- sm$s0; link <- sm$link
  yrs <- sort(unique(g$Year)); rings <- sort(unique(g$ring[g$ring > 0])); far <- if (length(rings)) max(rings) else NA
  tot <- g[, .(n = sum(n), sd = weighted.mean(sd, n)), by = Year]
  fill <- tot[sd <= 1e-7 | n < SCREEN_MIN_COVERAGE * median(n), Year]
  tc <- merge(g[ring == 0, .(Year, t = mean, st = sd)], g[ring > 0, .(c = weighted.mean(mean, n), sc = weighted.mean(sd, n)), by = Year], by = "Year")[order(Year)]
  # export breaks (as _common.recommend_design, v20.55): the core loses its pixels' history, or both groups jump together AND
  # the spread across pixels changes with them (a re-scaled export) AND the new level persists into the next year. A common
  # jump alone (a drought / a wet year: both groups move and revert) is a COMMON SHOCK -- the year x season fixed effects
  # absorb it; it is reported, no year is removed. (Until v20.54 any common jump > 3x the median change cut the post window.)
  dtt <- diff(tc$t); dcc <- diff(tc$c); breaks <- integer(0); shocks <- integer(0)
  if (length(dtt) >= 3) for (i in seq_along(dtt)) {
    rt <- median(abs(dtt[-i])); rc <- median(abs(dcc[-i]))
    if (isTRUE(sign(dtt[i]) == sign(dcc[i]) && abs(dtt[i]) > 3 * rt && abs(dcc[i]) > 3 * rc)) {
      r_t <- if (isTRUE(tc$st[i] > 0)) tc$st[i + 1] / tc$st[i] else 1; r_c <- if (isTRUE(tc$sc[i] > 0)) tc$sc[i + 1] / tc$sc[i] else 1
      rescaled <- isTRUE((r_t > 1.5 && r_c > 1.5) || (r_t < 1 / 1.5 && r_c < 1 / 1.5))
      persists <- if (i + 2 > nrow(tc)) TRUE else {
        nt <- tc$t[i + 2] - tc$t[i + 1]; nc <- tc$c[i + 2] - tc$c[i + 1]
        isTRUE((sign(nt) == sign(dtt[i]) || abs(nt) < 0.5 * abs(dtt[i])) && (sign(nc) == sign(dcc[i]) || abs(nc) < 0.5 * abs(dcc[i])))
      }
      if (rescaled && persists) breaks <- c(breaks, tc$Year[i + 1]) else shocks <- c(shocks, tc$Year[i + 1])
    }
  }
  breaks <- sort(unique(c(breaks, yrs[yrs >= treatment_year & !is.na(link) & link < 0.9])))
  valid <- setdiff(yrs, fill)
  pre_break <- suppressWarnings(max(breaks[breaks < treatment_year])); post_break <- suppressWarnings(min(breaks[breaks >= treatment_year]))
  pre <- valid[valid < treatment_year & (!is.finite(pre_break) | valid >= pre_break)]
  post <- valid[valid >= treatment_year & (!is.finite(post_break) | valid < post_break)]
  contaminated <- integer(0)
  if (is.finite(far) && length(pre) >= 2 && length(post)) {
    fr <- g[ring == far, .(Year, f = mean)]
    for (r in rings[rings < far & rings <= 2]) {
      gg <- merge(g[ring == r, .(Year, m = mean)], fr, by = "Year")[, gap := m - f]
      a0 <- gg[Year %in% pre, gap]; b0 <- gg[Year %in% post, gap]
      if (length(a0) >= 2 && length(b0) >= 1) {
        se <- sqrt(var(a0) / length(a0) + (if (length(b0) > 1) var(b0) / length(b0) else var(a0)))
        if (isTRUE(se > 0 && abs((mean(b0) - mean(a0)) / se) > 2)) contaminated <- c(contaminated, r)
      }
    }
  }
  ctrl <- rings[rings > (if (length(contaminated)) max(contaminated) else 0)]; if (length(ctrl) < 2) ctrl <- rings
  sn <- sm$sn_all[Year %in% c(pre, post)]
  seas <- if (nrow(sn) && all(sn[, .N, by = Season]$N == length(c(pre, post))) && min(sn$N) >= 0.5 * min(tot[Year %in% c(pre, post), n])) "all" else "yearly"
  rec <- list(control_rings = ctrl, pre_window = pre, post_window = post, seasons = seas, breaks = breaks, common_shocks = sort(unique(shocks)), fill_years = fill,
              contaminated_rings = contaminated, linkage = as.list(round(link, 3)))
  if (write) {
    writeLines(c("# Design chosen from the data (never from the effect)", "",
                 sprintf("- Pre-period: %s%s", paste(pre, collapse = ", "), if (is.finite(pre_break)) sprintf(" (after the export break in %d)", pre_break) else ""),
                 sprintf("- Post-period: %s%s", paste(post, collapse = ", "), if (is.finite(post_break)) sprintf(" (before the export break in %d: the pixels lose their history, or both groups jump and re-scale for good)", post_break) else ""),
                 sprintf("- Common shocks: %s -- years in which the core and the rings move together (weather, not an export break): the year x season fixed effects absorb them, no year is removed",
                         if (length(shocks)) paste(sort(unique(shocks)), collapse = ", ") else "none"),
                 sprintf("- Fill years: %s", if (length(fill)) paste(fill, collapse = ", ") else "none"),
                 sprintf("- SD across pixels on the annual rows, by year (the evidence of the fill years; a fill value has SD 0): %s", paste(sprintf("%d: %.3g", tot$Year, tot$sd), collapse = ", ")),   # v20.59
                 sprintf("- Control rings: %s%s", paste(ctrl, collapse = ", "), if (length(contaminated)) sprintf(" (rings %s move with the core: spillover)", paste(contaminated, collapse = ", ")) else ""),
                 sprintf("- Seasons: %s", seas), "", "The core's own effect is never used to choose any of this."),
               file.path(RESULTS_DIR, "DESIGN_RECOMMENDATION.md"))
  }
  info(sprintf("design from the data: pre %s, post %s, control rings %s, seasons %s%s", paste(pre, collapse = ","), paste(post, collapse = ","),
               paste(ctrl, collapse = ","), seas, paste0(if (length(breaks)) paste0("; export breaks ", paste(breaks, collapse = ",")) else "",
               if (length(shocks)) paste0("; common shocks (kept) ", paste(sort(unique(shocks)), collapse = ",")) else "",
               if (length(fill)) paste0("; fill years ", paste(fill, collapse = ","), " (SD across pixels on the annual rows: ", paste(sprintf("%d %.3g", tot$Year, tot$sd), collapse = ", "), ")") else "")))   # v20.59: the evidence
  rec
}

# v20.55: the seasons setting as ONE canonical string (as Python's normalize_seasons):
#   "all"  annual composite + Kharif / Rabi / Zaid together (your rule: year AND season variation; pixel x season and
#          year x season fixed effects) -- the default | "seasonal" the three seasons only | "yearly" the annual composite only |
#   one or several named seasons: "Rabi", c("Rabi", "Zaid"), "Rabi+Zaid" | "auto" the data decide (model_design)
SEASON_NAME_CODE <- c(yearly = 0L, annual = 0L, kharif = 1L, rabi = 2L, zaid = 3L)
normalize_seasons <- function(value) {
  parts <- tolower(trimws(unlist(strsplit(as.character(value), "[+, ]+")))); parts <- parts[nzchar(parts)]
  if (length(parts) == 1 && parts %in% c("seasonal", "yearly", "all", "auto")) return(parts)
  bad <- setdiff(parts, names(SEASON_NAME_CODE))
  if (length(bad) || !length(parts)) stop("SEASONS must be \"all\", \"seasonal\", \"yearly\", \"auto\" or season names (Kharif, Rabi, Zaid, e.g. \"Rabi\" or c(\"Rabi\", \"Zaid\")) -- got: ", paste(value, collapse = ", "))
  codes <- sort(unique(unname(SEASON_NAME_CODE[parts])))
  if (identical(codes, 0L)) return("yearly"); if (identical(codes, 1:3)) return("seasonal"); if (identical(codes, 0:3)) return("all")
  paste(c("yearly", "kharif", "rabi", "zaid")[codes + 1L], collapse = "+")
}
season_codes <- function(mode) {                                           # the Season codes a mode keeps (NULL = every row)
  if (identical(mode, "all")) return(NULL); if (identical(mode, "yearly")) return(0L); if (identical(mode, "seasonal")) return(1:3)
  unname(SEASON_NAME_CODE[strsplit(mode, "+", fixed = TRUE)[[1]]])
}
save_design <- function(d) { dir.create(OUTPUT_DIR, recursive = TRUE, showWarnings = FALSE); writeLines(toJSON(d[setdiff(names(d), "choices")], auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA), DESIGN_PATH) }

# ================================================================ v20.57: THE DESIGN IS SET IN THE MODEL NOTEBOOK AND APPLIED WHEN THE MODEL RUNS
# Every option of the design -- TREATMENT_TIMING (fund / registry / fixed), TREATMENT_YEAR, the fund rule, DOSE_VARIABLE, CONTROL_RINGS,
# PRE_YEARS / POST_YEARS, SEASONS, EXCLUDE_TRANSITION_YEAR, UNIT_FE, COHORT_OFFSET, OVERLAP_ROWS, FRAGMENT_RULE, POOLED_FE,
# EXCLUDE_GAPFILLED, COVARIATES -- is set in the settings cell of the MODEL notebook (defaults: lib/reward_paths.R) and turned into
# the design here, when the model runs, on the panel R_P00 built ONCE. Change an option and re-run the model: R_P00 is never re-run
# for it. What you set is what runs: DESIGN IN EFFECT (printed, and saved as DESIGN_IN_EFFECT.csv next to every result) lists each
# option as you set it, the value used and where it came from. The Python pipeline does the same (resolve_design); the two are
# compared option by option (python/validate_design_options.py).
.DESIGN_CACHE <- new.env()
DATA_WORDS <- c("data", "recommended")
is_data_opt <- function(v) is.character(v) && length(v) == 1 && tolower(trimws(v)) %in% DATA_WORDS
is_all_opt  <- function(v) length(v) == 1 && (is.na(v) || (is.character(v) && tolower(trimws(v)) %in% c("all", "every", "none")))
DOSE_VARIABLES <- c("dose_intensity_per_ha", "dose_amount_sws", "dose_share_of_target")
.opt <- function(k, default) { v <- get0(k, envir = globalenv(), ifnotfound = NULL); if (is.null(v)) get0(k, ifnotfound = default) else v }
.one_of <- function(k, v, allowed) { v <- tolower(trimws(as.character(v)[1])); if (!v %in% allowed) stop(k, " must be ", paste(sprintf("\"%s\"", allowed), collapse = " | "), " (got \"", v, "\")"); v }
design_settings <- function() {
  s <- list(design_mode = .one_of("DESIGN_MODE", .opt("DESIGN_MODE", "recommended"), c("recommended", "manual")),
            timing = .one_of("TREATMENT_TIMING", .opt("TREATMENT_TIMING", "fund"), c("fund", "registry", "fixed")),
            treatment_year = as.integer(.opt("TREATMENT_YEAR", 2022)),
            fund_start_rule = .one_of("FUND_START_RULE", .opt("FUND_START_RULE", "backcast"), c("backcast", "share", "file_start")),
            fund_start_share = as.numeric(.opt("FUND_START_SHARE", 0.10)), fund_rate_months = as.integer(.opt("FUND_RATE_MONTHS", 12L)),
            fund_dose_before_file = .one_of("FUND_DOSE_BEFORE_FILE", .opt("FUND_DOSE_BEFORE_FILE", "backcast"), c("backcast", "missing")),
            dose_variable = .one_of("DOSE_VARIABLE", .opt("DOSE_VARIABLE", "dose_intensity_per_ha"), DOSE_VARIABLES),
            control_rings = .opt("CONTROL_RINGS", "data"), pre_years = .opt("PRE_YEARS", "data"), post_years = .opt("POST_YEARS", "data"),
            seasons = .opt("SEASONS", "all"), exclude_transition_year = isTRUE(.opt("EXCLUDE_TRANSITION_YEAR", FALSE)),
            unit_fe = .one_of("UNIT_FE", .opt("UNIT_FE", "pixel_season"), c("pixel_season", "pixel")), cohort_offset = as.integer(.opt("COHORT_OFFSET", 0L)),
            overlap_rows = .one_of("OVERLAP_ROWS", .opt("OVERLAP_ROWS", "drop"), c("drop", "keep")),
            fragment_rule = .one_of("FRAGMENT_RULE", .opt("FRAGMENT_RULE", "drop"), c("drop", "keep")),
            fragment_min_share = as.numeric(.opt("FRAGMENT_MIN_SHARE", 0.05)),
            pooled_fe = .one_of("POOLED_FE", .opt("POOLED_FE", "site_period"), c("site_period", "period")),
            exclude_gapfilled = isTRUE(.opt("EXCLUDE_GAPFILLED", TRUE)), covariates = as.character(.opt("COVARIATES", c("Rain", "Tmax", "Tmean", "Tmin"))),
            sub_watersheds = .opt("SUB_WATERSHEDS", "data"),                    # v20.58: the processing set (the location rule)
            outcome_screen = screen_rule_R(.opt("OUTCOME_SCREEN", "drop")),    # v20.59: the outcome screen's rule -- drop | keep | off
            design_source = .one_of("DESIGN_SOURCE", .opt("DESIGN_SOURCE", "model"), c("panel", "model")),   # v20.59: "panel" = the panel's columns are estimated on (the notebooks' default) | "model" = the design in effect
            control_selection = control_selection_R(.opt("CONTROL_SELECTION", "rings")),                    # v20.59 (your fifth request): rings | pre_rings | pre_blocks
            control_select_k = as.integer(.opt("CONTROL_SELECT_K", 2L)), control_select_ratio = as.numeric(.opt("CONTROL_SELECT_RATIO", 3)),
            control_select_on = .one_of("CONTROL_SELECT_ON", .opt("CONTROL_SELECT_ON", "trend"), c("trend", "level", "both", "rmse")),
            control_block_deg = as.numeric(.opt("CONTROL_BLOCK_DEG", 0.01)),
            cluster = .one_of("CLUSTER", .opt("CLUSTER", "auto"), c("auto", "block")),                     # v20.59: ~1 km spatial blocks as clusters
            same_pixels = .one_of("SAME_PIXELS", .opt("SAME_PIXELS", "pre_post"), c("pre_post", "all", "off")),   # v20.59: the same pixels across the panel
            donut_rings = { v <- .opt("DONUT_RINGS", integer(0)); v <- suppressWarnings(as.integer(unlist(v))); v <- sort(unique(v[is.finite(v)])); if (length(v) && any(!v %in% 1:5)) stop("DONUT_RINGS must name rings 1..5"); v },   # spec 1
            landuse_keep = { v <- .opt("LANDUSE_KEEP", "all"); if (is.character(v) && length(v) == 1 && tolower(v) %in% c("all", "none", "off", "")) "all" else sort(unique(as.integer(unlist(v)))) },
            baseline_ndvi_min = { v <- .opt("BASELINE_NDVI_MIN", NA); v <- suppressWarnings(as.numeric(v[1])); if (is.finite(v) && (v < -1 || v > 1)) stop("BASELINE_NDVI_MIN must be an NDVI value in [-1, 1] or NA"); if (is.finite(v)) v else NA_real_ },
            min_pixel_coverage_pct = as.numeric(.opt("MIN_PIXEL_COVERAGE_PCT", SCREEN_MIN_COVERAGE)), drop_singletons = isTRUE(.opt("DROP_SINGLETONS", FALSE)),
            precision_tolerance = as.numeric(.opt("PRECISION_TOLERANCE", 1e-6)))
  if (!(is.finite(s$min_pixel_coverage_pct) && s$min_pixel_coverage_pct >= 0 && s$min_pixel_coverage_pct < 1)) stop("MIN_PIXEL_COVERAGE_PCT must be in [0, 1)")
  if (!(is.finite(s$precision_tolerance) && s$precision_tolerance >= 0 && s$precision_tolerance <= 1e-2)) stop("PRECISION_TOLERANCE must be in [0, 1e-2]")
  if (!(is.finite(s$control_select_k) && s$control_select_k >= 1L && s$control_select_k <= 5L)) stop("CONTROL_SELECT_K must be 1..5")
  if (!(is.finite(s$control_select_ratio) && s$control_select_ratio > 0)) stop("CONTROL_SELECT_RATIO must be > 0")
  if (!(is.finite(s$control_block_deg) && s$control_block_deg >= 0.001 && s$control_block_deg <= 1)) stop("CONTROL_BLOCK_DEG must be between 0.001 and 1 degree")
  sw <- unlist(s$sub_watersheds); if (!length(sw) || all(is.na(sw))) sw <- "data"
  s$sub_watersheds <- if (length(sw) == 1 && is.character(sw) && tolower(trimws(sw)) %in% c("data", "recommended", "auto", "major")) (if (tolower(trimws(sw)) == "major") "major" else "data") else as.character(sw)
  if (!is.finite(s$treatment_year)) stop("TREATMENT_YEAR must be a year (got ", .opt("TREATMENT_YEAR", NA), ")")
  if (!(is.finite(s$fund_start_share) && s$fund_start_share > 0 && s$fund_start_share <= 1)) stop("FUND_START_SHARE must be in (0, 1]")
  if (!(is.finite(s$fund_rate_months) && s$fund_rate_months >= 2)) stop("FUND_RATE_MONTHS must be >= 2")
  if (!(is.finite(s$fragment_min_share) && s$fragment_min_share >= 0 && s$fragment_min_share < 1)) stop("FRAGMENT_MIN_SHARE must be in [0, 1)")
  if (!is_data_opt(s$control_rings)) {
    r <- suppressWarnings(as.integer(s$control_rings))
    if (!length(r) || anyNA(r) || any(!r %in% 1:5)) stop("CONTROL_RINGS must be \"data\" or ring numbers from 1 to 5 (e.g. 1:3, c(2, 4)) -- got ", paste(s$control_rings, collapse = ","))
    s$control_rings <- sort(unique(r))
  }
  for (k in c("pre_years", "post_years")) {
    v <- s[[k]]
    if (!is_data_opt(v) && !is_all_opt(v)) {
      # v20.59: a NUMBER OF YEARS (PRE_YEARS 4 = the 4 years before the start; POST_YEARS 2 = the start year and the next) OR a CALENDAR
      # YEAR (PRE_YEARS 2015 = the first pre year; POST_YEARS 2025 = the last post year). v20.58 read every number as a count: your
      # PRE_YEARS <- 2022 became year_min = 2022 - 2022 = 0 ("USED: from 0") without a word.
      n <- suppressWarnings(as.integer(v))
      if (length(n) != 1 || is.na(n) || n < 1 || (n > 200 && n < 1900) || n > 2100)
        stop(toupper(k), " must be \"data\", NA / \"all\", a number of years (e.g. 4) or a calendar year (e.g. ",
             if (k == "pre_years") "2015 = the FIRST pre year" else "2025 = the LAST post year", ") -- got ", paste(v, collapse = ","))
      s[[k]] <- n
    }
    else if (is_all_opt(v)) s[[k]] <- NA_integer_ else s[[k]] <- "data"
  }
  s$seasons_setting <- normalize_seasons(s$seasons)
  s$covariates <- if (length(s$covariates) == 1 && tolower(s$covariates) == "all") c("Rain", "Tmax", "Tmean", "Tmin") else if (length(s$covariates) == 1 && tolower(s$covariates) == "none") character(0) else s$covariates
  s
}

.file_id <- function(p) if (!is.null(p) && nzchar(p) && file.exists(p)) paste(normalizePath(p, winslash = "/"), round(as.numeric(file.mtime(p)), 3), file.size(p)) else ""
panel_identity <- function() .file_id(panel_file())
panel_years_R <- function() {
  k <- paste("years", panel_identity()); if (!is.null(.DESIGN_CACHE[[k]])) return(.DESIGN_CACHE[[k]])
  # v20.58: with arrow the distinct years are found while scanning (never the whole column in RAM -- a panel beyond 98 % of the RAM)
  y <- if (!file.exists(panel_file())) integer(0) else if (HAS_ARROW) sort(unique(as.integer(dplyr::collect(dplyr::distinct(dplyr::select(arrow::open_dataset(PANEL_PATH), Year)))$Year)))
       else sort(unique(as.integer(panel_read("Year")$Year)))
  .DESIGN_CACHE[[k]] <- y; y
}

# ---------------------------------------------------------------- v20.58: THE LOCATION RULE -- YOUR RULE: only the CURRENT sub-watershed's own data
# Every row's LOCATION is known from the shapefile overlay R_P00 wrote (site_id, site_check). A DiD uses a row only when its pixel lies in
# a polygon (core or ring) of a sub-watershed THIS RUN processes -- the processing set, SUB_WATERSHEDS:
#   "data" (default)  every sub-watershed with at least FRAGMENT_MIN_SHARE (5 %) of the largest one's own rows: ONE export -> its
#                     sub-watershed (the major one); a pooled panel -> every sub-watershed exported. A neighbour's piece or a stray file
#                     (a few % of the rows) is not processed.
#   "major"           the largest sub-watershed only  |  names or ids, e.g. "Koranahalli" or c(1, 7) (names by your 80 % rule)
# Row codes (identical in Python: _location.py):
#   0 kept
#   1 another sub-watershed's data -- its sub-watershed is not processed in this run (a neighbour, a stray file, no id)      FRAGMENT_RULE
#   2 outside every sub-watershed polygon of the shapefile (site_check 3: the export's own id and ring cannot be verified)    FRAGMENT_RULE
#   3 overlap -- a control row of a pixel that is TREATED (core) in another processed sub-watershed; a pixel-year-season already in
#     the sample for another processed sub-watershed; the smaller of two pixels whose footprints overlap >= PIXEL_OVERLAP_MIN       OVERLAP_ROWS
#   4 the pixel's ring differs between its rows (the exports code it differently -- treated in one year, a control in another)   OVERLAP_ROWS
# "drop" (the default of both) leaves them out of EVERY group -- treated and control, pre and post; "keep" keeps them (flagged; the
# results folder says so: _keepFragments / _keepOverlap). Until v20.57 the rule looked at each export FILE: the rows OUTSIDE every
# polygon of a NAMED file stayed in, and the rows without a sub-watershed (site 0) counted as a SECOND sub-watershed in the
# design-based SE ("years within each of 2 sub-watersheds" on your one-sub-watershed panel, with half of the weight).
IN_POLYGON <- c(0L, 1L, 2L, 4L)                 # site_check: 0 confirmed, 1 corrected, 2 assigned, 4 not checked (3 = outside)
LOCATION_TEXT <- c("1" = "another sub-watershed's data (not processed in this run)", "2" = "outside every sub-watershed polygon",
                   "3" = "overlap (a pixel treated in another processed sub-watershed, repeated, or a near-duplicate)",
                   "4" = "the pixel's ring differs between its rows")
# R_P00 still codes every row PER EXPORT FILE (the panel's `fragment` column and site_tagging_by_file.csv: which files carry rows of other
# sub-watersheds) -- a REPORT since v20.58; the models decide by the location rule below. 0 the file's own sub-watershed (the one holding
# MORE than half of the file's rows inside a polygon) or no majority; 1 inside another sub-watershed's polygon; 2 outside, another id.
file_major <- function(site_id, site_check, majority = 0.5) {
  inp <- site_check %in% IN_POLYGON; if (!any(inp)) return(NA_integer_)
  tb <- table(site_id[inp]); k <- which.max(tb)
  if (as.numeric(tb[k]) > majority * sum(inp)) as.integer(names(tb)[k]) else NA_integer_
}
file_codes <- function(site_id, site_check, majority = 0.5) {
  site_id <- as.integer(fifelse(is.na(site_id), 0L, as.integer(site_id))); site_check <- as.integer(fifelse(is.na(site_check), 4L, as.integer(site_check)))
  m <- file_major(site_id, site_check, majority); codes <- integer(length(site_id))
  if (!is.na(m)) { inp <- site_check %in% IN_POLYGON; codes[inp & site_id != m] <- 1L; codes[!inp & site_id != m] <- 2L }
  codes
}
# v20.57 names kept (nothing removed): the PER-FILE fragment coding as a report -- R_P00's `fragment` column and site_tagging_by_file.csv
# use the same codes; the models decide by the location rule (location_codes_R) since v20.58
combo_table_R <- function(counts, majority = 0.5) {                  # counts: g (input id), s (site), c (site_check), n
  counts <- copy(counts)[, code := 0L]
  for (gid in unique(counts$g)) {
    t <- counts[g == gid]; inp <- t$c %in% IN_POLYGON; if (!any(inp)) next
    by <- t[inp, .(n = sum(n)), by = s][order(-n, s)]
    if (by$n[1] <= majority * sum(by$n)) next
    top <- by$s[1]
    counts[g == gid & c %in% IN_POLYGON & s != top, code := 1L]; counts[g == gid & !c %in% IN_POLYGON & s != top, code := 2L]
  }
  counts
}
minor_sites_R <- function(kept, min_share) {                          # kept: data.table site_id, n (code-0 rows)
  if (!nrow(kept)) return(integer(0)); top <- max(kept$n); sort(as.integer(kept[top > 0 & n < min_share * top, site_id]))
}
fragment_table_R <- function(min_share = .opt("FRAGMENT_MIN_SHARE", 0.05)) {
  key <- paste("frag", panel_identity(), min_share); if (!is.null(.DESIGN_CACHE[[key]])) return(.DESIGN_CACHE[[key]])
  out <- list(mode = "none", combos = NULL, kept = data.table(site_id = integer(0), n = integer(0)), minor = integer(0), by_site_code = data.table(site_id = integer(0), code = integer(0), n = integer(0)))
  if (!file.exists(panel_file())) return(out)
  nm <- panel_names()
  cf <- file.path(dirname(panel_file()), "FRAGMENTS_TABLE_R.json"); bsc <- NULL
  j <- tryCatch(if (file.exists(cf)) fromJSON(cf) else NULL, error = function(e) NULL)
  if (!is.null(j) && identical(j$panel, panel_identity())) {
    out$mode <- j$mode; bsc <- as.data.table(j$by_site_code); if (!is.null(j$combos) && length(j$combos)) out$combos <- as.data.table(j$combos)
  }
  if (is.null(bsc)) {
    if (all(c("site_id", "fragment") %in% nm)) {
      x <- panel_read(c("site_id", "fragment")); bsc <- x[, .(n = .N), by = .(site_id = as.integer(site_id), code = as.integer(fragment))]; out$mode <- "column"
    } else if (all(c("site_id", "site_check", "sws_export") %in% nm)) {
      x <- panel_read(c("sws_export", "site_id", "site_check"))
      cnt <- x[, .(n = .N), by = .(g = as.integer(fifelse(is.na(sws_export), 0L, as.integer(sws_export))), s = as.integer(site_id), c = as.integer(fifelse(is.na(site_check), 4L, as.integer(site_check))))]
      out$combos <- combo_table_R(cnt); out$mode <- "fallback"
      bsc <- out$combos[, .(n = sum(n)), by = .(site_id = s, code)]
    } else bsc <- data.table(site_id = integer(0), code = integer(0), n = integer(0))
    try(writeLines(toJSON(list(panel = panel_identity(), mode = out$mode, by_site_code = bsc, combos = out$combos), auto_unbox = TRUE, digits = NA), cf), silent = TRUE)
  }
  out$by_site_code <- bsc
  out$kept <- bsc[code == 0L, .(n = sum(n)), by = site_id]
  out$minor <- minor_sites_R(out$kept, min_share)
  .DESIGN_CACHE[[key]] <- out; out
}
fragment_codes_R <- function(x, tab) {                                # the per-file code of every row of x (0 kept, 1 / 2 in the files, 3 minor site)
  codes <- if ("fragment" %in% names(x)) as.integer(x$fragment) else if (!is.null(tab$combos) && all(c("sws_export", "site_id", "site_check") %in% names(x))) {
    k <- tab$combos[x, on = .(g = sws_export, s = site_id, c = site_check), code]; fifelse(is.na(k), 0L, as.integer(k))
  } else integer(nrow(x))
  codes[is.na(codes)] <- 0L
  if (length(tab$minor) && "site_id" %in% names(x)) codes[as.integer(x$site_id) %in% tab$minor] <- 3L
  codes
}
sites_after_fragments <- function(tab, rule) {                       # v20.58: the processing set of the location rule when given its table
  if (!is.null(tab$own)) return(if (rule == "drop") processing_set_R(tab)$sites else sort(unique(tab$own$site_id)))
  if (tab$mode == "none") return(if (file.exists(panel_file()) && "site_id" %in% panel_names()) sort(unique(as.integer(panel_read("site_id")$site_id))) else integer(0))
  if (rule == "drop") sort(tab$kept[n > 0 & !site_id %in% tab$minor, site_id]) else sort(unique(tab$by_site_code$site_id))
}
.loc_cache_file <- function() file.path(dirname(panel_file()), "LOCATION_TABLE_R.rds")
location_table_R <- function(verbose = FALSE) {
  key <- paste("loc", panel_identity()); if (!is.null(.DESIGN_CACHE[[key]])) return(.DESIGN_CACHE[[key]])
  out <- list(mode = "none", own = data.table(site_id = integer(0), n = numeric(0)), by_site_check = data.table(site_id = integer(0), site_check = integer(0), n = numeric(0)),
              ring_conflict = data.table(site_id = integer(0), pixel_id = character(0)), near_dup = data.table(pixel_id = character(0), keep_pixel = character(0), overlap = numeric(0)),
              n_pixels = 0L, n_pairs = 0L, seconds = 0)
  if (!file.exists(panel_file())) return(out)
  nm <- panel_names(); cf <- .loc_cache_file()
  j <- tryCatch(if (file.exists(cf)) readRDS(cf) else NULL, error = function(e) NULL)
  if (!is.null(j) && identical(j$panel, panel_identity()) && identical(j$overlap_min, PIXEL_OVERLAP_MIN)) { .DESIGN_CACHE[[key]] <- j$tab; return(j$tab) }
  if (!"site_id" %in% nm) { .DESIGN_CACHE[[key]] <- out; return(out) }
  t0 <- Sys.time(); has_chk <- "site_check" %in% nm
  # 1 rows per (sub-watershed, overlay check) -- who is in the panel, and where
  if (HAS_ARROW) {
    ds <- arrow::open_dataset(PANEL_PATH)
    bsc <- as.data.table(dplyr::collect(dplyr::summarise(dplyr::group_by(dplyr::select(ds, dplyr::all_of(c("site_id", if (has_chk) "site_check"))),
                                                                          dplyr::across(dplyr::all_of(c("site_id", if (has_chk) "site_check")))), n = dplyr::n())))
  } else bsc <- panel_read(c("site_id", if (has_chk) "site_check"))[, .(n = .N), by = c("site_id", if (has_chk) "site_check")]
  if (!has_chk) bsc[, site_check := 4L]
  bsc[, `:=`(site_id = as.integer(fifelse(is.na(site_id), 0L, as.integer(site_id))), site_check = as.integer(fifelse(is.na(site_check), 4L, as.integer(site_check))), n = as.numeric(n))]
  bsc <- bsc[, .(n = sum(n)), by = .(site_id, site_check)][order(site_id, site_check)]
  own <- bsc[site_id > 0L & site_check %in% IN_POLYGON, .(n = sum(n)), by = site_id][order(-n, site_id)]
  # 2 a pixel whose ring differs between its rows (inside a polygon): the exports disagree on its ring
  rc <- data.table(site_id = integer(0), pixel_id = character(0))
  if ("buff_km" %in% nm) {
    if (HAS_ARROW) {
      q <- dplyr::select(ds, dplyr::all_of(c("site_id", "pixel_id", "buff_km", if (has_chk) "site_check")))
      if (has_chk) q <- dplyr::filter(q, site_check != 3L)
      q <- dplyr::summarise(dplyr::group_by(q, site_id, pixel_id), bmin = min(buff_km), bmax = max(buff_km))
      rc <- as.data.table(dplyr::collect(dplyr::filter(q, bmin != bmax)))[, .(site_id = as.integer(site_id), pixel_id = as.character(pixel_id))]
    } else {
      x <- panel_read(c("site_id", "pixel_id", "buff_km", if (has_chk) "site_check")); if (has_chk) x <- x[site_check != 3L]
      rc <- x[, .(nr = uniqueN(buff_km)), by = .(site_id, pixel_id)][nr > 1L, .(site_id = as.integer(site_id), pixel_id = as.character(pixel_id))]
    }
  }
  # 3 pixels whose 10 m footprints still overlap >= PIXEL_OVERLAP_MIN (R_P00 merges them; this CONFIRMS it, and drops the smaller one of any
  #   pair that remains -- e.g. a panel written before the merge, or a changed threshold)
  nd <- data.table(pixel_id = character(0), keep_pixel = character(0), overlap = numeric(0)); npx <- 0L; npairs <- 0L
  if (all(c("latitude", "longitude") %in% nm) && exists("near_duplicate_pairs", mode = "function")) {
    if (HAS_ARROW) {
      q <- dplyr::select(ds, dplyr::all_of(c("pixel_id", "latitude", "longitude", if (has_chk) "site_check")))
      if (has_chk) q <- dplyr::filter(q, site_check != 3L)
      reg <- as.data.table(dplyr::collect(dplyr::summarise(dplyr::group_by(q, pixel_id), lat = mean(latitude), lon = mean(longitude), n_rows = dplyr::n())))
    } else {
      x <- panel_read(c("pixel_id", "latitude", "longitude", if (has_chk) "site_check")); if (has_chk) x <- x[site_check != 3L]
      reg <- x[, .(lat = mean(latitude), lon = mean(longitude), n_rows = .N), by = pixel_id]
    }
    reg <- reg[is.finite(lat) & is.finite(lon)]; setorder(reg, pixel_id); npx <- nrow(reg)
    pr <- near_duplicate_pairs(reg); npairs <- nrow(pr)
    if (npairs) {
      a_ <- reg[pr$i]; b_ <- reg[pr$j]; a_wins <- a_$n_rows > b_$n_rows | (a_$n_rows == b_$n_rows & a_$pixel_id < b_$pixel_id)
      nd <- data.table(pixel_id = fifelse(a_wins, b_$pixel_id, a_$pixel_id), keep_pixel = fifelse(a_wins, a_$pixel_id, b_$pixel_id), overlap = pr$overlap)
      nd <- nd[!duplicated(pixel_id)]
    }
  }
  out <- list(mode = if (has_chk) "overlay" else "ids only (no site_check: every row counts as inside its sub-watershed)", own = own, by_site_check = bsc,
              ring_conflict = unique(rc), near_dup = nd, n_pixels = npx, n_pairs = npairs, seconds = as.numeric(difftime(Sys.time(), t0, units = "secs")))
  try(saveRDS(list(panel = panel_identity(), overlap_min = PIXEL_OVERLAP_MIN, tab = out), cf), silent = TRUE)
  if (verbose) info(sprintf("location table of this panel (once; %.0f s): %s rows outside every polygon, %s pixel(s) whose ring differs between rows, %s near-duplicate pixel pair(s) >= %.0f %% of %s pixels",
                            out$seconds, format(sum(bsc[site_check == 3L, n]), big.mark = ","), format(nrow(out$ring_conflict), big.mark = ","), format(npairs, big.mark = ","),
                            100 * PIXEL_OVERLAP_MIN, format(npx, big.mark = ",")))
  .DESIGN_CACHE[[key]] <- out; out
}
# the sub-watersheds THIS run processes (SUB_WATERSHEDS)
processing_set_R <- function(tab, setting = .opt("SUB_WATERSHEDS", "data"), min_share = .opt("FRAGMENT_MIN_SHARE", 0.05)) {
  own <- tab$own[site_id > 0L]
  if (!nrow(own)) return(list(sites = integer(0), how = "no sub-watershed id in the panel: the location rule has nothing to go on (every row is kept)"))
  nm_of <- function(k) { v <- tryCatch(sws_names()[as.character(k)], error = function(e) rep(NA_character_, length(k))); ifelse(is.na(v), paste("site", k), v) }
  st <- as.character(unlist(setting))
  if (length(st) == 1 && tolower(trimws(st)) %in% c("data", "recommended", "auto")) {
    top <- max(own$n); s <- own[n >= min_share * top, site_id]; left <- own[n < min_share * top]
    return(list(sites = sort(as.integer(s)), how = sprintf("data: every sub-watershed with >= %g %% of the largest one's own rows -> %s%s", 100 * min_share,
                paste(sprintf("%s (%d)", nm_of(sort(s)), sort(s)), collapse = ", "),
                if (nrow(left)) sprintf("; not processed: %s", paste(sprintf("%s (%s rows, %.1f %%)", nm_of(left$site_id), format(left$n, big.mark = ","), 100 * left$n / top), collapse = ", ")) else "")))
  }
  if (length(st) == 1 && tolower(trimws(st)) == "major") { s <- own[order(-n, site_id)][1, site_id]; return(list(sites = as.integer(s), how = sprintf("major: %s (%d), the largest", nm_of(s), s))) }
  ids <- suppressWarnings(as.integer(st)); nm <- is.na(ids)
  if (any(nm)) { hit <- match_sws_name(st[nm]); ref <- sws_names(); ids[nm] <- as.integer(names(ref)[match(hit, ref)])
    if (anyNA(ids)) stop("SUB_WATERSHEDS: no sub-watershed matches ", paste(st[is.na(ids)], collapse = ", "), " (your 80 % name rule)") }
  miss <- setdiff(ids, own$site_id)
  if (length(miss) == length(ids)) stop("SUB_WATERSHEDS: none of ", paste(st, collapse = ", "), " is in this panel (it holds ", paste(nm_of(own$site_id), collapse = ", "), ")")
  if (length(miss)) warn("SUB_WATERSHEDS: ", paste(nm_of(miss), collapse = ", "), " not in this panel -- processed: ", paste(nm_of(setdiff(ids, miss)), collapse = ", "))
  s <- sort(unique(setdiff(ids, miss))); list(sites = s, how = sprintf("your setting: %s", paste(sprintf("%s (%d)", nm_of(s), s), collapse = ", ")))
}
# the location code of every row of x (x: site_id, pixel_id, buff_km, Year, Season [, site_check])
location_codes_R <- function(x, tab, S) {
  n <- nrow(x); code <- integer(n); if (!n) return(code)
  sid <- as.integer(x$site_id); sid[is.na(sid)] <- 0L
  chk <- if ("site_check" %in% names(x)) as.integer(x$site_check) else rep(4L, n); chk[is.na(chk)] <- 4L
  code[chk == 3L] <- 2L
  if (length(S)) code[code == 0L & !(sid %in% S)] <- 1L
  if (nrow(tab$ring_conflict)) code[code == 0L & paste(sid, x$pixel_id) %chin% tab$ring_conflict[, paste(site_id, pixel_id)]] <- 4L
  # v20.58: pixel ids compared as text (exact for integer, double and integer64 ids) -- %chin% on the integer ids stopped the run with
  # "table is type 'integer'" whenever near-duplicate pixels were present (found by validate_design_options.py)
  if (nrow(tab$near_dup)) code[code == 0L & as.character(x$pixel_id) %chin% as.character(tab$near_dup$pixel_id)] <- 3L
  k <- which(code == 0L)
  if (length(k)) {                                                     # a control row of a pixel that is TREATED (core) in another sub-watershed
    core <- unique(data.table(pixel_id = x$pixel_id[k], site_id = sid[k])[x$buff_km[k] == 0L])
    if (nrow(core)) {
      cand <- k[x$buff_km[k] > 0L]
      if (length(cand)) { m <- core[data.table(r = cand, pixel_id = x$pixel_id[cand], s = sid[cand]), on = "pixel_id", nomatch = NULL, allow.cartesian = TRUE]
                          bad_r <- unique(m[site_id != s, r]); if (length(bad_r)) code[bad_r] <- 3L }
    }
    k <- which(code == 0L)                                             # a pixel-year-season already in the sample (another sub-watershed): the
    if (length(k)) {                                                   # row nearest its core stays (lower ring, then the lower sub-watershed id)
      o <- data.table(i = k, pixel_id = x$pixel_id[k], Year = x$Year[k], Season = x$Season[k], b = x$buff_km[k], s = sid[k])
      setorder(o, pixel_id, Year, Season, b, s)
      rep_i <- o$i[duplicated(o, by = c("pixel_id", "Year", "Season"))]
      if (length(rep_i)) code[rep_i] <- 3L
    }
  }
  code
}

# ---------------------------------------------------------------- the data-driven design, once per panel version and implementation year
recommend_design_cached <- function(outcome = DESIGN_OUTCOME, treatment_year, fragment_rule, min_share, overlap_rows = "drop", sites = NULL) {
  key <- paste("rec", panel_identity(), outcome, treatment_year, fragment_rule, min_share, overlap_rows, paste(sites, collapse = "+"), "v20.58")
  if (!is.null(.DESIGN_CACHE[[key]])) return(.DESIGN_CACHE[[key]])
  cf <- file.path(dirname(panel_file()), "design_cache", paste0("rec_R_", substr(gsub("[^A-Za-z0-9]", "", key), 1, 12), "_", abs(sum(utf8ToInt(key) * seq_along(utf8ToInt(key)))) %% 1e9, ".json"))
  rec <- tryCatch(if (file.exists(cf)) { j <- fromJSON(cf); if (identical(j$key, key)) j$rec else NULL } else NULL, error = function(e) NULL)
  if (is.null(rec)) {
    rec <- tryCatch(recommend_design(outcome, treatment_year, write = TRUE, fragment_rule = fragment_rule, min_share = min_share, overlap_rows = overlap_rows, sites = sites), error = function(e) { warn("the data-driven design failed: ", conditionMessage(e)); NULL })
    if (!is.null(rec)) try({ dir.create(dirname(cf), recursive = TRUE, showWarnings = FALSE); writeLines(toJSON(list(key = key, rec = rec), auto_unbox = TRUE, digits = NA, null = "null"), cf) }, silent = TRUE)
  } else info(sprintf("design from the data (cached for this panel, implementation year %d): pre %s, post %s, control rings %s, seasons %s", as.integer(treatment_year),
                      paste(rec$pre_window, collapse = ","), paste(rec$post_window, collapse = ","), paste(rec$control_rings, collapse = ","), rec$seasons))
  .DESIGN_CACHE[[key]] <- rec; rec
}

# ---------------------------------------------------------------- the fund workbook under the rule in force (reward_fund.R), cached
fund_tables_R <- function(s, years = NULL) {
  if (!file.exists(FUND_RELEASE_PATH) || !requireNamespace("readxl", quietly = TRUE)) return(NULL)
  years <- years %||% panel_years_R(); if (!length(years)) years <- 2010:2035
  key <- paste("fund", .file_id(FUND_RELEASE_PATH), s$fund_start_rule, s$fund_start_share, s$fund_rate_months, s$fund_dose_before_file, min(years), max(years))
  if (!is.null(.DESIGN_CACHE[[key]])) return(.DESIGN_CACHE[[key]])
  long <- tryCatch(fund_monthly(FUND_RELEASE_PATH), error = function(e) { warn("fund workbook: ", conditionMessage(e)); NULL })
  if (is.null(long) || !nrow(long)) return(NULL)
  ser <- fund_series(long); tim <- fund_timing(ser, rule = s$fund_start_rule, share = s$fund_start_share, rate_months = s$fund_rate_months)
  dose <- fund_season_dose(ser, tim, min(years):max(years), before_file = s$fund_dose_before_file)
  out <- list(timing = tim, dose = dose, series = ser); .DESIGN_CACHE[[key]] <- out; out
}

# v20.59: PRE_YEARS / POST_YEARS -> the year window of the design. A number below 1900 counts years from the start (PRE_YEARS 4 = the 4
# years before it, POST_YEARS 2 = the start year and the next); a CALENDAR year names the bound itself (PRE_YEARS 2015 = the first pre
# year, POST_YEARS 2025 = the last post year). A bound that leaves NO year on its side of the start (PRE_YEARS 2022 with the start in 2022 --
# your v20.58 log: "USED: from 0") is not a window: it is said (DESIGN IN EFFECT + a warning) and every year on that side is used instead.
is_calendar_year <- function(v) length(v) == 1 && is.finite(v) && v >= 1900
year_bounds_R <- function(s, dk, base, usable, rec) {
  notes <- character(0); how_min <- "your setting"; how_max <- "your setting"
  year_min <- if ("pre_years" %in% dk) (if (usable) as.integer(min(rec$pre_window)) else NA_integer_) else if (is.na(s$pre_years)) NA_integer_
              else if (is_calendar_year(s$pre_years)) as.integer(s$pre_years) else as.integer(base - s$pre_years)
  year_max <- if ("post_years" %in% dk) (if (usable) as.integer(max(rec$post_window)) else NA_integer_) else if (is.na(s$post_years)) NA_integer_
              else if (is_calendar_year(s$post_years)) as.integer(s$post_years) else as.integer(base + s$post_years - 1L)
  if (!"pre_years" %in% dk && is.finite(year_min) && year_min >= base) {
    notes <- c(notes, sprintf("PRE_YEARS = %s leaves NO year before the start %d (a calendar year at or after it): every year before the start is used instead. Set PRE_YEARS to the FIRST pre year (e.g. %d), to a number of years before the start (e.g. 7) or NA (every year)",
                              paste(s$pre_years), base, base - 7L))
    how_min <- sprintf("PRE_YEARS %s is not before the start %d -> every year before it", paste(s$pre_years), base); year_min <- NA_integer_
  }
  if (!"post_years" %in% dk && is.finite(year_max) && year_max < base) {
    notes <- c(notes, sprintf("POST_YEARS = %s leaves NO year from the start %d on (a calendar year before it): every year from the start is used instead. Set POST_YEARS to the LAST post year (e.g. %d), to a number of years from the start (e.g. 2) or NA (every year)",
                              paste(s$post_years), base, base + 3L))
    how_max <- sprintf("POST_YEARS %s is before the start %d -> every year from it", paste(s$post_years), base); year_max <- NA_integer_
  }
  list(year_min = year_min, year_max = year_max, notes = notes, how_min = how_min, how_max = how_max,
       setting_min = if ("pre_years" %in% dk) "data" else if (is.na(s$pre_years)) "all" else if (is_calendar_year(s$pre_years)) sprintf("%d (calendar year)", s$pre_years) else sprintf("%d (years before the start)", s$pre_years),
       setting_max = if ("post_years" %in% dk) "data" else if (is.na(s$post_years)) "all" else if (is_calendar_year(s$post_years)) sprintf("%d (calendar year)", s$post_years) else sprintf("%d (years from the start)", s$post_years))
}

model_design <- function(verbose = TRUE, force = FALSE) {
  s <- design_settings()
  key <- paste(deparse(s), collapse = ""); key <- paste(key, panel_identity(), .file_id(FUND_RELEASE_PATH), .file_id(SITES_CSV))
  if (!force && identical(.DESIGN_CACHE$design_key, key)) return(.DESIGN_CACHE$design)
  ch <- list(); notes <- character(0); per_site <- list(); n_fund <- 0L
  add_ch <- function(option, setting, used, from) ch[[length(ch) + 1L]] <<- data.table(option = option, your_setting = paste(setting, collapse = ","), used = paste(used, collapse = ","), from = from)
  loc <- location_table_R(verbose = TRUE)                                      # v20.58: WHERE every row is (once per panel)
  ps <- processing_set_R(loc, s$sub_watersheds, s$fragment_min_share)          # and which sub-watersheds THIS run processes
  real <- if (identical(s$fragment_rule, "drop") || !length(ps$sites)) ps$sites else sort(unique(loc$own$site_id[loc$own$site_id > 0]))
  n_out <- sum(loc$by_site_check[site_check == 3L, n]); n_other <- sum(loc$by_site_check[site_check != 3L & !(site_id %in% ps$sites), n])
  if (!length(ps$sites)) n_other <- 0
  reg <- tryCatch(fread(SITES_CSV), error = function(e) data.table(SWSiD_All = integer(0), treatment_year = numeric(0)))
  reg_year <- function(k) { y <- reg$treatment_year[match(k, reg$SWSiD_All)]
    if (length(y) && is.finite(y)) list(year = as.integer(y), src = "registry") else list(year = s$treatment_year, src = sprintf("TREATMENT_YEAR %d (neither the fund file nor the registry dates it)", s$treatment_year)) }
  add_ch("DESIGN_MODE", s$design_mode, s$design_mode, "your setting")
  ss <- data.table(site_id = integer(0), year = integer(0), season = integer(0)); sy <- data.table(site_id = integer(0), year = integer(0))
  if (s$timing == "fund") {
    ft <- fund_tables_R(s)
    if (!is.null(ft)) {
      tt <- ft$timing[(!length(real) | site_id %in% real) & !is.na(first_treated_year)]
      if (nrow(tt)) { ss <- tt[, .(site_id = as.integer(site_id), year = as.integer(first_treated_year), season = as.integer(first_treated_season))]
        for (i in seq_len(nrow(tt))) per_site[[length(per_site) + 1L]] <- list(tt$site_id[i], tt$first_treated_label[i], sprintf("fund file: start %s (%s; %s)", tt$start_month[i], tt$start_rule[i], substr(tt$start_how[i], 1, 60))) }
    } else notes <- c(notes, sprintf("the fund workbook %s is not available: every sub-watershed falls back to its registry year", FUND_RELEASE_PATH))
    n_fund <- nrow(ss)                                                           # dated by the fund file, before any fallback
    for (k in setdiff(real, ss$site_id)) { r <- reg_year(k); ss <- rbind(ss, data.table(site_id = k, year = r$year, season = 3L))
      per_site[[length(per_site) + 1L]] <- list(k, sprintf("Zaid %d (whole year)", r$year), paste("NOT in the fund file ->", r$src))
      notes <- c(notes, sprintf("sub-watershed %d is not dated by the fund file: %s %d is used", k, r$src, r$year)) }
    setorder(ss, site_id); sy <- ss[, .(site_id, year = year + as.integer(season == 2L))]
    base <- if (nrow(ss)) min(ss$year) else s$treatment_year
    if (!nrow(ss)) notes <- c(notes, sprintf("no sub-watershed id in the panel: every row uses TREATMENT_YEAR %d", s$treatment_year))
    add_ch("TREATMENT_TIMING", "fund", "fund: first treated season per sub-watershed", paste("the fund workbook", FUND_RELEASE_PATH))
  } else if (s$timing == "registry") {
    for (k in real) { r <- reg_year(k); sy <- rbind(sy, data.table(site_id = k, year = r$year)); per_site[[length(per_site) + 1L]] <- list(k, as.character(r$year), r$src)
      if (grepl("TREATMENT_YEAR", r$src)) notes <- c(notes, sprintf("sub-watershed %d: implementation year UNKNOWN -> %s", k, r$src)) }
    base <- if (nrow(sy)) min(sy$year) else s$treatment_year
    add_ch("TREATMENT_TIMING", "registry", "registry: implementation year per sub-watershed", "data/sites/sites.csv")
  } else { base <- s$treatment_year; add_ch("TREATMENT_TIMING", "fixed", sprintf("fixed: %d for every sub-watershed", s$treatment_year), "your TREATMENT_YEAR") }
  add_ch("TREATMENT_YEAR", s$treatment_year, base, if (s$timing == "fixed") "your setting" else sprintf("the earliest first treated year of the %d sub-watershed(s) (the base of PRE_YEARS / POST_YEARS); yours = the fall-back", length(per_site)))
  for (p in per_site) add_ch(sprintf("  start of sub-watershed %d", as.integer(p[[1]])), sprintf("(from TREATMENT_TIMING = %s)", s$timing), p[[2]], p[[3]])
  # ---- the options set to "data"
  dk <- c(if (is_data_opt(s$control_rings)) "control_rings", if (identical(s$pre_years, "data")) "pre_years", if (identical(s$post_years, "data")) "post_years", if (identical(s$seasons_setting, "auto")) "seasons")
  rec <- NULL; usable <- FALSE
  if (length(dk) && s$design_mode == "recommended" && file.exists(panel_file())) {
    rec <- recommend_design_cached(DESIGN_OUTCOME, base, s$fragment_rule, s$fragment_min_share, s$overlap_rows, sites = ps$sites)
    usable <- !is.null(rec) && length(rec$pre_window) > 0 && length(rec$post_window) > 0
    if (!usable) notes <- c(notes, paste0("the data-driven design found no usable pre AND post window", if (!is.null(rec)) sprintf(" (export breaks %s, fill years %s)", paste(rec$breaks, collapse = ","), paste(rec$fill_years, collapse = ",")) else "",
                                          " -> every ring / every year is used for the options set to 'data'"))
  }
  src_d <- if (usable) sprintf("the data (DESIGN_RECOMMENDATION.md, %s, implementation year %d)", DESIGN_OUTCOME, base) else if (s$design_mode == "manual") "DESIGN_MODE = 'manual': 'data' = every ring / every year" else "no usable data-driven window: every ring / every year"
  rings <- if ("control_rings" %in% dk) (if (usable) as.integer(rec$control_rings) else 1:5) else s$control_rings
  yb <- year_bounds_R(s, dk, base, usable, rec); year_min <- yb$year_min; year_max <- yb$year_max; notes <- c(notes, yb$notes)   # v20.59: counts OR calendar years
  if (is.finite(year_min) && is.finite(year_max) && year_min > year_max) stop(sprintf("the year window is empty (%d > %d): check PRE_YEARS / POST_YEARS", year_min, year_max))
  drop_years <- if (usable && any(c("pre_years", "post_years") %in% dk) && identical(s$outcome_screen, "drop")) sort(as.integer(Filter(function(y) (!is.finite(year_min) || y >= year_min) && (!is.finite(year_max) || y <= year_max), as.integer(unlist(rec$fill_years))))) else integer(0)   # v20.59: OUTCOME_SCREEN keep / off keeps the fill years too
  seas <- if ("seasons" %in% dk) (if (usable) normalize_seasons(rec$seasons) else "all") else s$seasons_setting
  add_ch("CONTROL_RINGS", if ("control_rings" %in% dk) "data" else s$control_rings, rings, if ("control_rings" %in% dk) src_d else "your setting")
  add_ch("PRE_YEARS", yb$setting_min, if (is.finite(year_min)) paste("from", year_min) else "every year before the start", if ("pre_years" %in% dk) src_d else yb$how_min)
  add_ch("POST_YEARS", yb$setting_max, if (is.finite(year_max)) paste("to", year_max) else "every year from the start", if ("post_years" %in% dk) src_d else yb$how_max)
  if (length(drop_years)) add_ch("  years left out", "(from PRE_YEARS / POST_YEARS = data)", drop_years, "fill years of the data-driven window (not data)")
  add_ch("SEASONS", s$seasons_setting, seas, if ("seasons" %in% dk) src_d else "your setting")
  for (k in c("EXCLUDE_TRANSITION_YEAR", "UNIT_FE", "COHORT_OFFSET")) add_ch(k, s[[tolower(k)]], s[[tolower(k)]], "your setting")
  add_ch("SUB_WATERSHEDS", paste(s$sub_watersheds, collapse = ","), if (length(ps$sites)) ps$sites else "none (no sub-watershed id)", ps$how)
  add_ch("FRAGMENT_RULE", s$fragment_rule, s$fragment_rule, sprintf("your setting: rows of sub-watersheds NOT processed %s, rows outside every polygon %s -- %s (treated and control, pre and post)",
                                                                     format(n_other, big.mark = ","), format(n_out, big.mark = ","), if (s$fragment_rule == "drop") "left out" else "KEPT"))
  add_ch("OVERLAP_ROWS", s$overlap_rows, s$overlap_rows, sprintf("your setting: %s pixel(s) whose ring differs between rows, %s near-duplicate pair(s), pixels treated in another processed sub-watershed / repeated -- %s",
                                                                   format(nrow(loc$ring_conflict), big.mark = ","), format(loc$n_pairs, big.mark = ","), if (s$overlap_rows == "drop") "left out" else "KEPT"))
  add_ch("POOLED_FE", s$pooled_fe, if (length(real) > 1) s$pooled_fe else paste(s$pooled_fe, "(one sub-watershed: the same as 'period')"), "your setting")
  add_ch("DOSE_VARIABLE", s$dose_variable, s$dose_variable, "your setting (fund file; controls and untreated periods 0)")
  add_ch("FUND_START_RULE", s$fund_start_rule, s$fund_start_rule, paste0("your setting", if (s$timing != "fund") " (used for the dose only: TREATMENT_TIMING is not 'fund')" else ""))
  add_ch("EXCLUDE_GAPFILLED", s$exclude_gapfilled, s$exclude_gapfilled, "your setting")
  add_ch("OUTCOME_SCREEN", s$outcome_screen, s$outcome_screen, paste0("your setting", c(drop = " (a year-season constant across pixels -- a fill value -- or with collapsed coverage leaves the model; evidence: OUTCOME_SCREEN_<outcome>.csv)",
                                                                             keep = " (such year-seasons are reported and KEPT; results tagged _screenKept)", off = " (no screen)")[[s$outcome_screen]]))
  add_ch("DESIGN_SOURCE", s$design_source, s$design_source, paste0("your setting", c(panel = " (the PANEL's treat / control / pre / post / did -- the exports' Treat flag, PERIOD_RULE -- are estimated on; the design in effect above is compared with them)",
                                                                       model = " (the design in effect above is estimated on -- design-based modelling; DESIGN_SOURCE <- \"panel\" estimates on the panel's columns)")[[s$design_source]]))
  add_ch("CONTROL_SELECTION", s$control_selection, s$control_selection, paste0("your setting", switch(s$control_selection,
         rings = " (every ring of CONTROL_RINGS is the control group)",
         pre_rings = sprintf(" (per outcome, the %d ring(s) whose PRE-period series is closest to the treatment area's -- '%s'; decided on the pre period only, the same pixels in every year and season; CONTROL_SELECTION_<outcome>_R.csv)", s$control_select_k, s$control_select_on),
         pre_blocks = sprintf(" (per outcome, ~%.1f km blocks of control pixels closest to the treatment area's PRE-period series -- '%s' -- until %g x the treated pixels; the same pixels in every year and season; CONTROL_SELECTION_<outcome>_R.csv)", s$control_block_deg * 111, s$control_select_on, s$control_select_ratio))))
  add_ch("DONUT_RINGS", if (length(s$donut_rings)) paste(s$donut_rings, collapse = ",") else "none", if (length(s$donut_rings)) paste(s$donut_rings, collapse = ",") else "none", "your setting (rings left out of the control pool -- the spillover buffer next to the core)")
  add_ch("LANDUSE_KEEP", paste(s$landuse_keep, collapse = ","), paste(s$landuse_keep, collapse = ","), "your setting (a pixel is kept by its PRE-period land-use class)")
  add_ch("BASELINE_NDVI_MIN", s$baseline_ndvi_min, s$baseline_ndvi_min, "your setting (a pixel's pre-period mean NDVI must exceed it)")
  add_ch("MIN_PIXEL_COVERAGE_PCT", s$min_pixel_coverage_pct, s$min_pixel_coverage_pct, "your setting (a year-season below this share of the typical coverage is screened out)")
  add_ch("DROP_SINGLETONS", s$drop_singletons, s$drop_singletons, "your setting (series seen once leave before the demeaning)")
  add_ch("PRECISION_TOLERANCE", s$precision_tolerance, s$precision_tolerance, "your setting (|value| <= tolerance is the no-data zero; a year-season is constant within it)")
  add_ch("SAME_PIXELS", s$same_pixels, s$same_pixels, paste0("your setting", c(pre_post = " (every treated and control pixel is observed in pre AND post; a pixel seen on one side only leaves -- the groups are the same pixels across the panel)",
                                                                   all = " (every pixel is observed in every year-season of the sample: a balanced pixel set)", off = " (a pixel may contribute to one side only -- the v20.58 sample)")[[s$same_pixels]]))
  add_ch("CLUSTER", s$cluster, s$cluster, paste0("your setting", if (identical(s$cluster, "block")) " (~1 km spatial blocks of pixels -- many clusters, the spatial correlation of neighbouring pixels absorbed)" else sprintf(" (the sub-watershed; fewer than %d sub-watersheds -> the years)", MIN_SWS_CLUSTERS)))
  add_ch("COVARIATES", if (length(s$covariates)) s$covariates else "none", if (length(s$covariates)) s$covariates else "none", "your setting")
  d <- list(design_mode = s$design_mode, timing = s$timing, treatment_year = as.integer(base), treatment_year_setting = s$treatment_year,
            site_start = ss, site_years = sy, control_rings = as.integer(rings), year_min = year_min, year_max = year_max, drop_years = drop_years,
            pre_window = if (usable && "pre_years" %in% dk) as.integer(unlist(rec$pre_window)) else NULL, post_window = if (usable && "post_years" %in% dk) as.integer(unlist(rec$post_window)) else NULL,
            seasons = seas, seasons_setting = s$seasons_setting, exclude_transition_year = s$exclude_transition_year, unit_fe = s$unit_fe,
            cohort_offset = s$cohort_offset, overlap_rows = s$overlap_rows, fragment_rule = s$fragment_rule, fragment_min_share = s$fragment_min_share,
            pooled_fe = s$pooled_fe, dose_variable = s$dose_variable, exclude_gapfilled = s$exclude_gapfilled, covariates = s$covariates,
            outcome_screen = s$outcome_screen, design_source = s$design_source,                  # v20.59
            control_selection = s$control_selection, control_select_k = s$control_select_k, control_select_ratio = s$control_select_ratio,   # v20.59 (your fifth request)
            control_select_on = s$control_select_on, control_block_deg = s$control_block_deg, cluster = s$cluster, same_pixels = s$same_pixels,
            donut_rings = s$donut_rings, landuse_keep = s$landuse_keep, baseline_ndvi_min = s$baseline_ndvi_min, min_pixel_coverage_pct = s$min_pixel_coverage_pct,   # spec 1 / 3
            drop_singletons = s$drop_singletons, precision_tolerance = s$precision_tolerance,
            fund = list(start_rule = s$fund_start_rule, start_share = s$fund_start_share, rate_months = s$fund_rate_months, before_file = s$fund_dose_before_file),
            n_sites = length(real), sites = as.integer(real), n_fund_dated = as.integer(n_fund), data_keys = dk, choices = rbindlist(ch), notes = notes,
            sub_watersheds = s$sub_watersheds, processed = as.integer(ps$sites), processed_how = ps$how)
  if (verbose) {
    cc <- d$choices; w <- max(nchar(cc$option))
    info("DESIGN IN EFFECT (v20.59: every option is applied here, at the model stage -- the panel is not rebuilt):\n",
         paste(sprintf("  %-*s  your setting: %-34s  USED: %-48s  <- %s", w, cc$option, substr(cc$your_setting, 1, 34), substr(cc$used, 1, 48), substr(cc$from, 1, 90)), collapse = "\n"))
    for (n_ in notes) warn(n_)
  }
  .DESIGN_CACHE$design_key <- key; .DESIGN_CACHE$design <- d
  d
}
load_design <- function() model_design(verbose = is.null(.DESIGN_CACHE$design_key))
cov_tag <- function(cv) { cv <- as.character(cv); if (!length(cv)) return("covNone"); if (identical(sort(cv), sort(c("Rain", "Tmax", "Tmean", "Tmin")))) return("covAll4"); paste0("cov", paste(substr(cv, 1, 4), collapse = "-")) }
scenario_tag <- function(d) {
  r <- d$control_rings %||% CONTROL_RINGS; r <- as.integer(r)
  zs <- if (length(r) > 1 && identical(r, seq(min(r), max(r)))) sprintf("%d-%d", min(r), max(r)) else paste(r, collapse = "+")
  fr <- d$fund %||% list(start_rule = "backcast", start_share = 0.1, rate_months = 12L)
  rule_tag <- paste0(switch(fr$start_rule %||% "backcast", share = sprintf("Share%d", round(100 * (fr$start_share %||% 0.1))), file_start = "FileStart", ""),
                     if (!is.null(fr$rate_months) && as.integer(fr$rate_months) != 12L) sprintf("Rate%d", as.integer(fr$rate_months)) else "")
  # v20.57: "treatFund" only when the fund file dated at least one sub-watershed; a fund timing that fell back to the registry for
  # every sub-watershed (no workbook) says so: _siteyrs<years>_fundMissing (as Python)
  fund_t <- identical(d$timing, "fund") && NROW(d$site_start) > 0 && isTRUE(as.integer(d$n_fund_dated %||% 1L) > 0L)
  t <- sprintf("ctrl%s_treat%s", zs, if (fund_t) paste0("Fund", rule_tag) else as.character(as.integer(d$treatment_year %||% TREATMENT_YEAR)))
  if ((identical(d$timing, "registry") || (identical(d$timing, "fund") && !fund_t)) && NROW(d$site_years)) t <- paste0(t, "_siteyrs", paste(sort(unique(d$site_years$year)), collapse = "-"))
  if (identical(d$timing, "fund") && !fund_t) t <- paste0(t, "_fundMissing")
  if (isTRUE(d$exclude_transition_year)) t <- paste0(t, "_noTransition")
  if (isTRUE(as.integer(d$cohort_offset %||% 0L) != 0L)) t <- paste0(t, sprintf("_cohort%+d", as.integer(d$cohort_offset)))
  t <- paste0(t, "_", normalize_seasons(d$seasons %||% SEASONS))
  if (identical(d$pooled_fe, "site_period") && (d$n_sites %||% 2L) > 1) t <- paste0(t, "_feSitePeriod")
  if (identical(d$unit_fe, "pixel")) t <- paste0(t, "_fePixel")
  if (identical(d$overlap_rows %||% OVERLAP_ROWS, "keep")) t <- paste0(t, "_keepOverlap")
  if (identical(d$fragment_rule, "keep")) t <- paste0(t, "_keepFragments") else if (!is.null(d$fragment_min_share) && abs(d$fragment_min_share - 0.05) > 1e-12) t <- paste0(t, sprintf("_frag%g", round(100 * d$fragment_min_share, 3)))
  sw <- d$sub_watersheds %||% "data"                                              # v20.58: a processing set you chose has its own folder
  if (!identical(sw, "data")) t <- paste0(t, if (identical(sw, "major")) "_swsMajor" else paste0("_sws", paste(sort(as.integer(d$processed %||% integer(0))), collapse = "-")))
  if (!is.null(d$dose_variable) && d$dose_variable != "dose_intensity_per_ha") t <- paste0(t, c(dose_amount_sws = "_doseAmount", dose_share_of_target = "_doseShare")[[d$dose_variable]])
  if (identical(fr$before_file, "missing")) t <- paste0(t, "_doseObsOnly")
  if (isFALSE(d$exclude_gapfilled)) t <- paste0(t, "_withGapFilled")
  if (identical(d$outcome_screen, "keep")) t <- paste0(t, "_screenKept")                        # v20.59: the screen's cells kept (as Python)
  if (identical(d$design_source, "panel")) t <- paste0(t, "_panelDesign")                       # v20.59: the panel's design estimated on (as Python)
  cs <- d$control_selection %||% "rings"                                                        # v20.59: the pre period's control choice (as Python)
  if (cs %in% c("pre_rings", "pre_blocks")) t <- paste0(t, if (identical(cs, "pre_rings")) sprintf("_ctrlPre%dr", as.integer(d$control_select_k %||% 2L)) else sprintf("_ctrlPreBlk%gx", as.numeric(d$control_select_ratio %||% 3)),
                                                      c(trend = "", level = "L", both = "B")[[d$control_select_on %||% "trend"]])
  if (identical(d$cluster, "block")) t <- paste0(t, "_clBlock")                                  # v20.59: ~1 km spatial blocks as clusters (as Python)
  spx <- d$same_pixels %||% "pre_post"; if (identical(spx, "all")) t <- paste0(t, "_pixAll") else if (identical(spx, "off")) t <- paste0(t, "_pixAny")   # v20.59 (as Python)
  if (length(d$donut_rings %||% integer(0))) t <- paste0(t, "_donut", paste(d$donut_rings, collapse = "-"))                                          # spec 1 (as Python)
  if (!identical(d$landuse_keep %||% "all", "all")) t <- paste0(t, "_lu", paste(d$landuse_keep, collapse = "-"))
  if (is.finite(d$baseline_ndvi_min %||% NA)) t <- paste0(t, sprintf("_ndviPre%g", d$baseline_ndvi_min))
  if (abs((d$min_pixel_coverage_pct %||% 0.05) - 0.05) > 1e-12) t <- paste0(t, sprintf("_cov%d", as.integer(round(100 * d$min_pixel_coverage_pct))))
  if (isTRUE(d$drop_singletons)) t <- paste0(t, "_noSingle")
  t <- paste0(t, "_", cov_tag(d$covariates %||% COVARIATES))
  if (is.finite(d$year_min %||% NA) || is.finite(d$year_max %||% NA))
    t <- paste0(t, sprintf("_yr%s-%s", if (is.finite(d$year_min %||% NA)) d$year_min else "start", if (is.finite(d$year_max %||% NA)) d$year_max else "end"))
  if (length(d$drop_years)) t <- paste0(t, "_no", paste(d$drop_years, collapse = "-"))
  t
}

# ---------------------------------------------------------------- the design columns of the timing in force (as Python's build_treatment_columns)
# v20.59: the design IN EFFECT against the panel's own post column (the exports' Treat flag, R_P00 panel_design_columns_R): the same on every
# row, or on how many rows they differ. The DESIGN's columns are what the model estimates on -- your settings (the fund timing, TREATMENT_YEAR,
# the transition year); the panel's are the exporter's default. cmp = c(rows compared, rows that differ); NULL = the panel carries no post column.
design_timing_text_R <- function(d) switch(d$timing %||% "fixed",
  fund = sprintf("fund timing: the first treated season per sub-watershed, base year %d", as.integer(d$treatment_year)),
  registry = sprintf("registry timing, base year %d", as.integer(d$treatment_year)),
  sprintf("fixed: post = Year >= %d%s", as.integer(d$treatment_year), if (isTRUE(d$exclude_transition_year)) " with the transition year held out" else ""))
design_vs_panel_say_R <- function(cmp, d) {
  if (is.null(cmp)) {
    if (is.null(.DESIGN_CACHE$no_post_column_said)) { .DESIGN_CACHE$no_post_column_said <- TRUE
      info("this panel carries no post column (built before v20.59): the design in effect is used as it is -- re-run R_P00 to get the exports' design columns (treat, control, pre, post, did) into the panel") }
    return(invisible(NULL))
  }
  n <- as.numeric(cmp[1]); k <- as.numeric(cmp[2]); if (!is.finite(n) || n <= 0) return(invisible(NULL))
  src <- d$design_source %||% "model"
  if (k == 0) info(sprintf("DESIGN vs PANEL: the design in effect (%s) gives the same post period as the panel's post column (the exports' Treat flag) on every one of %s rows%s", design_timing_text_R(d), format(n, big.mark = ","),
                           if (identical(src, "panel")) " -- DESIGN_SOURCE = \"panel\": the panel's columns are estimated on" else ""))
  else if (identical(src, "panel")) info(sprintf("DESIGN vs PANEL: DESIGN_SOURCE = \"panel\" -- this model estimates on the PANEL's post / pre / did (the exports' Treat flag, PERIOD_RULE); the design in effect (%s) would differ on %s of %s rows (%.1f %%) -- set DESIGN_SOURCE <- \"model\" to estimate on it (your settings: TREATMENT_TIMING / TREATMENT_YEAR / EXCLUDE_TRANSITION_YEAR)",
                                                 design_timing_text_R(d), format(k, big.mark = ","), format(n, big.mark = ","), 100 * k / n))
  else info(sprintf("DESIGN vs PANEL: the design in effect (%s) differs from the panel's post column (the exports' Treat flag, R_P00) on %s of %s rows (%.1f %%) -- the DESIGN's columns are what this model estimates on (your settings: TREATMENT_TIMING / TREATMENT_YEAR / EXCLUDE_TRANSITION_YEAR); the panel's are the exporter's default",
                    design_timing_text_R(d), format(k, big.mark = ","), format(n, big.mark = ","), 100 * k / n))
  invisible(NULL)
}
# ================================================================ v20.59 (your fifth request): the control group chosen on the PRE period
# CONTROL_SELECTION -- "rings" (every ring of CONTROL_RINGS) | "pre_rings" (per outcome, the CONTROL_SELECT_K rings whose PRE-period series is
# closest to the treatment area's) | "pre_blocks" (~1 km blocks of control pixels, the closest first, until CONTROL_SELECT_RATIO x the treated
# pixels). The decision is a function of the PRE period alone, made once per outcome and kept for every year and season (the same control
# pixels across the whole panel); a rule on the post period, the outcome's overall mean or the result is refused (it selects on the outcome).
# The same numbers as Python's select_controls (in memory and out of core: the parent merges the partitions' sums exactly).
control_selection_R <- function(v) {
  s <- gsub("[- ]", "_", tolower(trimws(as.character(v)[1])))
  if (s %in% c("ring", "all", "all_rings", "none", "off", "false")) s <- "rings"
  if (s %in% c("pre_ring", "prerings", "pre", "pre_trend", "pretrend")) s <- "pre_rings"
  if (s %in% c("pre_block", "preblocks", "blocks", "block")) s <- "pre_blocks"
  if (grepl("post|mean|outcome|best|signif|result", s))
    stop("CONTROL_SELECTION \"", v, "\": choosing the control group on the POST period, on the outcome's overall mean or on the result selects on the outcome -- ",
         "the estimate is then biased by construction. Use \"pre_rings\" or \"pre_blocks\" (the PRE period decides, the same pixels in every year and season) or \"rings\"")
  if (!s %in% c("rings", "pre_rings", "pre_blocks")) stop("CONTROL_SELECTION must be \"rings\", \"pre_rings\" or \"pre_blocks\" (got \"", v, "\")")
  s
}
block_id_R <- function(pixel_id, deg = 0.01) {                                      # Python's block_id_from_pixel: the ~1 km block from the id alone
  units <- max(1, round(deg * 1e5))
  s <- if (is.character(pixel_id)) pixel_id else if (inherits(pixel_id, "integer64")) as.character(pixel_id) else sprintf("%.0f", as.numeric(pixel_id))
  has <- grepl("_", s, fixed = TRUE); ls <- numeric(length(s)); lo <- numeric(length(s))
  if (any(has)) { p <- tstrsplit(s[has], "_", fixed = TRUE); ls[has] <- as.numeric(p[[1]]); lo[has] <- as.numeric(p[[2]]) }
  if (any(!has)) { z <- s[!has]; z <- paste0(strrep("0", pmax(0L, 18L - nchar(z))), z); n <- nchar(z); ls[!has] <- as.numeric(substr(z, 1, n - 9)); lo[!has] <- as.numeric(substr(z, n - 8, n)) }
  (ls %/% units) * 1e6 + (lo %/% units)
}
block_ids_R <- function(x, deg = 0.01) {                                           # Python's block_ids: the id when it encodes the coordinates, else the
  b <- block_id_R(x$pixel_id, deg)                                                  #   frame's latitude / longitude (a synthetic panel with plain ids)
  if (all(b < 1e6) && all(c("latitude", "longitude") %in% names(x)) && all(is.finite(x$latitude)) && all(is.finite(x$longitude))) {
    units <- max(1, round(deg * 1e5)); b <- (round((x$latitude + 90) * 1e5) %/% units) * 1e6 + (round((x$longitude + 180) * 1e5) %/% units)
  }
  b
}
control_selection_facts_R <- function(x, o, d) {
  mode <- d$control_selection %||% "rings"
  m <- x[post == 0L & is.finite(get(o)), intersect(c("pixel_id", "buff_km", "Year", "Season", "treat", "latitude", "longitude", o), names(x)), with = FALSE]
  m[, unit := if (identical(mode, "pre_rings")) as.numeric(buff_km) else block_ids_R(m, d$control_block_deg %||% 0.01)]
  tt <- m[treat == 1L]; cc <- m[treat == 0L]
  list(agg_t = tt[, .(s = sum(get(o)), n = .N), by = .(Year, Season)], t_pixels = uniqueN(tt$pixel_id),
       agg_c = cc[, .(s = sum(get(o)), n = .N), by = .(unit, Year, Season)], pix_c = cc[, .(pixels = uniqueN(pixel_id)), by = unit], mode = mode)
}
control_selection_decide_R <- function(facts, o, d) {
  mode <- facts$mode; on <- d$control_select_on %||% "trend"
  agg_t <- facts$agg_t[, .(s = sum(s), n = sum(n)), by = .(Year, Season)]; agg_c <- facts$agg_c[, .(s = sum(s), n = sum(n)), by = .(unit, Year, Season)]
  pix_c <- facts$pix_c[, .(pixels = sum(pixels)), by = unit]
  if (!nrow(agg_t) || !nrow(agg_c)) stop(sprintf("CONTROL_SELECTION: no pre-period rows of %s to decide on (treated cells %d, control cells %d)", o, nrow(agg_t), nrow(agg_c)))
  agg_t[, `:=`(m_t = s / n, ti = Year * 10 + Season)]; mt_all <- sum(agg_t$s) / sum(agg_t$n)
  g <- merge(agg_c, agg_t[, .(Year, Season, m_t, ti)], by = c("Year", "Season")); g[, dif := s / n - m_t]
  if (!nrow(g)) stop(sprintf("CONTROL_SELECTION: no control unit shares a pre-period cell with the treatment area (%s)", o))
  tab <- g[, { lev <- mean(dif); xx <- ti - mean(ti); sxx <- sum(xx^2)
               .(pre_cells = .N, pre_rows = sum(n), pre_mean_control = sum(s) / sum(n), pre_mean_treated = mt_all, level_gap = lev, trend_distance = mean(abs(dif - lev)),
                 slope_difference_per_period = if (sxx > 0) sum(xx * (dif - lev)) / sxx else 0, rmse_gap = sqrt(mean(dif^2))) }, by = unit]
  tab <- merge(tab, pix_c, by = "unit", all.x = TRUE); tab[is.na(pixels), pixels := 0L]; setnames(tab, "pixels", "pre_pixels")
  tab[, score := switch(on, trend = trend_distance, level = abs(level_gap), both = trend_distance + abs(level_gap), rmse = rmse_gap)]
  tab[, candidate := pre_cells >= max(1, ceiling(0.5 * nrow(agg_t)))]
  if (identical(mode, "pre_blocks")) tab[, candidate := candidate & pre_pixels >= .opt("CONTROL_BLOCK_MIN_PIXELS", 30L)]
  tab[, cand_i := as.integer(candidate)]; setorder(tab, -cand_i, score, unit); tab[, cand_i := NULL]; tab[, rank := .I]
  chosen <- if (identical(mode, "pre_rings")) head(tab[candidate == TRUE, unit], as.integer(d$control_select_k %||% 2L)) else {
    need <- as.numeric(d$control_select_ratio %||% 3) * max(1, facts$t_pixels); ch <- numeric(0); got <- 0
    for (i in which(tab$candidate)) { ch <- c(ch, tab$unit[i]); got <- got + tab$pre_pixels[i]; if (got >= need) break }
    ch }
  tab[, selected := unit %in% chosen]; tab[, `:=`(outcome = o, kind = if (identical(mode, "pre_rings")) "ring" else "block", rule = on)]
  setcolorder(tab, c("outcome", "kind", "unit", "pre_cells", "pre_rows", "pre_pixels", "pre_mean_control", "pre_mean_treated", "level_gap", "trend_distance",
                     "slope_difference_per_period", "rmse_gap", "score", "candidate", "rank", "selected", "rule"))
  list(tab = tab, chosen = as.numeric(chosen))
}
record_control_selection_R <- function(tab, chosen, o, d, say = TRUE) {
  mode <- d$control_selection; ch <- tab[selected == TRUE]
  try(fwrite(tab, file.path(RESULTS_DIR, sprintf("CONTROL_SELECTION_%s_R.csv", o))), silent = TRUE)
  if (say) info(sprintf("CONTROL_SELECTION = \"%s\" (%s): decided on the PRE period only (%s), fixed for the whole panel -- %s chosen of %d (pre-trend distance %s; level gap %s); %s control pixels for %s candidates -> CONTROL_SELECTION_%s_R.csv",
                        mode, o, d$control_select_on %||% "trend", if (identical(mode, "pre_rings")) paste0("ring(s) ", paste(chosen, collapse = ", ")) else paste0("block(s) ", length(chosen)), nrow(tab),
                        paste(signif(head(ch$trend_distance, 5), 4), collapse = ", "), paste(sprintf("%+.4g", head(ch$level_gap, 5)), collapse = ", "),
                        format(sum(ch$pre_pixels), big.mark = ","), format(sum(tab$pre_pixels), big.mark = ","), o))
  if (say && identical(mode, "pre_rings") && any(!tab$selected)) { w <- min(tab[selected == FALSE, trend_distance]); b <- max(ch$trend_distance)
    if (is.finite(w) && b > w) warn(sprintf("CONTROL_SELECTION (%s): the rule '%s' kept a ring whose pre-trend distance (%.4g) is larger than a left-out ring's (%.4g) -- 'trend' is what the parallel-trends assumption asks for", o, d$control_select_on, b, w)) }
  list(outcome = o, mode = mode, units = as.numeric(chosen))
}
# v20.59 (your rule): the treated and control groups are the SAME pixels across the panel -- "pre_post": a pixel with an outcome only before or only
# after treatment leaves; "all": a pixel missing any year-season of the sample leaves (a balanced pixel set); "off": the v20.58 sample. As Python's
# same_pixels_rule, in memory and out of core (pixel partitions); confirmed by the sample integrity.
pixels_one_side_R <- function(x, rule) {
  if (identical(rule, "off") || !nrow(x) || !"pixel_id" %in% names(x)) return(0L)
  if (identical(rule, "pre_post")) { if (!"post" %in% names(x)) return(0L); g <- x[, .(mn = min(post), mx = max(post)), by = pixel_id]; return(sum(g$mn != 0L | g$mx != 1L)) }
  cells <- as.integer(x$Year) * 10L + as.integer(x$Season); g <- data.table(pixel_id = x$pixel_id, c = cells)[, .(k = uniqueN(c)), by = pixel_id]
  sum(g$k < uniqueN(cells))
}
same_pixels_R <- function(x, o, d, say = TRUE) {
  rule <- d$same_pixels %||% "pre_post"
  if (identical(rule, "off") || !all(c("pixel_id", "post") %in% names(x))) return(x)
  fin <- is.finite(x[[o]])
  keep_p <- if (identical(rule, "pre_post")) { g <- x[fin, .(mn = min(post), mx = max(post)), by = pixel_id]; g[mn == 0L & mx == 1L, pixel_id] }
            else { cells <- as.integer(x$Year) * 10L + as.integer(x$Season); g <- data.table(pixel_id = x$pixel_id[fin], c = cells[fin])[, .(k = uniqueN(c)), by = pixel_id]; g[k >= uniqueN(cells[fin]), pixel_id] }
  n_all <- uniqueN(x$pixel_id[fin]); keep <- x$pixel_id %in% keep_p
  res <- list(rule = rule, pixels_left_out = n_all - length(keep_p), rows_left_out = sum(!keep), pixels_kept = length(keep_p))
  if (say && res$pixels_left_out > 0)
    info(sprintf("SAME_PIXELS = \"%s\" (%s): %s pixel(s) / %s rows leave -- observed %s; the treated and control groups are the same %s pixels %s", rule, o,
                 format(res$pixels_left_out, big.mark = ","), format(res$rows_left_out, big.mark = ","), if (identical(rule, "pre_post")) "only before or only after treatment" else "in some year-seasons only",
                 format(res$pixels_kept, big.mark = ","), if (identical(rule, "pre_post")) "in pre and post" else "in every year and season"))
  ats <- attributes(x); y <- x[keep]
  for (a in setdiff(names(ats), c("names", "row.names", "class", ".internal.selfref"))) setattr(y, a, ats[[a]])
  setattr(y, "same_pixels", res); y
}
# spec 1: the top_k candidate rings whose PRE-treatment series is closest to the treatment ring's (as Python's select_optimal_control_rings)
select_optimal_control_rings_R <- function(x, outcome_var, treat_ring = 0L, candidate_rings = 2:5, pre_years = 2015:2021, top_k = 2L, on = "level") {
  m <- x[buff_km %in% c(treat_ring, candidate_rings) & Year %in% pre_years & is.finite(get(outcome_var)), c("pixel_id", "buff_km", "Year", "Season", outcome_var), with = FALSE]
  m[, `:=`(unit = as.numeric(buff_km), tr = buff_km == treat_ring)]; tt <- m[tr == TRUE]; cc <- m[tr == FALSE]
  facts <- list(agg_t = tt[, .(s = sum(get(outcome_var)), n = .N), by = .(Year, Season)], t_pixels = uniqueN(tt$pixel_id),
                agg_c = cc[, .(s = sum(get(outcome_var)), n = .N), by = .(unit, Year, Season)], pix_c = cc[, .(pixels = uniqueN(pixel_id)), by = unit], mode = "pre_rings")
  dec <- control_selection_decide_R(facts, outcome_var, list(control_select_k = as.integer(top_k), control_select_on = on))
  list(chosen = dec$chosen, table = dec$tab)
}
.keep_attrs <- function(x, y) { ats <- attributes(x); for (a in setdiff(names(ats), c("names", "row.names", "class", ".internal.selfref"))) setattr(y, a, ats[[a]]); y }
donut_rule_R <- function(x, d, say = TRUE) {                                   # spec 1: DONUT_RINGS leave the control pool
  dn <- d$donut_rings %||% integer(0); if (!length(dn)) return(x)
  hit <- x$treat == 0L & x$buff_km %in% dn; n <- sum(hit)
  if (say && n) info(sprintf("DONUT_RINGS = %s: %s control rows of ring(s) %s leave the control pool (the spillover buffer next to the treated core)", paste(dn, collapse = ","), format(n, big.mark = ","), paste(dn, collapse = ",")))
  y <- .keep_attrs(x, x[!hit]); setattr(y, "donut", list(rings = dn, rows_left_out = n)); y
}
.pixel_baseline_R <- function(x, col, how) {
  pre <- if ("post" %in% names(x)) x$post == 0L else rep(TRUE, nrow(x)); if (!any(pre)) pre <- rep(TRUE, nrow(x))
  v <- suppressWarnings(as.numeric(x[[col]])); ok_ <- pre & is.finite(v)
  s <- data.table(p = x$pixel_id[ok_], v = v[ok_])
  if (identical(how, "mode")) s[, .(b = as.numeric(names(which.max(table(v))))), by = p] else s[, .(b = mean(v)), by = p]
}
landuse_rule_R <- function(x, d, say = TRUE) {                                 # spec 1: LANDUSE_KEEP on the pixel's baseline class
  keep <- d$landuse_keep %||% "all"; if (identical(keep, "all") || !length(keep) || !"LandUse" %in% names(x)) return(x)
  b <- .pixel_baseline_R(x, "LandUse", "mode"); if (!nrow(b)) return(x)
  kp <- b[round(b) %in% as.integer(keep), p]
  if (!length(kp)) stop(sprintf("LANDUSE_KEEP %s keeps no pixel: the baseline classes present are %s", paste(keep, collapse = ","), paste(sprintf("%d: %d", as.integer(names(table(round(b$b)))), as.integer(table(round(b$b)))), collapse = ", ")))
  kr <- x$pixel_id %in% kp; res <- list(classes = as.integer(keep), pixels_left_out = nrow(b) - length(kp), rows_left_out = sum(!kr), pixels_kept = length(kp))
  if (say) info(sprintf("LANDUSE_KEEP = %s: %s pixels kept by their pre-period (baseline) class, %s pixels / %s rows leave", paste(keep, collapse = ","), format(length(kp), big.mark = ","), format(res$pixels_left_out, big.mark = ","), format(res$rows_left_out, big.mark = ",")))
  y <- .keep_attrs(x, x[kr]); setattr(y, "landuse", res); y
}
baseline_ndvi_rule_R <- function(x, d, say = TRUE) {                           # spec 1: BASELINE_NDVI_MIN on the pixel's pre-period mean NDVI
  th <- d$baseline_ndvi_min %||% NA; if (!is.finite(th) || !"NDVI" %in% names(x)) return(x)
  b <- .pixel_baseline_R(x, "NDVI", "mean"); if (!nrow(b)) return(x)
  kp <- b[b > th, p]; if (!length(kp)) stop(sprintf("BASELINE_NDVI_MIN %g keeps no pixel: the pre-period mean NDVI ranges %.3f..%.3f", th, min(b$b), max(b$b)))
  kr <- x$pixel_id %in% kp; res <- list(threshold = th, pixels_left_out = nrow(b) - length(kp), rows_left_out = sum(!kr), pixels_kept = length(kp))
  if (say) info(sprintf("BASELINE_NDVI_MIN = %g: %s pixels kept (pre-period mean NDVI above it), %s pixels / %s rows leave", th, format(length(kp), big.mark = ","), format(res$pixels_left_out, big.mark = ","), format(res$rows_left_out, big.mark = ",")))
  y <- .keep_attrs(x, x[kr]); setattr(y, "baseline_ndvi", res); y
}
OUTCOME_BOUNDS_R <- list(NDVI = c(-1, 1), EVI = c(-1, 1), SAVI = c(-1.5, 1.5), NDWI = c(-1, 1), NDMI = c(-1, 1), NDRE = c(-1, 1), LSWI = c(-1, 1), VCI = c(0, 100), TCI = c(0, 100), VHI = c(0, 100), LAI = c(0, 12), SMDI = c(-4, 4))
NODATA_VALUES_R <- c(-9999, -999, -10, 9999)
outcome_range_check_R <- function(x, outcome, say = TRUE) {                    # spec 3: range safety (as Python's outcome_range_check)
  if (!outcome %in% names(x)) return(NULL)
  v <- suppressWarnings(as.numeric(x[[outcome]])); fin <- is.finite(v); n <- sum(fin); bd <- OUTCOME_BOUNDS_R[[outcome]]; tol <- .opt("PRECISION_TOLERANCE", 1e-6)
  res <- list(outcome = outcome, n_finite = n, n_nan = sum(!fin), bounds = bd, n_outside_bounds = if (!is.null(bd) && n) sum(v[fin] < bd[1] | v[fin] > bd[2]) else 0L,
              n_nodata_codes = if (n) sum(v[fin] %in% NODATA_VALUES_R) else 0L, n_zero_padding = if (n) sum(abs(v[fin]) <= tol) else 0L,
              vmin = if (n) min(v[fin]) else NA, vmax = if (n) max(v[fin]) else NA)
  res$ok <- res$n_outside_bounds == 0 && res$n_nodata_codes == 0
  if (say) (if (res$ok) ok else warn)(sprintf("range safety (%s): %s finite values in [%.6g, %.6g]%s; %s outside, %s no-data codes, %s within %g of zero%s", outcome, format(n, big.mark = ","), res$vmin, res$vmax,
                                              if (!is.null(bd)) sprintf(" against the bounds [%g, %g]", bd[1], bd[2]) else "", format(res$n_outside_bounds, big.mark = ","), format(res$n_nodata_codes, big.mark = ","), format(res$n_zero_padding, big.mark = ","), tol,
                                              if (res$ok) "" else " -- CHECK THE EXPORTS (a no-data code or an out-of-range value entered as data)"))
  res
}
select_controls_R <- function(x, o, d, sel = NULL, say = TRUE) {
  mode <- d$control_selection %||% "rings"
  if (identical(mode, "rings")) return(x)
  if (is.null(sel)) { dec <- control_selection_decide_R(control_selection_facts_R(x, o, d), o, d); sel <- record_control_selection_R(dec$tab, dec$chosen, o, d, say = say) }
  unit <- if (identical(mode, "pre_rings")) as.numeric(x$buff_km) else block_ids_R(x, d$control_block_deg %||% 0.01)
  keep <- x$treat == 1L | unit %in% sel$units
  ats <- attributes(x); y <- x[keep]
  for (a in setdiff(names(ats), c("names", "row.names", "class", ".internal.selfref"))) setattr(y, a, ats[[a]])
  setattr(y, "control_selection", sel); y
}

design_columns <- function(x, d, site_period = NULL, say = TRUE) {   # v20.58: site_period given = decided on the WHOLE sample (out of
  if ("post" %in% names(x)) x[, .post_panel := as.integer(post)]      # v20.59: the panel's post (the exports' flag), compared below
  x[, treat := as.integer(buff_km == 0L)]                               #   core); say = FALSE: a partition's count is summed and said once
  ss <- as.data.table(d$site_start %||% data.table()); sy <- as.data.table(d$site_years %||% data.table())
  base <- as.integer(d$treatment_year)
  if (identical(d$timing, "fund") && nrow(ss)) {
    x[, cohort_row := row_cohort(as.integer(site_id), as.integer(Season), ss, base)]
  } else if (identical(d$timing, "registry") && nrow(sy)) {
    x[, cohort_row := { y <- sy$year[match(as.integer(site_id), sy$site_id)]; fifelse(is.na(y), base, as.integer(y)) }]
  } else x[, cohort_row := base]
  x[, post := as.integer(Year >= cohort_row)]
  panel_src <- identical(d$design_source, "panel") && ".post_panel" %in% names(x)   # v20.59: the panel's design is estimated on
  if (isTRUE(d$exclude_transition_year) && !panel_src) { n0 <- nrow(x); x <- x[Year != cohort_row]; x[, post := as.integer(Year > cohort_row)]
    setattr(x, "n_transition_left_out", n0 - nrow(x))
    if (say) info(sprintf("EXCLUDE_TRANSITION_YEAR: %s rows of each series' first treated year left out", format(n0 - nrow(x), big.mark = ","))) }
  post_design <- if (".post_panel" %in% names(x)) copy(x$post) else NULL           # the design in effect's post, compared with the panel's below
  if (panel_src) {                                                                  # v20.59 -- DESIGN_SOURCE "panel" (the notebooks' default): the PANEL's post
    x[, post := fifelse(is.na(.post_panel), post, as.integer(.post_panel))]        #   (the exports' Treat flag, PERIOD_RULE) is estimated on; each series' cohort =
    first <- x[post == 1L, .(first_post = min(Year)), by = site_id]                #   the first post year of its sub-watershed in the panel's own columns
    x[first, on = "site_id", cohort_row := i.first_post]; x[is.na(cohort_row), cohort_row := base]
  }
  x[, did := treat * post]
  x[, cohort := fifelse(treat == 1L, as.numeric(cohort_row + as.integer(d$cohort_offset %||% 0L)), Inf)]
  x[, event_time := fifelse(treat == 1L, Year - cohort_row, NA_integer_)]
  x[, unit := if (identical(d$unit_fe, "pixel")) as.character(pixel_id) else paste(pixel_id, Season, sep = "_")]
  if (is.null(site_period)) site_period <- uniqueN(x$site_id[x$site_id > 0]) >= 2 && identical(d$pooled_fe, "site_period")
  x[, period := if (site_period) paste(site_id, Year, Season, sep = "_") else paste(Year, Season, sep = "_")]
  x[, cohort_row := NULL]
  cmp <- NULL
  if (".post_panel" %in% names(x)) { cmp <- c(nrow(x), sum(x$.post_panel != post_design, na.rm = TRUE)); x[, .post_panel := NULL] }
  setattr(x, "post_vs_panel", cmp)                                     # v20.59: (rows compared, rows that differ); NULL = no post column in the panel
  if (say) design_vs_panel_say_R(cmp, d)
  x
}
attach_dose_R <- function(x, d) {
  s <- list(fund_start_rule = d$fund$start_rule, fund_start_share = d$fund$start_share, fund_rate_months = d$fund$rate_months, fund_dose_before_file = d$fund$before_file)
  ft <- fund_tables_R(s)
  cols <- c("dose_amount_sws", "dose_intensity_per_ha", "dose_share_of_target", "dose_estimated")
  if (!is.null(ft)) {
    for (c_ in intersect(cols, names(x))) set(x, j = c_, value = NULL)
    x[ft$dose, on = .(site_id, Year, Season), (cols) := mget(paste0("i.", cols))]
  } else {
    for (c_ in setdiff(cols, names(x))) set(x, j = c_, value = NA_real_)
    if (is.null(.DESIGN_CACHE$dose_notice)) { .DESIGN_CACHE$dose_notice <- TRUE
      warn("the fund workbook (", FUND_RELEASE_PATH, ") is not available: the dose is the panel's own ", d$dose_variable, " column where it has one") }
  }
  for (c_ in cols) set(x, j = c_, value = fifelse(x$did == 1L, as.numeric(x[[c_]]), 0))   # the dose belongs to the treatment area once treated
  x[, dose := get(d$dose_variable)]
  x
}

# ---------------------------------------------------------------- the data every model reads
# v20.58 (your rule "repeated rows are dropped"): how the panel on disk treated REPEATED rows (the same sub-watershed, pixel, year and season in
# two exports). Until v20.57 R_P00 filled the kept row's gaps with the repeated rows' values; a panel built so (no panel_build_settings_R.csv
# beside it, or DEDUP_FILL_FROM_DUPLICATES TRUE) holds values of dropped rows -- every model says so once per session until R_P00 rebuilds it.
.PANEL_DEDUP_NOTED <- new.env()
panel_dedup_note_R <- function(verbose = TRUE) {
  f <- file.path(dirname(PANEL_PATH), "panel_build_settings_R.csv")
  st <- tryCatch(if (file.exists(f)) fread(f, colClasses = "character") else NULL, error = function(e) NULL)
  fill <- if (is.null(st)) NA else identical(st[setting == "dedup_fill_from_duplicates", value], "TRUE")
  state <- if (is.na(fill)) "unknown" else if (fill) "filled" else "dropped whole"
  if (verbose && is.null(.PANEL_DEDUP_NOTED[[PANEL_PATH]]) && file.exists(PANEL_PATH) && state != "dropped whole") {
    assign(PANEL_PATH, TRUE, envir = .PANEL_DEDUP_NOTED)
    warn(if (state == "filled") "this panel was built with the gaps of the kept rows FILLED from REPEATED rows (DEDUP_FILL_FROM_DUPLICATES = TRUE) -- values of dropped rows are in it; your rule drops a repeated row whole: set it FALSE and re-run R_P00"
         else "this panel was built before v20.58 (no panel_build_settings_R.csv beside it): R_P00 then FILLED the gaps of the kept rows from REPEATED rows (another export of the same pixel, year and season) -- values of dropped rows may be in it. Your rule drops a repeated row whole: re-run R_P00")
  }
  invisible(state)
}

load_panel_R <- function(outcome, d = load_design(), extra = character(0), integrity = TRUE) {
  panel_dedup_note_R()                                                                              # v20.58
  cols <- panel_names()
  if (!outcome %in% cols) stop(sprintf("%s is not in the panel: no export carries this variable", outcome))   # v20.51
  lc_ <- load_columns_R(outcome, d, extra, cols); covs <- lc_$covs
  x <- panel_read(lc_$need, d$control_rings)
  S <- if ("site_id" %in% names(x)) load_processed_R(d) else integer(0)
  r <- load_rows_R(x, outcome, d, covs, if ("site_id" %in% names(x)) location_table_R() else NULL, S,
                   fill_src = function(need2) panel_read(c("pixel_id", "Year", "Season", need2)))
  x <- r$x; loc_rep <- r$loc_rep; n_gf <- r$n_gf
  x <- screen_outcome(x, outcome, as.integer(d$treatment_year), rule = d$outcome_screen %||% screen_rule_R())$dt   # v20.59: the rule of the design
  x <- design_columns(x, d)                                                   # v20.57: the timing in force (fund / registry / fixed)
  rng <- outcome_range_check_R(x, outcome); setattr(x, "range_check", rng)   # spec 3: range safety
  x <- donut_rule_R(x, d); x <- landuse_rule_R(x, d); x <- baseline_ndvi_rule_R(x, d)   # spec 1: the spillover buffer, the land-use / baseline masks
  x <- select_controls_R(x, outcome, d)                                       # v20.59: CONTROL_SELECTION -- the pre period's choice, fixed for the panel
  x <- same_pixels_R(x, outcome, d)                                           # v20.59: SAME_PIXELS -- the same pixels in pre and post (or every year-season)
  if (identical(d$cluster, "block")) { x[, block_id := block_ids_R(x, d$control_block_deg %||% 0.01)]; x[, cluster_id := as.character(block_id)] }   # v20.59
  else x[, cluster_id := as.character(get(cluster_col_for(x)))]
  x <- attach_dose_R(x, d)                                                    # v20.57: the fund file's dose under the timing in force
  setattr(x, "n_gapfilled_excluded", if (isTRUE(d$exclude_gapfilled %||% EXCLUDE_GAPFILLED)) n_gf else 0L)
  setattr(x, "covariates_used", covs)                                         # v20.57: what covs_in() hands every model
  setattr(x, "location_report", loc_rep)
  if (integrity) setattr(x, "integrity", sample_integrity_R(x, d, outcome, S))  # v20.58: the post-conditions, CONFIRMED on this sample
  setattr(x, "scenario", scenario_tag(d)); x
}
# v20.58: the pieces of load_panel_R, shared with the OUT-OF-CORE path (reward_outofcore.R) -- every pixel partition runs this same code
load_columns_R <- function(outcome, d, extra = character(0), cols = panel_names()) {   # the columns a model's sample is built from
  covs <- intersect(d$covariates %||% COVARIATES, cols)
  need <- intersect(unique(c("pixel_id", "site_id", "sws_name", "Year", "Season", "buff_km", "latitude", "longitude", "LandUse", if (is.finite(d$baseline_ndvi_min %||% NA)) "NDVI",   # spec 1
                             covs, outcome, extra, "site_check", "sws_export", "GapFilled", "Coverage", "post",   # v20.59: the panel's post, compared with the design
                             if (is.null(fund_tables_R(list(fund_start_rule = d$fund$start_rule, fund_start_share = d$fund$start_share, fund_rate_months = d$fund$rate_months,
                                                            fund_dose_before_file = d$fund$before_file)))) d$dose_variable)), cols)
  list(covs = covs, need = need)
}
load_processed_R <- function(d, loc = location_table_R())                  # the processing set of the design in force
  if (!is.null(d$processed)) d$processed else processing_set_R(loc, d$sub_watersheds %||% "data", d$fragment_min_share %||% 0.05)$sites
location_messages_R <- function(loc_rep, dc, outcome) {                     # what the location rule left out (or kept), per group
  if (is.null(loc_rep) || !nrow(loc_rep)) return(invisible(NULL))
  for (k in sort(unique(loc_rep$code))) {
    r <- loc_rep[code == k]; g <- function(t, p) sum(r[treated == t & post == p, N])
    (if (k %in% dc) info else warn)(sprintf("%s: %s rows %s -- %s (treated pre %s / post %s, control pre %s / post %s)", outcome, format(sum(r$N), big.mark = ","),
         if (k %in% dc) "left out" else "KEPT (your option)", LOCATION_TEXT[[as.character(k)]], format(g(TRUE, FALSE), big.mark = ","), format(g(TRUE, TRUE), big.mark = ","),
         format(g(FALSE, FALSE), big.mark = ","), format(g(FALSE, TRUE), big.mark = ",")))
  }
  invisible(NULL)
}
# The row rules of a model's sample, in order: the location rule, the gap-filled rows, the year window, the seasons, the annual covariate
# fill, the finite outcome / covariates. x = the panel rows of the design's rings; loc = location_table_R() (NULL: no sub-watershed id);
# fill_src(cols) = the panel's rows (EVERY ring) of those columns for the annual fill; say = FALSE (a partition): nothing is printed, the
# counts are returned and the parent says them once; fill_force = the covariates the WHOLE sample needs filled (out of core, second look).
load_rows_R <- function(x, outcome, d, covs, loc, S, fill_src, say = TRUE, fill_force = NULL) {
  # v20.58 -- YOUR RULE: only the CURRENT sub-watershed's own data (the location rule, reward_design.R above): rows of sub-watersheds this
  # run does not process, rows outside every polygon, overlapping / repeated pixels and pixels whose ring the exports disagree on leave
  # EVERY group -- treated and control, pre and post -- before anything else is computed on them
  loc_rep <- NULL; dc <- integer(0)
  if ("site_id" %in% names(x) && !is.null(loc)) {
    lc <- location_codes_R(x, loc, S)
    dc <- c(if (identical(d$fragment_rule %||% "drop", "drop")) 1:2, if (identical(d$overlap_rows %||% OVERLAP_ROWS, "drop")) 3:4)
    if (any(lc > 0L)) {
      sy <- as.data.table(d$site_years %||% data.table(site_id = integer(0), year = integer(0)))
      cy <- sy$year[match(as.integer(x$site_id), sy$site_id)]; cy[is.na(cy)] <- as.integer(d$treatment_year)
      loc_rep <- data.table(code = lc, treated = x$buff_km == 0L, post = x$Year >= cy)[code > 0L, .N, by = .(code, treated, post)]
      setorder(loc_rep, code, treated, post)                                   # v20.58: a fixed order (the same file in memory and out of core)
      loc_rep[, dropped := code %in% dc]
      if (say) location_messages_R(loc_rep, dc, outcome)
      if (length(dc)) x <- x[!lc %in% dc]
    }
  }
  # v20.52: rows the exporter FILLED from history (GapFilled = 1 / Coverage = 0) are not observations (EXCLUDE_GAPFILLED)
  gf <- rep(FALSE, nrow(x))
  if ("GapFilled" %in% names(x)) gf <- gf | (!is.na(x$GapFilled) & x$GapFilled > 0)
  if ("Coverage" %in% names(x)) gf <- gf | (!is.na(x$Coverage) & x$Coverage <= 0)
  n_gf <- sum(gf); n_gf_post <- sum(gf & x$Year >= as.integer(d$treatment_year)); gf_out <- n_gf && isTRUE(d$exclude_gapfilled %||% EXCLUDE_GAPFILLED)
  if (gf_out) {
    if (say) info(sprintf("%s: %s rows filled from history left out (%s of them in the post years)", outcome, format(n_gf, big.mark = ","), format(n_gf_post, big.mark = ",")))
    x <- x[!gf]
  }
  if (is.finite(d$year_min %||% NA)) x <- x[Year >= d$year_min]                  # v20.57: the window of the design in force
  if (is.finite(d$year_max %||% NA)) x <- x[Year <= d$year_max]
  if (length(d$drop_years)) x <- x[!Year %in% d$drop_years]
  sc <- season_codes(normalize_seasons(d$seasons %||% SEASONS))              # v20.53 / v20.55: "all" | "seasonal" | "yearly" | named seasons
  if (!is.null(sc)) x <- x[Season %in% sc]
  # v20.55 (as Python's fill_yearly_covariates, v20.24): a covariate the ANNUAL composite lacks is filled with the same
  # pixel-year's mean over that year's SEASONAL rows, so the annual rows keep their weather adjustment
  cvs <- covs; n_fill <- 0L; miss <- setNames(logical(length(cvs)), cvs); inf_ <- miss
  if (length(cvs) && any(x$Season == 0L)) {
    yr <- x$Season == 0L; miss <- vapply(cvs, function(cv) anyNA(x[[cv]][yr]), logical(1))
    inf_ <- vapply(cvs, function(cv) { v <- x[[cv]][yr]; any(!is.na(v) & !is.finite(v)) }, logical(1))   # +-Inf: filled only when the sample has an NA
    use <- if (is.null(fill_force)) miss else (miss | (cvs %in% fill_force))
    if (any(use)) {
      need2 <- cvs[use]
      tab2 <- fill_src(need2)[Season != 0L, lapply(.SD, function(v) { m <- mean(v, na.rm = TRUE); if (is.nan(m)) NA_real_ else m }), by = .(pixel_id, Year), .SDcols = need2]
      idx <- tab2[x[yr, .(pixel_id, Year)], on = c("pixel_id", "Year")]
      for (cv in need2) { cur <- x[[cv]][yr]; f <- idx[[cv]]; m <- !is.finite(cur) & is.finite(f); cur[m] <- f[m]; n_fill <- n_fill + sum(m); set(x, which(yr), cv, cur) }
      if (n_fill && say) info(sprintf("annual rows: %s covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean", format(n_fill, big.mark = ",")))
    }
  }
  n0 <- nrow(x)
  x <- x[is.finite(get(outcome))]
  for (cv in cvs) x <- x[is.finite(get(cv))]
  if (say && nrow(x) < n0) info(sprintf("%s: %s of %s rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)",
                                        outcome, format(n0 - nrow(x), big.mark = ","), format(n0, big.mark = ",")))
  list(x = x, loc_rep = loc_rep, dc = dc, n_gf = n_gf, n_gf_post = n_gf_post, gf_out = gf_out, n_fill = n_fill, n0 = n0, n1 = nrow(x), miss = miss, inf = inf_)
}

# ---------------------------------------------------------------- v20.58: SAMPLE INTEGRITY -- what enters the estimate, CONFIRMED (never assumed)
# After every filter, on the rows the model receives: only the processed sub-watersheds, nothing outside their polygons, no repeated
# pixel-year-season, one ring per pixel, no pixel both treated and a control, and exactly the rings / years / seasons of the design.
# Under the default rules (FRAGMENT_RULE / OVERLAP_ROWS "drop") a violation STOPS the model -- a leak is a bug, never a silent pass.
sample_integrity_R <- function(x, d, outcome = "", S = d$processed) integrity_decide_R(integrity_parts_R(x), d, outcome, S)
# v20.58: the integrity facts of a sample (or of one pixel partition: every fact is a count, a set or a range -- merged exactly by
# integrity_merge_R in reward_outofcore.R), and the verdict on them -- the SAME checks in memory and out of core
integrity_parts_R <- function(x) {
  nd <- anyDuplicated(x, by = c("pixel_id", "Year", "Season"))
  list(sites = sort(unique(as.integer(x$site_id))), site_na = anyNA(x$site_id), has_check = "site_check" %in% names(x), n_outside = if ("site_check" %in% names(x)) sum(x$site_check %in% 3L) else 0L,
       dup = if (nd == 0L) "" else paste(x[nd, .(pixel_id, Year, Season)], collapse = " "),
       n_ring_multi = nrow(x[, .(nr = uniqueN(buff_km)), by = .(site_id, pixel_id)][nr > 1L]),
       n_both = length(intersect(x[treat == 1L, unique(pixel_id)], x[treat == 0L, unique(pixel_id)])),
       n_one_side = pixels_one_side_R(x, .opt("SAME_PIXELS", "pre_post")),                                    # v20.59: your rule (the rows here are finite)
       rings = sort(unique(x$buff_km)), years = if (nrow(x)) range(x$Year) else c(NA_integer_, NA_integer_),
       years_set = sort(unique(x$Year)), seasons = sort(unique(x$Season)),
       rows = nrow(x), pixels = uniqueN(x$pixel_id))
}
integrity_decide_R <- function(p, d, outcome = "", S = d$processed) {
  strict_f <- identical(d$fragment_rule %||% "drop", "drop"); strict_o <- identical(d$overlap_rows %||% OVERLAP_ROWS, "drop")
  chk <- list(); add <- function(what, ok, detail, strict = TRUE) chk[[length(chk) + 1L]] <<- data.table(check = what, ok = isTRUE(ok), detail = detail, strict = strict)
  st <- p$sites
  add("only the processed sub-watersheds", !length(S) || (all(st %in% S) && !isTRUE(p$site_na)), sprintf("in the sample: %s | processed: %s", paste(st, collapse = ","), if (length(S)) paste(S, collapse = ",") else "all (no ids)"), strict_f)
  if (isTRUE(p$has_check)) add("nothing outside every polygon", p$n_outside == 0L, sprintf("%d rows outside", p$n_outside), strict_f)
  add("no repeated pixel-year-season", !nzchar(p$dup), if (!nzchar(p$dup)) sprintf("%s rows, every (pixel, year, season) once", format(p$rows, big.mark = ",")) else sprintf("repeated: %s", p$dup), strict_o)
  add("one ring per pixel", p$n_ring_multi == 0L, sprintf("%d pixel(s) with more than one ring", p$n_ring_multi), strict_o)
  add("no pixel both treated and a control", p$n_both == 0L, sprintf("%d pixel(s) on both sides", p$n_both), strict_o)
  spx <- d$same_pixels %||% "pre_post"                                                                       # v20.59: your rule, confirmed on the sample
  if (!identical(spx, "off") && !is.null(p$n_one_side))
    add(if (identical(spx, "pre_post")) "the same pixels in pre and post" else "the same pixels in every year-season", p$n_one_side == 0,
        sprintf("%d pixel(s) observed %s", as.integer(p$n_one_side), if (identical(spx, "pre_post")) "on one side only" else "in some year-seasons only"))
  rg <- p$rings; want_r <- c(0L, as.integer(d$control_rings))
  add("the rings of the design", all(rg %in% want_r) && any(rg == 0L) && any(rg > 0L), sprintf("rings in the sample %s | design %s", paste(rg, collapse = ","), paste(want_r, collapse = ",")))
  yr <- p$years; y_ok <- (!is.finite(d$year_min %||% NA) || yr[1] >= d$year_min) && (!is.finite(d$year_max %||% NA) || yr[2] <= d$year_max) && !any(p$years_set %in% (d$drop_years %||% integer(0)))
  add("the years of the design", y_ok, sprintf("years %d-%d | window %s-%s%s", yr[1], yr[2], if (is.finite(d$year_min %||% NA)) d$year_min else "start", if (is.finite(d$year_max %||% NA)) d$year_max else "end",
                                              if (length(d$drop_years)) paste0(", without ", paste(d$drop_years, collapse = ",")) else ""))
  sc <- season_codes(normalize_seasons(d$seasons %||% SEASONS)); ss <- p$seasons
  add("the seasons of the design", is.null(sc) || all(ss %in% sc), sprintf("seasons %s | %s", paste(SEASON_LABEL[as.character(ss)], collapse = ","), normalize_seasons(d$seasons %||% SEASONS)))
  tab <- rbindlist(chk); tab[, `:=`(outcome = outcome, rows = p$rows, pixels = p$pixels)]
  bad <- tab[ok == FALSE]
  if (nrow(bad[strict == TRUE])) stop(sprintf("SAMPLE INTEGRITY FAILED for %s -- %s. Nothing was estimated (a leak would bias every model).", outcome,
                                             paste(sprintf("%s: %s", bad[strict == TRUE, check], bad[strict == TRUE, detail]), collapse = " | ")))
  if (nrow(bad)) warn(sprintf("sample integrity (%s): %s -- your option keeps these rows", outcome, paste(sprintf("%s: %s", bad$check, bad$detail), collapse = " | ")))
  ok(sprintf("sample integrity (%s): %s rows, %s pixels | sub-watershed(s) %s | rings %s | years %d-%d | seasons %s | CONFIRMED: every (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s)",
             outcome, format(p$rows, big.mark = ","), format(p$pixels, big.mark = ","), paste(st, collapse = ","), paste(rg, collapse = ","), yr[1], yr[2],
             paste(SEASON_LABEL[as.character(ss)], collapse = ",")))
  tab
}

# ---------------------------------------------------------------- results: standardised, design SE attached, SE ~ 0 flagged
# v20.58: every result says WHAT its numbers are. An EFFECT has an estimate, an SE and a p-value (never NA: a model whose own SE is not
# identified -- e.g. one coefficient per year with the years as clusters -- gives the design-based SE, and says so); a TEST gives its
# statistic and p; a STATISTIC (Moran's I) its value, SE and p; a DIAGNOSTIC (a variance share) its value, described. The design-based
# check is printed on its own line: the SAME for every model on the same sample (it is a property of the data, not of the model).
MODEL_KIND <- c(M16 = "test", M17 = "statistic", M18 = "statistic", M19 = "diagnostic", M20 = "test")   # v20.58: M20 as Python (Cochran's Q)
NOT_ATT <- c("M06", "M10", "M15", "M24")                                            # effects that are NOT the treatment effect itself (as Python)
NOT_ATT_WHAT <- c(M06 = "the effect per unit of dose", M10 = "the triple difference (land use 2 minus the rest; truth 0 without heterogeneity)",
                  M15 = "the mean placebo effect (truth 0)", M24 = "the spillover into the nearest control ring (truth 0)")
STAT_NAME <- c(M16 = "pre-trend test statistic", M17 = "Moran's I", M18 = "Moran's I (the LISA table beside it)", M19 = "ICC (variance share)",
               M20 = "Cochran's Q (heterogeneity across sub-watersheds)")
# v20.58: columns a model adds to its headline row beside estimate / SE / p (the same names in Python's HEADLINE_<outcome>.csv)
HEADLINE_EXTRA <- c("p_any_placebo_bonferroni", "n_placebo_years", "breakdown_Mbar", "breakdown_how", "ring", "reference_ring",
                    "Q_df", "pooled_effect", "pooled_se", "I2", "tau2", "n_sub_watersheds", "did_rest", "third_dim",
                    "beta_interaction", "se_interaction", "p_interaction", "covariate")
r_se_how <- function(model, dt, engine = "R") {
  # v20.58: what each model's OWN standard error is -- written into every result and printed with it (never a generic label). dt = the
  # sample, or the facts of a sample (sample_facts: an out-of-core sample has only its facts)
  if (is.data.frame(dt)) { cc <- cluster_col_for(dt); G <- uniqueN(dt[[cc]]); ns <- uniqueN(dt$site_id[dt$site_id > 0]); nu <- uniqueN(dt$unit); np <- uniqueN(dt$pixel_id) }
  else { cc <- dt$cluster_col; G <- dt$G; ns <- dt$n_sites_pos; nu <- dt$n_units; np <- dt$n_pixels }
  cl <- sprintf("clustered by %s (%d clusters)", if (cc == "site_id") "sub-watershed" else "year", G)
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
# v20.58: the facts of a sample that every result row reports -- from the rows (in memory) or merged from the partitions (out of core)
sample_facts <- function(dt, outcome) {
  if (inherits(dt, "reward_ooc")) return(dt$facts)
  cc <- cluster_col_for(dt)
  list(cluster_col = cc, G = uniqueN(dt[[cc]]), n_obs = nrow(dt), n_pixels = uniqueN(dt$pixel_id), n_units = uniqueN(dt$unit),
       n_sites_pos = uniqueN(dt$site_id[dt$site_id > 0]), n_periods = uniqueN(dt$period), sites = sort(unique(dt$site_id)), rings = sort(unique(dt$buff_km)),
       years = range(dt$Year), baseline_mean = mean(dt[treat == 1 & post == 0][[outcome]], na.rm = TRUE),
       integrity = attr(dt, "integrity"), location_report = attr(dt, "location_report"), post_vs_panel = attr(dt, "post_vs_panel"))   # v20.59
}
save_result <- function(model, outcome, res, dt, d = load_design()) {
  tag <- scenario_tag(d); od <- file.path(RESULTS_DIR, model, tag); dir.create(od, recursive = TRUE, showWarnings = FALSE)
  if (!is.null(d$choices)) fwrite(d$choices, file.path(od, "DESIGN_IN_EFFECT.csv"))        # v20.57: the design of this run, even for a gap
  if (!is.null(res$error)) { res$error <- gsub("\\s+", " ", paste(res$error, collapse = " "))                    # v20.49: one line, always readable
    warn(model, " x ", outcome, ": ", res$error); fwrite(data.table(model = model, outcome = outcome, status = "data gap", reason = res$error), file.path(od, sprintf("%s_%s_DATA_GAP.csv", model, outcome))); return(invisible(NULL)) }
  kind <- res$kind %||% (MODEL_KIND[model] %||% "effect"); if (is.na(kind)) kind <- "effect"
  est <- suppressWarnings(as.numeric(res$estimate %||% NA_real_)); se <- suppressWarnings(as.numeric(res$se %||% NA_real_)); pv <- suppressWarnings(as.numeric(res$p_value %||% NA_real_))
  fx <- sample_facts(dt, outcome); G <- fx$G; se_how <- res$se_how %||% ""; p_how <- res$p_how %||% ""
  ds <- tryCatch(design_se(dt, outcome, est), error = function(e) list(se_design_unit = paste("design SE failed:", conditionMessage(e))))
  not_att <- model %in% NOT_ATT                                                      # v20.58: a dose slope / placebo / spillover is not the
  if (not_att) ds$p_estimate_design <- NA_real_                                      #   treatment effect: no p of it against the design SE
  if (kind == "effect" && !not_att && !is.finite(se) && is.finite(ds$se_design %||% NA)) {       # v20.58: never an NA SE on an effect
    se <- ds$se_design; se_how <- paste0("design-based (", ds$se_design_unit, "): this model's own SE is not identified here", if (nzchar(res$se_note %||% "")) paste0(" -- ", res$se_note) else "")
    pv <- ds$p_estimate_design; p_how <- sprintf("t with %g df against the design-based SE", ds$df_design)
  }
  if (is.finite(est) && is.finite(se) && se > 0 && !is.finite(pv) && kind %in% c("effect", "statistic")) {
    dfp <- res$df %||% max(1, G - 1); pv <- 2 * pt(abs(est / se), dfp, lower.tail = FALSE); if (!nzchar(p_how)) p_how <- sprintf("t with %g df from the estimate and its SE", dfp)
  }
  if (!nzchar(se_how) && is.finite(se)) se_how <- r_se_how(model, fx, res$engine %||% "R")
  row <- data.table(model = model, outcome = outcome, kind = kind, estimate = est, se = se, p_value = pv, se_how = se_how, p_how = p_how,
                    n_obs = fx$n_obs, n_pixels = fx$n_pixels, cluster_used = fx$cluster_col, n_clusters = G, engine = res$engine %||% "R",
                    did_design = ds$did_design %||% NA_real_, se_design = ds$se_design %||% NA_real_, df_design = ds$df_design %||% NA_real_,
                    p_design = ds$p_design %||% NA_real_, se_design_unit = ds$se_design_unit %||% "", p_estimate_design = ds$p_estimate_design %||% NA_real_,
                    did_design_period = ds$did_design_period %||% NA_real_, se_design_period = ds$se_design_period %||% NA_real_,
                    df_design_period = ds$df_design_period %||% NA_real_, p_design_period = ds$p_design_period %||% NA_real_,   # v20.55
                    n_periods = fx$n_periods, seasons_used = normalize_seasons(d$seasons %||% SEASONS),
                    sub_watersheds = paste(fx$sites, collapse = ","), rings = paste(fx$rings, collapse = ","),
                    years = paste(fx$years, collapse = "-"),
                    baseline_mean = fx$baseline_mean,
                    post_rows_differ_from_panel = if (!is.null(fx$post_vs_panel)) as.numeric(fx$post_vs_panel[2]) else NA_real_)   # v20.59: DESIGN vs PANEL
  row[, effect_pct_of_baseline := if (kind == "effect") 100 * estimate / baseline_mean else NA_real_]
  for (k in intersect(HEADLINE_EXTRA, names(res))) if (length(res[[k]])) set(row, j = k, value = res[[k]][1])   # v20.58: e.g. M34's breakdown Mbar,
  if (kind != "effect") row[, `:=`(se_note = res$se_note %||% (if (kind == "diagnostic") "a descriptive share of variance: it has no sampling SE" else if (kind == "test") "a test statistic: read its p-value" else ""))]
  if (kind == "effect" && is.finite(row$se) && (row$se <= 1e-9 || (is.finite(row$estimate) && abs(row$estimate) > 0 && row$se < 1e-7 * abs(row$estimate)))) {
    row[, `:=`(se_invalid = TRUE, se_invalid_why = "SE ~ 0: no variation left (fill values, or one cluster) -- NOT a result")]
    warn(model, " x ", outcome, ": SE ~ 0 -- NOT a result (see the outcome screen)")
  }
  if (kind == "effect" && !is.finite(row$se)) warn(model, " x ", outcome, ": NO standard error could be computed (", res$se_note %||% "the model gave none and the design-based SE is not identified", ") -- read the estimate with care")
  row[, `:=`(timing = d$timing %||% "", dose_variable = d$dose_variable %||% "", fragment_rule = d$fragment_rule %||% "", overlap_rows = d$overlap_rows %||% "", engine_version = R_ENGINE_VERSION)]
  fwrite(row, file.path(od, sprintf("%s_%s.csv", model, outcome)))
  if (!is.null(res$table)) fwrite(as.data.table(res$table), file.path(od, sprintf("%s_%s_table.csv", model, outcome)))
  if (!is.null(d$choices)) fwrite(d$choices, file.path(od, "DESIGN_IN_EFFECT.csv"))        # v20.57: what this run used, next to its results
  integ <- fx$integrity; if (!is.null(integ)) fwrite(integ, file.path(od, sprintf("SAMPLE_INTEGRITY_%s.csv", outcome)))   # v20.58
  lr <- fx$location_report; if (!is.null(lr) && nrow(lr)) { lr <- copy(lr); lr[, text := LOCATION_TEXT[as.character(code)]]; fwrite(lr, file.path(od, sprintf("LOCATION_RULE_%s.csv", outcome))) }
  f3 <- function(v) if (!is.finite(v)) "not identified" else if (v > 0 && v < 1e-300) "< 1e-300" else if (v == 0) "< 1e-300 (below machine precision)" else formatC(v, digits = 3, format = "g")
  head_txt <- switch(kind,
    effect = sprintf("estimate %.5g | SE %s, p %s (SE: %s%s)", row$estimate, f3(row$se), f3(row$p_value), row$se_how, if (nzchar(row$p_how)) paste0("; p: ", row$p_how) else ""),
    test = sprintf("%s %.4g, p %s (%s)", STAT_NAME[[model]], row$estimate, f3(row$p_value), row$engine),
    statistic = sprintf("%s %.4g | SE %s, p %s (%s)", STAT_NAME[[model]], row$estimate, f3(row$se), f3(row$p_value), row$engine),
    diagnostic = sprintf("%s %.4g (%s; %s)", STAT_NAME[[model]], row$estimate, row$se_note, row$engine))
  ok(sprintf("%s x %s: %s -> %s", model, outcome, head_txt, od))
  if (kind == "effect" && is.finite(row$se_design))
    info(sprintf("%s x %s -- design-based check on this sample (the same for every model, it is a property of the data): DiD of the treated-minus-control gaps %.5g, SE %s (%s, %g df), p %s%s%s",
                 model, outcome, row$did_design, f3(row$se_design), row$se_design_unit, row$df_design, f3(row$p_design),
                 if (is.finite(row$se_design_period)) sprintf(" | each year x season a draw: %.5g, SE %s (%g df), p %s", row$did_design_period, f3(row$se_design_period), row$df_design_period, f3(row$p_design_period)) else "",
                 if (not_att) sprintf(" (%s: not the treatment effect, so not tested against it)", NOT_ATT_WHAT[[model]]) else sprintf("; this estimate against that SE: p %s", f3(row$p_estimate_design))))
  invisible(row)
}

audit_results <- function() {
  fs <- list.files(RESULTS_DIR, pattern = "^M[0-9]{2}_.*\\.csv$", recursive = TRUE, full.names = TRUE)
  fs <- fs[!grepl("_table\\.csv$|_DATA_GAP\\.csv$", fs)]
  if (!length(fs)) { info("no results yet"); return(invisible(NULL)) }
  a <- rbindlist(lapply(fs, fread), fill = TRUE)
  if (!"kind" %in% names(a)) a[, kind := "effect"]
  a[, flags := fifelse(kind == "effect" & is.finite(se) & se <= 1e-9, "SE~0 (not a result)",
               fifelse(kind == "effect" & !is.finite(se), "NO SE (see se_how)",
               fifelse(kind == "effect" & is.finite(se_design) & is.finite(se) & se > 0 & se_design / se > 3, "model SE far below the design SE", "ok")))]
  fwrite(a, file.path(RESULTS_DIR, "RESULTS_AUDIT.csv")); ok(sprintf("results audit: %d results, %d with SE ~ 0 -> RESULTS_AUDIT.csv", nrow(a), sum(a$flags == "SE~0 (not a result)")))
  invisible(a)
}

# ---------------------------------------------------------------- v20.57: the estimation sample of each design variant -- the proof that every
# option does exactly what it says. python/validate_design_options.py runs the same variants through the Python engine and compares them row by
# row; tests/run_all_tests.R (scenario E) checks them in R alone. A variant = the settings that differ from these defaults.
DESIGN_DEFAULTS <- list(DESIGN_MODE = "recommended", TREATMENT_TIMING = "fund", TREATMENT_YEAR = 2022, FUND_START_RULE = "backcast", FUND_START_SHARE = 0.10,
                        FUND_RATE_MONTHS = 12L, FUND_DOSE_BEFORE_FILE = "backcast", DOSE_VARIABLE = "dose_intensity_per_ha", CONTROL_RINGS = "data",
                        PRE_YEARS = "data", POST_YEARS = "data", SEASONS = "all", EXCLUDE_TRANSITION_YEAR = FALSE, UNIT_FE = "pixel_season", COHORT_OFFSET = 0L,
                        OVERLAP_ROWS = "drop", FRAGMENT_RULE = "drop", FRAGMENT_MIN_SHARE = 0.05, POOLED_FE = "site_period", EXCLUDE_GAPFILLED = TRUE,
                        COVARIATES = c("Rain", "Tmax", "Tmean", "Tmin"), SUB_WATERSHEDS = "data", OUTCOME_SCREEN = "drop", DESIGN_SOURCE = "model",   # v20.59: + the screen's rule, the design's source
                        CONTROL_SELECTION = "rings", CONTROL_SELECT_K = 2L, CONTROL_SELECT_RATIO = 3, CONTROL_SELECT_ON = "trend", CONTROL_BLOCK_DEG = 0.01, CLUSTER = "auto",   # v20.59: the control selection, the cluster
                        SAME_PIXELS = "pre_post", DONUT_RINGS = integer(0), LANDUSE_KEEP = "all", BASELINE_NDVI_MIN = NA, MIN_PIXEL_COVERAGE_PCT = 0.05,
                        DROP_SINGLETONS = FALSE, PRECISION_TOLERANCE = 1e-6)   # spec 1 / 3
design_variant_samples <- function(variants, out_dir, outcome = "NDVI") {
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  for (nm in names(variants)) {
    for (k in names(DESIGN_DEFAULTS)) assign(k, DESIGN_DEFAULTS[[k]], envir = globalenv())
    v <- variants[[nm]]
    for (k in names(v)) assign(k, if (is.null(v[[k]]) || (is.list(v[[k]]) && !length(v[[k]]))) { if (k == "COVARIATES") character(0) else NA } else unlist(v[[k]]), envir = globalenv())
    r <- tryCatch({
      d <- model_design(verbose = FALSE, force = TRUE); x <- load_panel_R(outcome, d)
      out <- x[, .(pixel_id, site_id, Year, Season, buff_km, treat, post, did, cohort, event_time, dose, unit, period, cluster_id)]
      fwrite(out, file.path(out_dir, paste0(nm, ".csv")))
      writeLines(toJSON(list(tag = scenario_tag(d), control_rings = d$control_rings, year_min = d$year_min, year_max = d$year_max, drop_years = d$drop_years,
                             seasons = d$seasons, treatment_year = d$treatment_year, site_start = d$site_start, site_years = d$site_years, n_sites = d$n_sites,
                             sites = d$sites, choices = d$choices, rows = nrow(out)), auto_unbox = TRUE, digits = NA, null = "null", na = "null"),
                 file.path(out_dir, paste0(nm, ".json")))
      "ok" }, error = function(e) conditionMessage(e))
    if (!identical(r, "ok")) writeLines(toJSON(list(error = r), auto_unbox = TRUE), file.path(out_dir, paste0(nm, ".json")))
    cat(sprintf("[R] %-28s %s\n", nm, r))
  }
  for (k in names(DESIGN_DEFAULTS)) assign(k, DESIGN_DEFAULTS[[k]], envir = globalenv())
  invisible(TRUE)
}
