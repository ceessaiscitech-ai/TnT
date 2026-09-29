# 00_SETUP.R -- run ONCE in RStudio (open RWD_4Models.Rproj, then Source this file). Needs internet. Installs the packages of the
# four models of this project (M01, M02, M16, M34: fixest, HonestDiD + the pipeline's own) -- nothing for the other 41.
# Start from a FRESH session (Session -> Restart R): Windows cannot replace a package that is already loaded.
# v20.49: a repository chosen BEFORE this file runs is kept (e.g. Posit's pre-built Linux binaries, set by
# tests/install_and_test_linux.sh or by Posit Cloud) -- only an unset / "@CRAN@" repository becomes cloud.r-project.org.
# (v20.47 always replaced it with plain CRAN, so on Linux every package compiled from source.)
r0 <- getOption("repos")
if (is.null(r0) || !length(r0) || is.na(r0["CRAN"]) || identical(unname(r0["CRAN"]), "@CRAN@"))
  options(repos = c(CRAN = "https://cloud.r-project.org"))
repos <- getOption("repos")
options(Ncpus = max(1L, parallel::detectCores()))                 # v20.57: every core for parallel installs (no core held back)
# v20.55: ONE install chain for set-up time and run time -- lib/reward_packages.R: CRAN (a pre-built binary where the platform
# has one, else the source, compiled) -> the author's r-universe -> GitHub -> the GitHub source archive -> a mirror. The same
# function installs a package the first time a model needs it (AUTO_INSTALL_PACKAGES in lib/reward_paths.R), and every
# notebook confirms at its start that all packages are installed.
R_HOME_DIR <- normalizePath(if (file.exists("lib/reward_packages.R")) "." else "..", winslash = "/")
AUTO_INSTALL_PACKAGES <- TRUE
PIPELINE_MODELS <- c("M01", "M02", "M16", "M34")    # the four-model project: its packages only
source(file.path(R_HOME_DIR, "lib", "reward_packages.R"))
cran <- intersect(REWARD_R_PACKAGES$package[REWARD_R_PACKAGES$source == "CRAN"], project_packages())   # v20.58: THIS project's CRAN packages
                                                                                                # (PIPELINE_MODELS; all of them when NULL)
status <- ensure_packages(project_packages(), install = TRUE)                         # every package of the project, through the chain (v20.58)
# v20.56: a pre-built binary is installed even when CRAN has a newer source version (options(install.packages.compile.from.source)
# = "never" inside the chain), so Rtools is needed ONLY for a package that has no binary at all for your R version -- the chain
# then says which package and why. Packages already installed are NOT updated by default (an update can pull a source
# build); set UPDATE_PACKAGES <- TRUE to bring them up to date. Missing DEPENDENCIES of installed packages are still
# installed (v20.51: an older MatchIt needed 'chk').
UPDATE_PACKAGES <- FALSE
old_opt <- options(install.packages.compile.from.source = "never")
bin_type <- if (binary_platform()) "binary" else getOption("pkgType")
if (isTRUE(UPDATE_PACKAGES)) {
  op <- tryCatch(utils::old.packages(repos = repos, type = bin_type), error = function(e) NULL)
  to_update <- intersect(rownames(op), c(cran, intersect("HonestDiD", project_packages()), "IRkernel"))
  if (is.character(to_update) && length(to_update)) { cat("updating", length(to_update), "out-of-date package(s):", paste(to_update, collapse = ", "), "\n")
                                                     utils::install.packages(pkgs = to_update, repos = repos, type = bin_type) }
}
ap <- tryCatch(utils::available.packages(repos = repos), error = function(e) NULL)
if (!is.null(ap)) {
  deps <- unique(unlist(tools::package_dependencies(intersect(cran, rownames(ap)), db = ap, which = c("Depends", "Imports", "LinkingTo"), recursive = TRUE)))
  md <- setdiff(deps, c(rownames(utils::installed.packages()), rownames(utils::installed.packages(priority = "base"))))
  if (is.character(md) && length(md)) { cat("installing", length(md), "missing dependenc(ies):", paste(md, collapse = ", "), "\n")
                                       for (m_ in md) install_package_chain(m_, verbose = FALSE) }
}
if (!requireNamespace("chk", quietly = TRUE)) install_package_chain("chk", verbose = FALSE)   # older MatchIt versions call it
options(old_opt)
gh <- c(HonestDiD = "asheshrambachan/HonestDiD", synthdid = "synth-inference/synthdid", ritest = "grantmcdermott/ritest")
# the R notebooks in Jupyter too (the .ipynb in jupyter/): the R kernel IRkernel, registered for this user.
# v20.49: RStudio on Windows usually does not have Anaconda on its PATH, so `jupyter` was not found and the registration
# failed ("jupyter-client has to be installed"); the usual Anaconda / Miniconda locations are searched first.
find_jupyter <- function() {
  j <- Sys.which("jupyter"); if (nzchar(j)) return(unname(j))
  ev <- Sys.getenv(c("USERPROFILE", "LOCALAPPDATA", "ProgramData", "HOME")); ev <- ev[nzchar(ev)]
  cand <- c(as.vector(outer(ev, c("anaconda3", "Anaconda3", "miniconda3", "Miniconda3", "miniforge3"), file.path)),
            file.path("C:", c("anaconda3", "Anaconda3", "miniconda3", "ProgramData/anaconda3", "ProgramData/Anaconda3")))
  cand <- c(file.path(cand, "Scripts", "jupyter.exe"), file.path(cand, "bin", "jupyter"))
  cand <- cand[file.exists(cand)]; if (length(cand)) cand[1] else ""
}
if (!requireNamespace("IRkernel", quietly = TRUE)) install_package_chain("IRkernel", verbose = FALSE)
jup <- find_jupyter()
if (nzchar(jup)) Sys.setenv(PATH = paste(dirname(jup), Sys.getenv("PATH"), sep = .Platform$path.sep))
if (requireNamespace("IRkernel", quietly = TRUE)) {
  if (nzchar(jup)) { r <- try(IRkernel::installspec(user = TRUE)); if (!inherits(r, "try-error")) cat("R kernel registered with Jupyter:", jup, "\n")
  } else cat("Jupyter not found: to use the R notebooks in Jupyter, open the Anaconda Prompt and run  R -e \"IRkernel::installspec()\"\n")
}
st <- confirm_packages(install = TRUE)                                                # "N of N R packages installed" + PACKAGE_STATUS_R.csv
cat(build_tools_line(), "\n")
# v20.58: the OUT-OF-CORE engines of the R pipeline -- used ONLY beyond 98 % of the RAM (M01 / M02 / M16 / M34 and R_P00), in the order of
# OUT_OF_CORE (lib/reward_paths.R): Dask, then Spark (both through a Python that has dask / pyspark: PYTHON_EXE in lib/reward_paths.R, else
# python on the PATH or Anaconda), then R itself (always). Which of them this machine has:
try(local({
  info <- function(...) cat("[INFO]    ", ..., "\n", sep = "")
  source(file.path(R_HOME_DIR, "lib", "reward_paths.R"), local = TRUE)
  source(file.path(R_HOME_DIR, "lib", "reward_outofcore.R"), local = TRUE)
  ooc_status_table()
}))
cat("R ", R.version$major, ".", R.version$minor, " | next: tests/run_all_tests.R (or tests/selftest.R), then rstudio/R_P00_Prepare_Panel.Rmd\n", sep = "")
