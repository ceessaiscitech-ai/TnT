# reward_packages.R -- the R packages of the pipeline: PRE-BUILT FIRST, SOURCE WHEN NO BINARY EXISTS, installed at set-up
# time AND at run time with the same chain, and CONFIRMED at the start of every notebook (v20.55).
#
#   * install_package_chain(p): CRAN (a binary where the platform has one -- Windows, macOS, a Posit binary repository on
#     Linux -- else the source, compiled) -> the author's r-universe (binaries built from the GitHub source) -> GitHub
#     (remotes) -> the GitHub source archive (no API, so no rate limit) -> a mirror of the same code (synthdid).
#   * ensure_packages(pkgs, install = AUTO_INSTALL_PACKAGES): every package checked; a missing one is installed through the
#     chain when AUTO_INSTALL_PACKAGES is TRUE (reward_paths.R); returns one row per package (installed, version, how).
#   * confirm_packages(): prints "N of N R packages installed" with the missing ones and the models they serve, writes
#     results/PACKAGE_STATUS_R.csv -- called by every notebook's setup chunk, 00_SETUP.R and the tests.
#   * need(p): used by every model right before it calls a package -- installs it (chain) when missing and allowed, else
#     stops with the install command. So a package that was not installed at set-up is fetched the first time a model
#     needs it, and the run says which route provided it.
# The same rules hold in Python (P00 P12 / prebuilt_first: pip wheel -> sdist -> the pipeline's own engine).

if (!exists("AUTO_INSTALL_PACKAGES")) AUTO_INSTALL_PACKAGES <- TRUE
if (!exists("PIPELINE_MODELS")) PIPELINE_MODELS <- c("M01", "M02", "M16", "M34")   # v20.58: THIS project's models (as reward_paths.R); NULL = all 45 (RWDR)

# one row per package: where it comes from and which models use it (the Python bridge run_one.R has the same model list)
REWARD_R_PACKAGES <- data.frame(stringsAsFactors = FALSE, rbind(
  c("data.table", "CRAN", "every step"),                c("jsonlite", "CRAN", "every step"),
  c("arrow", "CRAN", "the panel (parquet)"),            c("dplyr", "CRAN", "helpers"),
  c("sf", "CRAN", "P00 (shapefile overlay)"),           c("RANN", "CRAN", "P00 (shifted grids)"),
  c("readxl", "CRAN", "P00 (Excel exports, fund file)"),c("fixest", "CRAN", "M01 M02 M09 M10 M12 M14 M15 M16 M20 M24-M26 M29 M31 M33"),
  c("did", "CRAN", "M05 M30"),                          c("DRDID", "CRAN", "M03"),
  c("qte", "CRAN", "M04 M35"),                          c("DIDmultiplegtDYN", "CRAN", "M13"),
  c("MatchIt", "CRAN", "M14"),                          c("spdep", "CRAN", "M17 M18"),
  c("lme4", "CRAN", "M19"),                             c("performance", "CRAN", "M19"),
  c("metafor", "CRAN", "M20"),                          c("bacondecomp", "CRAN", "M22"),
  c("didimputation", "CRAN", "M27"),                    c("did2s", "CRAN", "M28"),
  c("etwfe", "CRAN", "M32"),                            c("WeightIt", "CRAN", "M33"),
  c("quantreg", "CRAN", "M35"),                         c("fect", "CRAN", "M36 M37"),
  c("gsynth", "CRAN", "M38"),                           c("grf", "CRAN", "M39 M41 M42 M43"),
  c("DoubleML", "CRAN", "M40"),                         c("mlr3", "CRAN", "M40"),
  c("mlr3learners", "CRAN", "M40"),                     c("ranger", "CRAN", "M40"),
  c("bartCause", "CRAN", "M44"),                        c("glmnet", "CRAN", "M08"),
  c("remotes", "CRAN", "installs from GitHub"),         c("rmarkdown", "CRAN", "the .Rmd notebooks"),
  c("knitr", "CRAN", "the .Rmd notebooks"),             c("ps", "CRAN", "the run heartbeat"),
  c("HonestDiD", "github:asheshrambachan/HonestDiD", "M34"),
  c("synthdid", "github:synth-inference/synthdid", "M11 M45"),
  c("ritest", "github:grantmcdermott/ritest", "M25"),
  c("polars", "r-universe:https://rpolars.r-universe.dev", "M13 (DIDmultiplegtDYN)")))
names(REWARD_R_PACKAGES) <- c("package", "source", "used_by")
PACKAGE_MIRRORS <- c(synthdid = "https://skranz.r-universe.dev")   # v20.54: the authors' r-universe does not exist; this build is their commit a05029b

