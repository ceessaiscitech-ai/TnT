# run_one.R -- ONE model through its pre-built R package, for the Python pipeline (v20.43).
#   Rscript --vanilla R/run_one.R <MODEL> <OUTCOME> <INPUT .parquet|.csv> <OUT_DIR>
# Writes <OUT_DIR>/result.json:
#   ok, model, outcome, estimate, se, p_value, engine, packages {name: version}, r_version, head {...}, table [...], error
# The Python side (_common.prebuilt_first) makes it the model's PRIMARY result when this route is verified on a known
# answer (verify_r_models); any error here hands the model to the next implementation, with this error as the reason.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) stop("usage: Rscript run_one.R <MODEL> <OUTCOME> <INPUT> <OUT_DIR>")
model <- args[1]; outcome <- args[2]; input <- args[3]; out <- args[4]
dir.create(out, recursive = TRUE, showWarnings = FALSE)
self <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
here <- if (length(self) && !is.na(self)) dirname(normalizePath(self)) else "R"
suppressPackageStartupMessages({ library(data.table); library(jsonlite) })
if (file.exists(file.path(here, "reward_packages.R"))) { AUTO_INSTALL_PACKAGES <- !identical(Sys.getenv("REWARD_AUTO_INSTALL"), "0")   # v20.55: a missing
  source(file.path(here, "reward_packages.R"), local = environment()) }                                                # package is installed on first use

R_PACKAGES <- list(M03 = "DRDID", M04 = "qte", M09 = "fixest", M10 = "fixest", M12 = "fixest", M13 = "DIDmultiplegtDYN",
                   M14 = c("MatchIt", "fixest"), M15 = "fixest", M17 = "spdep", M18 = "spdep", M19 = c("lme4", "performance"),
                   M20 = c("metafor", "fixest"), M22 = "bacondecomp", M24 = "fixest", M25 = c("ritest", "fixest"), M26 = "fixest",
                   M27 = "didimputation", M28 = "did2s", M29 = "fixest", M30 = "did", M31 = "fixest", M32 = "etwfe",
                   M33 = c("WeightIt", "fixest"), M35 = "quantreg", M36 = "fect", M37 = "fect", M38 = "gsynth", M39 = "grf",
                   M40 = c("DoubleML", "mlr3", "mlr3learners", "ranger"), M41 = "grf", M42 = "grf", M43 = "grf", M44 = "bartCause",
                   M45 = "glmnet", M34 = c("HonestDiD", "fixest"))           # v20.58: M45 the elastic-net SC (as Python), M34 R's core model
