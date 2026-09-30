# run_all_tests.R -- THE COMPLETE R TEST (v20.58). RStudio: open RWDR.Rproj, open this file, Source.
# Terminal (from the R folder):  Rscript tests/run_all_tests.R          (everything, ~15-30 min on one core)
#                                Rscript tests/run_all_tests.R quick    (the models only, no notebook runs)
# A  ONE sub-watershed (Haligeri, as a single-site run): 10 years x (annual + Kharif), effect +0.05 from 2022.
# B  EIGHT sub-watersheds pooled: two cohorts (2020 and 2022), a fund file for the dose, export folders named the way
#    the real exports are -- "REWARD_<name>_Exports_final", misspelt names and files WITHOUT SWSiD_All, so the 80 % name
#    rule has to identify them.
# A model PASSES only with a result that meets its KNOWN ANSWER. A data gap is accepted only where the data truly lack
# what the model needs (listed per scenario). Anything else FAILS -- an error, an SE of ~0, a missing estimate.
# Then (not "quick") EVERY notebook on scenario B: rendered as RStudio's Knit does it (a fresh R session, rmarkdown)
# and executed in Jupyter through the R kernel (IRkernel). One table at the end: PASS / DATA GAP / FAIL.
# (v20.47's test called anything that did not crash a PASS -- the first real run showed that hid eleven defects.)
# C  (v20.54) the covariate rules as in Python (exported 0 / fill values missing, the negative barrier and its switch),
#    MEMORY_SHARE honoured, a D:/ root off Windows kept out of the project folder; (v20.58) a repeated row dropped whole.
# D  (v20.55) seasons AND years together (SEASONS kept by the recommended design), the season modes, the unbalanced panel,
#    the annual covariate fill, OVERLAP_ROWS, POOLED_FE, the common-shock rule, the one-to-one pixel merge, the package
#    confirmation -- every rule the Python pipeline applies (validate_r_parity.py proves the two structure the data alike).
# E  (v20.57) EVERY DESIGN OPTION AT THE MODEL STAGE: Artal's exports with a fragment of Beguru's core and a stray file of a
#    third sub-watershed, a fund workbook; each option (timing fund / registry / fixed, the fund rule, the dose, rings, years,
#    seasons, fragments, overlap, gap-filled, transition year) is set as a model notebook sets it and must do exactly that --
#    on ONE panel that R_P00 built once and that no option changes (python/validate_design_options.py: R == Python).
# F  (v20.58) YOUR RULE: no excluded row reaches any model -- your Koranahalli layout (named exports + repeating tiles, pixels outside every
#    polygon, a neighbour's core, a ring that flips, a shifted grid), written CLEAN and POISONED (every excluded row +5): all models identical,
#    the effect models at the truth, an SE and a p on every effect.
# G  (v20.58) the fall-backs beyond 98 % of the RAM are BATCHES (every unit used; forced here), the spatial statistics are spdep's to 1e-10,
#    the quantile DiD's cluster-robust SE reduces to quantreg's own.
# H  (v20.58) BEYOND 98 % OF THE RAM -- OUT OF CORE, EXACT: M01, M02, M16 and M34 on pixel partitions (lib/reward_outofcore.R) on EVERY engine
#    of this machine (Dask, Spark, R batches) give the in-memory numbers (fixest's to its convergence, 1e-8) and each other's exactly; a budget
#    below the need switches by itself; R_P00 block by block (lib/reward_prep_ooc.R) writes the SAME panel row for row and the same reports;
#    the design from the data and the outcome identities out of core are the in-memory ones.
args <- commandArgs(trailingOnly = TRUE); QUICK <- "quick" %in% args
# v20.58: "only=F" (or "only=B,F") runs those scenarios only -- the loop of fixes re-runs what it changed; a full run has no "only="
ONLY <- toupper(unlist(strsplit(sub("^only=", "", grep("^only=", args, value = TRUE)), ",")))
RUN <- function(k) !length(ONLY) || k %in% ONLY
R_HOME_DIR <- normalizePath(if (file.exists("lib/reward_paths.R")) "." else "..", winslash = "/")
# v20.51: the test points the SESSION at its own synthetic folder through environment variables. v20.50 left them set,
# so after Sourcing a test in RStudio, R_P00 read the test's sample files instead of your data. They are now restored
# (and your paths reloaded) when the test ends -- also if it stops with an error.
.env_keys <- c("REWARD_R_ROOT", "REWARD_SITES_CSV", "REWARD_FUND_PATH", "REWARD_TEST_RUN")
.env_old <- Sys.getenv(.env_keys, unset = NA_character_)
.restore_env <- function() {
  for (k in .env_keys) if (is.na(.env_old[[k]])) Sys.unsetenv(k) else do.call(Sys.setenv, setNames(list(.env_old[[k]]), k))
  try(suppressMessages(source(file.path(R_HOME_DIR, "lib", "reward_paths.R"))), silent = TRUE)
  cat("[INFO]    test finished -- this R session points at your data again:", ROOT, "\n")
}
Sys.setenv(REWARD_TEST_RUN = "1")
suppressPackageStartupMessages({ library(data.table); library(sf) })
RES <- list(); add <- function(scn, step, status, detail = "") RES[[length(RES) + 1]] <<- data.table(scenario = scn, step = step, status = status, detail = substr(gsub("\\s+", " ", detail), 1, 130))
load_libs <- function() for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
TMP <- file.path(tempdir(), "reward_all_tests"); unlink(TMP, recursive = TRUE); dir.create(TMP)
POLY <- st_read(file.path(R_HOME_DIR, "data", "sites", "SWSs20_KarnatakaAll5k.shp"), quiet = TRUE)
REG <- fread(file.path(R_HOME_DIR, "data", "sites", "sites.csv"))

# ---------------------------------------------------------------- the synthetic exports
make_scenario <- function(key, sites, cohort, n_ring, folder_of, file_of, with_id) {
  root <- file.path(TMP, key); dir.create(root, recursive = TRUE); set.seed(20 + nchar(key))
  sc <- copy(REG); sc[, treatment_year := as.numeric(treatment_year)]
  sc[SWSiD_All %in% as.integer(names(cohort)), treatment_year := as.numeric(cohort[as.character(SWSiD_All)])]
  fwrite(sc, file.path(root, "..", paste0(key, "_sites_test.csv")))
  pix <- rbindlist(lapply(sites, function(s) {
    h <- POLY[POLY$SWSiD_All == s, ]
    p <- do.call(rbind, lapply(0:5, function(r) st_sf(buff_km = r, geometry = st_sample(h[h$buff_km == r, ], n_ring))))
    ll <- st_coordinates(st_transform(p, 4326)); data.table(site = s, buff_km = p$buff_km, latitude = ll[, 2], longitude = ll[, 1], a = rnorm(nrow(p), 0, 0.03))
  }))
  yrs <- 2016:2025; shock <- setNames(rnorm(length(yrs), 0, 0.01), yrs)
  sshock <- CJ(site = sites, Year = yrs)[, s_sh := rnorm(.N, 0, 0.004)]
  for (s in sites) {
    dir.create(file.path(root, folder_of(s)), recursive = TRUE, showWarnings = FALSE)
    P <- pix[site == s]; yr0 <- cohort[[as.character(s)]]
    for (y in yrs) for (se in c("yearly", "Kharif")) {
      eff <- ifelse(P$buff_km == 0 & y >= yr0, 0.05, 0)
      d <- data.table(latitude = P$latitude, longitude = P$longitude, buff_km = P$buff_km, SubwshedID = "U1",
                      NDVI = 0.30 + P$a + 0.01 * (y - 2016) + shock[as.character(y)] + sshock[site == s & Year == y, s_sh] + eff +
                             rnorm(nrow(P), 0, 0.01) + (se == "Kharif") * 0.05,
                      Rain = 600 + rnorm(nrow(P), 0, 30), Tmax = 33 + rnorm(nrow(P), 0, .3), Tmean = 26 + rnorm(nrow(P), 0, 0.5),
                      Tmin = 19 + rnorm(nrow(P), 0, .3), LandUse = 1 + (seq_len(nrow(P)) %% 3))
      if (with_id(s)) d[, SWSiD_All := s]
      fwrite(d, file.path(root, folder_of(s), file_of(s, y, se)))
    }
  }
  list(root = normalizePath(root, winslash = "/"), sites_csv = normalizePath(file.path(root, "..", paste0(key, "_sites_test.csv")), winslash = "/"))
}
use_scenario <- function(S, fund = "") {
  Sys.setenv(REWARD_R_ROOT = S$root, REWARD_SITES_CSV = S$sites_csv, REWARD_FUND_PATH = if (nzchar(fund)) fund else file.path(S$root, "no_fund_file.xlsx"))
  load_libs()                                                    # v20.57: every design option back to its default (reward_paths.R)
}

# ---------------------------------------------------------------- the known answers (effect +0.05 everywhere)
ATT    <- c("M01", "M02", "M03", "M05", "M09", "M11", "M12", "M14", "M21", "M22", "M23", "M26", "M27", "M28", "M29",
            "M30", "M31", "M32", "M33", "M34")          # v20.58: M24's headline is the SPILLOVER (nearest ring vs the farthest): truth 0;
                                                        # M10's the TRIPLE difference (land use 2 minus the rest, as Python): truth 0
