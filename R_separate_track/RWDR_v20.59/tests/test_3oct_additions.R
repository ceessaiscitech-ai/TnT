# test_3oct_additions.R -- the 3 Oct changes of the R track, checked on their own (sourced by run_all_tests.R as scenario I; also
#     Rscript tests/test_3oct_additions.R         from the RWDR folder).
# 1  THE HANG of your R_P00 run: panel_variation_R, resolve_duplicates and pixel_registry were rewritten -- each new function must give the
#    OLD function's numbers exactly (the old bodies are kept here, verbatim, as the reference).
# 2  The 1-2 Oct Python corrections ported: a p-value on every result row (ensure_p_value_R), HEADLINES_ALL_VARIABLES_R.csv (headlines_all_R),
#    the precision report (panel_precision_report_R) and the float32 guard (panel_is_valid_R, panel_precision_note_R), the pipeline's own
#    products never read as exports (is_pipeline_product_R, discover_exports), the Windows worker cap (pool_cap_R).
# 3  build_panel.R twice on a folder that holds an EARLIER run's output: the products are excluded, the second run keeps the valid panel.
suppressPackageStartupMessages(library(data.table))
if (!exists("R_HOME_DIR")) R_HOME_DIR <- normalizePath(if (file.exists("lib/reward_paths.R")) "." else "..", winslash = "/")
.T3 <- file.path(tempdir(), "reward_3oct"); unlink(.T3, recursive = TRUE); dir.create(.T3, recursive = TRUE)
.root3 <- file.path(.T3, "exports"); dir.create(.root3)
.env_old3 <- Sys.getenv(c("REWARD_R_ROOT", "REWARD_TEST_RUN"), unset = NA_character_)
Sys.setenv(REWARD_R_ROOT = .root3, REWARD_TEST_RUN = "1")
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
RES3 <- list(); add3 <- function(step, ok_, detail = "") { RES3[[length(RES3) + 1]] <<- data.table(scenario = "I", step = step, status = if (isTRUE(ok_)) "PASS" else "FAIL", detail = substr(as.character(detail), 1, 300)); cat(sprintf("[%s] %s%s\n", if (isTRUE(ok_)) "PASS" else "FAIL", step, if (nzchar(detail)) paste0(" -- ", detail) else "")) }
same <- function(a, b) isTRUE(all.equal(a, b, check.attributes = FALSE))

# ---------------------------------------------------------------- 1. the rewritten steps give the old numbers
set.seed(3)
n_px <- 4000; blocks <- CJ(Year = 2016:2020, Season = 0:2)
syn <- rbindlist(lapply(seq_len(nrow(blocks)), function(b) {
  k <- sample(n_px, round(n_px * 0.7)); d <- data.table(pixel_id = sprintf("p%05d", k), site_id = 11L, site_check = sample(c(0L, 0L, 0L, 3L), length(k), TRUE), buff_km = sample(0:5, length(k), TRUE),
    Year = blocks$Year[b], Season = blocks$Season[b], latitude = 16 + k / 1e5, longitude = 77 + k / 1e5, src_file = sprintf("f_%d_%d.csv", blocks$Year[b], blocks$Season[b]), file_mtime = 1e9 + b * 10, fragment = 0L,
    schema_vintage = "2015_2025", NObsV = sample(5:30, length(k), TRUE))
  for (v in OUTCOME_VARS) d[, (v) := round(runif(.N, -0.2, 0.9), 6)]; for (v in WEATHER_VARS) d[, (v) := round(runif(.N, 0, 900), 3)]
  for (v in OUTCOME_VARS_CORE) d[sample(.N, round(.N * 0.08)), (v) := NA_real_]
  dup <- d[sample(.N, round(.N * 0.36))]; dup[, `:=`(src_file = sub("^f_", "g_", src_file), file_mtime = file_mtime + 3600)]           # a second, newer file of the same keys
  for (v in OUTCOME_VARS_CORE) dup[sample(.N, round(.N * 0.15)), (v) := NA_real_]; dup[, NDVI := NDVI + 0.001]
  rbind(d, dup) }))