reward_repos <- function() {
  r0 <- getOption("repos")
  if (is.null(r0) || !length(r0) || is.na(r0["CRAN"]) || identical(unname(r0["CRAN"]), "@CRAN@")) r0 <- c(r0[!names(r0) %in% "CRAN"], CRAN = "https://cloud.r-project.org")
  r0
}
# v20.56: Windows and macOS have pre-built CRAN binaries -- those are installed FIRST, and a source build (which needs Rtools
# on Windows) is attempted only when no binary exists for this R version AND the package can be built here: a pure-R
# package needs no tools; one with C / C++ / Fortran code needs Rtools (Windows) or Xcode's tools (macOS). Without them
# the chain says so and the models that use the package fall back to the engine -- nothing stops.
# (Your run: "Rtools is required to build R packages" -- R had chosen a newer SOURCE version over the binary; that choice is
#  now switched off: options(install.packages.compile.from.source = "never").)
binary_platform <- function() .Platform$OS.type == "windows" || identical(Sys.info()[["sysname"]], "Darwin")
has_build_tools <- function() {
  if (requireNamespace("pkgbuild", quietly = TRUE)) return(isTRUE(tryCatch(pkgbuild::has_build_tools(debug = FALSE), error = function(e) FALSE)))
  if (.Platform$OS.type == "windows") return(nzchar(Sys.which("make")) || any(nzchar(Sys.getenv(c("RTOOLS45_HOME", "RTOOLS44_HOME", "RTOOLS43_HOME", "RTOOLS42_HOME", "RTOOLS40_HOME")))))
  nzchar(Sys.which("make")) && (nzchar(Sys.which("gcc")) || nzchar(Sys.which("clang")))
}
needs_compilation <- function(p, repos = reward_repos()) {
  ap <- tryCatch(utils::available.packages(repos = repos), error = function(e) NULL)
  if (is.null(ap) || !p %in% rownames(ap)) return(NA)
  identical(tolower(ap[p, "NeedsCompilation"]), "yes")
}
RTOOLS_URL <- "https://cran.r-project.org/bin/windows/Rtools/"
pkg_installed <- function(p) requireNamespace(p, quietly = TRUE)
pkg_version <- function(p) tryCatch(as.character(utils::packageVersion(p)), error = function(e) NA_character_)
.pkg_msg <- function(...) if (exists("info", mode = "function")) info(...) else message("[INFO]    ", paste0(..., collapse = ""))
.pkg_try <- function(expr) suppressWarnings(tryCatch({ utils::capture.output(expr, type = "message"); TRUE }, error = function(e) FALSE))

install_package_chain <- function(p, verbose = TRUE) {
  if (pkg_installed(p)) return("already installed")
  repos <- reward_repos(); src <- REWARD_R_PACKAGES$source[match(p, REWARD_R_PACKAGES$package)]; if (is.na(src)) src <- "CRAN"
  old_opts <- options(Ncpus = max(1L, parallel::detectCores()), install.packages.compile.from.source = "never"); on.exit(options(old_opts), add = TRUE)
  how <- NA_character_; bin <- binary_platform(); tools <- has_build_tools()
  step <- function(label, expr) { if (!is.na(how)) return(invisible()); if (verbose) .pkg_msg(sprintf("installing '%s': %s ...", p, label)); .pkg_try(expr); if (pkg_installed(p)) how <<- label }
  if (startsWith(src, "r-universe:")) {                               # polars: a pre-built library from r-universe (NOT_CRAN on Linux)
    step(sprintf("r-universe (%s), pre-built", sub("^r-universe:", "", src)), { Sys.setenv(NOT_CRAN = "true"); utils::install.packages(pkgs = p, repos = c(sub("^r-universe:", "", src), repos)) })
  }
  # 1. CRAN, PRE-BUILT: the binary on Windows / macOS (never a source build here, even when the source is newer); on Linux the
  #    repository's build (a binary from a Posit Package Manager repository when one is set, else the source)
  if (bin) step("CRAN pre-built binary", utils::install.packages(pkgs = p, repos = repos, type = "binary"))
  else step("CRAN (the repository's build for this platform)", utils::install.packages(pkgs = p, repos = repos))
  if (startsWith(src, "github:")) {
    repo <- sub("^github:", "", src); owner <- sub("/.*", "", repo)
    step(sprintf("the author's r-universe (%s.r-universe.dev, pre-built)", owner), utils::install.packages(pkgs = p, repos = c(sprintf("https://%s.r-universe.dev", owner), repos), type = if (bin) "binary" else getOption("pkgType")))
    if (!pkg_installed("remotes")) .pkg_try(utils::install.packages(pkgs = "remotes", repos = repos, type = if (bin) "binary" else getOption("pkgType")))
    if (pkg_installed("remotes")) {                                     # these three are pure R: building them needs no Rtools
      step(sprintf("GitHub source (%s)", repo), remotes::install_github(repo, upgrade = "never", dependencies = TRUE, quiet = TRUE))
      step("the GitHub source archive (no API call)", remotes::install_url(sprintf("https://github.com/%s/archive/HEAD.tar.gz", repo), upgrade = "never", dependencies = TRUE, quiet = TRUE))
    }
    if (p %in% names(PACKAGE_MIRRORS)) step(sprintf("a mirror of the same code (%s)", PACKAGE_MIRRORS[[p]]), utils::install.packages(pkgs = p, repos = c(PACKAGE_MIRRORS[[p]], repos), type = if (bin) "binary" else getOption("pkgType")))
  }
  if (is.na(how)) {                                                    # 2. no pre-built package for this R version: the SOURCE, when it can be built here
    comp <- needs_compilation(p, repos)
    if (isTRUE(comp) && !tools) {
      if (verbose) message("[WARNING] '", p, "' has no pre-built binary for R ", R.version$major, ".", R.version$minor, " and needs compilation, but the build tools are not installed",
                           if (.Platform$OS.type == "windows") paste0(" -- install Rtools (", RTOOLS_URL, ", the version matching your R) and run 00_SETUP.R again;") else " (Xcode command-line tools / build-essential);",
                           " until then the models that use it fall back to the engine")
    } else step(if (isTRUE(comp)) "CRAN source, compiled here (Rtools / build tools found)" else "CRAN source (pure R, no compilation needed)",
                utils::install.packages(pkgs = p, repos = repos, type = "source"))
  }
  if (verbose) { if (!is.na(how)) .pkg_msg(sprintf("'%s' %s installed -- %s", p, pkg_version(p), how)) else message("[WARNING] '", p, "' could not be installed from any route (CRAN binary, source, r-universe, GitHub, archive, mirror)") }
  if (is.na(how)) "NOT installed" else how
}

