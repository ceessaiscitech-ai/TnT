# benchmark_prep_scale.R -- the SCALE BENCHMARK of the R preparation path (run_prep, lib/reward_prep.R: the in-memory path R_P00 and
# build_panel.R take) on SYNTHETIC exports written in the layout of the real Jantapur run (3 Oct 2026; task 1B).
#
#   Rscript tests/benchmark_prep_scale.R pixels=60000 [threads=4] [scratch=<folder>] [stage=all|generate|run] [old=FALSE] [tag=px60000]
#            [tiles=6] [dup_tiles=2] [dup_rows_share=0.357] [coverage=0.44] [second_id=0] [outside_share=0.001] [shift_share=0.002]
#            [years=2015-2025] [seasons=0,1,2,3] [seed=1] [keep_exports=TRUE]
#   Rscript tests/benchmark_prep_scale.R fit=<bench_steps_A.csv>,<bench_steps_B.csv>[,<C.csv>] [target_rows=86579265] [target_pixels=3287286]
#            [target_files=1253] [out=<csv>]
#
# WHAT IT DOES
#  1. generates exports under <scratch>/exports_<tag>/REWARD_Jantapur_Exports_final/CSV_<Year>_<Season>_tile<N>.csv: `pixels` 10 m grid
#     cells sampled INSIDE Jantapur's core (buff_km 0) and rings 1-5 of data/sites/SWSs20_KarnatakaAll5k.shp (SWSiD_All 11; the rings in
#     proportion to their area, as tests/run_all_tests.R make_scenario() samples points inside the polygons), a few pixels OUTSIDE every
#     polygon (0-1.5 km beyond ring 5, the file calls them ring 5), a small share on a grid SHIFTED 3 m from 2024 (near-duplicate pixels);
#     one block per year x season (2015-2025 x Yearly / Kharif / Rabi / Zaid = 44); every pixel is in a block with probability `coverage`
#     (the real run: 86.6 M rows / 3.29 M pixels = 26 rows per pixel over 44 blocks, an unbalanced panel); a block is split into `tiles`
#     spatial tiles; `dup_rows_share` of the rows (the real run: 30.9 M of 86.6 M = 35.7 %) belong to a pixel-year-season written AGAIN, with
#     re-drawn values and more gaps, in `dup_tiles` extra tiles of the block whose mtime is one hour NEWER (the newer file wins); blocks
#     alternate SWSiD_All 11 and `second_id` (0) so every pixel location is overlaid under TWO ids, as in the real run (6.57 M locations for
#     3.29 M pixels); Treat = the period flag (1 from 2023; TREATMENT_YEAR is 2022: the flag-vs-rule line); SubwshedID "U1"; the 21 outcome
#     and weather columns with 6-decimal values, ~1 % exact zeros (the exporter's no-data) and ~2 % empty cells, Rain -9999 / Tmin -10 fills;
#     LandUse, Coverage, SrcOpt, NObsV, NObsT, GapFilled, OptTier, UID.
#  2. sources the library exactly as build_panel.R does (REWARD_R_ROOT, REWARD_TEST_RUN, R_HOME_DIR; reward_paths.R, reward_design.R,
#     reward_prep.R, reward_models_core.R; OUTPUT_DIR under the scratch folder; N_THREADS = `threads`, applied to data.table and fixest).
#  3. re-assigns TIMING WRAPPERS in the global environment for the functions run_prep() looks up by name (read_export, overlay_sws and the sf
#     calls inside it, pixel_ids, merge_near_duplicate_pixels with pixel_registry / near_duplicate_pairs / canonical_pixel_map, resolve_duplicates,
#     drop_rows_without_outcome, panel_pixel_consistency_R (its arguments -- the unique() and uniqueN() of the inside rows -- timed apart),
#     panel_design_columns_R, panel_variation_R, panel_variation_report_R, bm_sws_means, panel_write, ...) and shadows for the data.table /
#     base generics run_prep calls inline (merge, unique, duplicated, rbindlist, setorder, setorderv; uniqueN and anyDuplicated only in the window
#     between the dedup step and the design columns, where run_prep calls them directly -- a global shadow switches GForce off elsewhere).
#     Each call records wall seconds, the RSS before and after and the process peak RSS (VmHWM of /proc/self/status, else ps) -- appended to
#     bench_calls_<tag>.csv AS IT HAPPENS (a killed run keeps what it measured).
#  4. runs run_prep() (the in-memory path forced: prep_mode_R is wrapped to say "memory" and to print what it would have decided), prints the
#     per-step table (inclusive and exclusive seconds, calls, peak RSS, share) and the total, writes bench_steps_<tag>.csv and appends one row
#     to bench_runs.csv (rows read, panel rows, pixels, files, total seconds, peak RSS).
#  old=TRUE re-assigns the 1 Oct-MORNING bodies (git 75fbb3f) of drop_rows_without_outcome, panel_pixel_consistency_R and pixel_registry --
#  the code the real run had when it went silent after the duplicate step (the three-fold inside subset of that version sits inside run_prep
#  itself and cannot be swapped in from outside).
#  fit=...: the scaling exponent per step from two runs (log(tB / tA) / log(rowsB / rowsA)), a linear fit with intercept when three runs are
#  given, and the extrapolation to the real run's rows / pixels / files -> bench_scaling.csv. The assumption is stated in the table.
# Nothing of the repository is modified; everything is written under <scratch>.
suppressPackageStartupMessages({ library(data.table) })
args <- commandArgs(trailingOnly = TRUE); kv <- strsplit(args[grepl("=", args, fixed = TRUE)], "=", fixed = TRUE)
opt <- setNames(lapply(kv, function(z) paste(z[-1], collapse = "=")), vapply(kv, `[`, "", 1))
`%or%` <- function(a, b) if (is.null(a) || !length(a) || (is.character(a) && length(a) == 1L && !nzchar(a))) b else a
num <- function(k, d) as.numeric(opt[[k]] %or% d); int <- function(k, d) as.integer(round(num(k, d)))
R_HOME_DIR <- normalizePath(if (nzchar(Sys.getenv("REWARD_R_HOME"))) Sys.getenv("REWARD_R_HOME") else {
  a <- grep("^--file=", commandArgs(), value = TRUE)
  if (length(a)) file.path(dirname(sub("^--file=", "", a)), "..") else if (file.exists("lib/reward_paths.R")) "." else ".." }, winslash = "/")