syn[sample(.N, 50), `:=`(latitude = latitude + 1e-6)]                                                                                # two coordinates for a few pixels (the consistency check)
# (a) panel_variation_R == the old body (verbatim)
panel_variation_old <- function(dt, vars = OUTCOME_VARS) {
  vs <- intersect(vars, names(dt)); if (!length(vs)) return(NULL)
  rbindlist(lapply(vs, function(v) {
    x <- dt[is.finite(get(v)), { z <- as.numeric(get(v)); mu <- mean(z); .(finite = .N, mean = mu, m2 = sum((z - mu)^2), min = min(z), max = max(z)) }, by = .(Year, Season)]
    x[, variable := rep(v, nrow(x))]; x }), use.names = TRUE, fill = TRUE)
}
vn <- panel_variation_R(copy(syn)); vo <- panel_variation_old(copy(syn))
add3("panel_variation_R (the hang): the rewritten step gives the old numbers (finite, mean, m2, min, max per outcome x year-season)", same(setorder(vn, variable, Year, Season), setorder(vo, variable, Year, Season)) && nrow(vn) == length(OUTCOME_VARS) * nrow(blocks), sprintf("%d cells", nrow(vn)))
# (b) resolve_duplicates == the old body (verbatim, v20.59 of 1 Oct), fill FALSE and TRUE
resolve_duplicates_old <- function(dt, keys = c("site_id", "pixel_id", "Year", "Season"), recency_margin_seconds = 1.0, say = FALSE) {
  keys <- intersect(keys, names(dt)); oc <- intersect(OUTCOME_VARS_CORE, names(dt))
  if ("site_id" %in% keys && "site_check" %in% names(dt)) {
    dt[, .site_key := fifelse(!is.na(site_check) & site_check == 3L, -1L, as.integer(site_id))]; keys[keys == "site_id"] <- ".site_key"
  }
  dup <- duplicated(dt, by = keys) | duplicated(dt, by = keys, fromLast = TRUE)
  if (!any(dup)) { if (".site_key" %in% names(dt)) dt[, .site_key := NULL]; attr(dt, "dedup") <- list(groups = 0L, removed = 0L, filled = 0L, not_used = 0L); return(dt) }
  g <- dt[dup]; r <- dt[!dup]
  g[, `:=`(.gmax = max(file_mtime)), by = keys]
  g[, .newest := as.integer(.gmax - file_mtime <= recency_margin_seconds)]
  g[, .nmiss := rowSums(!is.finite(as.matrix(.SD))), .SDcols = oc]
  g[, .nobs := if ("NObsV" %in% names(g)) fifelse(is.finite(suppressWarnings(as.numeric(NObsV))), suppressWarnings(as.numeric(NObsV)), -1) else -1]
  g[, .vr := if ("schema_vintage" %in% names(g)) fifelse(schema_vintage == "2026plus", 2L, fifelse(schema_vintage == "2015_2025", 1L, 0L)) else 0L]
  if (DEDUP_PRIORITY == "complete") setorderv(g, c(keys, ".nmiss", ".newest", ".nobs", ".vr", "src_file"), c(rep(1L, length(keys)), 1L, -1L, -1L, -1L, 1L))
  else setorderv(g, c(keys, ".newest", ".nmiss", ".nobs", ".vr", "src_file"), c(rep(1L, length(keys)), -1L, 1L, -1L, -1L, 1L))
  first <- g[, .SD[1L], by = keys]
  if ("fragment" %in% names(g)) first[g[, .(.fm = min(fragment)), by = keys], on = keys, fragment := i..fm]
  n_fill <- 0L; n_unused <- 0L; by_var <- integer(0); fill <- isTRUE(DEDUP_FILL_FROM_DUPLICATES)
  for (v in oc) {
    don <- g[is.finite(get(v)), .(.don = get(v)[1L]), by = keys]
    first[don, on = keys, .don := i..don]
    gap <- !is.finite(first[[v]]) & is.finite(first$.don)
    if (any(gap)) {
      if (fill) { set(first, which(gap), v, first$.don[gap]); n_fill <- n_fill + sum(gap) }
      else { n_unused <- n_unused + sum(gap); by_var[v] <- sum(gap) }
    }
    first[, .don := NULL]
  }
  first[, c(".gmax", ".newest", ".nmiss", ".nobs", ".vr") := NULL]
  out <- rbind(r, first, fill = TRUE); if (".site_key" %in% names(out)) out[, .site_key := NULL]
  attr(out, "dedup") <- list(groups = nrow(first), removed = nrow(g) - nrow(first), filled = n_fill, not_used = n_unused, not_used_by_variable = by_var)
  out
}
keyc <- c("site_id", "pixel_id", "Year", "Season", "src_file")
for (fill in c(FALSE, TRUE)) {
  DEDUP_FILL_FROM_DUPLICATES <- fill
  a <- resolve_duplicates(copy(syn), say = FALSE); b <- resolve_duplicates_old(copy(syn))
  setorderv(a, keyc); setorderv(b, keyc); setcolorder(a, names(b))
  add3(sprintf("resolve_duplicates (DEDUP_FILL_FROM_DUPLICATES = %s): the rewritten step keeps the same rows with the same values and the same counts", fill),
       same(a, b) && same(attr(a, "dedup")[c("groups", "removed", "filled", "not_used")], attr(b, "dedup")[c("groups", "removed", "filled", "not_used")]) && same(attr(a, "dedup")$not_used_by_variable, attr(b, "dedup")$not_used_by_variable),
       sprintf("%d rows kept, %d removed, %d filled, %d not used", nrow(a), attr(a, "dedup")$removed, attr(a, "dedup")$filled, attr(a, "dedup")$not_used))
}
DEDUP_FILL_FROM_DUPLICATES <- FALSE
# (c) pixel_registry == the old body (verbatim), and the block-by-block fall-back
pixel_registry_old <- function(dt) {
  oc <- intersect(OUTCOME_VARS_CORE, names(dt))
  d <- dt[, c("pixel_id", "latitude", "longitude", "file_mtime", "src_file", oc), with = FALSE]
  d[, n_ok := rowSums(is.finite(as.matrix(.SD))), .SDcols = oc]
  setorder(d, file_mtime)
  d[, .(lat = mean(latitude), lon = mean(longitude), mtime = max(file_mtime), n_rows = .N, n_ok = sum(n_ok), src = last(src_file)), by = pixel_id][, completeness := n_ok / pmax(n_rows, 1)][]
}
rn <- pixel_registry(copy(syn)); ro <- pixel_registry_old(copy(syn))
add3("pixel_registry: no frame copy and no N x K matrix -- the same registry (lat, lon, mtime, rows, usable cells, newest file, completeness)", same(rn, ro), sprintf("%d pixels", nrow(rn)))
.keep_pass <- .pixel_registry_pass; .pixel_registry_pass <- function(dt, oc) stop("cannot allocate vector of size 9.9 Gb")
rb <- suppressMessages(pixel_registry(copy(syn))); .pixel_registry_pass <- .keep_pass
cmp <- function(x) setorder(copy(x)[, .(pixel_id, lat = round(lat, 9), lon = round(lon, 9), mtime, n_rows, n_ok, completeness)], pixel_id)
add3("pixel_registry: the block-by-block fall-back (a memory error in the one pass) gives the same numbers", same(cmp(rb), cmp(ro)) && nrow(near_duplicate_pairs(rb)) == nrow(near_duplicate_pairs(ro)), sprintf("%d pixels, %d near-duplicate pairs", nrow(rb), nrow(near_duplicate_pairs(rb))))
add3("drop_rows_without_outcome: nothing to drop -> the same table (no copy), the count attribute 0", { x <- copy(syn); y <- drop_rows_without_outcome(x); identical(attr(y, "rows_dropped_no_outcome"), 0L) && nrow(y) == nrow(x) }, "")
add3("the design columns can be set on a table that went through the no-copy path (column slots kept)", { x <- drop_rows_without_outcome(resolve_duplicates(copy(syn), say = FALSE)); y <- panel_design_columns_R(x, say = FALSE); all(c("treat", "control", "pre", "post", "did") %in% names(y)) }, "")