build_tools_line <- function() {
  if (.Platform$OS.type == "windows") sprintf("Rtools: %s (needed only when a package has no pre-built binary for R %s.%s; %s)", if (has_build_tools()) "found" else "not installed", R.version$major, R.version$minor, RTOOLS_URL)
  else sprintf("build tools: %s (needed only when no pre-built binary exists)", if (has_build_tools()) "found" else "not found")
}

# v20.58: the packages THIS project needs -- every package whose 'used by' names no model (the pipeline itself) or one of PIPELINE_MODELS
models_named <- function(txt) {
  m <- regmatches(txt, gregexpr("M[0-9]{2}(\\s*-\\s*M[0-9]{2})?", txt))[[1]]
  unique(unlist(lapply(m, function(x) { r <- as.integer(regmatches(x, gregexpr("[0-9]{2}", x))[[1]]); sprintf("M%02d", seq(r[1], r[length(r)])) })))
}
project_packages <- function(models = PIPELINE_MODELS) {
  if (is.null(models) || !length(models)) return(REWARD_R_PACKAGES$package)
  keep <- vapply(REWARD_R_PACKAGES$used_by, function(u) { ids <- models_named(u); !length(ids) || any(ids %in% models) }, logical(1))
  REWARD_R_PACKAGES$package[keep]
}
ensure_packages <- function(pkgs = project_packages(), install = AUTO_INSTALL_PACKAGES, verbose = TRUE) {
  rows <- lapply(pkgs, function(p) {
    how <- if (pkg_installed(p)) "installed" else if (isTRUE(install)) install_package_chain(p, verbose = verbose) else "NOT installed"
    data.frame(package = p, installed = pkg_installed(p), version = pkg_version(p), how = how,
               used_by = REWARD_R_PACKAGES$used_by[match(p, REWARD_R_PACKAGES$package)], stringsAsFactors = FALSE)
  })
  do.call(rbind, rows)
}

confirm_packages <- function(pkgs = project_packages(), install = AUTO_INSTALL_PACKAGES, write = TRUE, quiet = FALSE) {
  st <- ensure_packages(pkgs, install = install, verbose = !quiet)
  n <- sum(st$installed); N <- nrow(st)
  if (write && exists("RESULTS_DIR")) { dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
    try(utils::write.csv(cbind(st, r_version = paste(R.version$major, R.version$minor, sep = "."), checked = format(Sys.time(), "%Y-%m-%d %H:%M:%S")),
                         file.path(RESULTS_DIR, "PACKAGE_STATUS_R.csv"), row.names = FALSE), silent = TRUE) }
  if (!quiet) {
    if (n == N) message(sprintf("[OK]      R packages: %d of %d installed (pre-built first, source where no binary exists) -- confirmed for this run%s",
                                n, N, if (any(st$how != "installed")) sprintf("; installed now: %s", paste(st$package[st$how != "installed"], collapse = ", ")) else ""))
    else {
      miss <- st[!st$installed, ]
      message(sprintf("[WARNING] R packages: %d of %d installed -- MISSING: %s", n, N,
                      paste(sprintf("%s (%s)", miss$package, miss$used_by), collapse = "; ")))
      message("[WARNING] the models these packages serve fall back to the engine or stop with the install command; run 00_SETUP.R (needs internet), or set AUTO_INSTALL_PACKAGES <- TRUE in lib/reward_paths.R; ", build_tools_line())
    }
  }
  invisible(st)
}

# the run-time guard every model calls: install through the chain when allowed, else stop with the command
need <- function(p, where = "CRAN") {
  if (pkg_installed(p)) return(invisible(TRUE))
  if (isTRUE(AUTO_INSTALL_PACKAGES)) install_package_chain(p, verbose = TRUE)
  if (!pkg_installed(p)) stop(sprintf("install '%s' (%s) -- 00_SETUP.R installs every package (needs internet)", p, where))
  invisible(TRUE)
}