ATT_ML <- c("M04", "M13", "M35", "M36", "M37", "M38", "M39", "M40", "M41", "M42", "M43", "M44", "M45")   # looser: +-0.02
judge <- function(m, r) {
  e <- suppressWarnings(as.numeric(r$estimate)); pv <- if ("p_value" %in% names(r)) suppressWarnings(as.numeric(r$p_value)) else NA_real_
  if (!isTRUE(is.finite(e))) return(c("FAIL", "no headline estimate"))
  if (isTRUE(r$se_invalid)) return(c("FAIL", paste("SE ~ 0:", r$se_invalid_why)))
  if (m %in% ATT)    return(if (abs(e - 0.05) <= 0.01) c("PASS", sprintf("%.4f (truth 0.05 +- 0.01)", e)) else c("FAIL", sprintf("%.4f, truth 0.05 +- 0.01", e)))
  if (m %in% ATT_ML) return(if (abs(e - 0.05) <= 0.02) c("PASS", sprintf("%.4f (truth 0.05 +- 0.02)", e)) else c("FAIL", sprintf("%.4f, truth 0.05 +- 0.02", e)))
  if (m == "M15") return(if (abs(e) <= 0.01) c("PASS", sprintf("placebo %.4f (truth 0)", e)) else c("FAIL", sprintf("placebo %.4f, truth 0", e)))
  if (m == "M24") return(if (abs(e) <= 0.01) c("PASS", sprintf("spillover %.4f (truth 0: no spillover simulated)", e)) else c("FAIL", sprintf("spillover %.4f, truth 0", e)))
  if (m == "M16") return(if (e >= 0 && e < 1e4 && isTRUE(pv > 0.001)) c("PASS", sprintf("F %.3g, p %.3g (no pre-trend simulated)", e, pv)) else c("FAIL", sprintf("F %.3g, p %.3g", e, pv)))
  if (m %in% c("M17", "M18")) return(if (abs(e) <= 1) c("PASS", sprintf("Moran's I %.3f", e)) else c("FAIL", sprintf("I %.3f outside [-1, 1]", e)))
  if (m == "M19") return(if (e >= 0 && e <= 1) c("PASS", sprintf("ICC %.3f", e)) else c("FAIL", sprintf("ICC %.3f outside [0, 1]", e)))
  if (m == "M10") return(if (abs(e) <= 0.01) c("PASS", sprintf("triple difference %.4f (truth 0: no heterogeneity by land use simulated)", e)) else c("FAIL", sprintf("triple difference %.4f, truth 0", e)))
  if (m == "M20") { pe <- if ("pooled_effect" %in% names(r)) suppressWarnings(as.numeric(r$pooled_effect)) else NA_real_   # v20.58: the TEST (as Python)
    return(if (is.finite(e) && e >= 0 && isTRUE(pv > 0.001) && isTRUE(abs(pe - 0.05) <= 0.01)) c("PASS", sprintf("Q %.3g, p %.3g (homogeneous effects simulated); pooled %.4f", e, pv, pe))
           else c("FAIL", sprintf("Q %.3g, p %.3g, pooled %.4f (truth 0.05)", e, pv, pe))) }
  if (m == "M25") return(if (abs(e - 0.05) <= 0.01 && isTRUE(pv < 0.05)) c("PASS", sprintf("estimate %.4f, randomisation p %.3g (true effect: must be small)", e, pv)) else c("FAIL", sprintf("estimate %.4f, randomisation p %.3g", e, pv)))
  if (m %in% c("M06", "M07")) return(c("PASS", sprintf("estimate %.4g (no known answer; runs end to end)", e)))
  c("FAIL", "no rule")
}
run_models <- function(scn, gaps) {
  d <- load_design()
  for (m in names(MODEL_FUN)) {
    r <- tryCatch(run_model_R(m, "NDVI", d), error = function(e) e)
    od <- file.path(RESULTS_DIR, m, scenario_tag(d)); gf <- file.path(od, sprintf("%s_NDVI_DATA_GAP.csv", m)); rf <- file.path(od, sprintf("%s_NDVI.csv", m))
    if (inherits(r, "error")) { add(scn, m, "FAIL", conditionMessage(r)); next }
    if (file.exists(gf) && (!file.exists(rf) || file.mtime(gf) >= file.mtime(rf))) {
      why <- tryCatch(paste(fread(gf)$reason, collapse = " "), error = function(e) ""); if (!length(why) || is.na(why)) why <- ""; pat <- gaps[[m]]
      if (!is.null(pat) && grepl(pat, why, fixed = TRUE)) add(scn, m, "DATA GAP", why)
      else if (grepl("^install ", why)) add(scn, m, "DATA GAP", paste("package missing:", why))
      else add(scn, m, "FAIL", paste("unexpected gap:", why))
      next
    }
    if (!file.exists(rf)) { add(scn, m, "FAIL", "no result and no data-gap file"); next }
    j <- judge(m, fread(rf)); add(scn, m, j[1], j[2])
  }
}