# ---------------------------------------------------------------- 2. the ported 1-2 Oct corrections
# (a) a p on every row
tb <- data.table(event_time = -2:2, beta = c(0.01, 0.00, 0.03, 0.05, 0.08), se = c(0.02, 0.02, 0.02, 0.02, 0.02), p_value = c(NA, NA, 0.123, NA, NA))
e1 <- ensure_p_value_R(copy(tb), G = 10L)
add3("ensure_p_value_R: p = 2 pt(|beta / se|, G - 1) where none was there, the existing p untouched, p_how says the rule", same(e1$p_value[-3], 2 * pt(abs(tb$beta / tb$se), 9, lower.tail = FALSE)[-3]) && e1$p_value[3] == 0.123 && grepl("t with 9 df", e1$p_how[1]) && is.na(e1$p_how[3]), paste(signif(e1$p_value, 3), collapse = " "))
e2 <- ensure_p_value_R(copy(tb)[, p_value := NULL]); add3("ensure_p_value_R: without clusters the normal p", same(e2$p_value, 2 * pnorm(-abs(tb$beta / tb$se))) && all(grepl("^normal", e2$p_how)), "")
e3 <- ensure_p_value_R(data.table(term = "x", estimate = "0.12 (text)", beta = 0.12, se = 0.04), G = 5L); add3("ensure_p_value_R: a character 'estimate' column is skipped, the numeric beta is used (M21's table)", is.finite(e3$p_value) && grepl("beta / se", e3$p_how), "")
e4 <- ensure_p_value_R(data.table(a = 1:3)); add3("ensure_p_value_R: a table without an estimate or SE is returned as it is", identical(names(e4), "a"), "")
# (b) the cross-variable headline file
hp <- file.path(.T3, "HEADLINES_ALL_VARIABLES_R.csv"); unlink(hp)
rw <- data.table(model = "M01", outcome = "NDVI", kind = "effect", estimate = 0.05, se = 0.01, p_value = 1e-6, p_how = "t", se_how = "cluster", engine = "fixest", engine_version = "20.59", n_clusters = 8L, n_obs = 1000L)
headlines_all_R(rw, "_s1", hp); headlines_all_R(copy(rw)[, estimate := 0.06], "_s1", hp); headlines_all_R(copy(rw)[, outcome := "LAI"], "_s1", hp); headlines_all_R(rw, "_s2", hp)
h <- fread(hp); add3("headlines_all_R: one row per model x outcome x scenario, replaced at every run (3 rows: M01 NDVI _s1 = the latest estimate, M01 LAI _s1, M01 NDVI _s2)", nrow(h) == 3 && h[outcome == "NDVI" & scenario == "_s1", estimate] == 0.06 && all(c("model", "outcome", "scenario", "estimate", "se", "p_value", "p_how", "written") %in% names(h)), paste(names(h), collapse = ","))
# (c) the precision report and the float32 guard
if (HAS_ARROW) {
  vals <- rep(c(0.4123456789, 0.4123456790, 0.4123456791, 0.41, 0, NA), 4)
  p64 <- file.path(.T3, "p64.parquet"); p32 <- file.path(.T3, "p32.parquet")
  arrow::write_parquet(data.frame(pixel_id = seq_along(vals), NDVI = vals, Rain = vals * 1000), p64)
  arrow::write_parquet(arrow::arrow_table(pixel_id = seq_along(vals), NDVI = arrow::Array$create(vals, type = arrow::float32())), p32)
  r64 <- panel_precision_report_R(p64, .T3, verbose = FALSE); n64 <- r64[variable == "NDVI"]; r32 <- panel_precision_report_R(p32, .T3, verbose = FALSE); n32 <- r32[variable == "NDVI"]
  add3("panel_precision_report_R: a double column with values 1e-10 apart -> 10 decimals needed, 5 distinct values, float32 would merge them, full precision kept, not float32-representable",
       n64$decimals_needed == 10 && n64$distinct_values == 5 && abs(n64$smallest_difference - 1e-10) < 1e-13 && isTRUE(n64$float32_would_merge_values) && isTRUE(n64$full_precision_kept) && isFALSE(n64$all_values_float32_representable) && file.exists(file.path(.T3, "panel_precision_report_R.csv")), sprintf("smallest difference %.3g", n64$smallest_difference))
  add3("panel_precision_report_R: the same values stored as float32 -> the three values merged, full precision NOT kept, every value float32-representable", n32$distinct_values <= 3 && isFALSE(n32$full_precision_kept) && isTRUE(n32$all_values_float32_representable), sprintf("%d distinct, stored %s", n32$distinct_values, n32$stored_dtype))
  add3("panel_is_valid_R: FALSE on the float32 panel (said why)", isFALSE(suppressMessages(panel_is_valid_R(p32, required_cols = c("pixel_id", "NDVI")))), "")
  add3("panel_is_valid_R: FALSE on a panel without panel_build_settings_R.csv beside it; FALSE without the file", isFALSE(suppressMessages(panel_is_valid_R(p64, required_cols = c("pixel_id", "NDVI")))) && isFALSE(suppressMessages(panel_is_valid_R(file.path(.T3, "none.parquet")))), "")
  .PANEL_PRECISION_NOTED <- new.env(); msgs <- capture.output(f32 <- panel_precision_note_R(p32)); msgs <- c(msgs, capture.output(f32b <- panel_precision_note_R(p32)))
  add3("panel_precision_note_R: a float32 panel is said once per session and the columns are returned", identical(f32, "NDVI") && identical(f32b, "NDVI") && sum(grepl("float32", msgs)) == 1, "")
}
# (d) the pipeline's own products are not exports
ex <- file.path(.root3, "REWARD_Jantapur_Exports_final"); dir.create(ex, recursive = TRUE)
one <- data.table(latitude = 16.75 + (1:30) / 1e4, longitude = 77.2 + (1:30) / 1e4, buff_km = rep(0:5, 5), SubwshedID = "U1", SWSiD_All = 11L, Year = 2020L, Season = 0L, Treat = 0, NDVI = round(runif(30, 0.2, 0.6), 6), LAI = 1.1, Rain = 500, Tmax = 33, Tmean = 26, Tmin = 19, LandUse = 2, Coverage = 1)
fwrite(one, file.path(ex, "CSV_2020_Yearly_tile0.csv"))
old <- file.path(.root3, "output_of_an_earlier_run"); dir.create(file.path(old, "TEMP"), recursive = TRUE); dir.create(file.path(.root3, "_out_of_core_R"))
if (HAS_ARROW) {
  sigR <- data.frame(pixel_id = "a", did = 0L, site_check = 0L, NDVI = 0.1); sigPy <- data.frame(pixel_id = 1L, did_term = 0L, schema_vintage = "x", NDVI = 0.1)
  arrow::write_parquet(sigR, file.path(old, "did_panel_full.parquet")); arrow::write_parquet(sigPy, file.path(old, "TEMP", "shard_2016_Yearly.parquet"))
  arrow::write_parquet(sigPy, file.path(.root3, "a_copy_of_the_panel.parquet")); arrow::write_parquet(sigR, file.path(.root3, "_out_of_core_R", "part_3.parquet"))
  arrow::write_parquet(data.frame(latitude = 16.8, longitude = 77.2, NDVI = 0.3), file.path(.root3, "a_real_parquet_export.parquet"))
}
fx <- suppressMessages(discover_exports()); pr <- attr(fx, "products")
add3("discover_exports: an earlier run's output folder (did_panel_full.parquet + its shard), a stray panel copy and an out-of-core partition inside the exports folder are the pipeline's own products; the real exports are read",
     (if (HAS_ARROW) nrow(fx) == 2 && length(pr) == 4 else nrow(fx) == 1) && all(!grepl("did_panel_full|shard_|a_copy|part_", basename(fx$file))), sprintf("%d export(s), %d product(s)", nrow(fx), length(pr)))
