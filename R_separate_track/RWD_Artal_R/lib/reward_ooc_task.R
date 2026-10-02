# reward_ooc_task.R -- v20.58: ONE out-of-core partition task in its own R process (Dask / Spark run it through lib/reward_ooc_engine.py)
#   Rscript --vanilla lib/reward_ooc_task.R <ctx.rds> <task> <partition> <out.rds>
# The task is the SAME R function the R batches call in the session (reward_outofcore.R: ooc_task_run) on the SAME context (the design of
# the run, the settings of the session); its result -- or its error, never swallowed -- is written to <out.rds>.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) stop("usage: Rscript reward_ooc_task.R <ctx.rds> <task> <partition> <out.rds>")
res <- tryCatch({
  ctx <- readRDS(args[1])
  for (k in names(ctx$globals)) assign(k, ctx$globals[[k]], envir = globalenv())
  R_HOME_DIR <- ctx$R_HOME_DIR; Sys.setenv(REWARD_OOC_WORKER = "1")
  suppressPackageStartupMessages({ library(data.table); library(jsonlite) })
  invisible(capture.output({
    for (f in c("reward_fund.R", "reward_design.R", "reward_prep.R", "reward_outofcore.R")) source(file.path(R_HOME_DIR, "lib", f), local = globalenv())
  }))
  for (k in names(ctx$globals)) assign(k, ctx$globals[[k]], envir = globalenv())   # the session's own settings again (a lib sets its defaults)
  setDTthreads(max(1L, as.integer(ctx$threads %||% 1L)))
  t0 <- Sys.time()
  out <- ooc_task_run(args[2], ctx, as.integer(args[3]))
  list(ok = TRUE, result = out, seconds = as.numeric(difftime(Sys.time(), t0, units = "secs")), pid = Sys.getpid())
}, error = function(e) list(ok = FALSE, error = conditionMessage(e), call = paste(deparse(conditionCall(e)), collapse = " ")))
tmp <- paste0(args[4], ".tmp"); saveRDS(res, tmp); file.rename(tmp, args[4])
invisible(NULL)