SCRATCH <- normalizePath(opt$scratch %or% file.path(tempdir(), "reward_bench"), winslash = "/", mustWork = FALSE); dir.create(SCRATCH, recursive = TRUE, showWarnings = FALSE)
fmt <- function(x) format(x, big.mark = ",", scientific = FALSE, trim = TRUE)

# ================================================================ fit: the scaling exponents and the extrapolation
if (!is.null(opt$fit)) {
  fs <- strsplit(opt$fit, ",", fixed = TRUE)[[1]]; stopifnot(length(fs) >= 2)
  S <- rbindlist(lapply(fs, fread), fill = TRUE); S <- S[order(rows_read)]
  runs <- unique(S[, .(tag, rows_read, rows_panel, pixels_panel, files, threads)]); setorder(runs, rows_read); print(runs)
  tr <- num("target_rows", 86579265); tp <- num("target_pixels", 3287286); tf <- num("target_files", 1253)
  A <- runs[nrow(runs) - 1L]; B <- runs[nrow(runs)]                                  # the two largest runs give the exponent
  W <- dcast(S[, .(tag, step, seconds_excl)], step ~ tag, value.var = "seconds_excl", fun.aggregate = sum)
  W[, order_first := S[tag == B$tag][match(W$step, step), order_first]]; setorder(W, order_first, na.last = TRUE)
  tA <- W[[A$tag]]; tB <- W[[B$tag]]; tA[is.na(tA)] <- 0; tB[is.na(tB)] <- 0
  expo <- ifelse(tA > 0.2 & tB > 0.2, log(tB / tA) / log(B$rows_read / A$rows_read), NA_real_)
  W[, per_file := grepl("^read_export$|^discover_exports$|^file_codes|^inline run_prep code after: read_export", step)]   # these scale with the files (1,253 in the real run) as well
  ext <- ifelse(is.finite(expo), tB * (tr / B$rows_read)^pmax(expo, 0), tB * (tr / B$rows_read))     # no exponent (tiny times): linear
  if (nrow(runs) >= 3) {                                                                # three runs: t = a + b * rows (a = the per-run / per-file fixed part)
    M <- dcast(S[, .(tag, step, seconds_excl)], step ~ tag, value.var = "seconds_excl", fun.aggregate = sum); M <- M[match(W$step, step)]
    X <- cbind(1, runs$rows_read); lin <- t(apply(as.matrix(M[, runs$tag, with = FALSE]), 1, function(y) { y[is.na(y)] <- 0; coef(lm.fit(X, y)) }))
    W[, `:=`(lin_intercept_s = lin[, 1], lin_per_1M_rows_s = lin[, 2] * 1e6)]
    W[, lin_extrap_min := round((pmax(lin_intercept_s, 0) * ifelse(per_file, tf / B$files, 1) + pmax(lin_per_1M_rows_s, 0) * tr / 1e6) / 60, 1)]
  }
  W[, `:=`(seconds_A = tA, seconds_B = tB, exponent = round(expo, 2), extrapolated_minutes = round(ext / 60, 1),
           superlinear = is.finite(expo) & expo > 1.15, threads_help = fifelse(grepl("^(read_export|resolve_duplicates|setorder|setorderv|duplicated|unique|merge|uniqueN|anyDuplicated|drop_rows_without_outcome|panel_variation_R|panel_design_columns_R|rbindlist)", step),
                                                                                "data.table threaded parts (fread, forder, subset, GForce): more threads help, up to the memory bandwidth", "mostly single-threaded R / sf / arrow: 128 threads do NOT help"))]
  W[per_file == TRUE, note := sprintf("also scales with the files: %s files in the real run vs %d here", fmt(tf), B$files)]
  setorder(W, -extrapolated_minutes)
  out <- opt$out %or% file.path(SCRATCH, "bench_scaling.csv"); fwrite(W, out)
  cat(sprintf("\nSCALING from %s (%s rows) and %s (%s rows) -> %s rows / %s pixels / %s files (%d threads here; the exponent is fitted on the rows;\n  pixels and rows grow together in these exports as in the real run: 25-26 rows per pixel; 128 threads on the real machine help only data.table's threaded parts)\n",
              A$tag, fmt(A$rows_read), B$tag, fmt(B$rows_read), fmt(tr), fmt(tp), fmt(tf), B$threads))
  print(W[, c("step", "seconds_A", "seconds_B", "exponent", "extrapolated_minutes", intersect("lin_extrap_min", names(W)), "superlinear"), with = FALSE][seconds_B > 0.05], nrows = 200)
  cat(sprintf("TOTAL extrapolated: %.0f min (power law per step)%s -> %s\n", sum(W$extrapolated_minutes, na.rm = TRUE),
              if ("lin_extrap_min" %in% names(W)) sprintf(" | %.0f min (linear with intercept, 3 runs)", sum(W$lin_extrap_min, na.rm = TRUE)) else "", out))
  quit(save = "no")
}