add3("is_pipeline_product_R by name: did_panel_full.parquet, shard_2016_Yearly_part2.parquet, part_2021_Rabi.parquet, part_12.csv -> products; CSV_2021_Rabi_tile3.csv -> an export",
     all(vapply(c("did_panel_full.parquet", "shard_2016_Yearly_part2.parquet", "part_2021_Rabi.parquet", "part_12.csv"), is_pipeline_product_R, logical(1))) && !is_pipeline_product_R("CSV_2021_Rabi_tile3.csv"), "")
# (e) the Windows worker cap
add3("pool_cap_R: 60 worker processes at most on Windows, every core elsewhere", (if (.Platform$OS.type == "windows") pool_cap_R(128L) == 60L else pool_cap_R(128L) == 128L) && WINDOWS_POOL_LIMIT_R == 60L && grepl("min(as.integer(n), WINDOWS_POOL_LIMIT_R)", paste(deparse(pool_cap_R), collapse = ""), fixed = TRUE), "")
add3("FORCE_REBUILD exists and is FALSE by default", exists("FORCE_REBUILD") && isFALSE(FORCE_REBUILD), "")

# ---------------------------------------------------------------- 3. build_panel.R twice on that folder (an earlier run's output inside the exports)
rs <- file.path(R.home("bin"), "Rscript"); bp <- file.path(R_HOME_DIR, "build_panel.R"); out3 <- file.path(.T3, "panel_out")
Sys.setenv(REWARD_R_HOME = R_HOME_DIR)
l1 <- suppressWarnings(system2(rs, c(bp, paste0("input=", .root3), paste0("output=", out3), "threads=2", "screen=FALSE"), stdout = TRUE, stderr = TRUE))
l2 <- suppressWarnings(system2(rs, c(bp, paste0("input=", .root3), paste0("output=", out3), "threads=2", "screen=FALSE"), stdout = TRUE, stderr = TRUE))
add3("build_panel.R on a folder holding an earlier run's output: the discovery line counts the products, the panel is built and the precision report written",
     any(grepl("own products from an earlier run", l1)) && file.exists(file.path(out3, "did_panel_full.parquet")) && file.exists(file.path(out3, "panel_precision_report_R.csv")) && any(grepl("\\[OK\\] +panel:", l1)),
     paste(grep("own products|panel:", l1, value = TRUE)[1], collapse = " "))
add3("build_panel.R a second time: the valid panel is KEPT (no rebuild), the precision report printed again", any(grepl("a valid panel is already there", l2)) && !any(grepl("rows read from", l2)) && any(grepl("precision of the stored panel", l2)), "")
add3("the progress lines: every step of the build is said before it starts (...) and when it ends (N s)", sum(grepl(" \\.\\.\\.$", l1)) >= 12 && sum(grepl("\\([0-9]+ s; [0-9.]+ min since the start\\)", l1)) >= 12, sprintf("%d start lines, %d end lines", sum(grepl(" \\.\\.\\.$", l1)), sum(grepl("min since the start", l1))))

res3 <- rbindlist(RES3); print(res3[, .(step = substr(step, 1, 110), status)]); cat(sprintf("\n3 Oct additions: %d PASS, %d FAIL\n", sum(res3$status == "PASS"), sum(res3$status == "FAIL")))
for (k in names(.env_old3)) if (is.na(.env_old3[[k]])) Sys.unsetenv(k) else do.call(Sys.setenv, setNames(list(.env_old3[[k]]), k))
if (sys.nframe() == 0L && any(res3$status == "FAIL")) quit(status = 1)
