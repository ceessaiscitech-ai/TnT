# reward_outofcore.R -- v20.58: M01, M02, M16 and M34 in R BEYOND 98 % OF THE RAM -- OUT OF CORE, EXACT, NEVER SAMPLED
# (the R twin of python/_outofcore.py + _ooc_models.py; the same four models in the full pipeline and in the four-model pipeline)
#
# Below 98 % of the RAM nothing changes: every row is in RAM at once (load_panel_R), one regression, no chunking. Beyond it -- and only
# then -- these four models do not stop and are never sampled: the run goes OUT OF CORE.
#   1  The panel is split into PIXEL PARTITIONS: every row of a pixel (all its years, seasons and rings) in one partition, by a hash of
#      pixel_id, streamed from the parquet file batch by batch (never whole in RAM). The split is kept next to the panel for the next
#      model / outcome (the same panel = the same split; a new panel replaces it).
#   2  Every partition runs the SAME R code as load_panel_R (load_rows_R: the location rule, gap-filled rows, the year window, the
#      seasons, the annual covariate fill, the finite values; design_columns: the timing in force). Only ADDITIVE facts cross between
#      partitions: counts, sums, the outcome screen's moments, the integrity facts, the design SE's cells.
#   3  The two-way fixed-effects regressions are solved EXACTLY from per-partition cross-products: the unit (pixel x season) effects are
#      removed inside each partition, the period effects jointly (Frisch-Waugh-Lovell and the Schur complement of the period block),
#      the CR1 sandwich from per-cluster score sums, with fixest's own small-sample rule (fixef.K "nested", G / (G - 1), t with G - 1 df).
#      tests/run_all_tests.R scenario H: in memory == out of core, and every engine gives the same numbers.
# The partition tasks run on the first available engine of OUT_OF_CORE (lib/reward_paths.R), in that order:
#   "dask"     Dask (Python): a LocalCluster runs the partition tasks (Rscript lib/reward_ooc_task.R) on every core
#   "spark"    Apache Spark (pyspark, local[cores]; needs Java 17+): the same tasks as Spark tasks
#   "batches"  R itself: one partition after another in this session (always available -- the last resort)
# An engine that is not installed is named with the reason and the next one is used. REWARD_FORCE_OUT_OF_CORE = dask | spark | batches |
# auto runs this path on data that would fit (the checks); REWARD_OOC_PARTITIONS sets the number of partitions (the checks).
suppressPackageStartupMessages(library(data.table))
OOC_MODELS_R <- c("M01", "M02", "M16", "M34")
OOC_ENGINES  <- c("dask", "spark", "batches")
OOC_LABEL    <- c(dask = "Dask", spark = "Apache Spark", batches = "R batches")
OOC_COPIES_R <- 4                     # working copies of a sample the in-memory path holds at its peak (filters, fixest's demeaned matrices)
if (!exists(".OOC") || !is.environment(.OOC)) .OOC <- new.env()           # this session's engines, their status and the split in use
`%||%` <- function(a, b) if (is.null(a) || !length(a)) b else a

# ================================================================ configuration
ooc_forced <- function() {
  v <- tolower(trimws(Sys.getenv("REWARD_FORCE_OUT_OF_CORE", "")))
  if (!nzchar(v) || v %in% c("0", "false", "no", "off")) return(NULL)
  if (v %in% OOC_ENGINES) v else "auto"
}
ooc_order <- function() {                                              # YOUR order (OUT_OF_CORE); the R batches always last
  o <- tolower(trimws(as.character(get0("OUT_OF_CORE", ifnotfound = OOC_ENGINES))))
  o <- o[o %in% OOC_ENGINES]; if (!length(o)) o <- OOC_ENGINES
  if (!"batches" %in% o) o <- c(o, "batches")
  f <- ooc_forced(); if (!is.null(f) && f %in% OOC_ENGINES) o <- c(f, setdiff(o, f))
  unique(o)
}
ooc_spill <- function(sub = "") {
  base <- get0("OUT_OF_CORE_SPILL_DIR", ifnotfound = "")
  if (!length(base) || !nzchar(base %||% "")) base <- file.path(dirname(PANEL_PATH), "_out_of_core_R")
  d <- if (nzchar(sub)) file.path(base, sub) else base
  dir.create(d, recursive = TRUE, showWarnings = FALSE); normalizePath(d, winslash = "/", mustWork = FALSE)
}
ooc_hash <- function(s) { f <- tempfile(); on.exit(unlink(f)); writeLines(paste(s, collapse = "\n"), f); substr(unname(tools::md5sum(f)), 1, 12) }
ooc_cores <- function() { n <- max(1L, as.integer(get0("N_THREADS", ifnotfound = parallel::detectCores()))); if (exists("pool_cap_R", mode = "function")) pool_cap_R(n) else n }   # 3 Oct: worker PROCESSES capped at 60 on Windows
ooc_budget <- function() { b <- ram_budget_bytes(); if (!is.finite(b) || b <= 0) 4e9 else b }
ooc_rscript <- function() { b <- R.home("bin"); f <- file.path(b, if (.Platform$OS.type == "windows") "Rscript.exe" else "Rscript"); if (file.exists(f)) f else "Rscript" }
ooc_helper <- function() file.path(R_HOME_DIR, "lib", "reward_ooc_engine.py")

# Python 3 for Dask / Spark: PYTHON_EXE (reward_paths.R), REWARD_PYTHON, python3 / python / py -3 on the PATH, then the usual Anaconda /
# Miniconda / Miniforge folders -- the first one that has dask or pyspark (else the first Python 3: the status table then says what is missing)
ooc_python <- function() {
  if (!is.null(.OOC$python)) return(.OOC$python)
  cand <- list(); add <- function(exe, args = character(0)) if (length(exe) && nzchar(exe) && (exe %in% c("py", "python", "python3") || file.exists(exe) || nzchar(Sys.which(exe))))
    cand[[length(cand) + 1L]] <<- list(exe = unname(exe), args = args)
  add(get0("PYTHON_EXE", ifnotfound = "")); add(Sys.getenv("REWARD_PYTHON")); add(Sys.which("python3")); add(Sys.which("python"))
  if (.Platform$OS.type == "windows") add(Sys.which("py"), "-3")
  ev <- Sys.getenv(c("USERPROFILE", "LOCALAPPDATA", "ProgramData", "HOME")); ev <- ev[nzchar(ev)]
  for (b in c(as.vector(outer(ev, c("anaconda3", "Anaconda3", "miniconda3", "Miniconda3", "miniforge3"), file.path)), "C:/anaconda3", "C:/ProgramData/anaconda3"))
    for (f in c(file.path(b, "python.exe"), file.path(b, "bin", "python"))) if (file.exists(f)) add(f)
  first <- NULL
  for (p in cand) {
    o <- tryCatch(suppressWarnings(system2(p$exe, c(p$args, "-c", shQuote("import sys, importlib.util as u; print(sys.version_info[0], int(bool(u.find_spec('dask'))), int(bool(u.find_spec('pyspark'))))")),
                                           stdout = TRUE, stderr = TRUE)), error = function(e) "")
    v <- strsplit(trimws(tail(o, 1)), " +")[[1]]
    if (length(v) == 3 && v[1] == "3") { if (is.null(first)) first <- p; if (v[2] == "1" || v[3] == "1") { .OOC$python <- p; return(p) } }
  }
  .OOC$python <- first %||% list(exe = "", args = character(0)); .OOC$python
}
# the engines on this machine: (available, detail) -- the helper answers for Dask and Spark
ooc_engine_status <- function(refresh = FALSE) {
  if (!refresh && !is.null(.OOC$status)) return(.OOC$status)
  st <- list(batches = list(ok = TRUE, detail = "R itself: one partition after another in this session (always available)"))
  py <- ooc_python()
  if (!nzchar(py$exe)) {
    st$dask <- st$spark <- list(ok = FALSE, detail = "no Python 3 found (set PYTHON_EXE in lib/reward_paths.R, or put python on the PATH)")
  } else if (!file.exists(ooc_helper())) {
    st$dask <- st$spark <- list(ok = FALSE, detail = paste("the helper", ooc_helper(), "is missing"))
  } else {
    f <- tempfile(fileext = ".json")
    o <- tryCatch(suppressWarnings(system2(py$exe, c(py$args, shQuote(ooc_helper()), "--status", shQuote(f)), stdout = TRUE, stderr = TRUE)), error = function(e) conditionMessage(e))
    j <- tryCatch(if (file.exists(f)) jsonlite::fromJSON(f, simplifyVector = FALSE) else NULL, error = function(e) NULL)
    for (e in c("dask", "spark")) st[[e]] <- if (!is.null(j[[e]])) list(ok = isTRUE(j[[e]]$ok), detail = as.character(j[[e]]$detail))
                                            else list(ok = FALSE, detail = paste("the helper did not answer:", substr(paste(o, collapse = " "), 1, 160)))
    unlink(f)
  }
  .OOC$status <- st; st
}
ooc_status_table <- function(verbose = TRUE) {                          # 00_SETUP.R / the notebooks print it
  st <- ooc_engine_status(); o <- ooc_order()
  tab <- data.table(engine = OOC_ENGINES, order = match(OOC_ENGINES, o), available = vapply(OOC_ENGINES, function(e) isTRUE(st[[e]]$ok), TRUE),
                    detail = vapply(OOC_ENGINES, function(e) st[[e]]$detail %||% "", ""))
  if (verbose) { info("out-of-core engines of the R pipeline (used only beyond 98 % of the RAM, in this order: ", paste(o, collapse = " -> "), "):"); print(tab[order(order)]) }
  invisible(tab)
}
ooc_choose <- function() {                                               # the engines to try, in order (the first available first)
  st <- ooc_engine_status(); o <- ooc_order(); skipped <- character(0); ok_ <- character(0)
  for (e in o) if (isTRUE(st[[e]]$ok)) ok_ <- c(ok_, e) else skipped <- c(skipped, sprintf("%s: %s", OOC_LABEL[[e]], st[[e]]$detail))
  list(engines = unique(c(ok_, "batches")), skipped = skipped)
}