# ================================================================ the parameters of the exports
PIXELS <- int("pixels", 60000); TILES <- int("tiles", 6); DUP_TILES <- int("dup_tiles", 2); DUP_ROWS_SHARE <- num("dup_rows_share", 0.357)
COVERAGE <- num("coverage", 0.44); SECOND_ID <- int("second_id", 0); OUTSIDE_SHARE <- num("outside_share", 0.001); SHIFT_SHARE <- num("shift_share", 0.002)
yr <- as.integer(strsplit(opt$years %or% "2015-2025", "-")[[1]]); YEARS <- yr[1]:yr[length(yr)]; SEASONS <- as.integer(strsplit(opt$seasons %or% "0,1,2,3", ",")[[1]])
SEED <- int("seed", 1); THREADS <- int("threads", 4); TAG <- opt$tag %or% sprintf("px%d%s", PIXELS, if (identical(tolower(opt$old %or% "FALSE"), "true")) "_old" else "")
STAGE <- tolower(opt$stage %or% "all"); OLD <- identical(tolower(opt$old %or% "FALSE"), "true"); KEEP <- !identical(tolower(opt$keep_exports %or% "TRUE"), "false")
EXPORTS_ROOT <- file.path(SCRATCH, sprintf("exports_px%d", PIXELS)); EXPORT_FOLDER <- file.path(EXPORTS_ROOT, "REWARD_Jantapur_Exports_final")
OUT_ROOT <- file.path(SCRATCH, sprintf("output_%s", TAG)); SEASON_WORD <- c("Yearly", "Kharif", "Rabi", "Zaid")
OUTC <- c("NDVI", "EVI", "SAVI", "LAI", "NDRE", "NDMI", "LSWI", "NDWI", "SMDI", "VCI", "TCI", "VHI", "ESI", "WSI", "WSSI", "RUSLE", "AGB"); WEATH <- c("Rain", "Tmax", "Tmean", "Tmin")
cat(sprintf("[BENCH]   tag %s | pixels %s | blocks %d (years %d-%d x seasons %s) | tiles %d + %d re-export tiles | dup rows share %.3f | coverage %.2f | threads %d | scratch %s\n",
            TAG, fmt(PIXELS), length(YEARS) * length(SEASONS), min(YEARS), max(YEARS), paste(SEASONS, collapse = ","), TILES, DUP_TILES, DUP_ROWS_SHARE, COVERAGE, THREADS, SCRATCH))

