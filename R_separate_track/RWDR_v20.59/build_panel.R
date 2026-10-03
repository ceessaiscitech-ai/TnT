# build_panel.R -- build the DID-ready panel from a folder of exports, from the command line (the same library and rules as R_P00; nothing
# of the design is set here -- every model sets its own in its first chunk).
#     Rscript build_panel.R input=D:/LKT/RWDR/data                          # output -> <input>/output (the R_P00 layout)
#     Rscript build_panel.R input=D:/exports/Jantapur output=D:/panels/Jantapur [threads=60] [force=TRUE] [screen=FALSE]
# Steps (R_P00's chunks): paths -> the packages confirmed -> run_prep() (every file read on every thread, the input audit, the overlay on
# the shapefile, the pixel linkage, the duplicates, the design columns from the exports' flag, the variation report, the panel written and
# CONFIRMED) -> the design the defaults give (every optional customisation OFF) -> the outcome screen per outcome. The Python twin:
# python build_panel.py --input ... [--output ...].
args <- commandArgs(trailingOnly = TRUE); kv <- strsplit(args[grepl("=", args, fixed = TRUE)], "=", fixed = TRUE); opt <- setNames(lapply(kv, `[`, 2), vapply(kv, `[`, "", 1))
if (is.null(opt$input)) stop("usage: Rscript build_panel.R input=<exports folder> [output=<folder>] [threads=N] [force=TRUE] [screen=FALSE]")
Sys.setenv(REWARD_R_ROOT = normalizePath(opt$input, winslash = "/", mustWork = TRUE), REWARD_TEST_RUN = "1")       # the root for this run only (no warning about a test's folder)
R_HOME_DIR <- normalizePath(if (nzchar(Sys.getenv("REWARD_R_HOME"))) Sys.getenv("REWARD_R_HOME") else { a <- grep("^--file=", commandArgs(), value = TRUE); if (length(a)) dirname(sub("^--file=", "", a)) else "." }, winslash = "/")
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
if (!is.null(opt$output)) {                                             # the output folder, when not <input>/output
  OUTPUT_DIR <- normalizePath(opt$output, winslash = "/", mustWork = FALSE); RESULTS_DIR <- file.path(OUTPUT_DIR, "results")
  PANEL_PATH <- file.path(OUTPUT_DIR, "did_panel_full.parquet"); DESIGN_PATH <- file.path(OUTPUT_DIR, "R_design.json")
}
if (!is.null(opt$threads)) N_THREADS <- max(1L, as.integer(opt$threads))
dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
cat("[INFO]    exports:", ROOT, "| output:", OUTPUT_DIR, "| threads:", N_THREADS, "\n")
invisible(confirm_packages())
t0 <- Sys.time()
if (!isTRUE(as.logical(opt$force %||% "FALSE")) && file.exists(PANEL_PATH) && exists("panel_is_valid_R", mode = "function") && isTRUE(tryCatch(panel_is_valid_R(), error = function(e) FALSE))) {
  ok(sprintf("a valid panel is already there: %s (force=TRUE rebuilds it)", PANEL_PATH)); panel_precision_report_R(verbose = TRUE)   # 3 Oct: the report in both branches (as build_panel.py)
} else panel <- run_prep()
design <- prepare_design(); str(design[setdiff(names(design), c("choices", "notes"))])      # the design the defaults give (every optional customisation OFF)
if (!identical(tolower(opt$screen %||% "TRUE"), "false")) {
  scr <- outcome_screen_R(OUTCOMES, design); fwrite(scr, file.path(RESULTS_DIR, "OUTCOME_SCREEN_R.csv")); print(scr)
}
ok(sprintf("panel: %s (%.0f s). Next: any R_Mxx notebook (its first chunk sets the design), or Rscript orchestrator.R config/analysis_config.yaml", PANEL_PATH, as.numeric(difftime(Sys.time(), t0, units = "secs"))))