# ================================================================ when: the 98 % rule (and the checks' switch)
panel_rows_R <- function() {
  if (HAS_ARROW && file.exists(PANEL_PATH)) return(as.numeric(tryCatch(nrow(arrow::open_dataset(PANEL_PATH)), error = function(e) NA_real_)))
  f <- panel_file(); if (!file.exists(f)) return(0)
  as.numeric(file.size(f)) / 120                                         # a CSV panel: ~120 bytes per row (an estimate)
}
ooc_need_bytes <- function(outcome, d) {                                 # what load_panel_R + the model would hold at their peak
  cols <- tryCatch(load_columns_R(outcome, d)$need, error = function(e) character(12))
  panel_rows_R() * 8 * (length(cols) + 16) * OOC_COPIES_R                # the read columns + the design columns (treat ... dose,
}                                                                        #   unit / period / cluster_id), x the working copies
run_mode_R <- function(model, outcome, d = load_design()) {
  if (!model %in% OOC_MODELS_R) return(list(mode = "memory", why = "in memory (this model has no out-of-core path)"))
  f <- ooc_forced()
  if (!is.null(f)) return(list(mode = "out_of_core", why = sprintf("REWARD_FORCE_OUT_OF_CORE = %s (the checks: the out-of-core path on data that would fit)", f)))
  need <- ooc_need_bytes(outcome, d); b <- ram_budget_bytes()
  if (is.finite(b) && is.finite(need) && need > b)
    return(list(mode = "out_of_core", why = sprintf("the sample needs ~%.2f GB in RAM and %.2f GB are free below 98 %% -- out of core instead (exact, never sampled)", need / 1e9, b / 1e9)))
  list(mode = "memory", why = sprintf("in memory: ~%.2f GB of %.2f GB free below 98 %%", need / 1e9, if (is.finite(b)) b / 1e9 else NA_real_))
}

# ================================================================ 1. the pixel partitions (streamed; kept for the next model / outcome)
ooc_part_of <- function(pid, K) {                                        # every row of a pixel -> the same partition
  if (is.numeric(pid)) return(as.integer(floor(abs(pid) * 0.6180339887498949 * 2654435761) %% K))
  pid <- as.character(pid); k <- regexpr("_", pid, fixed = TRUE)
  a <- suppressWarnings(as.numeric(substr(pid, 1L, k - 1L))); b <- suppressWarnings(as.numeric(substring(pid, k + 1L)))
  bad <- k < 1L | !is.finite(a) | !is.finite(b)
  out <- (a * 7919 + b) %% K
  if (any(bad)) {                                                        # another id form: its digits and length (deterministic)
    dg <- suppressWarnings(as.numeric(substr(gsub("[^0-9]", "", pid[bad]), 1L, 12L))); dg[!is.finite(dg)] <- 0
    out[bad] <- (dg * 31 + nchar(pid[bad])) %% K
  }
  as.integer(out)
}
ooc_plan <- function(ncols_task = 20L) {
  # K: the partitions hold EVERY column of the panel (one split per panel, reused by every model, outcome and the design from the data);
  # a task holds ncols_task of them with its working copies. W: the tasks that fit side by side below 98 %.
  rows <- panel_rows_R(); ncol_all <- length(panel_names())
  bpr_all <- 8 * (ncol_all + 16) * OOC_COPIES_R; bpr <- 8 * (ncols_task + 16) * OOC_COPIES_R; B <- ooc_budget(); W <- ooc_cores()
  per_task <- max(64 * 2^20, B / W); rows_per <- max(20000, floor(per_task / bpr_all))
  K <- max(1L, as.integer(ceiling(rows / rows_per)))
  env <- suppressWarnings(as.integer(Sys.getenv("REWARD_OOC_PARTITIONS", "")))
  if (isTRUE(env > 0)) K <- env else { if (!is.null(ooc_forced())) K <- max(K, 4L); K <- as.integer(2^ceiling(log2(K))) }   # a power of 2: reused
  list(K = K, rows = rows, bytes_per_row = bpr, budget = B, W = W, rows_per_part = ceiling(rows / K))
}
ooc_split <- function(K, verbose = TRUE) {
  key <- c(panel_identity(), as.character(K), "v20.58")
  root <- ooc_spill(); h <- ooc_hash(key); dir <- file.path(root, paste0("panel_", h)); man <- file.path(dir, "manifest.rds")
  m <- tryCatch(if (file.exists(man)) readRDS(man) else NULL, error = function(e) NULL)
  if (!is.null(m) && identical(m$key, key) && all(file.exists(m$files))) {
    if (verbose) info(sprintf("out of core: the pixel partitions of this panel are reused (%d partitions, %s rows) -- %s", K, format(sum(m$rows), big.mark = ","), dir))
    return(m)
  }
  for (old in list.dirs(root, recursive = FALSE)) if (startsWith(basename(old), "panel_") && basename(old) != basename(dir)) {   # another panel's split
    mo <- tryCatch(readRDS(file.path(old, "manifest.rds")), error = function(e) NULL)
    if (is.null(mo) || !identical(mo$key[1], panel_identity())) unlink(old, recursive = TRUE)
  }
  unlink(dir, recursive = TRUE); dir.create(dir, recursive = TRUE); t0 <- Sys.time()
  counts <- numeric(K); files <- character(K)
  if (HAS_ARROW && file.exists(PANEL_PATH)) {
    ds <- arrow::open_dataset(PANEL_PATH); cols <- names(ds)
    sb <- ds$NewScan(); invisible(sb$Project(cols)); invisible(sb$BatchSize(262144L)); rdr <- sb$Finish()$ToRecordBatchReader()
    files <- file.path(dir, sprintf("part_%04d.parquet", seq_len(K) - 1L)); writers <- vector("list", K); sinks <- vector("list", K)
    buf <- vector("list", K); nbuf <- integer(K); FLUSH <- 400000L; tmpl <- NULL
    flush <- function(p) {
      if (!length(buf[[p]])) return(invisible())
      tb <- if (length(buf[[p]]) == 1L) buf[[p]][[1]] else do.call(arrow::concat_tables, buf[[p]])
      if (is.null(writers[[p]])) { sinks[[p]] <<- arrow::FileOutputStream$create(files[p])
        writers[[p]] <<- arrow::ParquetFileWriter$create(tb$schema, sinks[[p]], properties = arrow::ParquetWriterProperties$create(names(tb), compression = "snappy")) }
      writers[[p]]$WriteTable(tb, chunk_size = max(1L, nrow(tb))); buf[[p]] <<- list(); nbuf[p] <<- 0L
    }
    while (!is.null(b <- rdr$read_next_batch())) {
      if (is.null(tmpl)) tmpl <- arrow::as_arrow_table(b[integer(0), ])
      if (!b$num_rows) next
      part <- ooc_part_of(as.vector(b$pixel_id), K) + 1L
      for (p in unique(part)) { idx <- which(part == p); tb <- arrow::as_arrow_table(b[idx, ])
        buf[[p]][[length(buf[[p]]) + 1L]] <- tb; nbuf[p] <- nbuf[p] + length(idx); counts[p] <- counts[p] + length(idx)
        if (nbuf[p] >= FLUSH) flush(p) }
    }
    for (p in seq_len(K)) { flush(p)
      if (is.null(writers[[p]])) {                                       # an empty partition: an empty file with the panel's schema
        if (is.null(tmpl)) stop("the panel has no rows"); arrow::write_parquet(tmpl, files[p]) }
      else { writers[[p]]$Close(); sinks[[p]]$close() } }
    fmt <- "parquet"
  } else {                                                               # a CSV panel (arrow not installed): chunks of rows
    f <- panel_file(); hdr <- names(fread(f, nrows = 0)); files <- file.path(dir, sprintf("part_%04d.csv", seq_len(K) - 1L)); skip <- 1L; CH <- 1000000L
    chr <- intersect(c("pixel_id", "unit", "period", "sws_name"), hdr)
    repeat {
      x <- tryCatch(fread(f, skip = skip, nrows = CH, header = FALSE, col.names = hdr, colClasses = list(character = chr)), error = function(e) NULL)
      if (is.null(x) || !nrow(x)) break
      part <- ooc_part_of(x$pixel_id, K) + 1L
      for (p in unique(part)) { y <- x[part == p]; fwrite(y, files[p], append = file.exists(files[p])); counts[p] <- counts[p] + nrow(y) }
      skip <- skip + nrow(x); if (nrow(x) < CH) break
    }
    for (p in seq_len(K)) if (!file.exists(files[p])) fwrite(fread(f, nrows = 0, colClasses = list(character = chr)), files[p])
    fmt <- "csv"
  }
  m <- list(key = key, K = K, files = normalizePath(files, winslash = "/"), rows = counts, format = fmt, dir = normalizePath(dir, winslash = "/"),
            seconds = as.numeric(difftime(Sys.time(), t0, units = "secs")))
  saveRDS(m, man)
  if (verbose) info(sprintf("out of core: the panel split into %d pixel partitions (%s rows; %s-%s rows each; %.0f s) -- kept for the next model / outcome: %s",
                            K, format(sum(counts), big.mark = ","), format(min(counts), big.mark = ","), format(max(counts), big.mark = ","), m$seconds, dir))
  m
}
ooc_read_part <- function(ctx, k, cols = NULL) {
  f <- ctx$parts[k]
  if (grepl("\\.parquet$", f)) {
    x <- if (is.null(cols)) arrow::read_parquet(f) else arrow::read_parquet(f, col_select = tidyselect::all_of(intersect(cols, ctx$part_cols)))
    return(as.data.table(x))
  }
  sel <- if (is.null(cols)) NULL else intersect(cols, ctx$part_cols)
  fread(f, select = sel, colClasses = list(character = intersect(c("pixel_id", "unit", "period", "sws_name"), ctx$part_cols)))
}