ver <- function(p) tryCatch(as.character(utils::packageVersion(p)), error = function(e) NA_character_)
`%||%` <- function(a, b) if (is.null(a) || !length(a)) b else a
first_num <- function(x, keys) {
  for (k in keys) if (!is.null(x[[k]]) && length(x[[k]])) { v <- suppressWarnings(as.numeric(x[[k]][1])); if (is.finite(v)) return(v) }
  NA_real_
}
standardise <- function(model, r) {
  tab <- NULL; head <- list()
  if (is.list(r) && !is.data.frame(r) && !is.null(r$estimate) && is.null(r$result) && is.null(r$global)) {   # v20.58: a core model (M02, M34 ...)
    head <- r[vapply(r, function(v) is.atomic(v) && length(v) == 1L, TRUE)]; tab <- r$table
  } else if (is.list(r) && !is.data.frame(r)) {
    if (model == "M18" && !is.null(r$lisa)) tab <- r$lisa
    else if (model == "M39" && !is.null(r$cate_by_covariate)) tab <- r$cate_by_covariate
    else if (!is.null(r$table)) tab <- r$table
    r1 <- if (!is.null(r$global)) r$global else if (!is.null(r$result)) r$result else NULL
    if (!is.null(r1)) head <- as.list(as.data.frame(r1)[1, , drop = FALSE])     # v20.58: M39's headline too -- the forest's ATT and SE (as R's own run)
  } else if (is.data.frame(r)) {
    if (nrow(r) == 1) head <- as.list(as.data.frame(r)[1, , drop = FALSE]) else tab <- r
  }
  est <- first_num(head, c("att", "ate", "beta", "att_avg", "pooled", "moran_I", "estimate", "ICC"))
  se  <- first_num(head, c("se", "std.error", "se_att"))
  p   <- first_num(head, c("p_value", "p_ri", "Q_p"))
  if (!is.finite(est) && !is.null(tab)) {                  # a table: the model's headline number
    t <- as.data.table(tab); b <- intersect(c("beta", "estimate", "att"), names(t))[1]
    if ("event_time" %in% names(t)) est <- mean(t[event_time >= 0][[b]], na.rm = TRUE)
    else if ("event" %in% names(t)) est <- mean(t[event >= 0][[b]], na.rm = TRUE)
    else if ("term" %in% names(t) && any(t$term == "did")) { est <- t[term == "did"][[b]][1]; if ("se" %in% names(t)) se <- t[term == "did"]$se[1] }
    else if ("term" %in% names(t) && any(grepl("::0:", t$term, fixed = TRUE))) est <- t[grepl("::0:", term, fixed = TRUE)][[b]][1]
    else if ("term" %in% names(t) && all(grepl("^exposure", t$term))) est <- mean(t[[b]], na.rm = TRUE)
    else if ("tau" %in% names(t)) { rw <- t[abs(tau - 0.5) < 1e-9]; est <- rw[[b]][1]                 # v20.58: the SE / p of the SAME row
      if ("se" %in% names(rw)) se <- suppressWarnings(as.numeric(rw$se[1])); if ("p_value" %in% names(rw)) p <- suppressWarnings(as.numeric(rw$p_value[1]))
      if ("se_note" %in% names(rw)) head$se_note <- as.character(rw$se_note[1]) }
    else if ("placebo_year" %in% names(t)) est <- mean(t$beta, na.rm = TRUE)
    else if ("cohort" %in% names(t)) est <- mean(t$att, na.rm = TRUE)
    else if ("learner" %in% names(t)) est <- mean(t$ate, na.rm = TRUE)
    else if ("cate_mean" %in% names(t)) est <- mean(t$cate_mean, na.rm = TRUE)
    else if (all(c("weight", "estimate") %in% names(t))) est <- sum(t$weight * t$estimate) / sum(t$weight)
    else if ("local_I" %in% names(t)) est <- mean(t$local_I, na.rm = TRUE)
    else if ("ICC" %in% names(t)) est <- t$ICC[1]
  }
  list(estimate = est, se = se, p_value = p, head = head, table = if (!is.null(tab)) as.data.frame(tab) else NULL)
}