# ================================================================ 1. the synthetic exports (the real layout)
generate_exports <- function() {
  suppressPackageStartupMessages(library(sf)); set.seed(SEED); setDTthreads(THREADS); t0 <- proc.time()[["elapsed"]]
  unlink(EXPORTS_ROOT, recursive = TRUE); dir.create(EXPORT_FOLDER, recursive = TRUE, showWarnings = FALSE)
  poly <- st_read(file.path(R_HOME_DIR, "data", "sites", "SWSs20_KarnatakaAll5k.shp"), quiet = TRUE); h <- poly[poly$SWSiD_All == 11L, ]   # Jantapur: core + rings 1-5 (UTM 43N)
  area <- as.numeric(st_area(h)); n_r <- pmax(1L, as.integer(round(PIXELS * area / sum(area))))
  cells <- function(g, n) {                                                            # random 10 m grid cells inside g (as the exporter's pixels)
    xy <- st_coordinates(st_sample(g, size = ceiling(n * 1.08))); xy <- unique(floor(xy[, 1:2] / 10) * 10 + 5); xy[seq_len(min(n, nrow(xy))), , drop = FALSE] }
  P <- rbindlist(lapply(seq_len(nrow(h)), function(i) { xy <- cells(h[i, ], n_r[i]); data.table(x = xy[, 1], y = xy[, 2], buff_km = as.integer(h$buff_km[i]), kind = "own") }))
  zone <- st_union(st_geometry(h)); ring_out <- st_difference(st_buffer(zone, 1500), zone)   # outside every polygon: 0-1.5 km beyond ring 5
  xo <- st_coordinates(st_sample(ring_out, size = max(5L, as.integer(round(OUTSIDE_SHARE * PIXELS)))))
  P <- rbind(P, data.table(x = floor(xo[, 1] / 10) * 10 + 5, y = floor(xo[, 2] / 10) * 10 + 5, buff_km = 5L, kind = "outside"))
  P[, `:=`(from_year = min(YEARS), to_year = max(YEARS))]
  n_sh <- as.integer(round(SHIFT_SHARE * PIXELS))                                     # a grid shifted 3 m from 2024: the originals end in 2023
  if (n_sh > 0 && max(YEARS) >= 2024L) { k <- sample(which(P$kind == "own"), n_sh); S <- copy(P[k])[, `:=`(x = x + 3, kind = "shift", from_year = 2024L)]; P[k, to_year := 2023L]; P <- rbind(P, S) }
  ll <- st_coordinates(st_transform(st_as_sf(as.data.frame(P[, .(x, y)]), coords = c("x", "y"), crs = st_crs(h)), 4326))
  P[, `:=`(lon = ll[, 1], lat = ll[, 2], uid = seq_len(.N), a = rnorm(.N, 0, 0.03), landuse = sample(1:5, .N, TRUE, prob = c(.15, .55, .15, .1, .05)))]
  P[, tile := pmin(TILES - 1L, as.integer(findInterval(lon, quantile(lon, probs = seq(0, 1, length.out = TILES + 1)), rightmost.closed = TRUE)) - 1L)]   # spatial tiles (longitude bands)
  r6 <- function(x) round(x, 6)
  mk_block <- function(Pb, y, s, dup = FALSE) {
    n <- nrow(Pb); eff <- ifelse(Pb$buff_km == 0L & y >= 2023L, 0.05, 0)
    ndvi <- 0.30 + Pb$a + 0.01 * (y - min(YEARS)) + c(0, 0.05, -0.04, -0.08)[s + 1L] + eff + rnorm(n, 0, 0.01)
    d <- data.table(UID = Pb$uid, Year = y, Season = s, SubwshedID = "U1", SWSiD_All = 11L, SWS_Name = "Jantapur", Treat = as.integer(y >= 2023L),
                    latitude = r6(Pb$lat), longitude = r6(Pb$lon), buff_km = Pb$buff_km, LandUse = Pb$landuse,
                    NDVI = r6(ndvi), SAVI = r6(0.8 * ndvi + rnorm(n, 0, 0.01)), EVI = r6(0.6 * ndvi + rnorm(n, 0, 0.01)), LAI = r6(pmax(0, 4 * ndvi + rnorm(n, 0, 0.2))),
                    LSWI = r6(ndvi - 0.2 + rnorm(n, 0, 0.02)), NDWI = r6(0.1 - ndvi + rnorm(n, 0, 0.02)), NDMI = r6(ndvi - 0.25 + rnorm(n, 0, 0.02)), NDRE = r6(0.5 * ndvi + rnorm(n, 0, 0.01)),
                    AGB = r6(pmax(0, 150 * ndvi + rnorm(n, 0, 10))), RUSLE = r6(pmax(0, 8 + rnorm(n, 0, 3))),
                    Rain = r6(pmax(0, c(900, 650, 120, 60)[s + 1L] + rnorm(n, 0, 60))), Tmax = r6(33 + rnorm(n, 0, .8)), Tmean = r6(26 + rnorm(n, 0, .6)), Tmin = r6(19 + rnorm(n, 0, .7)),
                    ESI = r6(rnorm(n, 0, 0.5)), WSSI = r6(rnorm(n, 0, 0.5)), WSI = r6(runif(n)), SMDI = r6(rnorm(n, 0, 1)), VCI = r6(runif(n, 0, 100)), TCI = r6(runif(n, 0, 100)), VHI = r6(runif(n, 0, 100)),
                    Coverage = r6(runif(n, 0.6, 1)), SrcOpt = sample(1:3, n, TRUE), NObsV = sample(1:40, n, TRUE), NObsT = sample(1:40, n, TRUE), GapFilled = as.integer(runif(n) < 0.03), OptTier = sample(1:4, n, TRUE))
    for (v in c(OUTC, WEATH)) { x <- d[[v]]; u <- runif(n); x[u < 0.01] <- 0; x[u >= 0.01 & u < 0.03] <- NA; if (dup) x[u >= 0.03 & u < 0.08] <- NA; set(d, j = v, value = x) }   # exact zeros, gaps (more in a re-export)
    d[runif(n) < 0.003, Rain := -9999]; d[runif(n) < 0.002, Tmin := -10]
    d
  }
  T0 <- Sys.time() - 7 * 86400; q <- DUP_ROWS_SHARE / (2 - DUP_ROWS_SHARE)              # q of the pixel-year-seasons twice -> 2q / (1 + q) of the rows shared
  BL <- CJ(Year = YEARS, Season = SEASONS); n_rows <- 0; n_dup <- 0; n_files <- 0L
  for (b in seq_len(nrow(BL))) {
    yb <- BL$Year[b]; sb <- BL$Season[b]; Pb <- P[from_year <= yb & to_year >= yb][runif(.N) < COVERAGE]; if (!nrow(Pb)) next   # (x, y are columns of P)
    d <- mk_block(Pb, yb, sb); sid <- if (b %% 2L == 1L || is.na(SECOND_ID)) 11L else SECOND_ID; d[, SWSiD_All := sid]
    for (t in 0:(TILES - 1L)) { f <- file.path(EXPORT_FOLDER, sprintf("CSV_%d_%s_tile%d.csv", yb, SEASON_WORD[sb + 1L], t)); fwrite(d[Pb$tile == t], f); Sys.setFileTime(f, T0); n_files <- n_files + 1L }
    n_rows <- n_rows + nrow(d)
    sel <- which(runif(nrow(d)) < q)
    if (length(sel)) {
      dd <- mk_block(Pb[sel], yb, sb, dup = TRUE); dd[, SWSiD_All := sid]; part <- rep_len(seq_len(DUP_TILES), length(sel))
      for (k in seq_len(DUP_TILES)) { f <- file.path(EXPORT_FOLDER, sprintf("CSV_%d_%s_tile%d.csv", yb, SEASON_WORD[sb + 1L], TILES + k - 1L)); fwrite(dd[part == k], f); Sys.setFileTime(f, T0 + 3600); n_files <- n_files + 1L }
      n_rows <- n_rows + length(sel); n_dup <- n_dup + length(sel)
    }
  }
  st <- data.table(tag = TAG, pixels_param = PIXELS, pixel_locations = nrow(P), own = sum(P$kind == "own"), outside = sum(P$kind == "outside"), shifted = sum(P$kind == "shift"),
                   blocks = nrow(BL), files = n_files, rows_written = n_rows, rows_in_repeated_groups = 2 * n_dup, share_rows_repeated = round(2 * n_dup / n_rows, 3),
                   bytes = sum(file.size(list.files(EXPORT_FOLDER, full.names = TRUE))), seconds = round(proc.time()[["elapsed"]] - t0, 1))
  fwrite(st, file.path(SCRATCH, sprintf("bench_exports_%s.csv", TAG)))
  cat(sprintf("[BENCH]   exports written: %d files, %s rows (%s in repeated groups = %.1f %%), %s pixel locations (%d outside, %d shifted), %.2f GB, %.0f s -> %s\n",
              n_files, fmt(n_rows), fmt(2 * n_dup), 100 * 2 * n_dup / n_rows, fmt(nrow(P)), st$outside, st$shifted, st$bytes / 1e9, st$seconds, EXPORT_FOLDER))
  invisible(st)
}
if (STAGE %in% c("all", "generate")) generate_exports()
if (STAGE == "generate") quit(save = "no")