# ================================================================ 2. the engines: the same task function everywhere
ooc_task_run <- function(task, ctx, k) {                                 # in this session (batches) or in a worker's R (reward_ooc_task.R)
  fn <- switch(task, prep = ooc_task_prep, presel = ooc_task_presel, balcells = ooc_task_balcells, sample = ooc_task_sample, gram = ooc_task_gram, scores = ooc_task_scores, recommend = ooc_task_recommend,
               p00_read = ooc_task_p00_read, p00_block = ooc_task_p00_block, stop("unknown out-of-core task ", task))
  fn(ctx, k)
}
ooc_globals <- function() {                                              # the settings a worker's R needs (every UPPER-CASE value of this session)
  nm <- ls(globalenv(), all.names = FALSE); nm <- nm[grepl("^[A-Z][A-Z0-9_]*$", nm)]
  out <- list()
  for (k in nm) { v <- get(k, envir = globalenv()); if (is.function(v) || is.environment(v)) next
    if (is.atomic(v) || (is.list(v) && !is.data.frame(v))) if (as.numeric(utils::object.size(v)) < 2e6) out[[k]] <- v }
  out
}
ooc_map <- function(task, ctx, n) {
  ctx$task <- task; ctx$globals <- ooc_globals(); ctx$R_HOME_DIR <- R_HOME_DIR
  cf <- file.path(ctx$run_dir, sprintf("ctx_%s_%d.rds", task, as.integer(.OOC$ctx_n <- (.OOC$ctx_n %||% 0L) + 1L)))
  saveRDS(ctx, cf); t0 <- Sys.time()
  for (e in ctx$engines) {
    if (e == "batches") {
      res <- lapply(seq_len(n), function(k) ooc_task_run(task, ctx, k))
      .OOC$last_engine <- "batches"; .OOC$trace <- c(.OOC$trace, sprintf("%s: %d tasks on R batches in %.1f s", task, n, as.numeric(difftime(Sys.time(), t0, units = "secs"))))
      return(res)
    }
    r <- tryCatch(ooc_remote(e, task, cf, n, ctx), error = function(err) err)
    if (!inherits(r, "error")) {
      .OOC$last_engine <- e; .OOC$trace <- c(.OOC$trace, sprintf("%s: %d tasks on %s in %.1f s", task, n, OOC_LABEL[[e]], as.numeric(difftime(Sys.time(), t0, units = "secs"))))
      return(r)
    }
    if (inherits(r, "ooc_task_error")) stop(conditionMessage(r), call. = FALSE)   # the R code of a partition failed: the same on every engine
    warn(sprintf("out of core: %s could not run '%s' (%s) -- the next engine takes over", OOC_LABEL[[e]], task, substr(conditionMessage(r), 1, 300)))
    ctx$engines <- setdiff(ctx$engines, e)
  }
  stop("no out-of-core engine could run '", task, "'")
}
# Dask / Spark: the helper (lib/reward_ooc_engine.py) runs as a server for this session; each job = the partition tasks, each task its
# own R process (Rscript lib/reward_ooc_task.R ctx task k out)
ooc_server <- function(e, W) {
  key <- paste(e, W); s <- .OOC$servers[[key]]
  if (!is.null(s) && file.exists(file.path(s$dir, "ready.json")) && !file.exists(file.path(s$dir, "exited.json"))) return(s)
  for (k in names(.OOC$servers)) if (startsWith(k, paste0(e, " "))) ooc_server_stop(k)
  dir <- ooc_spill(sprintf("engine_%d_%s_%d", Sys.getpid(), e, W)); unlink(list.files(dir, full.names = TRUE), recursive = TRUE)
  py <- ooc_python(); if (!nzchar(py$exe)) stop("no Python 3")
  log <- file.path(dir, "server.log")
  args <- c(py$args, shQuote(ooc_helper()), "--serve", shQuote(dir), "--engine", e, "--workers", W, "--parent", Sys.getpid(),
            "--memory", sprintf("%.0f", ooc_budget() / W), "--spill", shQuote(ooc_spill(paste0(e, "_spill"))), "--log", shQuote(log))
  system2(py$exe, args, stdout = FALSE, stderr = FALSE, wait = FALSE)
  t0 <- Sys.time()
  repeat {
    if (file.exists(file.path(dir, "ready.json"))) break
    if (file.exists(file.path(dir, "failed.json"))) stop(paste(readLines(file.path(dir, "failed.json"), warn = FALSE), collapse = " "))
    if (as.numeric(difftime(Sys.time(), t0, units = "secs")) > 240) stop("the ", OOC_LABEL[[e]], " engine did not start within 240 s (", log, ")")
    Sys.sleep(0.2)
  }
  s <- list(dir = dir, engine = e, W = W); if (is.null(.OOC$servers)) .OOC$servers <- list(); .OOC$servers[[key]] <- s
  info(sprintf("out of core: %s started with %d worker(s) for this session (%s)", OOC_LABEL[[e]], W, dir))
  s
}
ooc_server_stop <- function(key) {
  s <- .OOC$servers[[key]]; if (is.null(s)) return(invisible())
  try(writeLines("stop", file.path(s$dir, "stop")), silent = TRUE); .OOC$servers[[key]] <- NULL; invisible()
}
ooc_stop_all <- function() for (k in names(.OOC$servers)) ooc_server_stop(k)
ooc_remote <- function(e, task, cf, n, ctx) {
  W <- max(1L, min(as.integer(ctx$W), n)); s <- ooc_server(e, W)
  outs <- file.path(ctx$run_dir, sprintf("out_%s_%04d.rds", task, seq_len(n))); unlink(outs)
  rs <- ooc_rscript(); ts <- file.path(R_HOME_DIR, "lib", "reward_ooc_task.R")
  job <- list(items = lapply(seq_len(n), function(k) list(id = k, cmd = c(rs, "--vanilla", ts, cf, task, as.character(k), outs[k]))))
  .OOC$job_n <- (.OOC$job_n %||% 0L) + 1L; jid <- sprintf("job_%06d", .OOC$job_n)
  tmp <- file.path(s$dir, paste0(jid, ".tmp")); jsonlite::write_json(job, tmp, auto_unbox = TRUE, digits = NA); file.rename(tmp, file.path(s$dir, paste0(jid, ".json")))
  done <- file.path(s$dir, paste0(jid, ".done.json")); t0 <- Sys.time()
  repeat {
    if (file.exists(done)) break
    if (file.exists(file.path(s$dir, "exited.json"))) stop("the ", OOC_LABEL[[e]], " engine stopped: ", paste(readLines(file.path(s$dir, "exited.json"), warn = FALSE), collapse = " "))
    hb <- file.path(s$dir, "alive"); if (file.exists(hb) && as.numeric(difftime(Sys.time(), file.mtime(hb), units = "secs")) > 300) {
      .OOC$servers[[paste(e, W)]] <- NULL; stop("the ", OOC_LABEL[[e]], " engine stopped answering (no heartbeat for 5 min; ", file.path(s$dir, "server.log"), ")") }
    Sys.sleep(if (as.numeric(difftime(Sys.time(), t0, units = "secs")) < 5) 0.05 else 0.25)
  }
  r <- jsonlite::fromJSON(done, simplifyVector = FALSE); unlink(done)
  if (!isTRUE(r$ok)) stop(r$error %||% "the engine failed")
  res <- vector("list", n)
  for (k in seq_len(n)) {
    o <- tryCatch(readRDS(outs[k]), error = function(err) NULL)
    if (is.null(o)) {                                                   # the task's R process died (e.g. killed): an engine failure
      it <- r$items[[k]]; stop(sprintf("task %d of '%s' ended without a result (exit %s): %s", k, task, it$rc %||% "?", substr(paste(it$err %||% "", collapse = " "), 1, 400)))
    }
    if (!isTRUE(o$ok)) { err <- simpleError(sprintf("out of core (%s), partition %d of '%s': %s", OOC_LABEL[[e]], k, task, o$error)); class(err) <- c("ooc_task_error", class(err)); stop(err) }
    res[[k]] <- o$result
  }
  unlink(outs); res
}
reg.finalizer(.OOC, function(env) try(ooc_stop_all(), silent = TRUE), onexit = TRUE)

