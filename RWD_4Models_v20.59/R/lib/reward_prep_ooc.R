# reward_prep_ooc.R -- v20.58: R_P00 BEYOND 98 % OF THE RAM -- the panel built BLOCK BY BLOCK (year x season), the SAME panel row for row
#
# Below 98 % run_prep() reads every export at once (nothing changes). Beyond it the same rules run in two passes, never holding more than
# one export file or one block in RAM, on the engines of OUT_OF_CORE (Dask -> Spark -> R batches; lib/reward_outofcore.R):
#   PASS 1  one task per export file: read_export (the same harmonising, keys, buffers, missing values, negative covariates), the pixel id,
#           the file's sub-watershed id -- its rows kept on disk per year x season block; back to R only what is pixel- or file-level:
#           the pixel locations for the shapefile overlay (the FIRST location of each pixel x file id, as in memory), the rows per pixel x
#           file id (each file's majority sub-watershed: the fragment codes), the pixel registry's sums (the near-duplicate pixels)
#   then    the overlay, the fragment codes per file, the near-duplicate map -- pixel-level tables, the same functions as in memory
#   PASS 2  one task per block (a block too large for one task: per pixel group of it): the overlay's sub-watershed and ring, the fragment
#           code, the near-duplicate merge, the duplicates resolved (every key lies in one block), rows without an outcome out, the
#           confirmations; then the blocks are written one after another in the panel's order (year, season, sub-watershed, pixel), the
#           BM means merged, the panel's column order and types
# tests/run_all_tests.R scenario H checks it: in memory == block by block, every column of every row.
PREP_EXPANSION <- 6     # RAM per byte of export files when everything is read at once (text -> columns, the merges' copies)

prep_mode_R <- function(files) {
  f <- if (exists("ooc_forced", mode = "function")) ooc_forced() else NULL
  if (!is.null(f)) return(list(mode = "out_of_core", why = sprintf("REWARD_FORCE_OUT_OF_CORE = %s (the checks: block by block on data that would fit)", f)))
  need <- sum(as.numeric(file.size(files$file)), na.rm = TRUE) * PREP_EXPANSION; b <- ram_budget_bytes()
  if (is.finite(b) && need > b) return(list(mode = "out_of_core", why = sprintf("the exports need ~%.2f GB in RAM at once and %.2f GB are free below 98 %%", need / 1e9, b / 1e9)))
  list(mode = "memory", why = "")
}
.rank_type <- function(v) if (is.character(v) || is.factor(v)) 4L else if (is.double(v)) 3L else if (is.integer(v)) 2L else if (is.logical(v)) 1L else 4L
.as_type <- function(v, r) switch(as.character(r), "1" = as.logical(v), "2" = as.integer(v), "3" = as.numeric(v), as.character(v))
.na_of <- function(r, n) switch(as.character(r), "1" = rep(NA, n), "2" = rep(NA_integer_, n), "3" = rep(NA_real_, n), rep(NA_character_, n))
# the pixel registry's additive parts (pixel_registry, reward_prep.R): sums, counts, extremes; lat / lon exact when every row agrees
.reg_parts <- function(dt) {
  oc <- intersect(OUTCOME_VARS_CORE, names(dt))
  d <- dt[, c("pixel_id", "latitude", "longitude", "file_mtime", "src_file", oc), with = FALSE]
  d[, n_ok := rowSums(is.finite(as.matrix(.SD))), .SDcols = oc]
  d[, .(slat = sum(latitude), slon = sum(longitude), lat_lo = min(latitude), lat_hi = max(latitude), lon_lo = min(longitude), lon_hi = max(longitude),
        n_rows = .N, n_ok = sum(n_ok), mtime = max(file_mtime), mtime_lo = min(file_mtime), src = src_file[which.max(file_mtime)]), by = pixel_id]
}
.reg_merge <- function(parts) {                                   # pixel_registry()'s table from the parts, in its row order
  r <- rbindlist(parts)
  if (!nrow(r)) return(data.table(pixel_id = character(0), lat = numeric(0), lon = numeric(0), mtime = numeric(0), n_rows = integer(0), n_ok = numeric(0), src = character(0), completeness = numeric(0)))
  r <- r[, .(slat = sum(slat), slon = sum(slon), lat_lo = min(lat_lo), lat_hi = max(lat_hi), lon_lo = min(lon_lo), lon_hi = max(lon_hi),
             n_rows = sum(n_rows), n_ok = sum(n_ok), src = src[which.max(mtime)], mtime = max(mtime), mtime_lo = min(mtime_lo)), by = pixel_id]
  r[, `:=`(lat = fifelse(lat_lo == lat_hi, lat_lo, slat / n_rows), lon = fifelse(lon_lo == lon_hi, lon_lo, slon / n_rows))]
  setorderv(r, c("mtime_lo", "pixel_id"))                         # in memory: the pixels in the order of their first (oldest) row
  r[, completeness := n_ok / pmax(n_rows, 1)]
  r[, .(pixel_id, lat, lon, mtime, n_rows, n_ok, src, completeness)]
}