# ================================================================ 2. the library, exactly as build_panel.R sources it
Sys.setenv(REWARD_R_ROOT = normalizePath(EXPORTS_ROOT, winslash = "/", mustWork = TRUE), REWARD_TEST_RUN = "1",
           REWARD_FUND_PATH = file.path(SCRATCH, "no_fund_file.xlsx"))                      # (the fund workbook is not part of the benchmark, as in the tests)
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
OUTPUT_DIR <- normalizePath(OUT_ROOT, winslash = "/", mustWork = FALSE); RESULTS_DIR <- file.path(OUTPUT_DIR, "results")
PANEL_PATH <- file.path(OUTPUT_DIR, "did_panel_full.parquet"); DESIGN_PATH <- file.path(OUTPUT_DIR, "R_design.json")
if (STAGE != "summarise") unlink(OUTPUT_DIR, recursive = TRUE); dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
N_THREADS <- max(1L, THREADS); setDTthreads(N_THREADS); if (requireNamespace("fixest", quietly = TRUE)) fixest::setFixest_nthreads(N_THREADS)
cat(sprintf("[BENCH]   library sourced from %s | ROOT %s | OUTPUT_DIR %s | data.table %s threads %d | R %s | arrow %s | sf %s\n", R_HOME_DIR, ROOT, OUTPUT_DIR,
            as.character(packageVersion("data.table")), getDTthreads(), paste(R.version$major, R.version$minor, sep = "."), as.character(packageVersion("arrow")), as.character(packageVersion("sf"))))

if (OLD) {   # ---- the 1 Oct-MORNING bodies (git 75fbb3f, the state of the real run), re-assigned in the global environment
  drop_rows_without_outcome <- function(dt) {
    oc <- intersect(OUTCOME_VARS, names(dt)); if (!length(oc)) return(dt)
    any_ok <- rowSums(is.finite(as.matrix(dt[, ..oc]))) > 0
    attr_n <- sum(!any_ok); out <- dt[any_ok]; attr(out, "rows_dropped_no_outcome") <- attr_n; out
  }
  panel_pixel_consistency_R <- function(pix, n_rep, n_rows, write = TRUE) {
    g <- pix[, .(sites = uniqueN(site_id), rings = uniqueN(buff_km), coords = uniqueN(paste(latitude, longitude))), by = pixel_id]
    bad <- g[sites > 1 | rings > 1 | coords > 1]
    if (write) fwrite(bad, file.path(OUTPUT_DIR, "panel_pixel_consistency_R.csv"))
    if (!nrow(bad) && n_rep == 0) ok(sprintf("pixel consistency CONFIRMED: %s pixels (old body)", format(nrow(g), big.mark = ",")))
    else warn(sprintf("pixel consistency NOT met: %s repeated; %s two sites, %s two rings, %s two coordinates (old body)", n_rep, sum(g$sites > 1), sum(g$rings > 1), sum(g$coords > 1)))
    invisible(list(pixels = nrow(g), two_sites = sum(g$sites > 1), two_rings = sum(g$rings > 1), repeated = n_rep))
  }
  pixel_registry <- function(dt) {
    oc <- intersect(OUTCOME_VARS_CORE, names(dt))
    d <- dt[, c("pixel_id", "latitude", "longitude", "file_mtime", "src_file", oc), with = FALSE]
    d[, n_ok := rowSums(is.finite(as.matrix(.SD))), .SDcols = oc]
    setorder(d, file_mtime)
    d[, .(lat = mean(latitude), lon = mean(longitude), mtime = max(file_mtime), n_rows = .N, n_ok = sum(n_ok), src = src_file[.N]), by = pixel_id][, completeness := n_ok / pmax(n_rows, 1)][]
  }
  cat("[BENCH]   old=TRUE: drop_rows_without_outcome (N x K matrix), panel_pixel_consistency_R (uniqueN(paste()) per pixel) and pixel_registry (src_file[.N] per pixel) are the 1 Oct-morning bodies (git 75fbb3f)\n")
}

# ================================================================ 3. the timing wrappers (re-assigned in the global environment; run_prep looks the functions up by name)
.BENCH <- new.env(); .BENCH$stack <- integer(0); .BENCH$seq <- 0L; .BENCH$rows <- list()
.BENCH$calls_csv <- file.path(SCRATCH, sprintf("bench_calls_%s.csv", TAG)); if (STAGE != "summarise") unlink(.BENCH$calls_csv)
bench_rss_gb <- function() tryCatch(as.numeric(ps::ps_memory_info(ps::ps_handle())[["rss"]]) / 1e9, error = function(e) NA_real_)
bench_hwm_gb <- function() {                                                            # the process peak RSS (Linux VmHWM; elsewhere the current RSS)
  if (file.exists("/proc/self/status")) { v <- grep("^VmHWM:", readLines("/proc/self/status"), value = TRUE); if (length(v)) return(as.numeric(gsub("[^0-9]", "", v)) * 1024 / 1e9) }
  bench_rss_gb()
}
bench_size <- function(x) if (is.data.frame(x)) nrow(x) else if (is.atomic(x)) length(x) else NA_real_
bench_run <- function(step, thunk, detail = "") {                                       # one timed call: the stack gives parent / depth (nested wrapped calls)
  .BENCH$seq <- .BENCH$seq + 1L; id <- .BENCH$seq; parent <- if (length(.BENCH$stack)) tail(.BENCH$stack, 1L) else 0L; .BENCH$stack <- c(.BENCH$stack, id)
  t0 <- proc.time()[["elapsed"]]; r0 <- bench_rss_gb()
  out <- tryCatch(thunk(), finally = { .BENCH$stack <- head(.BENCH$stack, -1L) })
  t1 <- proc.time()[["elapsed"]]; r1 <- bench_rss_gb(); h1 <- bench_hwm_gb()
  d <- if (is.function(detail)) tryCatch(detail(out), error = function(e) "") else detail
  rec <- data.table(id = id, parent = parent, depth = length(.BENCH$stack), step = step, detail = substr(gsub("[\r\n,]+", " ", d), 1, 120), seconds = round(t1 - t0, 3),
                    t_start = round(t0, 3), t_end = round(t1, 3), rss_before_gb = round(r0, 3), rss_after_gb = round(r1, 3), peak_rss_gb = round(h1, 3), rows_out = bench_size(out))
  .BENCH$rows[[length(.BENCH$rows) + 1L]] <- rec; fwrite(rec, .BENCH$calls_csv, append = file.exists(.BENCH$calls_csv))
  out
}
bench_wrap <- function(name, step = name, detail = NULL) {                              # a global function -> the same function, timed
  orig <- get(name, envir = globalenv(), mode = "function"); force(orig)
  w <- function(...) bench_run(step, function() orig(...), if (is.null(detail)) "" else function(out) detail(list(...), out))
  assign(name, w, envir = globalenv()); invisible(name)
}
bench_shadow <- function(name, impl, step = name, detail = NULL, only_direct = FALSE) {   # a base / data.table / sf generic run_prep calls inline -> timed, then the real one
  w <- function(...) {                                                                  # only_direct: recorded only when run_prep itself calls it (a call per group inside a step --
    if (only_direct && length(.BENCH$stack) != 1L) return(impl(...))                   #   the 1 Oct-morning consistency check: 3 uniqueN() per pixel -- would be inflated by the recording)
    bench_run(step, function() impl(...), if (is.null(detail)) "" else function(out) detail(list(...), out))
  }
  assign(name, w, envir = globalenv()); invisible(name)
}
bench_unshadow <- function(...) suppressWarnings(rm(list = c(...), envir = globalenv()))
.by <- function(a) { b <- a$by %or% a$by.x %or% NULL; if (is.null(b)) "" else paste(b, collapse = ",") }
.rows_in <- function(a) { x <- a[[1]]; if (is.data.frame(x)) sprintf("%s rows in", fmt(nrow(x))) else if (is.atomic(x)) sprintf("%s values in", fmt(length(x))) else if (is.list(x)) sprintf("%d parts in", length(x)) else "" }
.detail_rows <- function(a, out) sprintf("%s; %s out", .rows_in(a), fmt(bench_size(out) %or% NA))
.detail_by <- function(a, out) sprintf("by=%s; %s; %s out", .by(a), .rows_in(a), fmt(bench_size(out) %or% NA))