# ================================================================ 3. the partition tasks
# PREP (phase A): the row rules of load_panel_R on the partition (the annual fill reads the partition's every ring), and the facts the
# parent merges: the location report, the counts it says, the outcome screen's moments per year x season, the rows per site x year x season
ooc_task_prep <- function(ctx, k) {
  x_all <- ooc_read_part(ctx, k, unique(c(ctx$need, "pixel_id", "Year", "Season", ctx$covs)))
  rings <- ctx$d$control_rings
  x <- x_all[buff_km == 0 | buff_km %in% rings, intersect(ctx$need, names(x_all)), with = FALSE]
  r <- load_rows_R(x, ctx$outcome, ctx$d, ctx$covs, ctx$loc, ctx$S, fill_src = function(need2) x_all[, c("pixel_id", "Year", "Season", need2), with = FALSE],
                   say = FALSE, fill_force = ctx$fill_force)
  x <- r$x; o <- ctx$outcome
  scr <- if (nrow(x)) x[, { v <- get(o); mu <- mean(v); .(n = .N, mean = mu, m2 = sum((v - mu)^2), min = min(v), max = max(v), n_treated = sum(buff_km == 0), n_control = sum(buff_km > 0)) }, by = .(Year, Season)]   # v20.59: + min, max
         else data.table(Year = integer(0), Season = integer(0), n = integer(0), mean = numeric(0), m2 = numeric(0), min = numeric(0), max = numeric(0), n_treated = integer(0), n_control = integer(0))
  cnt <- if ("site_id" %in% names(x)) x[, .N, by = .(site_id, Year, Season)] else x[, .(site_id = 0L, N = .N), by = .(Year, Season)]
  saveRDS(x, file.path(ctx$run_dir, sprintf("a_%04d.rds", k)), compress = FALSE)
  r$x <- NULL; c(r, list(screen = scr, counts = cnt, cols = names(x)))
}
# SAMPLE (phase B): the screen's year-seasons out, the design columns of the timing in force, the final sample written; the facts of the
# sample (integrity, the result row's facts, the design SE's cells, what M02 / M16 need to know)
ooc_task_presel <- function(ctx, k) {                                    # v20.59: one partition's pre-period facts for CONTROL_SELECTION
  a <- file.path(ctx$run_dir, sprintf("a_%04d.rds", k)); x <- readRDS(a)
  if (nrow(ctx$bad)) x <- x[!ctx$bad, on = .(Year, Season)]
  x <- design_columns(x, ctx$d, site_period = ctx$site_period, say = FALSE)
  x <- donut_rule_R(x, ctx$d, say = FALSE); x <- landuse_rule_R(x, ctx$d, say = FALSE); x <- baseline_ndvi_rule_R(x, ctx$d, say = FALSE)   # spec 1
  control_selection_facts_R(x, ctx$outcome, ctx$d)
}
ooc_task_balcells <- function(ctx, k) {                                  # 4 Oct: one partition's (sub-watershed, year-season) cells of the variable
  a <- file.path(ctx$run_dir, sprintf("a_%04d.rds", k)); x <- readRDS(a); o <- ctx$outcome
  if (nrow(ctx$bad)) x <- x[!ctx$bad, on = .(Year, Season)]
  x <- design_columns(x, ctx$d, site_period = ctx$site_period, say = FALSE)
  x <- donut_rule_R(x, ctx$d, say = FALSE); x <- landuse_rule_R(x, ctx$d, say = FALSE); x <- baseline_ndvi_rule_R(x, ctx$d, say = FALSE)
  x <- select_controls_R(x, o, ctx$d, sel = ctx$ctrl_sel, say = FALSE)
  x <- same_pixels_R(x, o, ctx$d, say = FALSE)
  balance_cells_R(x, o)
}
ooc_task_sample <- function(ctx, k) {
  a <- file.path(ctx$run_dir, sprintf("a_%04d.rds", k)); x <- readRDS(a); o <- ctx$outcome
  if (nrow(ctx$bad)) x <- x[!ctx$bad, on = .(Year, Season)]
  x <- design_columns(x, ctx$d, site_period = ctx$site_period, say = FALSE)
  x <- donut_rule_R(x, ctx$d, say = FALSE); x <- landuse_rule_R(x, ctx$d, say = FALSE); x <- baseline_ndvi_rule_R(x, ctx$d, say = FALSE)   # spec 1
  x <- select_controls_R(x, o, ctx$d, sel = ctx$ctrl_sel, say = FALSE)     # v20.59: the parent's decision applied (the same pixels in every partition)
  x <- same_pixels_R(x, o, ctx$d, say = FALSE); spo <- attr(x, "same_pixels")   # v20.59: SAME_PIXELS per partition (a pixel's rows are all here), summed by the parent
  x <- balanced_panel_R(x, o, ctx$d, cells = ctx$bal_cells, say = FALSE); bpo <- attr(x, "balanced_panel")   # 4 Oct: against the WHOLE sample's cells (the parent's first pass)
  if (identical(ctx$d$cluster, "block")) x[, block_id := block_ids_R(x, ctx$d$control_block_deg %||% 0.01)]   # v20.59
  n_tr <- attr(x, "n_transition_left_out") %||% 0L
  pvp <- attr(x, "post_vs_panel")                                       # v20.59: read BEFORE the column subset below (a subset drops the attributes)
  keep <- intersect(c("pixel_id", "site_id", "Year", "Season", "buff_km", "site_check", o, ctx$covs, "treat", "post", "did", "event_time", "unit", "period", "block_id"), names(x))
  x <- x[, ..keep]
  saveRDS(x, file.path(ctx$run_dir, sprintf("s_%04d.rds", k)), compress = FALSE); unlink(a)
  cells <- function(pos) {                                               # the design SE's cells (design_se / design_se_event): unit-demeaned
    d_ <- if (pos) x[site_id > 0L] else x                                #   outcome per site x year x season x group, post per cell
    d_ <- d_[, .(site_id, Year, Season, treat, post, unit, y = get(o))]; d_[, y := y - mean(y), by = unit]
    list(g = d_[, .(s = sum(y), n = .N), by = .(site_id, Year, Season, treat)], pp = d_[, .(post = max(post), pmin = min(post)), by = .(site_id, Year, Season)],
         seasons = sort(unique(d_$Season)))
  }
  pw <- ctx$m16_window
  tr <- x[post == 0L & treat == 1L & is.finite(event_time) & event_time >= pw[1] & event_time <= pw[2], .N, by = .(event_time, Year)]
  list(n_transition = n_tr, integrity = integrity_parts_R(x, if (isTRUE(ctx$d$use_balanced_panel) && identical(ctx$d$balanced_panel, "drop")) o else NULL, ctx$bal_cells),
       post_vs_panel = pvp, same_out = spo, bal_out = bpo,          # v20.59: (rows, rows that differ) or NULL; SAME_PIXELS; 4 Oct: BALANCED_PANEL
       facts = list(n_obs = nrow(x), n_pixels = uniqueN(x$pixel_id), n_units = uniqueN(x$unit), periods = unique(x$period), sites = sort(unique(x$site_id)),
                    rings = sort(unique(x$buff_km)), years = if (nrow(x)) range(x$Year) else c(NA_integer_, NA_integer_), years_set = sort(unique(x$Year)),
                    seasons = sort(unique(x$Season)), base_s = sum(x[treat == 1 & post == 0][[o]], na.rm = TRUE), base_n = sum(is.finite(x[treat == 1 & post == 0][[o]])),
                    blocks_set = if ("block_id" %in% names(x)) unique(x$block_id) else NULL),                                   # v20.59
       cells_all = cells(FALSE), cells_pos = if ("site_id" %in% names(x)) cells(TRUE) else NULL,
       ks02 = sort(unique(x[treat == 1L & is.finite(event_time), event_time])), m16_tr = tr[, .(event_time, Year)],
       m16_g = x[post == 0L, .(s = sum(get(o)), n = .N), by = .(site_id, Year, treat)])
}
# the regression samples: all rows | one season (M01 by season) | M16's pre-period leads sample
ooc_spec_rows <- function(x, sp) switch(sp$rows, all = x, season = x[Season == sp$season],
  m16 = x[post == 0L & ((treat == 1L & is.finite(event_time) & event_time >= sp$pw1 & event_time <= sp$ref) | (treat == 0L & Year %in% sp$years))],
  stop("unknown sample ", sp$rows))