res <- list(ok = FALSE, model = model, outcome = outcome, r_version = paste(R.version$major, R.version$minor, sep = "."))
res$packages <- as.list(sapply(unique(c("data.table", "fixest", R_PACKAGES[[model]])), ver))
tryCatch({
  dt <- if (grepl("\\.parquet$", input)) {
    if (!requireNamespace("arrow", quietly = TRUE)) stop("install the R package 'arrow' to read parquet input")
    as.data.table(arrow::read_parquet(input))
  } else fread(input)
  suppressPackageStartupMessages(library(fixest))
  DEFAULT_COVS <- c("Rain", "Tmax", "Tmean", "Tmin")          # v20.45: the four weather covariates; LandUse is never one
  ec <- Sys.getenv("REWARD_COVARIATES", unset = NA)            # v20.58: the Python design's COVARIATES ("" = none) -- every covariate-using
  if (!is.na(ec)) DEFAULT_COVS <- if (nzchar(ec)) strsplit(ec, ",", fixed = TRUE)[[1]] else character(0)   #   model follows it (covs_in)
  RESULTS_ROOT <- out
  out_dir <- function(model, tag) { d <- file.path(RESULTS_ROOT, model); dir.create(d, recursive = TRUE, showWarnings = FALSE); d }
  if (!"unit" %in% names(dt)) dt[, unit := pixel_id]
  if ("cohort" %in% names(dt)) dt[, cohort := suppressWarnings(as.numeric(cohort))]
  if ("event_time" %in% names(dt)) dt[, event_time := suppressWarnings(as.numeric(event_time))]
  setattr(dt, "scenario", "bridge"); setattr(dt, "covariates_used", intersect(DEFAULT_COVS, names(dt)))
  source(file.path(here, "models_prebuilt.R"), local = FALSE)
  # v20.58: the core models of the R pipeline (reward_models_core.R) run here too -- with the SAME code as R's own run, so a Python model whose
  # PRIMARY is R gives R's number (M34: HonestDiD on M02's event study; v20.57 Python used diff-diff's on a Callaway-Sant'Anna base)
  CORE_R <- c("M01", "M02", "M05", "M06", "M11", "M16", "M21", "M23", "M34")
  if (model %in% CORE_R) {
    COVARIATES <- DEFAULT_COVS; RESULTS_DIR <- out; R_HOME_DIR <- dirname(here)
    if (!exists("SEASON_LABEL")) SEASON_LABEL <- c("0" = "Yearly", "1" = "Kharif", "2" = "Rabi", "3" = "Zaid")
    if (!exists("ok", mode = "function")) ok <- function(...) cat("[OK]      ", ..., "\n", sep = "")
    if (!exists("warn", mode = "function")) warn <- function(...) cat("[WARNING] ", ..., "\n", sep = "")
    core <- new.env(parent = globalenv())                   # its own environment: the core's standardise() (R's headline row) must not replace
    source(file.path(here, "reward_models_core.R"), local = core)   # the bridge's (result.json) -- v20.58's first bridge run of M34 failed on that
    r <- core$MODEL_FUN[[model]](dt, outcome)
  } else r <- run_model_strict(model, dt, outcome)
  s <- standardise(model, r)
  res$estimate <- s$estimate; res$se <- s$se; res$p_value <- s$p_value; res$head <- s$head; res$table <- s$table
  if (is.list(r) && !is.data.frame(r)) { res$se_how <- r$se_how %||% s$head$se_how; res$p_how <- r$p_how %||% s$head$p_how }   # v20.58: what the SE and p are
  else if (is.data.frame(r) && "se_how" %in% names(r)) { res$se_how <- as.character(r$se_how[1]); if ("p_how" %in% names(r)) res$p_how <- as.character(r$p_how[1]) }
  res$engine <- paste0("R ", paste(R_PACKAGES[[model]] %||% "fixest", collapse = " + "))
  # v20.58: what the SE and the p ARE, never a generic label -- R's own texts (r_se_how) when the model gave none; the p of a package said too
  if (!nzchar(res$se_how %||% "") && is.finite(res$se %||% NA_real_) && exists("r_se_how", mode = "function"))
    res$se_how <- tryCatch(r_se_how(model, dt, res$engine), error = function(e) NULL)
  if (is.finite(res$p_value %||% NA_real_) && !nzchar(res$p_how %||% "")) {
    res$p_how <- if (!is.null(s$head$p_ri)) "randomisation inference: (1 + #{|beta_perm| >= |beta|}) / (1 + permutations)"
                 else if ("fixest" %in% (R_PACKAGES[[model]] %||% "fixest") && "cluster_id" %in% names(dt)) sprintf("fixest: t with %d df (the clusters - 1)", max(1L, uniqueN(dt$cluster_id) - 1L))
                 else NULL }
  res$ok <- is.finite(s$estimate) || !is.null(s$table)
  if (!res$ok) res$error <- "the package returned no usable estimate"
}, error = function(e) res$error <<- conditionMessage(e))
writeLines(toJSON(res, auto_unbox = TRUE, digits = NA, na = "null", null = "null", force = TRUE), file.path(out, "result.json"))