# the pipeline's own steps
for (nm in c("discover_exports", "read_export", "input_audit_report_R", "pixel_ids", "overlay_sws", "working_sws_line", "file_codes", "merge_near_duplicate_pixels",
             "near_dup_map_R", "pixel_registry", "near_duplicate_pairs", "canonical_pixel_map", "resolve_duplicates", "drop_rows_without_outcome",
             "panel_design_columns_R", "panel_variation_R", "panel_variation_report_R", "panel_kept_report_R", "build_fund_tables", "bm_sws_means", "panel_write"))
  bench_wrap(nm, detail = .detail_rows)
# the shadows of the generics run_prep (and the steps above) call inline
bench_shadow("merge", function(x, y, ...) base::merge(x, y, ...), step = "merge", detail = .detail_by)
bench_shadow("unique", function(x, ...) base::unique(x, ...), step = "unique", detail = .detail_by)
bench_shadow("duplicated", function(x, ...) base::duplicated(x, ...), step = "duplicated", detail = .detail_by)
bench_shadow("rbindlist", function(l, ...) data.table::rbindlist(l, ...), step = "rbindlist", detail = .detail_rows)
bench_shadow("setorderv", function(x, cols = colnames(x), ...) data.table::setorderv(x, cols, ...), step = "setorderv", detail = function(a, out) sprintf("cols=%s; %s rows", paste(a[[2]], collapse = ","), fmt(nrow(a[[1]]))))
setorder <- function(x, ..., na.last = FALSE) { cols <- vapply(as.list(substitute(list(...)))[-1L], function(v) paste(deparse(v), collapse = ""), ""); bench_run("setorder", function() data.table::setorder(x, ..., na.last = na.last), sprintf("cols=%s; %s rows", paste(cols, collapse = ","), fmt(nrow(x)))) }
# sf inside overlay_sws (library(sf) is attached there; the global environment still comes first on the search path)
bench_shadow("st_read", function(...) sf::st_read(...), step = "overlay: st_read(shapefile)")
bench_shadow("st_as_sf", function(x, ...) sf::st_as_sf(x, ...), step = "overlay: st_as_sf(points)", detail = .detail_rows)
bench_shadow("st_transform", function(x, ...) sf::st_transform(x, ...), step = "overlay: st_transform(points)", detail = .detail_rows)
bench_shadow("st_intersects", function(x, y, ...) sf::st_intersects(x, y, ...), step = "overlay: st_intersects(points, polygons)", detail = .detail_rows)
# uniqueN / anyDuplicated only in the window where run_prep calls them directly (after the dedup, before the design columns): elsewhere a shadow turns GForce off
.shadow_window_on <- function() { bench_shadow("uniqueN", function(x, ...) data.table::uniqueN(x, ...), step = "uniqueN", detail = .detail_by, only_direct = TRUE)
                                  bench_shadow("anyDuplicated", function(x, ...) base::anyDuplicated(x, ...), step = "anyDuplicated", detail = .detail_by, only_direct = TRUE) }
.shadow_window_off <- function() bench_unshadow("uniqueN", "anyDuplicated")
local({ orig <- drop_rows_without_outcome; drop_rows_without_outcome <<- function(...) { out <- orig(...); .shadow_window_on(); out } })
local({ orig <- panel_design_columns_R; panel_design_columns_R <<- function(...) { .shadow_window_off(); orig(...) } })
# panel_pixel_consistency_R: its ARGUMENTS are the unique() of the inside rows and a uniqueN() over them (run_prep builds them in the call) -- timed apart from the body
local({ orig <- panel_pixel_consistency_R                                               # (orig is already the timed one)
  panel_pixel_consistency_R <<- function(pix, n_rep, n_rows, write = TRUE) {
    bench_run("pixel consistency: arguments (unique() of the inside rows, uniqueN(pixel, Year, Season))", function() { force(pix); force(n_rep); force(n_rows); NULL })
    orig(pix, n_rep, n_rows, write)
  } })