ooc_spec_W <- function(xs, vars) {                                       # the variables, event / lead dummies built as the models build them
  W <- matrix(0, nrow(xs), length(vars), dimnames = list(NULL, vars))
  for (v in vars) W[, v] <- if (startsWith(v, "et::")) as.numeric(xs$treat == 1L & xs$event_time %in% as.integer(sub("^et::", "", v)))
                             else if (startsWith(v, "lead::")) as.numeric(xs$treat == 1L & xs$event_time %in% as.integer(sub("^lead::", "", v)))
                             else as.numeric(xs[[v]])
  W
}
ooc_unit_demean <- function(W, unit) {                                   # the unit (pixel x season) effects: exact, inside the partition
  g <- match(unit, unique(unit)); nu <- tabulate(g)
  list(Wt = W - (rowsum(W, g, reorder = FALSE) / nu)[g, , drop = FALSE], g = g, nu = nu)
}
# GRAM: per regression sample -- the unit-demeaned cross-products, their sums per period, the period block's structure (n_p and
# C' diag(1 / n_u) C, C = units x periods counts), the facts of the fixed-effects rule (units, nesting in the clusters)
ooc_task_gram <- function(ctx, k) {
  x <- readRDS(file.path(ctx$run_dir, sprintf("s_%04d.rds", k))); out <- list()
  for (sp in ctx$specs) {
    xs <- ooc_spec_rows(x, sp); if (!nrow(xs)) next
    W <- ooc_spec_W(xs, sp$vars); u <- ooc_unit_demean(W, xs$unit); Wt <- u$Wt
    pl <- unique(xs$period); pidx <- match(xs$period, pl); cl <- as.character(xs[[ctx$cluster_col]])
    cu <- data.table(u = u$g, p = pidx)[, .N, by = .(u, p)]
    Cm <- Matrix::sparseMatrix(i = cu$u, j = cu$p, x = as.numeric(cu$N), dims = c(length(u$nu), length(pl)))
    CT <- methods::as(methods::as(Matrix::crossprod(Cm, Matrix::Diagonal(x = 1 / u$nu) %*% Cm), "generalMatrix"), "TsparseMatrix")
    out[[sp$id]] <- list(N = nrow(xs), n_units = length(u$nu), WtW = crossprod(Wt), periods = pl, DW = rowsum(Wt, pidx, reorder = FALSE), np = tabulate(pidx, length(pl)),
                         ci = CT@i + 1L, cj = CT@j + 1L, cx = CT@x, unit_nested = all(data.table(u = u$g, c = cl)[, uniqueN(c), by = u]$V1 == 1L),
                         pc = unique(data.table(period = xs$period, cluster = cl)), clusters = unique(cl))
  }
  out
}
# SCORES: the two-way residualised variables (the period effects' projection subtracted, unit-demeaned) and, per regression, the residual
# and the per-cluster score sums
ooc_task_scores <- function(ctx, k) {
  x <- readRDS(file.path(ctx$run_dir, sprintf("s_%04d.rds", k))); out <- list()
  for (sp in ctx$specs) {
    sol <- ctx$sol[[sp$id]]; if (is.null(sol)) next
    xs <- ooc_spec_rows(x, sp); if (!nrow(xs)) next
    W <- ooc_spec_W(xs, sp$vars); u <- ooc_unit_demean(W, xs$unit)
    Gp <- sol$Gam[match(xs$period, sol$periods), , drop = FALSE]
    Wtt <- u$Wt - (Gp - (rowsum(Gp, u$g, reorder = FALSE) / u$nu)[u$g, , drop = FALSE])
    cl <- as.character(xs[[ctx$cluster_col]])
    out[[sp$id]] <- lapply(sol$regs, function(r) {
      if (is.null(r$K)) return(NULL)
      e <- Wtt[, r$y] - drop(Wtt[, r$K, drop = FALSE] %*% r$b)
      S <- rowsum(Wtt[, r$K, drop = FALSE] * e, cl, reorder = FALSE)
      list(clusters = rownames(S), S = unname(S))
    })
  }
  out
}

# ================================================================ 4. the exact two-way fixed-effects solution from the partitions
ooc_components <- function(P, i, j) {                                   # connected components of the periods (a unit spanning two joins them)
  lab <- seq_len(P); if (!length(i)) return(lab)
  repeat {
    m <- pmin(lab[i], lab[j]); t1 <- data.table(n = c(i, j), m = c(m, m))[, .(m = min(m)), by = n]
    new <- lab; new[t1$n] <- pmin(new[t1$n], t1$m); new <- new[new]; new <- new[new]
    if (identical(new, lab)) break
    lab <- new
  }
  lab
}
ooc_solve <- function(parts, sp) {
  parts <- Filter(Negate(is.null), parts); if (!length(parts)) return(list(error = "no row in this regression sample"))
  vars <- sp$vars; m <- length(vars)
  periods <- sort(unique(unlist(lapply(parts, `[[`, "periods")))); P <- length(periods)
  DW <- matrix(0, P, m, dimnames = list(NULL, vars)); npv <- numeric(P); WtW <- matrix(0, m, m, dimnames = list(vars, vars))
  ii <- list(); jj <- list(); xx <- list(); N <- 0; nU <- 0; nest_u <- TRUE; pcs <- list(); cls <- character(0)
  for (p in parts) {
    idx <- match(p$periods, periods)
    DW[idx, ] <- DW[idx, ] + p$DW; npv[idx] <- npv[idx] + p$np; WtW <- WtW + p$WtW
    ii[[length(ii) + 1L]] <- idx[p$ci]; jj[[length(jj) + 1L]] <- idx[p$cj]; xx[[length(xx) + 1L]] <- p$cx
    N <- N + p$N; nU <- nU + p$n_units; nest_u <- nest_u && isTRUE(p$unit_nested); pcs[[length(pcs) + 1L]] <- p$pc; cls <- union(cls, p$clusters)
  }
  i <- unlist(ii); j <- unlist(jj)
  CC <- Matrix::sparseMatrix(i = i, j = j, x = unlist(xx), dims = c(P, P))
  DD <- Matrix::Diagonal(x = npv) - CC                                   # D' M_unit D: the period block after the unit effects
  off <- i != j; comp <- ooc_components(P, i[off], j[off])
  ref <- !duplicated(comp)                                               # one reference period per connected component
  keep <- which(!ref); Gam <- matrix(0, P, m, dimnames = list(NULL, vars))
  if (length(keep)) {
    A <- DD[keep, keep, drop = FALSE]; rhs <- DW[keep, , drop = FALSE]
    sol <- if (length(keep) <= 6000) { Ad <- as.matrix(A); Ad <- (Ad + t(Ad)) / 2
      R <- tryCatch(chol(Ad), error = function(e) NULL)
      if (!is.null(R)) backsolve(R, forwardsolve(t(R), rhs)) else { ev <- eigen(Ad, symmetric = TRUE); pos <- ev$values > max(ev$values) * 1e-12
        ev$vectors[, pos, drop = FALSE] %*% (crossprod(ev$vectors[, pos, drop = FALSE], rhs) / ev$values[pos]) } }
      else as.matrix(Matrix::solve(Matrix::Cholesky(Matrix::forceSymmetric(A)), rhs))
    Gam[keep, ] <- sol
  }
  M <- WtW - crossprod(DW, Gam); M <- (M + t(M)) / 2
  pc <- unique(rbindlist(pcs)); nest_p <- all(pc[, .N, by = period]$N == 1L)
  L <- c(unit = nU, period = P); nest <- c(unit = nest_u, period = nest_p)
  ka <- sum(L) - (length(L) - 1); k_fe <- if (any(nest)) ka - sum(L[nest]) + sum(nest) else ka   # fixest's default (fixef.K = "nested")
  list(periods = periods, Gam = Gam, M = M, WtW = WtW, N = N, G = length(cls), k_fe = k_fe, n_units = nU, n_periods = P, components = length(unique(comp)))
}
ooc_reg <- function(sol, y, x) {                                        # a regression from the residualised cross-products (collinear out)
  x <- unique(x[x %in% colnames(sol$M)]); M <- sol$M; K <- character(0)
  for (v in x) {
    base <- sol$WtW[v, v]
    r2 <- if (!length(K)) M[v, v] else M[v, v] - drop(M[v, K, drop = FALSE] %*% solve(M[K, K, drop = FALSE], M[K, v]))
    if (is.finite(r2) && base > 0 && r2 > 1e-10 * base) K <- c(K, v)
  }
  if (!length(K)) return(list(y = y, K = NULL, error = "no regressor varies within units and periods", dropped = x))
  b <- drop(solve(M[K, K, drop = FALSE], M[K, y])); names(b) <- K
  list(y = y, K = K, b = b, dropped = setdiff(x, K))
}
# the fits of every regression of every sample: two passes over the partitions (the cross-products, then the per-cluster scores)
ooc_fits <- function(S, specs) {
  ctx <- S$ctx; ctx$specs <- specs; ctx$cluster_col <- S$cluster_col
  gp <- ooc_map("gram", ctx, S$K)
  sols <- list(); fits <- list()
  for (sp in specs) {
    s <- tryCatch(ooc_solve(lapply(gp, function(p) p[[sp$id]]), sp), error = function(e) list(error = conditionMessage(e)))
    if (!is.null(s$error)) { fits[[sp$id]] <- list(error = s$error); next }
    s$regs <- lapply(sp$regs, function(r) ooc_reg(s, r$y, r$x))
    sols[[sp$id]] <- list(periods = s$periods, Gam = s$Gam, regs = lapply(s$regs, function(r) r[c("y", "K", "b")]))
    fits[[sp$id]] <- list(sol = s, N = s$N, weight = if (!is.null(sp$weight) && sp$weight %in% colnames(s$M)) s$M[sp$weight, sp$weight] else NA_real_)
  }
  ctx$sol <- sols
  sc <- if (length(sols)) ooc_map("scores", ctx, S$K) else list()
  eng <- sprintf("exact two-way FE out of core (Frisch-Waugh-Lovell + Schur complement of the period block; %s, %d pixel partitions)", OOC_LABEL[[.OOC$last_engine %||% "batches"]], S$K)
  for (sp in specs) {
    if (!is.null(fits[[sp$id]]$error)) next
    s <- fits[[sp$id]]$sol; out <- list()
    for (rid in names(sp$regs)) {
      r <- s$regs[[rid]]
      if (is.null(r$K)) { out[[rid]] <- list(error = r$error); next }
      Ss <- list()
      for (p in sc) { q <- p[[sp$id]][[rid]]; if (is.null(q)) next; Ss[[length(Ss) + 1L]] <- data.table(cl = q$clusters, q$S) }
      Sg <- rbindlist(Ss)[, lapply(.SD, sum), by = cl]; Sm <- as.matrix(Sg[, -1, with = FALSE])
      meat <- crossprod(Sm); K <- r$K; N <- s$N; G <- s$G
      Bi <- solve(s$M[K, K, drop = FALSE]); Bi <- (Bi + t(Bi)) / 2
      V <- Bi %*% meat %*% Bi * (G / (G - 1)) * ((N - 1) / max(1, N - length(K) - s$k_fe)); V <- (V + t(V)) / 2
      se <- sqrt(diag(V)); b <- r$b; p <- 2 * pt(abs(b / se), max(1, G - 1), lower.tail = FALSE)
      names(se) <- names(p) <- K; dimnames(V) <- list(K, K)
      out[[rid]] <- list(coef = b, se = se, p = p, vcov = V, n = N, G = G, dropped = r$dropped, engine = eng)
    }
    fits[[sp$id]]$regs <- out; fits[[sp$id]]$sol <- NULL
  }
  fits
}
ooc_get <- function(fits, spec, reg) {                                  # one fit, or its error (as fe_fit would stop)
  f <- fits[[spec]]; if (is.null(f)) stop("no rows in this regression sample")
  if (!is.null(f$error)) stop(f$error)
  r <- f$regs[[reg]]; if (is.null(r)) stop("the regression was not fitted")
  if (!is.null(r$error)) stop(r$error)
  r
}