# ---------------------------------------------------------------- PASS 1: one export file
ooc_task_p00_read <- function(ctx, i) {
  f <- ctx$files[i]
  x <- tryCatch(read_export(f$file, f$Year, f$Season, f$sws_hint, f$folder, f$sws_file, f$mtime), error = function(e) e)
  if (inherits(x, "error")) return(list(ok = FALSE, warn = paste0(basename(f$file), ": ", conditionMessage(x))))
  x[, pixel_id := pixel_ids(latitude, longitude)]
  x[, sws_export := suppressWarnings(as.integer(if ("SWSiD_All" %in% names(x)) SWSiD_All else NA_integer_))]
  x[is.na(sws_hint), sws_hint := ""]
  x[is.na(sws_export), sws_export := sws_file]
  blocks <- x[, .N, by = .(Year, Season)]
  for (b in seq_len(nrow(blocks))) {
    y <- blocks$Year[b]; s <- blocks$Season[b]; d <- file.path(ctx$run_dir, "blocks", sprintf("%d_%d", y, s)); dir.create(d, recursive = TRUE, showWarnings = FALSE)
    saveRDS(x[Year == y & Season == s], file.path(d, sprintf("f_%06d.rds", i)), compress = FALSE)
  }
  list(ok = TRUE, rows = nrow(x), src_file = if (nrow(x)) x$src_file[1] else basename(f$file), sws_file = f$sws_file,
       px = unique(x[, .(pixel_id, latitude, longitude, sws_export)], by = c("pixel_id", "sws_export")),
       pairs = x[, .N, by = .(pixel_id, sws_export)], types = vapply(x, .rank_type, 1L), reg = .reg_parts(x), blocks = blocks)
}
# ---------------------------------------------------------------- PASS 2: one block (or one pixel group of a large block)
ooc_task_p00_block <- function(ctx, k) {
  job <- ctx$jobs[k]; bd <- file.path(ctx$run_dir, "blocks", job$block); fs <- sort(list.files(bd, pattern = "^f_[0-9]+\\.rds$", full.names = TRUE))
  cm <- ctx$cmap; J <- as.integer(job$J); j <- as.integer(job$j)
  parts <- lapply(fs, function(f) { x <- readRDS(f)
    if (J > 1L) { canon <- if (nrow(cm)) cm$canonical_pixel_id[match(x$pixel_id, cm$pixel_id)] else rep(NA_character_, nrow(x))
                  canon[is.na(canon)] <- x$pixel_id[is.na(canon)]; x <- x[ooc_part_of(canon, J) == j] }   # all rows of a (merged) pixel together
    x })
  dt <- rbindlist(parts, fill = TRUE); rm(parts)
  for (c_ in setdiff(names(ctx$types), names(dt))) set(dt, j = c_, value = .na_of(ctx$types[[c_]], nrow(dt)))   # rbindlist's fill over EVERY file
  for (c_ in names(ctx$types)) if (.rank_type(dt[[c_]]) != ctx$types[[c_]]) set(dt, j = c_, value = .as_type(dt[[c_]], ctx$types[[c_]]))
  # the overlay's sub-watershed and ring (on the exports' own pixel ids, as in memory), the name, the fragment code of each row's file
  dt <- merge(dt, ctx$px, by = c("pixel_id", "sws_export"), all.x = TRUE)
  dt[site_check %in% c(1L, 2L) & !is.na(ring_poly), buff_km := ring_poly]
  dt[, sws_name := ctx$ids[as.character(site_id)]]
  sid <- as.integer(fifelse(is.na(dt$site_id), 0L, as.integer(dt$site_id))); chk <- as.integer(fifelse(is.na(dt$site_check), 4L, as.integer(dt$site_check)))
  m <- unname(ctx$major[dt$src_file]); inp <- chk %in% IN_POLYGON; code <- integer(nrow(dt)); hm <- !is.na(m)
  code[hm & inp & sid != m] <- 1L; code[hm & !inp & sid != m] <- 2L; dt[, fragment := code]
  if (nrow(cm)) dt[cm, on = "pixel_id", `:=`(pixel_id = i.canonical_pixel_id, latitude = i.canonical_lat, longitude = i.canonical_lon)]   # near-duplicate pixels
  dt <- resolve_duplicates(dt, say = FALSE); dd <- attr(dt, "dedup")
  n_no <- 0L
  if (DROP_ROWS_WITHOUT_OUTCOME) { n0 <- nrow(dt); dt <- drop_rows_without_outcome(dt); n_no <- n0 - nrow(dt) }
  nk <- anyDuplicated(dt, by = c("site_id", "pixel_id", "Year", "Season"))
  if (nk) stop(sprintf("duplicate removal FAILED: (site %s, pixel %s, %s, season %s) is still repeated -- please report this", dt$site_id[nk], dt$pixel_id[nk], dt$Year[nk], dt$Season[nk]))
  no <- dt[site_check == 3L, anyDuplicated(.SD), .SDcols = c("pixel_id", "Year", "Season")]
  if (no) stop("duplicate removal FAILED: a pixel outside every polygon is still repeated in a year-season -- please report this")
  n2 <- nrow(dt) - uniqueN(dt, by = c("pixel_id", "Year", "Season"))
  reg2 <- if (isTRUE(NEAR_DUPLICATE_PIXELS)) .reg_parts(dt) else NULL
  dt <- panel_design_columns_R(dt, say = FALSE); dchk <- attr(dt, "design_check")                  # v20.59: the DiD columns, per block
  vpart <- panel_variation_R(dt)                                                                    # v20.59: the block's exact moments per outcome
  dt <- dt[, intersect(ctx$keep, names(dt)), with = FALSE]
  sites0 <- unique(dt$site_id[dt$site_id > 0 & dt$fragment == 0L])
  setorder(dt, Year, Season, site_id, pixel_id)
  out <- file.path(ctx$run_dir, sprintf("out_%06d.rds", k)); saveRDS(dt, out, compress = FALSE)
  list(rows = nrow(dt), dedup = dd, n_no = n_no, n2 = n2, reg2 = reg2, sites0 = sites0, sites = sort(unique(dt$site_id)), pixels = unique(dt$pixel_id),
       block = job$block, j = j, file = out, design = dchk, variation = vpart)
}