# panel_variation_R: its `get(v)` in j makes data.table collect ALL columns for every group ("'(m)get' found in j. ansvars being set to all columns";
# 16 s per outcome at 290 k rows x 51 columns, 17 outcomes = 281 s of a 315 s run; the same numbers with .SDcols = v take 0.4 s). A run at
# 1.5 M rows could not finish in one go with it, so: variation=probe1 (default) times the ORIGINAL form on the FIRST outcome at the run's full
# size (x 17 = the real cost, derived in the table) and computes the 17 outcomes with the .SDcols form (identical numbers, asserted on that
# outcome); variation=orig leaves the function as it is; variation=fast substitutes without the probe.
VARIATION <- tolower(opt$variation %or% "probe1")
.variation_fast <- function(dt, vars = OUTCOME_VARS) {
  vs <- intersect(vars, names(dt)); if (!length(vs)) return(NULL)
  rbindlist(lapply(vs, function(v) {
    x <- dt[is.finite(get(v)), { z <- as.numeric(.SD[[1L]]); mu <- mean(z); .(finite = .N, mean = mu, m2 = sum((z - mu)^2), min = min(z), max = max(z)) }, by = .(Year, Season), .SDcols = v]
    x[, variable := rep(v, nrow(x))]; x }), use.names = TRUE, fill = TRUE)
}
if (VARIATION != "orig") local({ orig <- panel_variation_R                             # (orig is the timed library function)
  panel_variation_R <<- function(dt, vars = OUTCOME_VARS, ...) {
    vs <- intersect(vars, names(dt)); n_oc <- length(vs)
    if (VARIATION == "probe1" && n_oc) {
      one <- orig(dt, vars = vs[1])                                                     # timed by the wrapper: step "panel_variation_R", 1 outcome
      fast1 <- bench_run("panel_variation_R: the .SDcols form of the same outcome (identical numbers)", function() .variation_fast(dt, vars = vs[1]))
      cat(sprintf("[BENCH]   panel_variation_R probe: the original form on %s (1 of %d outcomes) vs the .SDcols form -- identical: %s\n", vs[1], n_oc, isTRUE(all.equal(one, fast1))))
    }
    bench_run(sprintf("panel_variation_R (.SDcols form substituted for the run, %d outcomes)", n_oc), function() .variation_fast(dt, vars = vs))
  } })
# the in-memory path, whatever the 98 % rule would say on this machine (the real run took it)
local({ orig <- prep_mode_R; prep_mode_R <<- function(files) { m <- orig(files); cat(sprintf("[BENCH]   prep_mode_R would say \"%s\"%s -- the in-memory path is run (the real run's)\n", m$mode, if (nzchar(m$why)) paste0(" (", m$why, ")") else "")); list(mode = "memory", why = "") } })
if (!exists("ok", mode = "function")) ok <- function(...) cat("[OK]      ", ..., "\n", sep = "")