tryCatch({
# ---------------------------------------------------------------- A: one sub-watershed
if (RUN("A")) {
A <- make_scenario("A_one_sws", 7L, c("7" = 2022), 120, function(s) "Haligeri", function(s, y, se) sprintf("CSV_%d_%s_tile0.csv", y, se), function(s) TRUE)
use_scenario(A)
t <- tryCatch({ run_prep(); prepare_design() }, error = function(e) e)
add("A", "preparation", if (inherits(t, "error")) "FAIL" else "PASS", if (inherits(t, "error")) conditionMessage(t) else scenario_tag(t))
if (!inherits(t, "error"))                                                         # v20.57: no fund workbook here -> registry years, said so
  add("A", "fund timing without a workbook: each sub-watershed on its registry year, the results folder says so (_fundMissing)",
      if (grepl("_siteyrs2022_fundMissing", scenario_tag(t), fixed = TRUE) && all(t$site_years$year == 2022L)) "PASS" else "FAIL", scenario_tag(t))
run_models("A", list(M06 = "no dose", M07 = "not fitted", M08 = "instrument", M20 = ">= 2 sub-watersheds"))   # v20.58: M45 = the ring-series elastic net (one sub-watershed suffices)
}

# ---------------------------------------------------------------- C: the covariate rules and settings (v20.54, as Python)
if (RUN("C")) {
if (!exists("read_export", mode = "function")) load_libs()      # v20.58: "only=C" runs C on its own (A loads the libraries otherwise)
fC <- file.path(TMP, "covariate_rules.csv")
fwrite(data.table(latitude = 16.1, longitude = 75.1, buff_km = 0, SubwshedID = "U1", NDVI = 0.4, Rain = c(-1.5, 0, -9999, 5), Tmin = c(-10, 18, -3, 0)), fC)   # v20.55: SubwshedID is essential, as in Python
ALLOW_NEGATIVE_COVARIATES <- FALSE; r_on <- read_export(fC, 2020L, 1L, "x", "x")
ALLOW_NEGATIVE_COVARIATES <- TRUE;  r_off <- read_export(fC, 2020L, 1L, "x", "x"); ALLOW_NEGATIVE_COVARIATES <- FALSE
okC <- isTRUE(all.equal(r_on$Rain, c(0, NA, NA, 5))) && isTRUE(all.equal(r_on$Tmin, c(NA, 18, 0, NA))) &&
       isTRUE(all.equal(r_off$Rain, c(-1.5, NA, NA, 5))) && isTRUE(all.equal(r_off$Tmin, c(NA, 18, -3, NA)))
add("C", "covariates as Python: exported 0 and fill values missing; negatives floored (barrier on) / kept (ALLOW_NEGATIVE_COVARIATES)",
    if (okC) "PASS" else "FAIL", sprintf("on: Rain %s Tmin %s | off: Rain %s Tmin %s", paste(r_on$Rain, collapse = ","), paste(r_on$Tmin, collapse = ","),
                                          paste(r_off$Rain, collapse = ","), paste(r_off$Tmin, collapse = ",")))
MEMORY_SHARE <- 0.5; s_half <- memory_share(FALSE); MEMORY_SHARE <- 1.0; s_all <- memory_share(FALSE)
add("C", "MEMORY_SHARE honoured (your optional manual setting; 1.0 = the whole machine)", if (s_half == 0.5 && s_all == 1) "PASS" else "FAIL",
    sprintf("0.5 -> %s, 1.0 -> %s", s_half, s_all))
pr <- portable_root("D:/LKT/RWDR/data", TRUE)
add("C", "a D:/ root off Windows maps under ~/REWARD_data (no stray 'D:' folder in the project)",
    if (.Platform$OS.type == "windows" || (grepl("REWARD_data", pr, fixed = TRUE) && !grepl("^[A-Za-z]:", pr))) "PASS" else "FAIL", pr)
# v20.58 (second pass, found by the poison test with cloud gaps): a REPEATED row is dropped WHOLE -- none of its values fills a gap of the kept row
# (until v20.58 R_P00 and P00 filled the kept row's gaps from the dropped rows); DEDUP_FILL_FROM_DUPLICATES = TRUE is the option -- as Python
dd <- data.table(site_id = 1L, pixel_id = c(1, 1, 2), Year = 2023L, Season = 1L, NDVI = c(NA, 0.9, 0.5), LAI = c(1.0, 1.5, 1.1),
                 src_file = c("new.csv", "old.csv", "old.csv"), file_mtime = c(9, 1, 1))
r0 <- resolve_duplicates(copy(dd)); DEDUP_FILL_FROM_DUPLICATES <- TRUE; r1 <- resolve_duplicates(copy(dd)); DEDUP_FILL_FROM_DUPLICATES <- FALSE
k0 <- r0[pixel_id == 1]; k1 <- r1[pixel_id == 1]
okDup <- nrow(r0) == 2L && nrow(k0) == 1L && is.na(k0$NDVI) && isTRUE(k0$LAI == 1) && identical(attr(r0, "dedup")$not_used, 1L) && identical(attr(r0, "dedup")$filled, 0L) &&
         nrow(k1) == 1L && isTRUE(all.equal(k1$NDVI, 0.9)) && isTRUE(k1$LAI == 1) && identical(attr(r1, "dedup")$filled, 1L)
add("C", "a repeated row is dropped WHOLE: the kept (newer) row keeps its gap, the older row's value is not used; DEDUP_FILL_FROM_DUPLICATES = TRUE fills it (as Python)",
    if (okDup) "PASS" else "FAIL", sprintf("default: NDVI %s LAI %s (values not used %s) | TRUE: NDVI %s LAI %s (filled %s)", k0$NDVI, k0$LAI, attr(r0, "dedup")$not_used,
                                           k1$NDVI, k1$LAI, attr(r1, "dedup")$filled))
}

# ---------------------------------------------------------------- D (v20.55): seasons + years together, your options, the unbalanced panel,
if (RUN("D")) {
# the pooled site x period FE, the common-shock rule, the one-to-one pixel merge, the package confirmation -- each as in Python
make_D <- function() {
  root <- file.path(TMP, "D_options"); dir.create(root, recursive = TRUE); set.seed(55)
  sc <- copy(REG); sc[, treatment_year := as.numeric(treatment_year)]; sc[SWSiD_All %in% c(1L, 7L), treatment_year := 2022]
  fwrite(sc, file.path(TMP, "D_sites_test.csv"))
  pix <- rbindlist(lapply(c(1L, 7L), function(s) {
    h <- POLY[POLY$SWSiD_All == s, ]
    p <- do.call(rbind, lapply(0:5, function(r) st_sf(buff_km = r, geometry = st_sample(h[h$buff_km == r, ], 12))))
    ll <- st_coordinates(st_transform(p, 4326)); data.table(site = s, buff_km = p$buff_km, latitude = ll[, 2], longitude = ll[, 1], a = rnorm(nrow(p), 0, 0.03))
  }))
  # one pixel OUTSIDE every polygon, carried by BOTH exports: core (buff 0) in Artal's file, ring 3 in Haligeri's -> the overlap case
  bb <- st_bbox(st_transform(POLY, 4326)); out_pt <- c(lat = unname(bb["ymax"]) + 0.05, lon = unname(bb["xmax"]) + 0.05)
  yrs <- 2016:2025; shock <- setNames(rnorm(length(yrs), 0, 0.005), yrs); shock["2023"] <- 0.06          # 2023: a common shock (weather), reverting
  for (s in c(1L, 7L)) {
    fd <- file.path(root, if (s == 1L) "REWARD_Artal_Exports_final" else "REWARD_Haligeri_Exports_final"); dir.create(fd, recursive = TRUE, showWarnings = FALSE)
    P <- pix[site == s]
    for (y in yrs) for (se in c("yearly", "Kharif", "Rabi")) {
      if (se == "Rabi" && !y %in% c(2018:2021, 2023)) next                                    # Rabi only in some years: an unbalanced panel
      sec <- c(yearly = 0, Kharif = 1, Rabi = 2)[[se]]
      lat <- P$latitude + if (y == 2025) 3 / 110574 else 0                                     # 2025: the grid shifted 3 m (one-to-one merge)
      eff <- ifelse(P$buff_km == 0 & y >= 2022, 0.05, 0)
      bk <- P$buff_km; if (s == 7L && y >= 2023) bk[which(P$buff_km == 1L)[1]] <- 0L          # v20.58: one Haligeri ring-1 pixel the export
      d <- data.table(latitude = lat, longitude = P$longitude, buff_km = bk, SubwshedID = "U1", SWSiD_All = s,   # calls core from 2023 (ring conflict)
                      NDVI = 0.30 + P$a + 0.01 * (y - 2016) + shock[as.character(y)] + eff + rnorm(nrow(P), 0, 0.01) + c(0, 0.05, -0.02)[sec + 1],
                      Rain = 600 + rnorm(nrow(P), 0, 30), Tmax = 33 + rnorm(nrow(P), 0, .3), Tmean = 26 + rnorm(nrow(P), 0, 0.5), Tmin = 19 + rnorm(nrow(P), 0, .3), LandUse = 1)
      d[, EVI := 0.8 * NDVI]
      if (s == 1L && se == "yearly") d[, c("Rain", "Tmax", "Tmean", "Tmin") := NA_real_]      # Artal's annual composite lacks weather (filled from the seasons)
      if (s == 1L && y == 2019 && se == "Kharif") d[1:3, NDVI := NA_real_]                     # NDVI missing in three cells (EVI present)
      d <- rbind(d, data.table(latitude = out_pt[["lat"]], longitude = out_pt[["lon"]], buff_km = if (s == 1L) 0 else 3, SubwshedID = "U1", SWSiD_All = s,
                               NDVI = 0.5 + eff[1] * (s == 1L), Rain = 600, Tmax = 33, Tmean = 26, Tmin = 19, LandUse = 1, EVI = 0.4), fill = TRUE)
      fwrite(d, file.path(fd, sprintf("CSV_%d_%s_tile0.csv", y, se)))
    }
  }
  P7 <- pix[site == 7L]; flip_pt <- c(lat = P7[buff_km == 1L]$latitude[1], lon = P7[buff_km == 1L]$longitude[1])
  list(root = normalizePath(root, winslash = "/"), sites_csv = normalizePath(file.path(TMP, "D_sites_test.csv"), winslash = "/"), out_pt = out_pt, flip_pt = flip_pt)
}
D <- make_D(); use_scenario(D)
SEASONS <- "all"; OVERLAP_ROWS <- "drop"; POOLED_FE <- "site_period"
tD <- tryCatch({ run_prep(); prepare_design() }, error = function(e) e)
add("D", "preparation (two sub-watersheds, Rabi in some years only, a shifted 2025 grid, an annual composite without weather)", if (inherits(tD, "error")) "FAIL" else "PASS",
    if (inherits(tD, "error")) conditionMessage(tD) else scenario_tag(tD))
if (!inherits(tD, "error")) {
  dD <- tD
  # D1 the design keeps YOUR seasons ("all") although Rabi is missing in some years; "auto" would follow the data
  rD <- recommend_design("NDVI", 2022L, write = FALSE)
  add("D", "SEASONS = 'all' kept by the recommended design (the data-driven choice would be yearly: Rabi missing in some years)",
      if (identical(dD$seasons, "all") && identical(rD$seasons, "yearly")) "PASS" else "FAIL", sprintf("design %s | data-driven %s", dD$seasons, rD$seasons))
  # D2 a common shock (2023, both groups, reverting) is reported, not cut; the 2025 shifted grid is merged (linkage 1) -> every post year stays
  add("D", "common-shock rule: 2023 reported as a common shock, post window keeps 2022-2025; shifted 2025 grid merged (pixel history kept)",
      if (2023 %in% rD$common_shocks && !2023 %in% rD$breaks && setequal(rD$post_window, 2022:2025) && isTRUE(rD$linkage[["2025"]] >= 0.95)) "PASS" else "FAIL",
      sprintf("shocks %s | breaks %s | post %s | linkage 2025 %s", paste(rD$common_shocks, collapse = ","), paste(rD$breaks, collapse = ","), paste(rD$post_window, collapse = ","), rD$linkage[["2025"]]))
  ov <- fread(file.path(OUTPUT_DIR, "pixel_overlap_report.csv"))
  add("D", "near-duplicate merge one-to-one (every canonical pixel receives one shifted pixel)", if (ov$pixels_merged > 0 && ov$pixels_merged == ov$canonical_pixels_receiving) "PASS" else "FAIL",
      sprintf("%d merged onto %d canonical pixels", ov$pixels_merged, ov$canonical_pixels_receiving))
  # D3 season modes select the right rows; all = yearly + seasonal
  xs <- lapply(c("all", "seasonal", "yearly", "kharif"), function(m) { dm <- dD; dm$seasons <- m; load_panel_R("NDVI", dm) })
  names(xs) <- c("all", "seasonal", "yearly", "kharif")
  ok3 <- setequal(unique(xs$all$Season), c(0L, 1L, 2L)) && setequal(unique(xs$seasonal$Season), c(1L, 2L)) && identical(unique(xs$yearly$Season), 0L) &&
         identical(unique(xs$kharif$Season), 1L) && nrow(xs$all) == nrow(xs$seasonal) + nrow(xs$yearly)
  add("D", "season modes: all = annual + Kharif + Rabi rows | seasonal | yearly | a named season", if (ok3) "PASS" else "FAIL",
      sprintf("rows all %d = seasonal %d + yearly %d; kharif %d", nrow(xs$all), nrow(xs$seasonal), nrow(xs$yearly), nrow(xs$kharif)))
  # D4 the unbalanced panel: the Rabi years are simply present where exported; a missing NDVI cell leaves only the NDVI estimation
  xe <- load_panel_R("EVI", dD)
  kN <- xs$all[, paste(pixel_id, Year, Season)]; kE <- xe[, paste(pixel_id, Year, Season)]
  gap <- setdiff(kE, kN); gap_pix <- sub(" .*", "", gap)
  ok4 <- length(gap) == 3 && all(gap_pix %in% xs$all$pixel_id) && !length(setdiff(kN, kE)) && setequal(unique(xs$all[Season == 2L, Year]), c(2018:2021, 2023))
  add("D", "unbalanced panel: 3 cells with NDVI missing leave the NDVI estimation only (their pixels keep every other period; EVI keeps the cells); Rabi years present where exported",
      if (ok4) "PASS" else "FAIL", sprintf("cells only in EVI %d, only in NDVI %d, Rabi years %s", length(gap), length(setdiff(kN, kE)), paste(sort(unique(xs$all[Season == 2L, Year])), collapse = ",")))
  # D5 the annual composite's missing weather is filled with the pixel-year's seasonal mean
  ann <- xs$all[site_id == 1L & Season == 0L]                                                        # the fill table is built from the PANEL's seasonal rows (as Python)
  sea <- panel_read(c("pixel_id", "site_id", "Year", "Season", "Rain"))[site_id == 1L & Season != 0L, .(m = mean(Rain, na.rm = TRUE)), by = .(pixel_id, Year)]
  chk <- merge(ann[, .(pixel_id, Year, Rain)], sea, by = c("pixel_id", "Year"))
  add("D", "annual rows: weather the composite lacks filled with the same pixel-year's seasonal mean (as Python)", if (nrow(chk) && all(is.finite(chk$Rain)) && max(abs(chk$Rain - chk$m)) < 1e-9) "PASS" else "FAIL",
      sprintf("%d annual rows filled, max |fill - seasonal mean| %.2g", nrow(chk), if (nrow(chk)) max(abs(chk$Rain - chk$m)) else NA))
  # D6 OVERLAP_ROWS (v20.58, the location rule): a pixel whose RING differs between rows (Haligeri's export calls one ring-1 pixel core from
  # 2023) leaves WHOLE under "drop" (every row, every year) and stays under "keep" (tag _keepOverlap). The pixel outside every polygon that
  # both exports carry has no sub-watershed of its own: it leaves under FRAGMENT_RULE "drop" whatever OVERLAP_ROWS says. (Until v20.57 that
  # outside pixel was the overlap case; the shapefile has no two sub-watersheds' polygons overlapping, so a located pixel cannot be core in
  # one and a control in another -- only an unlocated one could, and the location rule removes it first.)
  xy_D6 <- panel_read(c("pixel_id", "latitude", "longitude"))                      # (not "pl": that name is polars' -- M13 needs it)
  xy_D6[, d_flip := sqrt((latitude - D$flip_pt[["lat"]])^2 + (longitude - D$flip_pt[["lon"]])^2)]   # the nearest pixel (the 2025 grid is shifted 3 m)
  pid_flip <- unique(xy_D6[d_flip < 1e-4 & d_flip == min(d_flip), pixel_id])
  pid_out <- unique(xy_D6[abs(latitude - D$out_pt[["lat"]]) < 1e-6, pixel_id]); rm(xy_D6)
  dk <- dD; dk$overlap_rows <- "keep"; xk <- load_panel_R("NDVI", dk)
  n_drop <- nrow(xs$all[pixel_id %in% pid_flip]); n_keep <- nrow(xk[pixel_id %in% pid_flip]); n_out <- nrow(xs$all[pixel_id %in% pid_out]) + nrow(xk[pixel_id %in% pid_out])
  add("D", "OVERLAP_ROWS: a pixel whose ring differs between rows leaves whole by default, stays with 'keep' (tag _keepOverlap); the pixel outside every polygon never enters",
      if (length(pid_flip) == 1 && n_drop == 0 && n_keep > 0 && length(pid_out) >= 1 && n_out == 0 && grepl("_keepOverlap", scenario_tag(dk), fixed = TRUE) &&
          !grepl("_keepOverlap", scenario_tag(dD), fixed = TRUE)) "PASS" else "FAIL",
      sprintf("ring-conflict pixel(s) %d: rows under drop %d, keep %d | outside pixel(s) %d: rows %d", length(pid_flip), n_drop, n_keep, length(pid_out), n_out))
  # D7 pooled design: the period fixed effect is sub-watershed x year x season (POOLED_FE = "site_period"), as Python
  add("D", "POOLED_FE = site_period: period FE = sub-watershed x year x season in the pooled panel", if (all(grepl("^[0-9]+_[0-9]{4}_[0-9]$", head(xs$all$period, 50)))) "PASS" else "FAIL", paste(head(unique(xs$all$period), 3), collapse = " "))
  # D8 M01 on the seasons-and-years sample recovers the effect with year x season and pixel x season FE
  f1 <- fe_fit(xs$all, "NDVI", c("did", covs_in(xs$all)))
  add("D", "M01 on annual + seasonal rows (pixel x season, site x year x season FE) recovers +0.05", if (abs(f1$coef[["did"]] - 0.05) < 0.01) "PASS" else "FAIL", sprintf("did %.4f (SE %.4f, %s)", f1$coef[["did"]], f1$se[["did"]], f1$engine))
  # D9 the package confirmation every notebook prints
  st <- confirm_packages(install = FALSE, write = FALSE, quiet = TRUE)
  add("D", "packages confirmed at run time (confirm_packages: every R package, its version and route)", if (nrow(st) == length(project_packages()) && all(st$installed)) "PASS" else "DATA GAP",   # v20.58: the project's packages
      sprintf("%d of %d installed%s", sum(st$installed), nrow(st), if (all(st$installed)) "" else paste0(" -- missing: ", paste(st$package[!st$installed], collapse = ", "))))
}
}

# ---------------------------------------------------------------- B: eight sub-watersheds, two cohorts, real-style names
if (RUN("B") || !QUICK) {
sitesB <- c(1L, 2L, 3L, 4L, 7L, 8L, 9L, 10L); cohB <- setNames(c(rep(2022, 4), rep(2020, 4)), sitesB)
spell <- c("1" = "Artal", "2" = "Begur", "3" = "Chatrakodihalli", "4" = "Chittaragi", "7" = "Halligera", "8" = "Honnutagi", "9" = "Hunsehadagli", "10" = "Jammapura")
B <- make_scenario("B_eight_sws", sitesB, cohB, 40, function(s) sprintf("REWARD_%s_Exports_final", spell[[as.character(s)]]),
                   function(s, y, se) if (s == 1L) sprintf("CSV_%s_v111_%d_%s_tile0_sub0.csv", "Artal", y, se) else sprintf("CSV_%d_%s_tile0.csv", y, se),
                   function(s) !s %in% c(1L, 3L, 9L))                                   # three sub-watersheds named ONLY by folder / file
fund <- rbindlist(lapply(sitesB, function(s) { y0 <- cohB[[as.character(s)]]
  dts <- seq(as.Date(sprintf("%d-07-15", y0)), as.Date("2025-01-15"), by = "3 months")
  data.table(SWS = paste(spell[[as.character(s)]], "Sub-watershed"), Date = dts, Progress = cumsum(rep(10 + s, length(dts))) * 1000, Area_ha = 500 + 20 * s) }))
fund_path <- file.path(TMP, "fund_test.xlsx"); openxlsx::write.xlsx(fund, fund_path); fund_path <- normalizePath(fund_path, winslash = "/")
use_scenario(B, fund_path)
t <- tryCatch({ run_prep(); prepare_design() }, error = function(e) e)
add("B", "preparation", if (inherits(t, "error")) "FAIL" else "PASS", if (inherits(t, "error")) conditionMessage(t) else scenario_tag(t))
pn <- panel_read(c("site_id", "site_check"))
nm_ok <- pn[site_id %in% c(1L, 3L, 9L), mean(site_check == 0L)]
add("B", "80 % name rule (files without SWSiD_All)", if (isTRUE(nm_ok == 1)) "PASS" else "FAIL",
    sprintf("rows of Artal / Chatrakodihalli / Hunsehadagli confirmed by their folder or file name: %.1f %%", 100 * nm_ok))
TREATMENT_TIMING <- "registry"; xB <- load_panel_R("NDVI", model_design(verbose = FALSE))      # v20.57: the model stage builds the cohorts
add("B", "two cohorts from sites.csv (TREATMENT_TIMING = 'registry')", if (setequal(unique(xB[treat == 1L, cohort]), c(2020, 2022))) "PASS" else "FAIL", paste(sort(unique(xB[treat == 1L, cohort])), collapse = ", "))
TREATMENT_TIMING <- "fund"; xF <- load_panel_R("NDVI", model_design(verbose = FALSE))
nd <- xF[treat == 1L & post == 1L & is.finite(dose) & dose > 0, uniqueN(site_id)]
add("B", "dose from the fund file (80 % names), attached when the model runs", if (nd == length(sitesB)) "PASS" else "FAIL", sprintf("%d of %d sub-watersheds carry a dose", nd, length(sitesB)))
add("B", "fund timing: each sub-watershed's first treated season from the workbook = its cohort here (releases from July of its year)",
    if (setequal(unique(xF[treat == 1L, cohort]), c(2020, 2022))) "PASS" else "FAIL", paste(sort(unique(xF[treat == 1L, cohort])), collapse = ", "))
run_models("B", list(M08 = "instrument"))
}

# ---------------------------------------------------------------- E (v20.57): every design option at the model stage, on one panel built once
if (RUN("E")) {
make_E <- function() {
  root <- file.path(TMP, "E_options"); unlink(root, recursive = TRUE); dir.create(root, recursive = TRUE); set.seed(57)
  mk <- function(s, n, rings = 0:5) { h <- POLY[POLY$SWSiD_All == s, ]; p <- do.call(rbind, lapply(rings, function(r) st_sf(buff_km = r, geometry = st_sample(h[h$buff_km == r, ], n))))
    ll <- st_coordinates(st_transform(p, 4326)); data.table(buff_km = p$buff_km, latitude = ll[, 2], longitude = ll[, 1], a = rnorm(nrow(p), 0, 0.03)) }
  A <- mk(1L, 30); Bf <- mk(2L, 6, 0L); S <- mk(4L, 1, 0:2)                       # Artal; 6 points of Beguru's CORE in Artal's files; a stray file (Chittharagi)
  dir.create(file.path(root, "REWARD_Artal_Exports_final")); dir.create(file.path(root, "REWARD_Chittaragi_Exports_final"))
  for (y in 2016:2025) for (se in c("yearly", "Kharif", "Rabi", "Zaid")) {
    sc <- c(yearly = 0L, Kharif = 1L, Rabi = 2L, Zaid = 3L)[[se]]
    fx <- function(P) { eff <- ifelse(P$buff_km == 0 & ((sc == 2L & y >= 2024) | (sc != 2L & y >= 2025)), 0.05, 0)
      data.table(latitude = P$latitude, longitude = P$longitude, buff_km = P$buff_km, SubwshedID = "U1",
                 NDVI = 0.3 + P$a + 0.006 * (y - 2016) + c(0, 0.06, 0.01, -0.05)[sc + 1L] + eff + rnorm(nrow(P), 0, 0.008),
                 Rain = if (sc == 0L) NA_real_ else 600 + rnorm(nrow(P), 0, 30), Tmax = if (sc == 0L) NA_real_ else 33 + rnorm(nrow(P), 0, .3),
                 Tmean = if (sc == 0L) NA_real_ else 26 + rnorm(nrow(P), 0, .3), Tmin = if (sc == 0L) NA_real_ else 19 + rnorm(nrow(P), 0, .3), LandUse = 1,
                 GapFilled = as.integer(y == 2025 & sc == 1L & runif(nrow(P)) < 0.2)) }
    fwrite(rbind(fx(A), fx(Bf)), file.path(root, "REWARD_Artal_Exports_final", sprintf("CSV_Artal_%d_%s_tile0.csv", y, se)))
    fwrite(fx(S), file.path(root, "REWARD_Chittaragi_Exports_final", sprintf("CSV_Chittaragi_%d_%s_tile0.csv", y, se)))
  }
  fund <- data.table(SWS = "Artal", Date = seq(as.Date("2024-10-01"), as.Date("2026-07-01"), by = "month"))[, `:=`(Progress = 40 + 10 * (seq_len(.N) - 1), Target = 500, Area = 4632.33845007)]
  fp <- file.path(TMP, "E_fund.xlsx"); openxlsx::write.xlsx(fund, fp)
  list(root = normalizePath(root, winslash = "/"), sites_csv = normalizePath(file.path(R_HOME_DIR, "data", "sites", "sites.csv"), winslash = "/"), fund = normalizePath(fp, winslash = "/"))
}
E <- make_E(); use_scenario(E, E$fund)
tE <- tryCatch(run_prep(), error = function(e) e)
add("E", "preparation (fragments coded per export file, nothing of the design baked in)", if (inherits(tE, "error")) "FAIL" else "PASS",
    if (inherits(tE, "error")) conditionMessage(tE) else sprintf("%s rows; fragment codes %s", format(nrow(tE), big.mark = ","), paste(names(table(tE$fragment)), table(tE$fragment), sep = ":", collapse = " ")))
if (!inherits(tE, "error")) {
  md5_0 <- tools::md5sum(panel_file())
  vars <- list(base = list(), frag_keep = list(FRAGMENT_RULE = "keep"), registry = list(TREATMENT_TIMING = "registry"), fixed_2023 = list(TREATMENT_TIMING = "fixed", TREATMENT_YEAR = 2023),
               share = list(FUND_START_RULE = "share"), rings_1_3 = list(CONTROL_RINGS = 1:3), pre4_post2 = list(PRE_YEARS = 4, POST_YEARS = 2),
               pre_cal = list(TREATMENT_TIMING = "fixed", TREATMENT_YEAR = 2022, PRE_YEARS = 2018, POST_YEARS = 2024),                    # v20.59: calendar years
               pre_at_start = list(TREATMENT_TIMING = "fixed", TREATMENT_YEAR = 2022, PRE_YEARS = 2022),                                 # v20.59: no pre year -> said, every year before
               screen_keep = list(OUTCOME_SCREEN = "keep"),                                                                              # v20.59: the screen's cells kept
               design_panel = list(DESIGN_SOURCE = "panel", TREATMENT_TIMING = "fixed", TREATMENT_YEAR = 2023),                           # v20.59: the panel's post (2022) wins over 2023
               rabi = list(SEASONS = "Rabi"), manual = list(DESIGN_MODE = "manual"), transition = list(EXCLUDE_TRANSITION_YEAR = TRUE),
               gapfilled_kept = list(EXCLUDE_GAPFILLED = FALSE), dose_amount = list(DOSE_VARIABLE = "dose_amount_sws"))
  od <- file.path(TMP, "E_out"); design_variant_samples(vars, od)
  rd <- function(v) { f <- file.path(od, paste0(v, ".csv")); if (file.exists(f)) fread(f) else NULL }
  chkE <- function(v, what, ok, detail = "") add("E", sprintf("%-14s %s", v, what), if (isTRUE(ok)) "PASS" else "FAIL", detail)
  b <- rd("base")
  chkE("base", "only the major sub-watershed (Artal) -- Beguru's core fragment and the stray file dropped", !is.null(b) && identical(sort(unique(b$site_id)), 1L), paste(sort(unique(b$site_id)), collapse = ","))
  chkE("base", "fund timing: Rabi rows from 2024, every other series from 2025 (back-cast start 2024-07)", !is.null(b) && all(b[treat == 1L & Season == 2L, cohort] == 2024) && all(b[treat == 1L & Season != 2L, cohort] == 2025))
  chkE("base", "dose: Rabi 2024 = 30 / 4632.3 per ha (released by Sep 2024 on the back-cast line); 0 on the rings",
       !is.null(b) && isTRUE(all.equal(unique(b[treat == 1L & Year == 2024 & Season == 2L, dose]), 30 / 4632.33845007)) && all(b[treat == 0L, dose] == 0))
  k <- rd("frag_keep"); chkE("frag_keep", "fragments kept with FRAGMENT_RULE = 'keep'", !is.null(k) && all(c(1L, 2L, 4L) %in% unique(k$site_id)), paste(sort(unique(k$site_id)), collapse = ","))
  r <- rd("registry"); chkE("registry", "registry timing: cohort 2022 (sites.csv)", !is.null(r) && all(r[treat == 1L, cohort] == 2022))
  f3 <- rd("fixed_2023"); chkE("fixed_2023", "fixed timing: cohort = TREATMENT_YEAR 2023", !is.null(f3) && all(f3[treat == 1L, cohort] == 2023))
  sh <- rd("share"); chkE("share", "share rule: 10 % of the target reached Nov 2024 -> first treated Zaid 2025 (every series 2025)", !is.null(sh) && all(sh[treat == 1L, cohort] == 2025))
  r13 <- rd("rings_1_3"); chkE("rings_1_3", "CONTROL_RINGS <- 1:3 used although DESIGN_MODE = 'recommended'", !is.null(r13) && setequal(unique(r13[buff_km > 0, buff_km]), 1:3), paste(sort(unique(r13$buff_km)), collapse = ","))
  p4 <- rd("pre4_post2"); chkE("pre4_post2", "PRE_YEARS 4 / POST_YEARS 2 from the first treated year (2024): 2020-2025", !is.null(p4) && min(p4$Year) == 2020 && max(p4$Year) == 2025, paste(range(p4$Year), collapse = "-"))
  pc <- rd("pre_cal"); chkE("pre_cal", "PRE_YEARS 2018 / POST_YEARS 2024 as CALENDAR years (v20.59): 2018-2024", !is.null(pc) && min(pc$Year) == 2018 && max(pc$Year) == 2024, if (is.null(pc)) "no sample" else paste(range(pc$Year), collapse = "-"))
  ps <- rd("pre_at_start"); chkE("pre_at_start", "PRE_YEARS 2022 = the start (v20.58: 'USED: from 0'): said, every year before the start used", !is.null(ps) && min(ps$Year) == 2016 && any(ps$post == 0L) && any(ps$post == 1L), if (is.null(ps)) "no sample" else paste(range(ps$Year), collapse = "-"))
  sk <- rd("screen_keep"); skj <- tryCatch(fromJSON(file.path(od, "screen_keep.json")), error = function(e) NULL)
  chkE("screen_keep", "OUTCOME_SCREEN = 'keep': the same rows as base here (no fill year in E), the results folder tagged _screenKept", !is.null(sk) && nrow(sk) == nrow(b) && !is.null(skj$tag) && grepl("_screenKept", skj$tag, fixed = TRUE), if (is.null(skj$tag)) "no tag" else skj$tag)
  pp <- tryCatch(panel_read(c("Year", "post", "pre", "did", "treat", "control", "buff_km")), error = function(e) NULL)
  pnames <- tryCatch(panel_names(), error = function(e) character(0))
  chkE("panel", "the panel carries treat / control / pre / post / did (v20.59): post = the exports' Treat flag (the Year rule here: Year >= 2022), pre = 1 - post, did = treat x post; Treat itself used and NOT kept",
       !is.null(pp) && all(c("treat", "control", "pre", "post", "did") %in% names(pp)) && all(pp$post == as.integer(pp$Year >= 2022L)) && all(pp$pre == 1L - pp$post) && all(pp$did == pp$treat * pp$post) && all(pp$treat == as.integer(pp$buff_km == 0L)) && all(pp$control == as.integer(pp$buff_km %in% 1:5))
       && length(pnames) > 0 && !"Treat" %in% pnames,
       if (is.null(pp)) "panel not readable" else paste0(paste(intersect(c("treat", "control", "pre", "post", "did", "Treat"), pnames), collapse = ","), " (", length(pnames), " columns)"))
  dp <- rd("design_panel"); dpj <- tryCatch(fromJSON(file.path(od, "design_panel.json")), error = function(e) NULL)
  chkE("design_panel", "DESIGN_SOURCE = 'panel' under TREATMENT_YEAR 2023: post = the panel's post (Year >= 2022) on every row, cohort 2022, the results folder tagged _panelDesign",
       !is.null(dp) && all(dp$post == as.integer(dp$Year >= 2022L)) && all(dp[treat == 1L, cohort] == 2022) && !is.null(dpj$tag) && grepl("_panelDesign", dpj$tag, fixed = TRUE),
       if (is.null(dpj$tag)) "no tag" else dpj$tag)
  pcx <- tryCatch(fread(file.path(OUTPUT_DIR, "panel_pixel_consistency_R.csv")), error = function(e) NULL)
  chkE("panel", "R_P00 confirmed the pixel consistency (v20.59): panel_pixel_consistency_R.csv written with 0 offenders (one sub-watershed and one ring per pixel, once per year-season)",
       !is.null(pcx) && nrow(pcx) == 0, if (is.null(pcx)) "file missing" else sprintf("%d offenders", nrow(pcx)))
  chkE("panel", "R_P00 wrote panel_design_check_R.csv and panel_variation_by_block.csv (v20.59)", file.exists(file.path(OUTPUT_DIR, "panel_design_check_R.csv")) && file.exists(file.path(OUTPUT_DIR, "panel_variation_by_block.csv")))
  # v20.59 -- YOUR RULE confirmed on the input files: input_design_audit_R.csv (Treat 1 = post / 0 = pre, buff_km 0 = treatment / 1-5 = control), PERIOD_RULE recorded
  ia <- tryCatch(fread(file.path(OUTPUT_DIR, "input_design_audit_R.csv")), error = function(e) NULL)
  bsr <- tryCatch(fread(file.path(OUTPUT_DIR, "panel_build_settings_R.csv")), error = function(e) NULL)
  chkE("panel", "R_P00 confirmed every input file (input_design_audit_R.csv): Treat 1 / 0 on every row (these test exports carry no Treat column: the Year rule, said), buff_km 0 / 1-5 on every row, PERIOD_RULE 'treat' recorded in panel_build_settings_R.csv",
       !is.null(ia) && nrow(ia) > 0 && all(ia$treat_post_rows + ia$treat_pre_rows + ia$treat_unusable_rows == ia$rows) && all(ia$treat_unusable_rows == 0L) && all(ia$buff_outside_0to5_rows == 0L) && sum(ia$treat_post_rows) > 0 && sum(ia$treat_pre_rows) > 0
       && sum(ia$buff0_treatment_rows) > 0 && sum(ia$buff1to5_control_rows) > 0 && all(ia$period_rule == "treat") && identical(period_rule_R(), "treat")
       && !is.null(bsr) && identical(bsr[setting == "period_rule", value], "treat") && identical(bsr[setting == "period_rows_dropped", value], "0"),
       if (is.null(ia)) "audit not readable" else sprintf("%d files, post %d, pre %d, buff0 %d, buff1-5 %d", nrow(ia), sum(ia$treat_post_rows), sum(ia$treat_pre_rows), sum(ia$buff0_treatment_rows), sum(ia$buff1to5_control_rows)))
  # the rule on a small frame: "year" = the Year rule, "both" drops the disagreeing row (the exports' flag 0 in 2022 against the rule 1)
  dq <- data.table(buff_km = c(0L, 0L, 3L, 3L, 7L), Year = c(2021L, 2022L, 2021L, 2022L, 2022L), Season = 0L, Treat = c(0, 0, 0, 1, 1))
  q_treat <- panel_design_columns_R(copy(dq), say = FALSE)
  PERIOD_RULE <- "year"; q_year <- panel_design_columns_R(copy(dq), say = FALSE)
  PERIOD_RULE <- "both"; q_both <- panel_design_columns_R(copy(dq), say = FALSE); ab <- input_audit_R(copy(dq), "q.csv")
  PERIOD_RULE <- "treat"
  # v20.59: the overlay options at the panel level -- SITE_GEOMETRY_CHECK (trust the file's id) and BUFF_FROM_GEOMETRY (confirmed rows take the polygon ring too)
  pxq <- data.table(pixel_id = c("a", "b"), latitude = c(15.1, 15.2), longitude = c(76.1, 76.2), sws_export = c(7L, NA_integer_))
  SITE_GEOMETRY_CHECK <- FALSE; oq <- overlay_or_trust(copy(pxq)); SITE_GEOMETRY_CHECK <- TRUE
  BUFF_FROM_GEOMETRY <- TRUE; rq <- ring_from_polygon_codes(); BUFF_FROM_GEOMETRY <- FALSE
  PIXEL_ONE_SITE <- FALSE; rq0 <- ring_from_polygon_codes(); PIXEL_ONE_SITE <- TRUE          # v20.59: the v20.58 rule -- the corrected / assigned rows only
  chkE("panel", "SITE_GEOMETRY_CHECK <- FALSE trusts the file's id (site_check 4, no overlay); BUFF_FROM_GEOMETRY <- TRUE takes the polygon ring on confirmed rows too; PIXEL_ONE_SITE (the default) on every row, FALSE on the corrected / assigned rows only (v20.59)",
       identical(oq$site_check, c(4L, 4L)) && identical(oq$site_id, c(7L, 0L)) && identical(rq, c(0L, 1L, 2L)) && identical(ring_from_polygon_codes(), c(0L, 1L, 2L)) && identical(rq0, c(1L, 2L)),
       sprintf("checks %s | ids %s | codes %s | one-site off %s", paste(oq$site_check, collapse = ","), paste(oq$site_id, collapse = ","), paste(rq, collapse = ","), paste(rq0, collapse = ",")))
  chkE("panel", "N_THREADS counts every logical processor (all_logical_cores_R >= detectCores) (v20.59)", all_logical_cores_R() >= parallel::detectCores(), sprintf("%d vs %d", all_logical_cores_R(), parallel::detectCores()))
  chkE("panel", "PERIOD_RULE 'treat' | 'year' | 'both' on a small frame: the flag / the rule / the disagreeing row leaves (v20.59)",
       identical(q_treat$post, c(0L, 0L, 0L, 1L, 1L)) && identical(q_year$post, c(0L, 1L, 0L, 1L, 1L)) && nrow(q_both) == 4L && identical(q_both$post, c(0L, 0L, 1L, 1L))
       && identical(attr(q_both, "design_check")$rows_dropped, 1L) && ab$treat_vs_year_disagree_rows == 1L && ab$buff_outside_0to5_rows == 1L && ab$buff0_treatment_rows == 2L,
       sprintf("treat %s | year %s | both %s (%d rows)", paste(q_treat$post, collapse = ""), paste(q_year$post, collapse = ""), paste(q_both$post, collapse = ""), nrow(q_both)))
  ra <- rd("rabi"); chkE("rabi", "SEASONS = 'Rabi': Rabi rows only", !is.null(ra) && identical(sort(unique(ra$Season)), 2L))
  mn <- rd("manual"); chkE("manual", "DESIGN_MODE = 'manual': 'data' = rings 1-5, every year", !is.null(mn) && setequal(unique(mn[buff_km > 0, buff_km]), 1:5) && min(mn$Year) == 2016)
  tr <- rd("transition"); chkE("transition", "EXCLUDE_TRANSITION_YEAR: no first treated year of a treated series", !is.null(tr) && !any(tr[treat == 1L, Year == cohort]))
  gk <- rd("gapfilled_kept"); chkE("gapfilled_kept", "EXCLUDE_GAPFILLED = FALSE keeps the history-filled rows (more rows than base)", !is.null(gk) && nrow(gk) > nrow(b), sprintf("%d vs %d", nrow(gk), nrow(b)))
  da <- rd("dose_amount"); chkE("dose_amount", "DOSE_VARIABLE = 'dose_amount_sws': Kharif 2025 = 110 (released by May 2025)", !is.null(da) && isTRUE(all.equal(unique(da[treat == 1L & Year == 2025 & Season == 1L, dose]), 110)))
  chkE("all", "the panel file is unchanged by every option (md5)", identical(unname(tools::md5sum(panel_file())), unname(md5_0)))
  COVARIATES <- "all"; xA <- load_panel_R("NDVI", model_design(verbose = FALSE, force = TRUE))       # v20.57: "all" reached no model before
  chkE("covariates_all", "COVARIATES <- 'all' = the four weather covariates in every model (covs_in)", setequal(covs_in(xA), c("Rain", "Tmax", "Tmean", "Tmin")), paste(covs_in(xA), collapse = ","))
  pv <- attr(xA, "post_vs_panel")                                                       # v20.59: DESIGN vs PANEL -- the fund timing (Rabi 2024) against the exports' 2022 flag
  chkE("design_vs_panel", "DESIGN vs PANEL: the fund timing differs from the panel's post (the exports' 2022 flag) on some rows and says so", !is.null(pv) && pv[2] > 0 && pv[2] < pv[1], if (is.null(pv)) "no comparison" else paste(pv[2], "of", pv[1]))
  TREATMENT_TIMING <- "fixed"; xB2 <- load_panel_R("NDVI", model_design(verbose = FALSE, force = TRUE)); pv2 <- attr(xB2, "post_vs_panel"); TREATMENT_TIMING <- "fund"
  chkE("design_vs_panel", "DESIGN vs PANEL: fixed 2022 = the exports' flag on every row (0 differ)", !is.null(pv2) && pv2[2] == 0 && pv2[1] == nrow(xB2), if (is.null(pv2)) "no comparison" else paste(pv2[2], "of", pv2[1]))
  chkE("screen_evidence", "the outcome screen wrote its evidence (OUTCOME_SCREEN_NDVI.csv: rows, pixels, mean, SD, min, max per year-season)", file.exists(file.path(RESULTS_DIR, "OUTCOME_SCREEN_NDVI.csv")) && all(c("rows", "pixels", "sd_across_pixels", "min", "max", "why") %in% names(fread(file.path(RESULTS_DIR, "OUTCOME_SCREEN_NDVI.csv")))))
  COVARIATES <- c("Rain", "Tmax", "Tmean", "Tmin"); invisible(model_design(verbose = FALSE, force = TRUE))
}
}

# ---------------------------------------------------------------- F (v20.58): YOUR RULE -- no excluded row reaches any model (the POISON test)
if (RUN("F") || RUN("H")) {                                          # v20.58: the layout below is scenario H's too
# Your Koranahalli layout rebuilt: NAMED full exports and UNNAMED tiles repeating the same pixels (older files), pixels OUTSIDE every polygon in
# both, a piece of Kodihalli's CORE in the tiles, three ring-1 pixels the named files call "core" from 2023 (their ring flips), a 2025 grid
# shifted 3 m, LSWI = NDMI and WSSI = 1 - ESI, the four seasons, a fund workbook (Rabi 2024). Your settings: CONTROL_RINGS 1:3, PRE_YEARS 4,
# SEASONS "seasonal". The data are written twice with the same random numbers: CLEAN, and POISONED -- every row the design must leave out
# carries +5 on the outcomes and +100 mm / +5 degrees on the covariates, in every year, season and group. Every model runs on both: its
# estimate, SE and p must be IDENTICAL, and the effect models must find the truth (+0.05).
make_F <- function(root, poison, seed = 58L) {
  unlink(root, recursive = TRUE); dir.create(root, recursive = TRUE); set.seed(seed)
  P5 <- if (poison) 5 else 0
  zone <- st_union(POLY[POLY$SWSiD_All == 13L, ])
  mk <- function(s, n, rings = 0:5) { h <- POLY[POLY$SWSiD_All == s, ]; p <- do.call(rbind, lapply(rings, function(r) st_sf(buff_km = r, geometry = st_sample(h[h$buff_km == r, ], n))))
    ll <- st_coordinates(st_transform(p, 4326)); data.table(buff_km = p$buff_km, latitude = ll[, 2], longitude = ll[, 1], a = rnorm(nrow(p), 0, 0.03), kind = "own") }
  K <- mk(13L, 40)                                                         # Koranahalli: core + rings 1-5
  K[which(buff_km == 1L)[1:3], kind := "flip"]                            # three ring-1 pixels the named files call core from 2023
  K[which(buff_km == 0L)[1:2], kind := "shift"]                            # two core pixels on a grid shifted 3 m in 2025
  N <- mk(12L, 6, 0L)[, kind := "neighbour"]                               # Kodihalli's core in the (unnamed) tiles
  ring_out <- st_difference(st_buffer(zone, 1500), zone)                   # outside every polygon: 0-1.5 km beyond ring 5
  po <- st_coordinates(st_transform(st_sample(ring_out, 6), 4326))
  O <- data.table(buff_km = c(0L, 0L, 5L, 5L, 5L, 5L), latitude = po[, 2], longitude = po[, 1], a = rnorm(6, 0, 0.03), kind = "outside")
  yrs <- 2016:2025; sea <- c(yearly = 0L, Kharif = 1L, Rabi = 2L, Zaid = 3L)
  shock <- CJ(Year = yrs, Season = 0:3)[, s := rnorm(.N, 0, 0.01)]
  dir.create(file.path(root, "REWARD_Koranahalli_Exports_final")); dir.create(file.path(root, "tiles"))
  for (y in yrs) for (sn in names(sea)) {
    sc <- sea[[sn]]; sh <- shock[Year == y & Season == sc, s]
    val <- function(P, b, site) { eff <- ifelse(site == 13L & b == 0L & ((sc == 2L & y >= 2024) | (sc != 2L & y >= 2025)), 0.05, 0)
      0.35 + P$a + 0.005 * (y - 2016) + c(0, 0.06, 0.01, -0.05)[sc + 1L] + sh + eff + rnorm(nrow(P), 0, 0.008) }
    bk <- K$buff_km; bk[K$kind == "flip" & y >= 2023] <- 0L
    lat <- K$latitude + ifelse(K$kind == "shift" & y == 2025, 3 / 110574, 0)
    v <- val(K, bk, 13L)
    # v20.58 (second pass): CLOUD GAPS -- 3 % of the own pixels' rows have no value (every band), as your exports where a scene is missing, so the
    # panel is UNBALANCED as real data are, and a repeated tile's value could fill the gap of the named export's row (it did until v20.58: P00
    # filled the kept row's gaps from the dropped repeated rows -- now DEDUP_FILL_FROM_DUPLICATES = FALSE). The same draws in both runs.
    v <- ifelse(runif(nrow(K)) < 0.03, NA_real_, v)
    # v20.58 (hard check): EVERY row the design leaves out, in EVERY year, season and group -- rings 4-5 (CONTROL_RINGS 1:3) in all years, every
    # ring before the window (2020 = the Rabi 2024 start - PRE_YEARS 4), the annual composite of every ring (SEASONS "seasonal"), the flipping
    # pixels in ALL their rows (a pixel whose ring differs between exports leaves whole), Kodihalli always. The first v20.58 test poisoned only
    # post-period rings 4-5, the core's early years / composite and the flipped "core" rows; a leak elsewhere would have passed it
    excl <- (bk %in% 4:5) | (y < 2020) | (sc == 0L) | (K$kind == "flip")
    v <- v + P5 * excl
    ov <- val(O, O$buff_km, 0L) + P5
    named <- rbind(data.table(latitude = lat, longitude = K$longitude, buff_km = bk, v = v, x = as.integer(excl)),
                   data.table(latitude = O$latitude, longitude = O$longitude, buff_km = O$buff_km, v = ov, x = 1L))
    tiles <- rbind(data.table(latitude = K$latitude, longitude = K$longitude, buff_km = K$buff_km, v = val(K, K$buff_km, 13L) + P5, x = 1L),
                   data.table(latitude = N$latitude, longitude = N$longitude, buff_km = N$buff_km, v = val(N, N$buff_km, 12L) + P5, x = 1L),
                   data.table(latitude = O$latitude, longitude = O$longitude, buff_km = O$buff_km, v = val(O, O$buff_km, 0L) + P5, x = 1L))
    wr <- function(d, f) {                          # v20.58: the COVARIATES of an excluded row are poisoned too (Rain +100, temperatures +5)
      n <- nrow(d); esi <- 0.5 + 0.2 * (d$v - 0.35) + rnorm(n, 0, 0.002); x <- d$x * P5 / 5
      out <- data.table(latitude = d$latitude, longitude = d$longitude, buff_km = d$buff_km, SubwshedID = "U1",
                        NDVI = d$v, EVI = 0.8 * d$v + rnorm(n, 0, 0.003), NDMI = 0.6 * d$v - 0.1, ESI = esi,
                        Rain = if (sc == 0L) NA_real_ else 600 + rnorm(n, 0, 30) + 100 * x, Tmax = if (sc == 0L) NA_real_ else 33 + rnorm(n, 0, .3) + 5 * x,
                        Tmean = if (sc == 0L) NA_real_ else 26 + rnorm(n, 0, .3) + 5 * x, Tmin = if (sc == 0L) NA_real_ else 19 + rnorm(n, 0, .3) + 5 * x,
                        LandUse = 1 + (seq_len(n) %% 2))
      out[, LSWI := NDMI]; out[, WSSI := 1 - ESI]; fwrite(out, f)
    }
    wr(named, file.path(root, "REWARD_Koranahalli_Exports_final", sprintf("CSV_Koranahalli_%d_%s_tile0.csv", y, sn)))
    half <- seq_len(nrow(tiles)) %% 2L
    for (k in 0:1) { f <- file.path(root, "tiles", sprintf("CSV_%d_%s_tile%d.csv", y, sn, k + 1L)); wr(tiles[half == k], f)
                     Sys.setFileTime(f, as.POSIXct("2025-01-01 00:00:00", tz = "UTC")) }
  }
  fund <- data.table(SWS = "Koranahalli", Date = seq(as.Date("2024-10-01"), as.Date("2026-07-01"), by = "month"))[, `:=`(Progress = 40 + 10 * (seq_len(.N) - 1), Target = 500, Area = 6741)]
  fp <- file.path(dirname(root), paste0(basename(root), "_fund.xlsx")); openxlsx::write.xlsx(fund, fp)
  list(root = normalizePath(root, winslash = "/"), sites_csv = normalizePath(file.path(R_HOME_DIR, "data", "sites", "sites.csv"), winslash = "/"), fund = normalizePath(fp, winslash = "/"))
}
F_SETTINGS <- list(DESIGN_MODE = "recommended", TREATMENT_TIMING = "fund", CONTROL_RINGS = 1:3, PRE_YEARS = 4, POST_YEARS = NA, SEASONS = "seasonal",
                   OVERLAP_ROWS = "drop", FRAGMENT_RULE = "drop", POOLED_FE = "site_period", SUB_WATERSHEDS = "data")
run_F <- function(key, poison, models = names(MODEL_FUN)) {
  Fx <- make_F(file.path(TMP, key), poison); use_scenario(Fx, Fx$fund)
  run_prep(); invisible(prepare_design())
  for (k in names(F_SETTINGS)) assign(k, F_SETTINGS[[k]], envir = globalenv())
  d <- model_design(verbose = TRUE, force = TRUE)
  for (m in models) try(run_model_R(m, "NDVI", d))
  fs <- list.files(RESULTS_DIR, pattern = "^M[0-9]{2}_NDVI(_DATA_GAP)?\\.csv$", recursive = TRUE, full.names = TRUE)
  list(res = rbindlist(lapply(fs, function(f) { x <- fread(f); x[, file := basename(f)] }), fill = TRUE), d = d, dir = RESULTS_DIR)
}
# v20.58 (hard check, as Python's validate_location_poison.py): EVERY number of EVERY file a model wrote -- not only the headline estimate,
# SE and p -- must be the same with the excluded rows poisoned (tables, event-time rows, pixel counts, placebo years, ...)
all_numbers <- function(root) {
  fs <- list.files(root, pattern = "\\.csv$", recursive = TRUE, full.names = TRUE)
  out <- lapply(fs, function(f) {
    x <- tryCatch(fread(f), error = function(e) NULL); if (is.null(x) || !nrow(x)) return(NULL)
    rel <- substring(normalizePath(f, winslash = "/"), nchar(normalizePath(root, winslash = "/")) + 2L)
    rbindlist(lapply(names(x), function(c) { v <- suppressWarnings(as.numeric(x[[c]]))
      if (!any(is.finite(v)) || grepl("^(secs|seconds|elapsed|elapsed_s|n_jobs_used|cores)$", c)) return(NULL)
      data.table(file = rel, col = c, row = seq_along(v), v = v) }))
  })
  rbindlist(out)
}
F_GAPS <- c(M07 = "BM means (ground data of >= 6 sub-watershed x seasons)", M08 = "instrument", M20 = ">= 2 sub-watersheds")
if (RUN("F")) tryCatch({
  Fc <- run_F("F_clean", FALSE); Fp <- run_F("F_poison", TRUE)
  cmp <- merge(Fc$res[, .(model, file, kind, est_c = estimate, se_c = se, p_c = p_value)], Fp$res[, .(model, file, est_p = estimate, se_p = se, p_p = p_value)], by = c("model", "file"), all = TRUE)
  same <- function(a, b) (is.na(a) & is.na(b)) | (is.finite(a) & is.finite(b) & abs(a - b) <= 1e-9 * pmax(1, abs(a)))
  cmp[, identical := same(est_c, est_p) & same(se_c, se_p) & same(p_c, p_p)]
  bad <- cmp[identical == FALSE, model]
  add("F", "POISON: every model's estimate, SE and p identical with the excluded rows at +5 (no other location, overlap, repeat, ring, year or season leaks)",
      if (!length(bad)) "PASS" else "FAIL", if (!length(bad)) sprintf("%d model results identical", nrow(cmp)) else paste("differ:", paste(bad, collapse = ", ")))
  na_ <- all_numbers(Fc$dir); nb_ <- all_numbers(Fp$dir)
  an <- merge(na_, nb_, by = c("file", "col", "row"), all = TRUE, suffixes = c("_c", "_p"))
  an[, same := same(v_c, v_p)]; badf <- unique(an[same == FALSE | is.na(same), file])
  add("F", "POISON (every number): every cell of every file written identical in the clean and the poisoned run",
      if (!length(badf)) "PASS" else "FAIL", if (!length(badf)) sprintf("%d numbers in %d files identical", nrow(an), uniqueN(an$file))
      else paste0(length(badf), " file(s) differ: ", paste(head(badf, 8), collapse = ", "),
                  " | e.g. ", paste(head(an[same == FALSE | is.na(same), sprintf("%s %s[%d] %s vs %s", basename(file), col, row, format(v_c), format(v_p))], 4), collapse = "; ")))
  for (m in sort(unique(cmp$model))) {
    r <- cmp[model == m][1]; gapf <- grepl("DATA_GAP", r$file)
    if (gapf) { add("F", m, if (m %in% names(F_GAPS)) "DATA GAP" else "FAIL", if (m %in% names(F_GAPS)) paste("expected on one sub-watershed:", F_GAPS[[m]]) else "unexpected data gap"); next }
    kind <- r$kind; e <- r$est_c
    okse <- kind != "effect" || (is.finite(r$se_c) && is.finite(r$p_c))
    tol <- if (m %in% ATT_ML) 0.02 else 0.01
    truth_ok <- if (m %in% c("M10", "M15", "M24")) abs(e) <= 0.01 else if (m %in% c("M06", "M16", "M17", "M18", "M19", "M20")) TRUE else abs(e - 0.05) <= tol
    add("F", m, if (isTRUE(r$identical) && okse && isTRUE(truth_ok)) "PASS" else "FAIL",
        sprintf("%s %.4f | SE %s | p %s | clean == poison: %s", kind, e, format(signif(r$se_c, 3)), format(signif(r$p_c, 3)), r$identical))
  }
  # the location rule in numbers: what left the sample, per group (treated / control, pre / post)
  lr <- list.files(file.path(dirname(RESULTS_DIR)), pattern = "^LOCATION_RULE_NDVI\\.csv$", recursive = TRUE, full.names = TRUE)
  add("F", "the location rule reported (LOCATION_RULE_<outcome>.csv beside every result)", if (length(lr)) "PASS" else "FAIL", sprintf("%d file(s)", length(lr)))
  # ---------------------------------------------------------------- G (v20.58): batches instead of samples, exact spatial statistics, cluster-robust quantiles
  gm_ <- intersect(c("M04", "M17", "M18", "M19", "M35", "M40", "M42", "M43", "M44"), names(MODEL_FUN))   # v20.58: the project's models with a batch fall-back
  if (length(gm_)) {
  FORCE_BATCH_UNITS <<- 60; Fb <- tryCatch(run_F("F_batch", TRUE, gm_), finally = FORCE_BATCH_UNITS <<- NULL)   # v20.58: reset after (it stayed 60)
  cb <- merge(Fp$res[, .(model, file, est_p = estimate)], Fb$res[, .(model, file, est_b = estimate, eng = engine)], by = c("model", "file"))
  for (m in cb$model) { r <- cb[model == m]; exact <- m %in% c("M17", "M18")
    ok <- if (exact) abs(r$est_b - r$est_p) <= 1e-12 else abs(r$est_b - 0.05) <= 0.02 || (m == "M19" && abs(r$est_b - r$est_p) < 0.02)
    add("G", sprintf("%s in BATCHES (beyond 98 %% of the RAM; forced here): every unit used, %s", m, if (exact) "the same answer to 1e-12" else "the answer within tolerance"),
        if (isTRUE(ok)) "PASS" else "FAIL", sprintf("batches %.5f vs all at once %.5f", r$est_b, r$est_p)) }   # v20.59: a model without its package (NA) fails its own row, not the scenario
  } else info("G: none of this project's models has a batch fall-back -- M01, M02, M16 and M34 go OUT OF CORE beyond 98 % (scenario H)")
  if (all(c("M17", "M18") %in% names(MODEL_FUN))) {                                  # v20.58: the spatial models' checks (spdep) where they are part of the project
  set.seed(7); n <- 1600; g <- CJ(i = 1:40, j = 1:40)[, `:=`(lat = 15 + i * 9e-5 + rnorm(.N, 0, 1e-6), lon = 76 + j * 9e-5 + rnorm(.N, 0, 1e-6))]
  v <- sin(g$i / 7) + cos(g$j / 9) + rnorm(n, 0, 0.3); xy <- knn_xy(g$lat, g$lon); nn <- knn_index(xy, 8L)
  lw <- spdep::nb2listw(spdep::knn2nb(structure(list(nn = nn, np = n, k = 8L, dimension = 2L, x = xy), class = "knn")), style = "W")
  mt <- spdep::moran.test(v, lw, alternative = "two.sided"); lm_ <- unclass(spdep::localmoran(v, lw)); mo <- moran_knn(v, nn, 8L)
  dmax <- max(abs(mt$estimate[1] - mo$I), abs(mt$estimate[3] - mo$VI) / mt$estimate[3], max(abs(lm_[, 1:5] - mo$local)))
  add("G", "Moran's I / LISA formulas on the k-NN index == spdep (the path used beyond 98 % of the RAM)", if (dmax < 1e-10) "PASS" else "FAIL", sprintf("largest difference %.1e", dmax))
  kd <- all(vapply(seq_len(n), function(i) setequal(nn[i, ], spdep::knearneigh(xy, k = 8L, use_kd_tree = FALSE)$nn[i, ]), logical(1))[1:200])
  add("G", "k-NN from the kd-tree == spdep's exhaustive search", if (kd) "PASS" else "FAIL")
  }
  if ("M35" %in% names(MODEL_FUN)) {                                                 # v20.58: the quantile DiD's check (quantreg) where M35 is part of the project
  dq <- data.table(unit = rep(1:300, each = 10), period = factor(rep(1:10, 300)), cl = seq_len(3000)); dq[, did := as.integer(unit <= 100 & as.integer(period) > 6)]
  dq[, y_w := 0.05 * did + rnorm(3000, 0, 0.01)]; fq <- quantreg::rq(y_w ~ did + period, data = dq, tau = 0.5, method = "fn")
  a1 <- rq_cluster_se(fq, dq$cl)[["did"]]; a2 <- summary(fq, se = "ker")$coefficients["did", 2] * sqrt(3000 / 2999)
  add("G", "M35 cluster-robust quantile SE: one row per cluster == quantreg's own kernel SE", if (abs(a1 / a2 - 1) < 1e-8) "PASS" else "FAIL", sprintf("%.10f vs %.10f", a1, a2))
  }
}, error = function(e) add("F", "scenario F", "FAIL", conditionMessage(e)))
}

# ---------------------------------------------------------------- H (v20.58): beyond 98 % of the RAM -- out of core, exact, on every engine
if (RUN("H")) {
tryCatch({
  Hx <- make_F(file.path(TMP, "H"), FALSE); use_scenario(Hx, Hx$fund)
  h_cells <- function(root) {                                        # every number of every result file (M* folders)
    fs <- list.files(root, pattern = "\\.csv$", recursive = TRUE); fs <- fs[grepl("^M[0-9]{2}/", fs)]
    rbindlist(lapply(fs, function(f) { x <- fread(file.path(root, f)); if (!nrow(x)) return(NULL)
      if (grepl("LOCATION_RULE_", f)) setorderv(x, intersect(c("code", "treated", "post"), names(x)))
      rbindlist(lapply(names(x), function(c_) { v <- x[[c_]]; if (!is.numeric(v) && !is.logical(v)) return(NULL); data.table(file = f, col = c_, row = seq_along(v), v = as.numeric(v)) })) }))
  }
  h_cmp <- function(a, b, tol) {                                    # tol NA: identical; else |a - b| <= tol * max(1, |a|)
    m <- merge(a, b, by = c("file", "col", "row"), all = TRUE, suffixes = c("_a", "_b"))
    same <- (is.na(m$v_a) & is.na(m$v_b)) | (!is.na(m$v_a) & !is.na(m$v_b) & (m$v_a == m$v_b | (!is.na(tol) & is.finite(m$v_a) & is.finite(m$v_b) & abs(m$v_a - m$v_b) <= tol * pmax(1, abs(m$v_a)))))
    rel <- with(m[!is.na(v_a) & !is.na(v_b) & is.finite(v_a) & is.finite(v_b) & v_a != v_b], abs(v_a - v_b) / pmax(abs(v_a), abs(v_b)))
    list(ok = all(same), n = nrow(m), files = uniqueN(m$file), bad = m[!same], worst_abs = max(c(0, with(m[is.finite(v_a) & is.finite(v_b)], abs(v_a - v_b)))), worst_rel = max(c(0, rel)))
  }
  run_prep(); invisible(prepare_design())
  for (k in names(F_SETTINGS)) assign(k, F_SETTINGS[[k]], envir = globalenv())
  HM <- intersect(c("M01", "M02", "M16", "M34"), names(MODEL_FUN))
  run_H <- function(tag) { d <- model_design(verbose = FALSE, force = TRUE); unlink(RESULTS_DIR, recursive = TRUE); dir.create(RESULTS_DIR, recursive = TRUE)
    for (m in HM) run_model_R(m, "NDVI", d)
    dst <- file.path(TMP, "H_results", tag); unlink(dst, recursive = TRUE); dir.create(dst, recursive = TRUE)
    file.copy(list.files(RESULTS_DIR, full.names = TRUE), dst, recursive = TRUE); h_cells(dst) }
  Sys.unsetenv("REWARD_FORCE_OUT_OF_CORE"); Sys.unsetenv("REWARD_OOC_PARTITIONS"); Sys.unsetenv("REWARD_RAM_BUDGET_BYTES")
  mem <- run_H("memory"); st <- ooc_engine_status(refresh = TRUE); got <- list()
  for (e in OOC_ENGINES) {
    if (!isTRUE(st[[e]]$ok)) { add("H", sprintf("M01 M02 M16 M34 out of core on %s", OOC_LABEL[[e]]), "DATA GAP", paste("not available on this machine:", st[[e]]$detail)); next }
    Sys.setenv(REWARD_FORCE_OUT_OF_CORE = e, REWARD_OOC_PARTITIONS = "5"); got[[e]] <- run_H(e)
    r <- h_cmp(mem, got[[e]], 1e-8)
    add("H", sprintf("M01 M02 M16 M34 out of core on %s (5 pixel partitions) == in memory", OOC_LABEL[[e]]), if (r$ok && nrow(got[[e]]) == nrow(mem)) "PASS" else "FAIL",
        sprintf("%d numbers in %d files; largest difference %.1e (relative %.1e: fixest converges to 1e-8)%s", r$n, r$files, r$worst_abs, r$worst_rel,
                if (!r$ok) paste(" | e.g.", paste(head(r$bad[, sprintf("%s %s[%d] %s vs %s", basename(file), col, row, format(v_a), format(v_b))], 3), collapse = "; ")) else ""))
  }
  Sys.unsetenv("REWARD_OOC_PARTITIONS")
  if (length(got) >= 2) { e0 <- names(got)[1]; for (e in names(got)[-1]) { r <- h_cmp(got[[e0]], got[[e]], NA)
    add("H", sprintf("%s == %s: every number identical (the same R code on every engine)", OOC_LABEL[[e]], OOC_LABEL[[e0]]), if (r$ok) "PASS" else "FAIL", sprintf("%d numbers", r$n)) } }
  Sys.unsetenv("REWARD_FORCE_OUT_OF_CORE"); Sys.setenv(REWARD_RAM_BUDGET_BYTES = "3000000")
  rm_ <- run_mode_R("M01", "NDVI", model_design(verbose = FALSE, force = TRUE)); sw <- run_H("switch"); Sys.unsetenv("REWARD_RAM_BUDGET_BYTES")
  r <- h_cmp(mem, sw, 1e-8)
  add("H", "the switch at 98 %: a RAM budget below the need -> out of core BY ITSELF, the in-memory numbers", if (identical(rm_$mode, "out_of_core") && r$ok) "PASS" else "FAIL",
      sprintf("run_mode_R: %s (%s); %d numbers, largest difference %.1e", rm_$mode, sub(" -- out of core.*$", "", rm_$why), r$n, r$worst_abs))
  # the design from the data and the outcome identities, out of core == in memory
  d0 <- model_design(verbose = FALSE, force = TRUE); cols <- intersect(c("pixel_id", "Year", "Season", "buff_km", "NDVI", "site_id", "site_check"), panel_names())
  Sys.setenv(REWARD_FORCE_OUT_OF_CORE = "batches", REWARD_OOC_PARTITIONS = "4")
  sa <- recommend_summary_mem("NDVI", d0$treatment_year, "drop", 0.05, "drop", d0$processed, cols); sb <- recommend_summary_ooc("NDVI", d0$treatment_year, "drop", 0.05, "drop", d0$processed, cols)
  ra <- recommend_from_summary(sa, d0$treatment_year, FALSE); rb <- recommend_from_summary(sb, d0$treatment_year, FALSE)
  ga <- sa$g[order(Year, ring)]; gb <- sb$g[order(Year, ring)]
  okg <- nrow(ga) == nrow(gb) && identical(ga$n, gb$n) && isTRUE(all.equal(ga$mean, gb$mean, tolerance = 1e-12)) && isTRUE(all.equal(ga$sd, gb$sd, tolerance = 1e-10))
  add("H", "the design from the data out of core (pixel partitions) == in memory: the same cells and the same choice", if (okg && identical(ra, rb) && identical(sa$link, sb$link)) "PASS" else "FAIL",
      sprintf("pre %s, post %s, rings %s, seasons %s", paste(rb$pre_window, collapse = ","), paste(rb$post_window, collapse = ","), paste(rb$control_rings, collapse = ","), rb$seasons))
  oc <- intersect(OUTCOMES, panel_names()); x <- panel_read(oc)
  ia <- outcome_identities_stream_R(oc); Sys.unsetenv("REWARD_FORCE_OUT_OF_CORE"); Sys.unsetenv("REWARD_OOC_PARTITIONS")
  ib <- local({ out <- data.table(a = character(0), b = character(0), r = numeric(0), slope = numeric(0), intercept = numeric(0), n = numeric(0))
    for (i in seq_along(oc)) for (j in seq_along(oc)) if (i < j) { a <- x[[oc[i]]]; b <- x[[oc[j]]]; m <- is.finite(a) & is.finite(b); if (sum(m) < 3 || sd(a[m]) == 0 || sd(b[m]) == 0) next
      r_ <- cor(a[m], b[m]); if (is.finite(r_) && abs(r_) > 0.999999) { sl <- r_ * sd(b[m]) / sd(a[m]); out <- rbind(out, data.table(a = oc[i], b = oc[j], r = r_, slope = sl, intercept = mean(b[m]) - sl * mean(a[m]), n = sum(m))) } }
    out })
  add("H", "the outcome identities row group by row group == all rows at once", if (nrow(ia) == nrow(ib) && identical(ia$a, ib$a) && identical(ia$b, ib$b) && identical(ia$n, ib$n) &&
      isTRUE(all.equal(ia$slope, ib$slope, tolerance = 1e-12)) && isTRUE(all.equal(ia$intercept, ib$intercept, tolerance = 1e-10))) "PASS" else "FAIL",
      sprintf("%d identities: %s", nrow(ia), paste(sprintf("%s = %.3g %+.3g x %s", ia$b, ia$intercept, ia$slope, ia$a), collapse = "; ")))
  # R_P00 block by block (year x season) == in memory: the panel row for row, its schema, every report
  keep_f <- c(basename(PANEL_PATH), "site_tagging_by_sws.csv", "site_tagging_by_file.csv", "pixel_overlap_report.csv", "pixel_overlap_map.csv", "panel_build_settings_R.csv", "panel_balance_by_block.csv")
  snap <- function(tag) { dst <- file.path(TMP, "H_panel", tag); unlink(dst, recursive = TRUE); dir.create(dst, recursive = TRUE)
    for (f in keep_f) if (file.exists(file.path(OUTPUT_DIR, f))) file.copy(file.path(OUTPUT_DIR, f), file.path(dst, f)); dst }
  pa <- snap("memory"); pa_t <- arrow::read_parquet(file.path(pa, basename(PANEL_PATH)), as_data_frame = FALSE); pa_d <- as.data.table(pa_t)
  for (e in c("batches", setdiff(names(got), "batches"))) {
    Sys.setenv(REWARD_FORCE_OUT_OF_CORE = e, REWARD_OOC_PARTITIONS = if (e == "batches") "3" else ""); run_prep(); pb <- snap(e)
    Sys.unsetenv("REWARD_FORCE_OUT_OF_CORE"); Sys.unsetenv("REWARD_OOC_PARTITIONS")
    pb_t <- arrow::read_parquet(file.path(pb, basename(PANEL_PATH)), as_data_frame = FALSE); pb_d <- as.data.table(pb_t)
    dif <- character(0)
    if (!identical(dim(pa_d), dim(pb_d)) || !identical(names(pa_d), names(pb_d))) dif <- "shape / names" else for (c_ in names(pa_d)) {
      u <- pa_d[[c_]]; v <- pb_d[[c_]]
      if (c_ %in% c("latitude", "longitude")) { if (any(is.na(u) != is.na(v)) || isTRUE(max(abs(u - v), na.rm = TRUE) > 1e-12)) dif <- c(dif, c_) } else if (!identical(u, v)) dif <- c(dif, c_) }
    rep_ok <- all(vapply(setdiff(keep_f, basename(PANEL_PATH)), function(f) { fa <- file.path(pa, f); fb <- file.path(pb, f); if (!file.exists(fa)) return(!file.exists(fb))
      x <- fread(fa); y <- fread(fb); if ("setting" %in% names(x)) { x <- x[setting != "written"]; y <- y[setting != "written"] }; isTRUE(all.equal(x, y, check.attributes = FALSE)) }, TRUE))
    add("H", sprintf("R_P00 block by block on %s%s == in memory: the panel row for row (schema too) and every report", OOC_LABEL[[e]], if (e == "batches") ", every block in 3 pixel groups" else ""),
        if (!length(dif) && rep_ok && pa_t$schema$Equals(pb_t$schema, check_metadata = TRUE)) "PASS" else "FAIL",
        sprintf("%s rows x %d columns%s", format(nrow(pb_d), big.mark = ","), ncol(pb_d), if (length(dif)) paste(" | differ:", paste(dif, collapse = ", ")) else ""))
  }
  run_prep()                                                          # the panel of the other scenarios: built in memory again
}, error = function(e) add("H", "scenario H", "FAIL", conditionMessage(e)), finally = { for (k in c("REWARD_FORCE_OUT_OF_CORE", "REWARD_OOC_PARTITIONS", "REWARD_RAM_BUDGET_BYTES")) Sys.unsetenv(k)
                                                                           try(ooc_stop_all(), silent = TRUE) })
}

# ---------------------------------------------------------------- the notebooks on B: RStudio's Knit and Jupyter (IRkernel)
find_jupyter <- function() {
  j <- Sys.which("jupyter"); if (nzchar(j)) return(unname(j))
  ev <- Sys.getenv(c("USERPROFILE", "LOCALAPPDATA", "ProgramData", "HOME")); ev <- ev[nzchar(ev)]
  cand <- c(as.vector(outer(ev, c("anaconda3", "Anaconda3", "miniconda3", "Miniconda3", "miniforge3"), file.path)), file.path("C:", c("anaconda3", "ProgramData/anaconda3")))
  cand <- c(file.path(cand, "Scripts", "jupyter.exe"), file.path(cand, "bin", "jupyter")); cand <- cand[file.exists(cand)]; if (length(cand)) cand[1] else ""
}
if (!QUICK) {
  out <- file.path(TMP, "notebooks"); dir.create(out); rs <- file.path(R.home("bin"), "Rscript")
  rmds <- sort(list.files(file.path(R_HOME_DIR, "rstudio"), pattern = "\\.Rmd$", full.names = TRUE))
  rmds <- c(rmds[grepl("R_P00", rmds)], rmds[!grepl("R_P00|R_RUN_ALL|R_V01", rmds)], rmds[grepl("R_RUN_ALL", rmds)], rmds[grepl("R_V01", rmds)])
  for (f in rmds) {                              # RStudio's Knit: a fresh R session renders the notebook in its global env
    o <- suppressWarnings(system2(rs, c("-e", shQuote(sprintf("rmarkdown::render('%s', output_dir = '%s', quiet = TRUE, envir = globalenv())", f, out))), stdout = TRUE, stderr = TRUE))
    st <- attr(o, "status"); okk <- (is.null(st) || st == 0) && !any(grepl("^Error|^Quitting from", o))
    add("B", paste("RStudio Knit", basename(f)), if (okk) "PASS" else "FAIL", if (okk) "rendered" else paste(tail(o, 3), collapse = " | "))
  }
  jup <- find_jupyter()
  if (!nzchar(jup)) add("B", "Jupyter (IRkernel)", "DATA GAP", "jupyter not found (see 00_SETUP.R)")
  else for (f in sub("\\.Rmd$", ".ipynb", file.path(R_HOME_DIR, "jupyter", basename(rmds)))) {
    o <- suppressWarnings(system2(jup, c("nbconvert", "--to", "notebook", "--execute", "--ExecutePreprocessor.kernel_name=ir", "--ExecutePreprocessor.timeout=3600",
                                         "--output-dir", shQuote(out), shQuote(f)), stdout = TRUE, stderr = TRUE))
    st <- attr(o, "status"); okk <- is.null(st) || st == 0
    add("B", paste("Jupyter (IRkernel)", basename(f)), if (okk) "PASS" else "FAIL", if (okk) "executed" else paste(tail(o, 2), collapse = " | "))
  }
}

# ---------------------------------------------------------------- the verdict
tab <- rbindlist(RES); options(width = 220); print(tab, nrows = 400)
cat(sprintf("\n%d PASS | %d DATA GAP (the data lack what the model needs, or a package is missing) | %d FAIL\n", sum(tab$status == "PASS"), sum(tab$status == "DATA GAP"), sum(tab$status == "FAIL")))
cat(if (any(tab$status == "FAIL")) "RESULT: FAIL -- send this table\n" else "RESULT: PASS -- the R pipeline works on this machine\n")
fwrite(tab, file.path(R_HOME_DIR, "tests", "LAST_TEST_RESULTS.csv"))
}, finally = .restore_env())