# ================================================================ 5. the sample, out of core (load_panel_R's twin)
ooc_merge_moments <- function(s) {                                       # the screen's (Year, Season) table from the partitions' moments
  s <- rbindlist(s, fill = TRUE)
  if (!nrow(s)) return(data.table(Year = integer(0), Season = integer(0), n = integer(0), sd = numeric(0), mean = numeric(0), min = numeric(0), max = numeric(0), n_pixels = numeric(0), n_treated = integer(0), n_control = integer(0)))
  for (k in c("min", "max")) if (!k %in% names(s)) set(s, j = k, value = NA_real_)
  s[, `:=`(sn = sum(n)), by = .(Year, Season)]
  s[, mu := sum(n * mean) / sn, by = .(Year, Season)]
  out <- s[, .(n = sum(n), m2 = sum(m2) + sum(n * (mean - mu)^2), mean = mu[1], min = min(min), max = max(max), n_treated = sum(n_treated), n_control = sum(n_control)), by = .(Year, Season)]
  out[, sd := fifelse(n > 1, sqrt(m2 / (n - 1)), NA_real_)]; out[, n_pixels := NA_real_]   # v20.59: min / max travel; distinct pixels are not additive
  setorder(out, Year, Season); out[, .(Year, Season, n, sd, mean, min, max, n_pixels, n_treated, n_control)]
}
integrity_merge_R <- function(ps) {
  first_dup <- ""; for (p in ps) if (nzchar(p$dup)) { first_dup <- p$dup; break }
  list(sites = sort(unique(unlist(lapply(ps, `[[`, "sites")))), site_na = any(vapply(ps, function(p) isTRUE(p$site_na), TRUE)), has_check = any(vapply(ps, function(p) isTRUE(p$has_check), TRUE)),
       n_outside = sum(vapply(ps, function(p) as.numeric(p$n_outside), 0)), dup = first_dup,
       n_ring_multi = sum(vapply(ps, function(p) as.numeric(p$n_ring_multi), 0)), n_both = sum(vapply(ps, function(p) as.numeric(p$n_both), 0)),
       rings = sort(unique(unlist(lapply(ps, `[[`, "rings")))), years = { y <- unlist(lapply(ps, function(p) p$years)); y <- y[is.finite(y)]; if (length(y)) range(y) else c(NA_integer_, NA_integer_) },
       years_set = sort(unique(unlist(lapply(ps, `[[`, "years_set")))), seasons = sort(unique(unlist(lapply(ps, `[[`, "seasons")))),
       rows = sum(vapply(ps, function(p) as.numeric(p$rows), 0)), pixels = sum(vapply(ps, function(p) as.numeric(p$pixels), 0)),
       n_one_side = sum(vapply(ps, function(p) as.numeric(p$n_one_side %||% 0), 0)),                             # v20.59
       n_unbalanced = if (any(vapply(ps, function(p) !is.null(p$n_unbalanced), TRUE))) sum(vapply(ps, function(p) as.numeric(p$n_unbalanced %||% 0), 0)) else NULL)   # 4 Oct
}
ooc_load_R <- function(outcome, d, plan, engines) {
  panel_dedup_note_R()
  cols <- panel_names()
  if (!outcome %in% cols) stop(sprintf("%s is not in the panel: no export carries this variable", outcome))
  lc_ <- load_columns_R(outcome, d, character(0), cols); covs <- lc_$covs
  has_site <- "site_id" %in% lc_$need
  loc <- if (has_site) location_table_R() else NULL; S <- if (has_site) load_processed_R(d, loc) else integer(0)
  sp <- ooc_split(plan$K)
  run_dir <- ooc_spill(sprintf("run_%d_%s", Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%OS3"))); dir.create(run_dir, recursive = TRUE, showWarnings = FALSE)
  part_cols <- if (sp$format == "parquet") names(arrow::open_dataset(sp$files[1])) else names(fread(sp$files[1], nrows = 0))
  W <- max(1L, min(plan$W, floor(plan$budget / max(1, plan$bytes_per_row * max(1, plan$rows_per_part)))))
  ctx <- list(outcome = outcome, d = d, covs = covs, need = lc_$need, loc = loc, S = S, parts = sp$files, part_cols = part_cols, run_dir = run_dir,
              engines = engines, W = W, threads = max(1L, floor(ooc_cores() / W)), m16_window = c(-4L, -1L), fill_force = NULL)
  # ---- phase A: the row rules
  pa <- ooc_map("prep", ctx, plan$K)
  dc <- pa[[1]]$dc; for (p in pa) if (length(p$dc)) dc <- p$dc
  lr <- rbindlist(lapply(pa, `[[`, "loc_rep")); loc_rep <- NULL
  if (nrow(lr)) { loc_rep <- lr[, .(N = sum(N)), by = .(code, treated, post)]; setorder(loc_rep, code, treated, post); loc_rep[, dropped := code %in% dc]; location_messages_R(loc_rep, dc, outcome) }
  miss <- Reduce(`|`, lapply(pa, `[[`, "miss")); if (length(covs) && length(miss)) {         # the annual fill: the WHOLE sample decides
    redo <- which(vapply(pa, function(p) any(!p$miss & p$inf & miss[names(p$miss)]), TRUE))   # (+-Inf of a partition without an NA)
    if (length(redo)) { ctx$fill_force <- names(miss)[miss]; for (k in redo) pa[[k]] <- ooc_task_run("prep", ctx, k); ctx$fill_force <- NULL }
  }
  n_gf <- sum(vapply(pa, function(p) as.numeric(p$n_gf), 0)); n_gf_post <- sum(vapply(pa, function(p) as.numeric(p$n_gf_post), 0))
  if (n_gf && isTRUE(d$exclude_gapfilled %||% EXCLUDE_GAPFILLED))
    info(sprintf("%s: %s rows filled from history left out (%s of them in the post years)", outcome, format(n_gf, big.mark = ","), format(n_gf_post, big.mark = ",")))
  n_fill <- sum(vapply(pa, function(p) as.numeric(p$n_fill), 0))
  if (n_fill) info(sprintf("annual rows: %s covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean", format(n_fill, big.mark = ",")))
  n0 <- sum(vapply(pa, function(p) as.numeric(p$n0), 0)); n1 <- sum(vapply(pa, function(p) as.numeric(p$n1), 0))
  if (n1 < n0) info(sprintf("%s: %s of %s rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)",
                            outcome, format(n0 - n1, big.mark = ","), format(n0, big.mark = ",")))
  # ---- the outcome screen on the merged moments (screen_decide / screen_refuse: the in-memory rules)
  s <- ooc_merge_moments(lapply(pa, `[[`, "screen"))
  rule <- d$outcome_screen %||% screen_rule_R()                                   # v20.59: the rule of the design (drop / keep / off), the evidence file
  dec <- if (identical(rule, "off")) NULL else screen_decide(s, outcome, rule)
  bad <- if (is.null(dec)) s[0, .(Year, Season)] else dec$drop
  cnt <- rbindlist(lapply(pa, `[[`, "counts"))[, .(N = sum(N)), by = .(site_id, Year, Season)]
  if (nrow(bad)) cnt <- cnt[!bad, on = .(Year, Season)]
  screen_refuse(sort(unique(cnt[N > 0, Year])), outcome, as.integer(d$treatment_year), TRUE, dec)
  s1 <- unique(cnt[N > 0 & site_id > 0, site_id])
  ctx$bad <- if (nrow(bad)) bad[, .(Year, Season)] else data.table(Year = integer(0), Season = integer(0))
  ctx$site_period <- length(s1) >= 2 && identical(d$pooled_fe, "site_period")
  ctx$ctrl_sel <- NULL                                                                      # v20.59: CONTROL_SELECTION decided ONCE by the parent on the
  if (!identical(d$control_selection %||% "rings", "rings")) {                              #   merged pre-period facts of every partition; the workers apply it
    pf <- ooc_map("presel", ctx, plan$K)
    facts <- list(agg_t = rbindlist(lapply(pf, `[[`, "agg_t")), t_pixels = sum(vapply(pf, function(p) as.numeric(p$t_pixels), 0)),
                  agg_c = rbindlist(lapply(pf, `[[`, "agg_c")), pix_c = rbindlist(lapply(pf, `[[`, "pix_c")), mode = d$control_selection)
    dec <- control_selection_decide_R(facts, outcome, d); ctx$ctrl_sel <- record_control_selection_R(dec$tab, dec$chosen, outcome, d)
  }
  ctx$bal_cells <- NULL                                                                     # 4 Oct: BALANCED_PANEL -- the cells of the WHOLE sample first
  if (isTRUE(d$use_balanced_panel)) ctx$bal_cells <- unique(rbindlist(ooc_map("balcells", ctx, plan$K)))
  # ---- phase B: the design columns, the final sample and its facts
  pb <- ooc_map("sample", ctx, plan$K)
  bpl <- Filter(Negate(is.null), lapply(pb, `[[`, "bal_out"))                                               # 4 Oct: BALANCED_PANEL, summed over the partitions
  if (length(bpl)) balanced_panel_say_R(list(rule = bpl[[1]]$rule, pixels_unbalanced = sum(vapply(bpl, function(v) as.numeric(v$pixels_unbalanced), 0)),
                                             pixels_total = sum(vapply(bpl, function(v) as.numeric(v$pixels_total), 0)), rows_left_out = sum(vapply(bpl, function(v) as.numeric(v$rows_left_out), 0)),
                                             pixels_kept = sum(vapply(bpl, function(v) as.numeric(v$pixels_kept), 0))), outcome)
  n_tr <- sum(vapply(pb, function(p) as.numeric(p$n_transition), 0))
  if (isTRUE(d$exclude_transition_year)) info(sprintf("EXCLUDE_TRANSITION_YEAR: %s rows of each series' first treated year left out", format(n_tr, big.mark = ",")))
  pv <- Filter(Negate(is.null), lapply(pb, `[[`, "post_vs_panel"))                                   # v20.59: DESIGN vs PANEL, summed over the partitions
  post_vs_panel <- if (length(pv)) c(sum(vapply(pv, function(v) as.numeric(v[1]), 0)), sum(vapply(pv, function(v) as.numeric(v[2]), 0))) else NULL
  design_vs_panel_say_R(post_vs_panel, d)
  spl <- Filter(Negate(is.null), lapply(pb, `[[`, "same_out"))                                              # v20.59: SAME_PIXELS, summed over the partitions
  if (length(spl) && sum(vapply(spl, function(v) as.numeric(v$pixels_left_out), 0)) > 0)
    info(sprintf("SAME_PIXELS = \"%s\" (%s): %s pixel(s) / %s rows leave -- observed %s; the treated and control groups are the same %s pixels", spl[[1]]$rule, outcome,
                 format(sum(vapply(spl, function(v) as.numeric(v$pixels_left_out), 0)), big.mark = ","), format(sum(vapply(spl, function(v) as.numeric(v$rows_left_out), 0)), big.mark = ","),
                 if (identical(spl[[1]]$rule, "pre_post")) "only before or only after treatment" else "in some year-seasons only", format(sum(vapply(spl, function(v) as.numeric(v$pixels_kept), 0)), big.mark = ",")))
  fx <- lapply(pb, `[[`, "facts")
  sites <- sort(unique(unlist(lapply(fx, `[[`, "sites")))); pos <- sites[sites > 0]
  cluster_col <- if (identical(d$cluster, "block")) "block_id" else if (length(pos) >= MIN_SWS_CLUSTERS) "site_id" else "Year"   # v20.59: ~1 km blocks
  years_set <- sort(unique(unlist(lapply(fx, `[[`, "years_set"))))
  G <- if (cluster_col == "site_id") length(unique(sites)) else if (cluster_col == "block_id") length(unique(unlist(lapply(fx, `[[`, "blocks_set")))) else length(years_set)
  bn <- sum(vapply(fx, function(f) as.numeric(f$base_n), 0))
  facts <- list(cluster_col = cluster_col, G = G, n_obs = sum(vapply(fx, function(f) as.numeric(f$n_obs), 0)), n_pixels = sum(vapply(fx, function(f) as.numeric(f$n_pixels), 0)),
                n_units = sum(vapply(fx, function(f) as.numeric(f$n_units), 0)), n_sites_pos = length(pos), n_periods = length(unique(unlist(lapply(fx, `[[`, "periods")))),
                sites = sites, rings = sort(unique(unlist(lapply(fx, `[[`, "rings")))),
                years = { y <- unlist(lapply(fx, `[[`, "years")); y <- y[is.finite(y)]; range(y) },
                baseline_mean = if (bn > 0) sum(vapply(fx, function(f) as.numeric(f$base_s), 0)) / bn else NaN,
                location_report = loc_rep, post_vs_panel = post_vs_panel)                            # v20.59
  facts$integrity <- integrity_decide_R(integrity_merge_R(lapply(pb, `[[`, "integrity")), d, outcome, S)
  use_pos <- any(sites > 0L) && has_site
  cl_ <- lapply(pb, function(p) if (use_pos) p$cells_pos else p$cells_all)
  g <- rbindlist(lapply(cl_, `[[`, "g"))[, .(m = sum(s) / sum(n)), by = .(site_id, Year, Season, treat)]
  pp <- rbindlist(lapply(cl_, `[[`, "pp"))[, .(post = max(post), pmin = min(pmin)), by = .(site_id, Year, Season)]
  n_seasons <- length(unique(unlist(lapply(cl_, `[[`, "seasons"))))
  m16g <- rbindlist(lapply(pb, `[[`, "m16_g"))[, .(m = sum(s) / sum(n)), by = .(site_id, Year, treat)]
  seasons <- sort(unique(unlist(lapply(fx, `[[`, "seasons"))))
  ctx$bad <- NULL
  structure(list(outcome = outcome, d = d, covs = covs, scenario = scenario_tag(d), K = plan$K, ctx = ctx, run_dir = run_dir, facts = facts,
                 cluster_col = cluster_col, is_year = cluster_col == "Year", seasons = seasons, years_set = years_set,
                 ks02 = sort(unique(unlist(lapply(pb, `[[`, "ks02")))), m16_tr = unique(rbindlist(lapply(pb, `[[`, "m16_tr"))), m16_g = m16g,
                 design_se = function(est) if (!nrow(g)) list(se_design = NA_real_, p_design = NA_real_, se_design_unit = "not identified") else design_se_core(copy(g), copy(pp), n_seasons, est),
                 design_se_event = function(est) design_event_core(copy(g), copy(pp), est)),
            class = "reward_ooc")
}
print.reward_ooc <- function(x, ...) cat(sprintf("<out-of-core sample: %s rows, %s pixels, %d pixel partitions>\n", format(x$facts$n_obs, big.mark = ","), format(x$facts$n_pixels, big.mark = ","), x$K))

# ================================================================ 6. the four models, out of core (the in-memory code's own tables)
ooc_m01 <- function(S, outcome) {
  cv <- S$covs; vars <- c(outcome, "did", cv)
  regs <- list(main = list(y = outcome, x = c("did", cv)))
  if (length(cv)) { regs$f0 <- list(y = outcome, x = "did"); for (c_ in cv) regs[[paste0("cov:", c_)]] <- list(y = c_, x = "did") }
  specs <- list(main = list(id = "main", rows = "all", vars = vars, regs = regs))
  ss <- S$seasons
  if (length(ss) >= 2) for (s_ in ss) specs[[paste0("season:", s_)]] <- list(id = paste0("season:", s_), rows = "season", season = s_, vars = vars,
                                                                            regs = list(main = list(y = outcome, x = c("did", cv))), weight = "did")
  fits <- ooc_fits(S, specs)
  f <- ooc_get(fits, "main", "main"); out <- c(pick(f, "did"), engine = paste(f$engine, "(two-way FE)"))
  if (length(cv)) out$table <- covariate_response_core(outcome, cv, function(y, x, c_ = NULL) ooc_get(fits, "main", if (is.null(c_)) "f0" else paste0("cov:", c_)))
  if (length(ss) >= 2) {
    parts <- lapply(ss, function(s_) { id <- paste0("season:", s_); why <- ""
      f_ <- tryCatch(ooc_get(fits, id, "main"), error = function(e) { why <<- conditionMessage(e); NULL })
      list(season = s_, f = f_, why = why, rows = fits[[id]]$N %||% 0L, weight = fits[[id]]$weight %||% NA_real_) })
    bs <- by_season_core(outcome, parts)
    od <- file.path(RESULTS_DIR, "M01", S$scenario); dir.create(od, recursive = TRUE, showWarnings = FALSE)
    fwrite(bs, file.path(od, sprintf("M01_%s_by_season.csv", outcome)))
  }
  out
}
ooc_m02 <- function(S, outcome) {
  ks <- S$ks02; ks <- ks[ks != -1L]
  if (!length(ks)) stop("no event time other than the reference year -1")
  vars <- c(outcome, paste0("et::", ks), S$covs)
  fits <- ooc_fits(S, list(main = list(id = "main", rows = "all", vars = vars, regs = list(main = list(y = outcome, x = vars[-1])))))
  m02_finish(ooc_get(fits, "main", "main"), S$is_year, S$design_se_event)
}
ooc_m16 <- function(S, outcome, pre_window = c(-4L, -2L), ref = -1L) {
  tr <- S$m16_tr; ks <- sort(unique(tr$event_time)); ks <- ks[ks != ref]; f <- NULL
  if (length(ks) && any(tr$event_time == ref) && !S$is_year) {
    vars <- c(outcome, paste0("lead::", ks), S$covs)
    fits <- ooc_fits(S, list(m16 = list(id = "m16", rows = "m16", pw1 = pre_window[1], ref = ref, years = sort(unique(tr$Year)), vars = vars,
                                        regs = list(main = list(y = outcome, x = vars[-1])))))
    f <- tryCatch(ooc_get(fits, "m16", "main"), error = function(e) { info("M16: the cluster-robust leads fit failed (", conditionMessage(e), ") -- the design-based test is used"); NULL })
  }
  m16_core(ks, f, function() copy(S$m16_g), S$is_year)
}
ooc_m34 <- function(S, outcome) {
  need("HonestDiD", "GitHub asheshrambachan/HonestDiD")
  m34_from_event(ooc_m02(S, outcome), S$is_year, S$design_se_event)
}
OOC_MODEL_FUN <- list(M01 = ooc_m01, M02 = ooc_m02, M16 = ooc_m16, M34 = ooc_m34)

# ================================================================ 7. the run (run_model_R hands the four models here beyond 98 %)
ooc_run_model_R <- function(id, outcome, d, why = "") {
  t0 <- Sys.time(); .OOC$trace <- character(0)
  plan <- ooc_plan(length(tryCatch(load_columns_R(outcome, d)$need, error = function(e) character(20)))); ch <- ooc_choose()
  info(sprintf("OUT OF CORE (%s x %s): %s -- %d pixel partitions of ~%s rows, engines in order: %s%s", id, outcome, why, plan$K, format(plan$rows_per_part, big.mark = ","),
               paste(OOC_LABEL[ch$engines], collapse = " -> "), if (length(ch$skipped)) paste0(" (not available: ", paste(ch$skipped, collapse = "; "), ")") else ""))
  S <- tryCatch(ooc_load_R(outcome, d, plan, ch$engines), error = function(e) e)
  if (inherits(S, "error")) { save_result(id, outcome, list(error = conditionMessage(S)), NULL, d); return(invisible(NULL)) }
  on.exit(if (!identical(Sys.getenv("REWARD_OOC_KEEP_PARTS"), "1")) unlink(S$run_dir, recursive = TRUE), add = TRUE)
  res <- tryCatch(OOC_MODEL_FUN[[id]](S, outcome), error = function(e) list(error = conditionMessage(e)))
  out <- save_result(id, outcome, res, S, d)
  info(sprintf("%s x %s done out of core in %.1f s (%s)", id, outcome, as.numeric(difftime(Sys.time(), t0, units = "secs")), paste(.OOC$trace, collapse = "; ")))
  invisible(out)
}

# ================================================================ 8. the design from the data, out of core (recommend_design's summary)
ooc_task_recommend <- function(ctx, k) {
  a0 <- ooc_read_part(ctx, k, ctx$cols); a0 <- a0[, intersect(ctx$cols, names(a0)), with = FALSE]; o <- ctx$outcome
  if ("site_id" %in% names(a0) && !is.null(ctx$loc)) { lc <- location_codes_R(a0, ctx$loc, ctx$S); if (length(ctx$dc)) a0 <- a0[!lc %in% ctx$dc] }
  a <- a0[is.finite(get(o))]
  mom <- if (nrow(a)) a[, { v <- get(o); mu <- mean(v); .(n = .N, mean = mu, m2 = sum((v - mu)^2)) }, by = .(Season, Year, ring = buff_km)] else NULL
  core <- unique(a0[buff_km == 0, .(pixel_id, Year, Season)])              # pixels PRESENT (not: with a finite outcome), as in memory
  refp <- unique(core[Year == ctx$treatment_year - 1L, .(pixel_id, Season)])
  core[, inref := FALSE]; if (nrow(refp)) core[refp, on = .(pixel_id, Season), inref := TRUE]
  list(mom = mom, link = core[, .(n_pix = .N, n_ref = sum(inref)), by = .(Season, Year)], seasons = sort(unique(a$Season)))
}
recommend_summary_ooc <- function(outcome, treatment_year, fragment_rule, min_share, overlap_rows, sites, cols) {
  plan <- ooc_plan(length(cols)); sp <- ooc_split(plan$K)
  has_site <- "site_id" %in% cols; loc <- if (has_site) location_table_R() else NULL
  S <- if (!has_site) integer(0) else if (is.null(sites)) processing_set_R(loc, "data", min_share)$sites else sites
  dc <- c(if (identical(fragment_rule, "drop")) 1:2, if (identical(overlap_rows, "drop")) 3:4)
  run_dir <- ooc_spill(sprintf("run_%d_%s", Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%OS3"))); on.exit(unlink(run_dir, recursive = TRUE), add = TRUE)
  part_cols <- if (sp$format == "parquet") names(arrow::open_dataset(sp$files[1])) else names(fread(sp$files[1], nrows = 0))
  ch <- ooc_choose(); W <- max(1L, min(ooc_cores(), plan$K))
  ctx <- list(outcome = outcome, cols = cols, loc = loc, S = S, dc = dc, parts = sp$files, part_cols = part_cols, run_dir = run_dir, engines = ch$engines, W = W,
              threads = max(1L, floor(ooc_cores() / W)), treatment_year = as.integer(treatment_year))
  pr <- ooc_map("recommend", ctx, plan$K)
  mom <- rbindlist(lapply(pr, `[[`, "mom"))
  if (!nrow(mom)) stop("no finite ", outcome, " value in the panel")
  s0 <- min(mom$Season)
  m <- mom[Season == s0]; m[, `:=`(sn = sum(n)), by = .(Year, ring)]; m[, mu := sum(n * mean) / sn, by = .(Year, ring)]
  g <- m[, .(n = sum(n), m2 = sum(m2) + sum(n * (mean - mu)^2), mean = mu[1]), by = .(Year, ring)]
  g[, sd := fifelse(n > 1, sqrt(m2 / (n - 1)), NA_real_)]; setorder(g, Year, ring); g <- g[, .(Year, ring, n, mean, sd)]
  lk <- rbindlist(lapply(pr, `[[`, "link"))[Season == s0, .(n_pix = sum(n_pix), n_ref = sum(n_ref)), by = Year]
  yrs <- sort(unique(g$Year))
  link <- vapply(yrs, function(y) { r <- lk[Year == y]; if (nrow(r) && r$n_pix > 0) r$n_ref / r$n_pix else NA_real_ }, 0); names(link) <- yrs
  sn_all <- mom[Season != s0, .(N = sum(n)), by = .(Season, Year)]
  info(sprintf("design from the data: %d pixel partitions read out of core (the panel does not fit below 98 %% of the RAM)", plan$K))
  list(g = g, s0 = s0, link = link, sn_all = sn_all)
}

# ================================================================ 9. the outcome identities, row group by row group (a panel beyond 98 %)
outcome_identities_stream_R <- function(oc, first_n = 1e6) {
  ds <- arrow::open_dataset(PANEL_PATH)
  scan <- function() { sb <- ds$NewScan(); invisible(sb$Project(oc)); invisible(sb$BatchSize(262144L)); sb$Finish()$ToRecordBatchReader() }
  rdr <- scan(); nfin <- setNames(numeric(length(oc)), oc); first <- list(); nf <- 0
  while (!is.null(b <- rdr$read_next_batch())) {
    x <- as.data.table(b); for (o in oc) nfin[o] <- nfin[o] + sum(is.finite(x[[o]]))
    if (nf < first_n) { take <- min(nrow(x), first_n - nf); first[[length(first) + 1L]] <- x[seq_len(take)]; nf <- nf + take }
  }
  oc <- oc[nfin[oc] > 2]; first <- rbindlist(first)
  pairs <- list()
  for (i in seq_along(oc)) for (j in seq_along(oc)) if (i < j) {
    a <- first[[oc[i]]]; b <- first[[oc[j]]]; m <- is.finite(a) & is.finite(b); if (sum(m) < 3) next
    if (!isTRUE(abs(suppressWarnings(cor(a[m], b[m]))) > 0.99999)) next
    pairs[[length(pairs) + 1L]] <- c(oc[i], oc[j])
  }
  out <- data.table(a = character(0), b = character(0), r = numeric(0), slope = numeric(0), intercept = numeric(0), n = numeric(0))
  if (!length(pairs)) return(out)
  acc <- lapply(pairs, function(p) c(n = 0, ma = 0, mb = 0, saa = 0, sbb = 0, sab = 0))
  rdr <- scan()
  while (!is.null(bt <- rdr$read_next_batch())) {
    x <- as.data.table(bt)
    for (q in seq_along(pairs)) {
      a <- x[[pairs[[q]][1]]]; b <- x[[pairs[[q]][2]]]; m <- is.finite(a) & is.finite(b); nb <- sum(m); if (!nb) next
      a <- a[m]; b <- b[m]; ma <- mean(a); mb <- mean(b); s <- acc[[q]]; n <- s[["n"]] + nb; da <- ma - s[["ma"]]; db <- mb - s[["mb"]]
      acc[[q]] <- c(n = n, ma = s[["ma"]] + da * nb / n, mb = s[["mb"]] + db * nb / n, saa = s[["saa"]] + sum((a - ma)^2) + da * da * s[["n"]] * nb / n,
                    sbb = s[["sbb"]] + sum((b - mb)^2) + db * db * s[["n"]] * nb / n, sab = s[["sab"]] + sum((a - ma) * (b - mb)) + da * db * s[["n"]] * nb / n)
    }
  }
  for (q in seq_along(pairs)) {
    s <- acc[[q]]; if (s[["n"]] < 3) next
    sa <- sqrt(s[["saa"]] / (s[["n"]] - 1)); sb <- sqrt(s[["sbb"]] / (s[["n"]] - 1)); if (!is.finite(sa) || !is.finite(sb) || sa == 0 || sb == 0) next
    r <- s[["sab"]] / sqrt(s[["saa"]] * s[["sbb"]])
    if (is.finite(r) && abs(r) > 0.999999) { sl <- r * sb / sa
      out <- rbind(out, data.table(a = pairs[[q]][1], b = pairs[[q]][2], r = r, slope = sl, intercept = s[["mb"]] - sl * s[["ma"]], n = s[["n"]])) }
  }
  out
}