# ================================================================ 4. the run and the tables
# bench_summarise(): the per-step table from the per-call records (also stage=summarise, which rebuilds it from bench_calls_<tag>.csv).
# seconds_excl = a call's seconds minus its nested wrapped calls'; the gaps between the steps run_prep calls directly are its own inline lines.
# With variation=probe1 the ORIGINAL form's remaining outcomes are DERIVED from the one-outcome probe (in_real_run TRUE) and the substituted
# .SDcols rows are shown but kept OUT of the real run's total (in_real_run FALSE).
bench_summarise <- function(calls, tag, panel_rows, pixels_panel, n_oc = length(OUTCOME_VARS), threads = getDTthreads(), old = OLD, variation = VARIATION, peak_gb = bench_hwm_gb(), write = TRUE) {
  calls <- copy(calls); calls[, children_s := 0]
  calls[, parent_step := step[match(parent, id)]]; calls[depth >= 2L & !is.na(parent_step), step := paste0(step, " < ", parent_step)]   # a nested call carries its parent's name
  ch <- calls[parent > 0, .(s = sum(seconds)), by = parent]; calls[ch, on = .(id = parent), children_s := i.s]; calls[, seconds_excl := pmax(0, seconds - children_s)]
  run_row <- calls[step == "run_prep (total)"]; total_s <- run_row$seconds
  top <- calls[depth == 1L][order(t_start)]                                            # the steps run_prep calls directly; the gaps between them = its own inline code
  gaps <- if (nrow(top) > 1) data.table(id = NA_integer_, parent = 1L, depth = 1L, step = sprintf("inline run_prep code after: %s", top$step[-nrow(top)]), detail = "unwrapped lines of run_prep between the two steps",
                                       seconds = pmax(0, top$t_start[-1] - top$t_end[-nrow(top)]), t_start = top$t_end[-nrow(top)], t_end = top$t_start[-1], rss_before_gb = top$rss_after_gb[-nrow(top)],
                                       rss_after_gb = top$rss_before_gb[-1], peak_rss_gb = top$peak_rss_gb[-1], rows_out = NA_real_, children_s = 0, seconds_excl = pmax(0, top$t_start[-1] - top$t_end[-nrow(top)])) else NULL
  tail_gap <- data.table(id = NA_integer_, parent = 1L, depth = 1L, step = c("inline run_prep code before the first step", "inline run_prep code after the last step (settings, balance table, final counts)"), detail = "",
                         seconds = c(top$t_start[1] - run_row$t_start, run_row$t_end - top$t_end[nrow(top)]), t_start = c(run_row$t_start, top$t_end[nrow(top)]), t_end = c(top$t_start[1], run_row$t_end),
                         rss_before_gb = NA_real_, rss_after_gb = NA_real_, peak_rss_gb = run_row$peak_rss_gb, rows_out = NA_real_, children_s = 0, seconds_excl = c(top$t_start[1] - run_row$t_start, run_row$t_end - top$t_end[nrow(top)]))
  allc <- rbind(calls[step != "run_prep (total)"], gaps, tail_gap, fill = TRUE); allc[, in_real_run := TRUE]
  pv <- calls[step == "panel_variation_R" | startsWith(step, "panel_variation_R <")]
  if (variation == "probe1" && nrow(pv)) {                                             # the real cost of the original form: the one-outcome probe x the other outcomes
    pv <- pv[1]
    allc <- rbind(allc, data.table(step = sprintf("panel_variation_R: ORIGINAL form, the other %d outcomes (DERIVED: %d x the 1-outcome probe)", n_oc - 1L, n_oc - 1L), depth = 1L, seconds = pv$seconds * (n_oc - 1L), seconds_excl = pv$seconds * (n_oc - 1L),
                                   t_start = pv$t_start, peak_rss_gb = pv$peak_rss_gb, rss_after_gb = pv$rss_after_gb, detail = sprintf("%.1f s for one outcome at %s rows", pv$seconds, fmt(panel_rows)), in_real_run = TRUE), fill = TRUE)
    allc[grepl("^panel_variation_R \\(\\.SDcols form substituted|^panel_variation_R: the \\.SDcols form|< panel_variation_R \\(\\.SDcols|< panel_variation_R: the \\.SDcols", step), in_real_run := FALSE]
  }
  steps <- allc[, .(calls = .N, seconds_incl = round(sum(seconds), 2), seconds_excl = round(sum(seconds_excl), 2), peak_rss_gb = max(peak_rss_gb, na.rm = TRUE), rss_after_gb_max = suppressWarnings(max(rss_after_gb, na.rm = TRUE)),
                    depth = min(depth), order_first = min(t_start), rows_out = suppressWarnings(max(rows_out, na.rm = TRUE)), in_real_run = all(in_real_run)), by = step][order(order_first)]
  total_real <- sum(steps[in_real_run == TRUE, seconds_excl]); steps[, share_pct := round(100 * seconds_excl / total_real, 1)]
  rows_read <- calls[step == "rbindlist" & depth == 1L, max(rows_out, na.rm = TRUE)]; files_n <- calls[step == "read_export", .N]
  steps[, `:=`(tag = tag, rows_read = rows_read, rows_panel = panel_rows, pixels_panel = pixels_panel, files = files_n, threads = threads, total_seconds = round(total_real, 1), measured_seconds = round(total_s, 1), old_bodies = old, variation = variation)]
  if (write) {
    steps_csv <- file.path(SCRATCH, sprintf("bench_steps_%s.csv", tag)); fwrite(steps, steps_csv); run_csv <- file.path(SCRATCH, "bench_runs.csv")
    fwrite(data.table(tag = tag, pixels_param = PIXELS, files = files_n, rows_read = rows_read, rows_panel = panel_rows, pixels_panel = pixels_panel, total_seconds = round(total_real, 1), total_minutes = round(total_real / 60, 2),
                      measured_seconds = round(total_s, 1), peak_rss_gb = round(peak_gb, 2), threads = threads, old_bodies = old, variation = variation, data_table = as.character(packageVersion("data.table")),
                      r_version = paste(R.version$major, R.version$minor, sep = "."), cores = parallel::detectCores(), ram_gb = round(as.numeric(ps::ps_system_memory()$total) / 1e9, 1), when = format(Sys.time(), "%Y-%m-%d %H:%M:%S")),
           run_csv, append = file.exists(run_csv))
    cat(sprintf("\n[BENCH]   PER-STEP TABLE -- %s: %s rows read from %d files -> panel %s rows, %s pixels | total %.1f s (%.1f min) as the ORIGINAL code would run%s | peak RSS %.2f GB | %d threads\n", tag, fmt(rows_read), files_n,
                fmt(panel_rows), fmt(pixels_panel), total_real, total_real / 60, if (variation == "probe1") sprintf(" (measured %.1f s with the .SDcols form substituted)", total_s) else "", peak_gb, threads))
    options(width = 200); print(steps[, .(step = substr(step, 1, 95), depth, calls, seconds_incl, seconds_excl, share_pct, peak_rss_gb = round(peak_rss_gb, 2), rows_out, in_real_run)], nrows = 300)
    cat(sprintf("[BENCH]   -> %s (steps), %s (every call), %s (runs)\n", steps_csv, file.path(SCRATCH, sprintf("bench_calls_%s.csv", tag)), run_csv))
  }
  invisible(steps)
}
if (STAGE == "summarise") {                                                            # rebuild the tables of an earlier run from its per-call records
  cl <- fread(file.path(SCRATCH, sprintf("bench_calls_%s.csv", TAG))); rr <- fread(file.path(SCRATCH, "bench_runs.csv"))[tag == TAG]; rr <- rr[nrow(rr)]
  bench_summarise(cl, TAG, panel_rows = cl[step == "panel_design_columns_R", max(rows_out)], pixels_panel = rr$pixels_panel, threads = rr$threads, old = isTRUE(rr$old_bodies), variation = opt$variation %or% rr$variation %or% "probe1", peak_gb = rr$peak_rss_gb)
  quit(save = "no")
}
cat(sprintf("[BENCH]   run_prep() starts: RSS %.2f GB, peak so far %.2f GB\n", bench_rss_gb(), bench_hwm_gb()))
panel <- bench_run("run_prep (total)", function() run_prep())
bench_unshadow("merge", "unique", "duplicated", "rbindlist", "setorderv", "setorder", "st_read", "st_as_sf", "st_transform", "st_intersects", "uniqueN", "anyDuplicated")
bench_summarise(rbindlist(.BENCH$rows), TAG, panel_rows = nrow(panel), pixels_panel = uniqueN(panel$pixel_id), n_oc = length(intersect(OUTCOME_VARS, names(panel))))
if (!KEEP) unlink(EXPORTS_ROOT, recursive = TRUE)