# ---------------------------------------------------------------- the pipeline block by block (run_prep's twin)
run_prep_ooc <- function(files, t0 = Sys.time(), why = "") {
  ch <- ooc_choose(); B <- ooc_budget(); cores <- ooc_cores()
  run_dir <- ooc_spill(sprintf("p00_%d_%s", Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%OS3"))); dir.create(run_dir, recursive = TRUE, showWarnings = FALSE)
  keep_parts <- identical(Sys.getenv("REWARD_OOC_KEEP_PARTS"), "1"); on.exit(if (!keep_parts) unlink(run_dir, recursive = TRUE), add = TRUE)
  info(sprintf("R_P00 OUT OF CORE: %s -- the %d export files are read one by one and the panel is built block by block (year x season), engines in order: %s%s",
               why, nrow(files), paste(OOC_LABEL[ch$engines], collapse = " -> "), if (length(ch$skipped)) paste0(" (not available: ", paste(ch$skipped, collapse = "; "), ")") else ""))
  info("reading ", nrow(files), " files (", N_THREADS, " threads)")
  big <- max(c(1, as.numeric(file.size(files$file))), na.rm = TRUE) * PREP_EXPANSION
  W1 <- max(1L, min(cores, floor(B / big), nrow(files)))
  ctx <- list(files = files, run_dir = run_dir, engines = ch$engines, W = W1, threads = max(1L, floor(cores / W1)))
  p1 <- ooc_map("p00_read", ctx, nrow(files))
  for (p in p1) if (!isTRUE(p$ok)) warn(p$warn)
  good <- Filter(function(p) isTRUE(p$ok), p1); n_bad <- length(p1) - length(good)
  nrow_all <- sum(vapply(good, function(p) as.numeric(p$rows), 0))
  if (!nrow_all) stop("no export could be read under ", ROOT)
  ok(sprintf("%s rows read from %d files%s", format(nrow_all, big.mark = ","), nrow(files) - n_bad, if (n_bad) sprintf(" (%d unreadable, see above)", n_bad) else ""))
  good <- Filter(function(p) p$rows > 0, good)
  ids <- sws_names()
  nm_tab <- unique(rbindlist(lapply(good, function(p) data.table(src_file = p$src_file, sws_file = p$sws_file))))[, .(files = .N), by = sws_file]
  info("sub-watershed named by the export files (>= 80 % rule): ", paste(sprintf("%s %d file(s)", fifelse(is.na(nm_tab$sws_file), "none", ids[as.character(nm_tab$sws_file)]), nm_tab$files), collapse = " | "))
  px <- unique(rbindlist(lapply(good, `[[`, "px")), by = c("pixel_id", "sws_export"))
  info("overlaying ", format(nrow(px), big.mark = ","), " pixel locations on the 20 sub-watersheds x rings")
  px <- overlay_sws(px)
  fwrite(px[, .N, by = .(site_id, site_check)][order(site_id)], file.path(OUTPUT_DIR, "site_tagging_by_sws.csv"))
  # the fragment codes of every file (file_codes: the file's majority sub-watershed), from its rows per pixel x file id
  pr <- rbindlist(lapply(good, function(p) p$pairs[, src_file := p$src_file]))
  pr <- merge(pr, px[, .(pixel_id, sws_export, site_id, site_check)], by = c("pixel_id", "sws_export"), all.x = TRUE)
  pr[, `:=`(sid = as.integer(fifelse(is.na(site_id), 0L, as.integer(site_id))), chk = as.integer(fifelse(is.na(site_check), 4L, as.integer(site_check))))]
  fc <- pr[, .(n = sum(N)), by = .(src_file, sid, chk)]
  maj <- fc[, { inp <- chk %in% IN_POLYGON
    if (!any(inp)) .(m = NA_integer_) else { tb <- .SD[inp, .(n = sum(n)), by = sid][order(sid)]; k <- which.max(tb$n)
      .(m = if (tb$n[k] > 0.5 * sum(tb$n)) as.integer(tb$sid[k]) else NA_integer_) } }, by = src_file]
  major <- setNames(maj$m, maj$src_file)
  fc[, m := major[src_file]]
  fc[, code := fifelse(is.na(m), 0L, fifelse(chk %in% IN_POLYGON & sid != m, 1L, fifelse(!(chk %in% IN_POLYGON) & sid != m, 2L, 0L)))]
  ft <- fc[, .(rows = sum(n), file_sws = if (is.na(m[1])) 0L else m[1], fragment_rows_other_sws = sum(n[code == 1L]), fragment_rows_outside_other_id = sum(n[code == 2L])), by = src_file]
  setorder(ft, src_file); fwrite(ft, file.path(OUTPUT_DIR, "site_tagging_by_file.csv"))
  if (any(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id > 0))
    info(sprintf("fragments of other sub-watersheds inside the export files: %s rows in %d file(s) (coded; FRAGMENT_RULE in the models drops them) -> site_tagging_by_file.csv",
                 format(sum(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id), big.mark = ","), sum(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id > 0)))
  # the near-duplicate pixels (the registry of every row, merged from the files)
  cmap <- if (isTRUE(NEAR_DUPLICATE_PIXELS)) near_dup_map_R(.reg_merge(lapply(good, `[[`, "reg")))
          else data.table(pixel_id = character(0), canonical_pixel_id = character(0), canonical_lat = numeric(0), canonical_lon = numeric(0), overlap = numeric(0))
  # the panel's columns and their types: those of rbindlist(fill = TRUE) over EVERY file, then the columns R_P00 adds
  tys <- list(); for (p in good) for (c_ in names(p$types)) tys[[c_]] <- max(tys[[c_]] %||% 0L, p$types[[c_]])
  all_cols <- unique(c(unlist(lapply(good, function(p) names(p$types))), "site_id", "ring_poly", "site_check", "sws_name", "fragment", PANEL_DESIGN_COLS))
  keep <- intersect(c("pixel_id", "site_id", "Year", "Season", "latitude", "longitude", "buff_km", "sws_export", "site_check", "sws_name",
                      "fragment", "SubwshedID", "Treat", PANEL_DESIGN_COLS, OUTCOME_VARS, WEATHER_VARS, DESCRIPTOR_VARS, EXTRA_VARS), all_cols)
  keep <- setdiff(keep, panel_columns_left_out_R())
  # PASS 2: the blocks (a block larger than one task's share of the RAM: in pixel groups)
  bl <- rbindlist(lapply(good, `[[`, "blocks"))[, .(N = sum(N)), by = .(Year, Season)][order(Year, Season)]
  bpr <- 8 * (length(tys) + 12) * 4
  bl[, J := pmax(1L, as.integer(ceiling(N * bpr / max(64 * 2^20, B / cores))))]
  env <- suppressWarnings(as.integer(Sys.getenv("REWARD_OOC_PARTITIONS", ""))); if (isTRUE(env > 1)) bl[, J := pmax(J, env)]   # the checks: every block in groups
  jobs <- bl[, .(j = seq_len(J) - 1L), by = .(Year, Season, J)][, block := sprintf("%d_%d", Year, Season)]
  W2 <- max(1L, min(cores, floor(B / max(1, max(bl$N / bl$J) * bpr)), nrow(jobs)))
  ctx2 <- list(run_dir = run_dir, engines = ch$engines, W = W2, threads = max(1L, floor(cores / W2)), jobs = jobs,
               px = px[, .(pixel_id, sws_export, site_id, ring_poly, site_check)], major = major, cmap = cmap, types = unlist(tys), keep = keep, ids = ids)
  p2 <- ooc_map("p00_block", ctx2, nrow(jobs))
  # the counts of the duplicates, the rows without an outcome, the confirmations -- summed over the blocks, said once (as in memory)
  dd <- lapply(p2, `[[`, "dedup"); g_ <- sum(vapply(dd, function(z) as.numeric(z$groups %||% 0), 0)); rm_ <- sum(vapply(dd, function(z) as.numeric(z$removed %||% 0), 0))
  n_fill <- sum(vapply(dd, function(z) as.numeric(z$filled %||% 0), 0)); n_unused <- sum(vapply(dd, function(z) as.numeric(z$not_used %||% 0), 0))
  bv <- unlist(lapply(dd, function(z) z$not_used_by_variable)); by_var <- if (length(bv)) tapply(bv, names(bv), sum) else integer(0)
  if (length(by_var)) by_var <- by_var[intersect(OUTCOME_VARS_CORE, names(by_var))]
  if (g_ > 0) ok(sprintf("%s rows shared a (sub-watershed, pixel, year, season) with another file (a pixel outside every polygon: the same pixel, year and season, whatever id the files gave it) -> %s kept (the %s file wins, then the more complete row)%s",
                         format(g_ + rm_, big.mark = ","), format(g_, big.mark = ","), if (DEDUP_PRIORITY == "complete") "more complete" else "newer",
                         if (isTRUE(DEDUP_FILL_FROM_DUPLICATES)) sprintf("; %s missing values FILLED from the dropped rows (DEDUP_FILL_FROM_DUPLICATES = TRUE)", format(n_fill, big.mark = ",")) else "; each kept AS IT IS, the repeated rows dropped whole"))
  if (n_unused) ok(sprintf("repeated rows DROPPED WHOLE: their %s value(s) where the kept row has a gap were NOT used (%s) -- DEDUP_FILL_FROM_DUPLICATES = FALSE (your rule). If your exports are SPLIT by variable (one file NDVI, another LAI of the same pixel-period), set DEDUP_FILL_FROM_DUPLICATES <- TRUE (lib/reward_prep.R) and re-run R_P00",
                           format(n_unused, big.mark = ","), paste(sprintf("%s %s", names(by_var), format(by_var, big.mark = ",")), collapse = ", ")))
  n_no <- sum(vapply(p2, function(p) as.numeric(p$n_no), 0))
  if (n_no > 0) info(sprintf("%s rows without any outcome left the panel (after the duplicates were resolved: a newer export's empty row is not replaced by an older repeated one)", format(n_no, big.mark = ",")))
  n2 <- sum(vapply(p2, function(p) as.numeric(p$n2), 0))
  if (n2) info(sprintf("%s pixel-year-season(s) lie in the polygons of TWO sub-watersheds (their zones overlap): kept once per sub-watershed -- the location rule of the models keeps each in its own sub-watershed only", format(n2, big.mark = ",")))
  rows <- sum(vapply(p2, function(p) as.numeric(p$rows), 0))
  if (isTRUE(NEAR_DUPLICATE_PIXELS)) {
    reg2 <- .reg_merge(lapply(p2, `[[`, "reg2")); left <- nrow(near_duplicate_pairs(reg2))
    (if (left) warn else ok)(sprintf("near-duplicate pixels CONFIRMED: %s pixel(s) remain whose footprints overlap >= %.0f %% among %s pixels%s", format(left, big.mark = ","),
                                     100 * PIXEL_OVERLAP_MIN, format(nrow(reg2), big.mark = ","), if (left) " (a chain the one-to-one merge cannot join) -- the models leave the smaller of each pair out (OVERLAP_ROWS)" else ""))
  }
  ok(sprintf("duplicates CONFIRMED removed: %s rows, every (sub-watershed, pixel, year, season) exactly once", format(rows, big.mark = ",")))
  panel_design_report_R(panel_design_merge_R(lapply(p2, `[[`, "design")))                       # v20.59: the blocks' design checks, said once
  panel_variation_report_R(lapply(p2, `[[`, "variation"))                                        # v20.59: the blocks' moments merged exactly
  n_sites <- length(unique(unlist(lapply(p2, `[[`, "sites0"))))
  info(sprintf("%d sub-watershed(s) in the panel after the fragment rule (the pooled design, POOLED_FE and the clusters are set by each model)", n_sites))
  ftab <- tryCatch(build_fund_tables(sort(unique(bl$Year)), out_dir = file.path(RESULTS_DIR, "FUND")), error = function(e) { warn("fund tables: ", conditionMessage(e)); NULL })
  if (!is.null(ftab)) print(ftab$timing[, .(site_id, sws_name, area_ha, first_month, amount_first_month, backcast_start, first_treated_label, cohort_annual)])
  bm <- if (!exists("PIPELINE_MODELS") || !length(PIPELINE_MODELS) || "M07" %in% PIPELINE_MODELS) bm_sws_means() else NULL   # v20.58: M07's input only
  w <- NULL; if (!is.null(bm)) { bm[, bm_var := paste0("BM_", variable)]; w <- dcast(bm, site_id + Year + Season ~ bm_var, value.var = "value") }
  # the blocks, one after another in the panel's order (year, season, sub-watershed, pixel); a block in pixel groups: sub-watershed by sub-watershed
  jobs[, k := .I]; out_path <- panel_file(); unlink(out_path); writer <- NULL; sink <- NULL; bal <- list(); pix_all <- character(0); sites_all <- integer(0)
  put <- function(x) {
    if (!is.null(w)) { x <- merge(x, w, by = c("site_id", "Year", "Season"), all.x = TRUE); setorder(x, Year, Season, site_id, pixel_id) }
    panel_plain_attrs(x)                                             # a block's key / dedup counts are not the panel's: never written into its metadata
    if (HAS_ARROW) {
      tb <- arrow::as_arrow_table(x)
      if (is.null(writer)) { sink <<- arrow::FileOutputStream$create(PANEL_PATH)
        writer <<- arrow::ParquetFileWriter$create(tb$schema, sink, properties = arrow::ParquetWriterProperties$create(names(tb), compression = "snappy")) }
      writer$WriteTable(tb, chunk_size = max(1L, nrow(tb)))
    } else fwrite(x, out_path, append = file.exists(out_path))
  }
  for (b in unique(jobs$block)) {
    ks <- jobs[block == b, k]
    if (length(ks) == 1L) { x <- readRDS(p2[[ks]]$file); put(x); rm(x) }
    else for (s in sort(unique(unlist(lapply(p2[ks], `[[`, "sites"))))) {
      x <- rbindlist(lapply(ks, function(k) { y <- readRDS(p2[[k]]$file); y[site_id == s] })); setorder(x, Year, Season, site_id, pixel_id); put(x); rm(x) }
    pxb <- unique(unlist(lapply(p2[ks], `[[`, "pixels"))); yb <- jobs[block == b, Year][1]; sb <- jobs[block == b, Season][1]
    bal[[length(bal) + 1L]] <- data.table(Year = yb, Season = sb, pixels = length(pxb)); pix_all <- unique(c(pix_all, pxb))
    sites_all <- unique(c(sites_all, unlist(lapply(p2[ks], `[[`, "sites")))); for (k in ks) unlink(p2[[k]]$file)
  }
  if (!is.null(writer)) { writer$Close(); sink$close() }
  if (!HAS_ARROW) info("arrow is not installed: the panel is written as ", panel_file(), " (install arrow: faster and smaller)")
  fwrite(data.table(setting = c("engine_policy", "dedup_priority", "dedup_fill_from_duplicates", "dedup_values_filled", "dedup_values_not_used",
                                "near_duplicate_pixels", "pixel_overlap_min", "written"),
                    value = c("v20.58", DEDUP_PRIORITY, as.character(isTRUE(DEDUP_FILL_FROM_DUPLICATES)), as.character(n_fill),
                              as.character(n_unused), as.character(isTRUE(NEAR_DUPLICATE_PIXELS)), as.character(PIXEL_OVERLAP_MIN),
                              format(Sys.time(), "%Y-%m-%d %H:%M:%S"))), file.path(OUTPUT_DIR, "panel_build_settings_R.csv"))
  bal <- rbindlist(bal)[order(Year, Season)]
  fwrite(bal, file.path(OUTPUT_DIR, "panel_balance_by_block.csv"))
  ok(sprintf("panel: %s rows, %s pixels, %d sub-watershed(s), %d year-seasons (pixels per year-season %s-%s: an unbalanced panel is kept as it is; a missing pixel-period leaves only the estimations that need it) -> %s (%.1f min, block by block: %s)",
             format(rows, big.mark = ","), format(length(pix_all), big.mark = ","), length(unique(sites_all[sites_all > 0])), nrow(bal), min(bal$pixels), max(bal$pixels),
             PANEL_PATH, as.numeric(difftime(Sys.time(), t0, units = "mins")), paste(.OOC$trace, collapse = "; ")))
  invisible(NULL)
}

# ---------------------------------------------------------------- the outcome screen of R_P00 (every outcome's usable years), out of core when needed
outcome_screen_R <- function(outcomes = OUTCOMES, d = load_design()) {
  big <- !is.null(ooc_forced()) || isTRUE(ooc_need_bytes(DESIGN_OUTCOME, d) > ram_budget_bytes())
  rbindlist(lapply(outcomes, function(o) tryCatch({
    if (big) {
      plan <- ooc_plan(length(load_columns_R(o, d)$need)); S <- ooc_load_R(o, d, plan, ooc_choose()$engines); on.exit(unlink(S$run_dir, recursive = TRUE), add = TRUE)
      data.table(outcome = o, status = "usable", years = paste(S$years_set, collapse = ","))
    } else { x <- load_panel_R(o, d); data.table(outcome = o, status = "usable", years = paste(sort(unique(x$Year)), collapse = ",")) }
  }, error = function(e) data.table(outcome = o, status = "NOT usable", years = conditionMessage(e)))))
}
