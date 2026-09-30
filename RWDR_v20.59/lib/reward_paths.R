# reward_paths.R -- where the R pipeline reads and writes, and its design settings (v20.45; v20.57: the design is set in each MODEL notebook).
R_ENGINE_VERSION <- "20.59"
# The ONLY line you normally change is ROOT. The exports live under ROOT (any depth, like D:\LKT\TST_Artal for Python);
# everything the pipeline writes goes to ROOT/output (the same layout as the Python pipeline).
DEFAULT_ROOT      <- "D:/LKT/RWDR/data"                                          # v20.50: the RWDR project's data folder
ROOT              <- Sys.getenv("REWARD_R_ROOT", DEFAULT_ROOT)
if (nzchar(Sys.getenv("REWARD_R_ROOT")) && !nzchar(Sys.getenv("REWARD_TEST_RUN")))         # v20.51: a test's folder left behind
  message("[WARNING] data root = ", ROOT, " -- taken from REWARD_R_ROOT, which a test sets. Your data: ", DEFAULT_ROOT,
          ". Run  Sys.unsetenv('REWARD_R_ROOT')  (or Session -> Restart R) and run this notebook again.")
LEGACY_ROOT       <- "D:/LKT/TST_ArtalR"                                         # the data folder before MIGRATE_DATA.bat
# v20.54: a Windows drive path on Linux / macOS (a test machine) is not a path there -- dir.create() below made a folder
# literally named "D:" inside the project. There the root becomes ~/REWARD_data/<project>/data (as in Python; said once).
# Windows is unchanged.
portable_root <- function(p, quiet = FALSE) {
  if (.Platform$OS.type == "windows" || !grepl("^[A-Za-z]:[/\\\\]", p)) return(p)
  parts <- strsplit(sub("^[A-Za-z]:[/\\\\]+", "", p), "[/\\\\]+")[[1]]; parts <- parts[nzchar(parts)]
  keep <- if (length(parts) >= 2 && tolower(parts[length(parts)]) %in% c("data", "input", "inputs", "exports", "output")) tail(parts, 2) else tail(parts, 1)
  q <- do.call(file.path, as.list(c(path.expand("~"), "REWARD_data", keep)))
  if (!quiet) message("[INFO]    ", p, " is a Windows path; on this system the data root is ", q, " (set REWARD_R_ROOT to change it)")
  q
}
if (!nzchar(Sys.getenv("REWARD_R_ROOT")) && !dir.exists(portable_root(ROOT, TRUE)) && dir.exists(portable_root(LEGACY_ROOT, TRUE))) {
  message("[INFO]    ", ROOT, " does not exist yet -- using the old data folder ", LEGACY_ROOT, " (run MIGRATE_DATA.bat to move it)")
  ROOT <- LEGACY_ROOT
}
ROOT              <- portable_root(ROOT)
# v20.58: the models THIS project carries -- NULL = all 45 (RWDR). The four-model project (RWD_4Models) sets c("M01", "M02", "M16", "M34"):
# its R_P00 prepares only what they need, and the package checks and tests cover only them. Its output folder is its own (OUTPUT_SUBDIR).
if (!exists("PIPELINE_MODELS")) PIPELINE_MODELS <- NULL
OUTPUT_SUBDIR     <- "output"
OUTPUT_DIR        <- file.path(ROOT, OUTPUT_SUBDIR)
RESULTS_DIR       <- file.path(OUTPUT_DIR, "results")
PANEL_PATH        <- file.path(OUTPUT_DIR, "did_panel_full.parquet")
DESIGN_PATH       <- file.path(OUTPUT_DIR, "R_design.json")
CROSSWALK_PATH    <- "D:/LKT/RWD_Sub_watershed_final_list.xlsx"                                  # shared with Python
FUND_RELEASE_PATH <- Sys.getenv("REWARD_FUND_PATH", "D:/LKT/Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx")    # shared with Python

# the bundle's own R folder (set by every notebook's setup chunk before sourcing this file)
if (!exists("R_HOME_DIR")) R_HOME_DIR <- normalizePath(".", winslash = "/")
SHAPEFILE  <- Sys.getenv("REWARD_SHAPEFILE", file.path(R_HOME_DIR, "data", "sites", "SWSs20_KarnatakaAll5k.shp"))   # 20 sub-watersheds x (core + rings 1-5); the env var is for the tests (v20.55)
SITES_CSV  <- Sys.getenv("REWARD_SITES_CSV", file.path(R_HOME_DIR, "data", "sites", "sites.csv"))   # implementation year per sub-watershed (the env var is for the tests)
GROUND_DIR <- file.path(R_HOME_DIR, "data", "ground")                              # benchmark-site (BM) data

# ---- THE DESIGN (v20.57): the DEFAULTS of every option a MODEL notebook applies when it runs. Each R_Mxx notebook / Rmd has the
#      same options in its settings cell -- set them THERE and re-run that model; R_P00 (the panel) is never re-run for a design
#      choice. What you set is what runs: DESIGN IN EFFECT (printed by model_design(), saved as DESIGN_IN_EFFECT.csv next to every
#      result) lists each option, the value used and where it came from.
DESIGN_MODE       <- "recommended"      # "recommended": an option set to "data" is chosen FROM THE DATA (DESIGN_RECOMMENDATION.md) |
                                        #   "manual": "data" = every ring / every year. A value you set is ALWAYS used as set (both modes)
TREATMENT_TIMING  <- "fund"             # "fund": each sub-watershed's first treated SEASON from your fund workbook (release timing,
                                        #   back-cast before the file, the season AFTER the start) | "registry": sites.csv | "fixed"
TREATMENT_YEAR    <- 2022               # "fixed" timing, and the fall-back for a sub-watershed the fund file / registry does not date
FUND_START_RULE   <- "backcast"         # "backcast" | "share" (the amount reaches FUND_START_SHARE of the target) | "file_start"
FUND_START_SHARE  <- 0.10; FUND_RATE_MONTHS <- 12L
FUND_DOSE_BEFORE_FILE <- "backcast"     # the dose between the back-cast start and the file's first month: "backcast" (flagged) | "missing"
DOSE_VARIABLE     <- "dose_intensity_per_ha"   # amount released / treatment area | "dose_amount_sws" | "dose_share_of_target"
CONTROL_RINGS     <- "data"             # "data" | 1:5 | 1:3 | c(2, 4)
PRE_YEARS         <- "data"             # "data" | NA (every year before the start) | a number of years
POST_YEARS        <- "data"             # "data" | NA (every year from the start) | a number of years
SEASONS           <- "all"              # YOUR RULE: annual composite + Kharif / Rabi / Zaid together (year AND season variation) | "seasonal"
                                        #   (the three seasons only) | "yearly" | one or several seasons: "Rabi", c("Rabi", "Zaid") | "auto" = the data
EXCLUDE_TRANSITION_YEAR <- FALSE        # TRUE = the first treated year of each series leaves the sample (robustness)
PERIOD_RULE       <- "treat"            # v20.59 (YOUR RULE, R_P00): what sets the panel's post (1) / pre (0) -- "treat": the exports' Treat column
                                        #   (1 = post, 0 = pre; a row without a usable flag takes the Year rule, counted) | "year": Year >= TREATMENT_YEAR
                                        #   for every row (v20.58) | "both": the Treat column AND the Year rule must AGREE -- a row where they disagree
                                        #   (or whose flag is not 0 / 1) LEAVES the DID-ready panel, counted per input file (input_design_audit_R.csv).
                                        #   The treatment AREA is never read from Treat: buff_km / distance 0 = the treatment area, 1-5 = the control rings
UNIT_FE           <- "pixel_season"     # one fixed effect per pixel x season series | "pixel"
COHORT_OFFSET     <- 0L                 # shift every cohort by N years (robustness)
SUB_WATERSHEDS    <- "data"             # v20.58: the sub-watershed(s) a run processes: "data" = every one with >= FRAGMENT_MIN_SHARE of the largest
                                        #   one's own rows (ONE export = its own sub-watershed) | "major" (the largest only) | names or ids
FRAGMENT_RULE     <- "drop"             # YOUR RULE (v20.58, the location rule): rows of sub-watersheds NOT processed and rows outside every polygon
                                        #   leave every group (treated / control, pre / post) | "keep"
FRAGMENT_MIN_SHARE <- 0.05              # a sub-watershed with fewer own rows than this share of the largest one is not processed ("data")
COVARIATES        <- c("Rain", "Tmax", "Tmean", "Tmin")   # "all" = the FOUR weather covariates; LandUse is never one
OUTCOMES          <- c("NDVI", "EVI", "SAVI", "LAI", "NDRE", "NDMI", "LSWI", "NDWI", "SMDI", "VCI", "TCI", "VHI",
                       "ESI", "WSI", "WSSI", "RUSLE", "AGB")
DESIGN_OUTCOME    <- "NDVI"             # the outcome whose data decide breaks / spillover (the "data" options)

# ---- data rules (the same as the Python pipeline)
PIXEL_SIZE_M        <- 10
PIXEL_OVERLAP_MIN   <- 0.65             # a later export's pixel IS an earlier pixel when their 10 m footprints overlap this much
MIN_SWS_CLUSTERS    <- 6                # >= 6 sub-watersheds -> cluster on them; fewer -> on years
SCREEN_MIN_COVERAGE <- 0.05             # a year-season with < 5 % of the typical pixel coverage is not data
N_MAX_UNITS         <- NULL; N_MAX_PIXELS_MIXED <- NULL; N_MAX_ML <- NULL; N_MAX_SPATIAL <- NULL   # v20.57 YOUR 98 % RULE: NULL = no fixed sample size -- a model
                                                                          #   samples ONLY what would not fit below 98 % of the RAM (units_that_fit);
                                                                          #   a number caps it by hand. v20.55: 2 M / 400 k / 4 M (fixed)
# v20.59: EVERY logical processor of the machine. On Windows a box with more than 64 logical processors (your 2 x EPYC) is split into
# PROCESSOR GROUPS and detectCores() reports ONE group (64); the CIM / WMI count covers them all (as Python's _hardware.logical_cores_all).
all_logical_cores_R <- function() {
  n <- suppressWarnings(as.integer(parallel::detectCores())); if (!isTRUE(n >= 1L)) n <- 1L
  if (.Platform$OS.type == "windows") {
    m <- tryCatch(suppressWarnings(as.integer(system2("powershell", c("-NoProfile", "-Command",
           "(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors"), stdout = TRUE, stderr = FALSE)[1])), error = function(e) NA_integer_)
    if (!isTRUE(m >= 1L)) m <- tryCatch(suppressWarnings(as.integer(Sys.getenv("NUMBER_OF_PROCESSORS"))), error = function(e) NA_integer_)
    if (isTRUE(m > n)) n <- m
  }
  n
}
N_THREADS           <- max(1L, all_logical_cores_R())           # v20.52: EVERY core (no reserve, no split); v20.59: every processor group
SITE_GEOMETRY_CHECK <- TRUE                                     # v20.59 (as Python): every row's sub-watershed from its latitude / longitude in the shapefile
                                                                #   (confirmed / corrected / assigned; the file's id only labels) | FALSE = trust the file's id
BUFF_FROM_GEOMETRY  <- FALSE                                    # v20.59 (as Python): TRUE = buff_km always from the polygon ring | FALSE = only where the
                                                                #   sub-watershed was corrected or assigned (a confirmed row keeps the exported ring, reported)
EXCLUDE_GAPFILLED   <- TRUE                                     # v20.52: rows filled from history are not estimated on (as Python)
OUTCOME_SCREEN      <- "drop"                                  # v20.59: the outcome screen -- "drop": a year-season constant across pixels (a fill value)
                                                               #   or with collapsed coverage leaves every model, its evidence in OUTCOME_SCREEN_<outcome>.csv |
                                                               #   "keep": reported and KEPT (results tagged _screenKept) | "off". Set per model in its notebook
MEMORY_SHARE        <- 1.0                                     # optional manual cap (as _paths.MEMORY_SHARE in Python)
# v20.58 -- BEYOND 98 % OF THE RAM (never before): M01, M02, M16 and M34 go OUT OF CORE instead of stopping -- exact, never sampled
# (lib/reward_outofcore.R: pixel partitions, the same R code per partition, the two-way FE solved from their cross-products). The engines
# in YOUR order; one that is not installed is named with the reason and the next is used; the R batches are always the last resort:
#   "dask"    Dask (Python): keeps the familiar PyData ecosystem, no Java -- the partition tasks on every core
#   "spark"   Apache Spark (pyspark, local[all cores]; Java 17+): the enterprise engine for heavy SQL-like warehousing pipelines
#   "batches" R itself: one partition after another in this session (always available)
OUT_OF_CORE         <- c("dask", "spark", "batches")
OUT_OF_CORE_SPILL_DIR <- ""                                    # where the partitions go: "" = <the panel's folder>/_out_of_core_R
PYTHON_EXE          <- ""                                      # the Python with dask / pyspark: "" = python3 / python / py -3 on the PATH
OVERLAP_ROWS        <- "drop"           # YOUR RULE (v20.58): overlapping pixels leave every group -- a pixel TREATED in another processed sub-watershed
                                        #   (as a control), a repeated pixel-year-season, a near-duplicate pixel (footprint >= PIXEL_OVERLAP_MIN), a pixel
                                        #   whose ring the exports disagree on; "keep" keeps them (tag _keepOverlap)
POOLED_FE           <- "site_period"    # v20.55 (as Python P00 POOLED_FE): with SEVERAL sub-watersheds in the panel the period fixed effect is
                                        # sub-watershed x year x season ("site_period": each sub-watershed's own shocks are absorbed, the
                                        # effect is identified core vs rings WITHIN each sub-watershed) | "period": one year x season effect
                                        # shared by all sub-watersheds. With ONE sub-watershed both are the same.
AUTO_INSTALL_PACKAGES <- TRUE           # v20.55: a package a step needs and that is not installed is installed THEN, through the same chain
                                        # as 00_SETUP.R (CRAN binary -> source -> author's r-universe -> GitHub -> archive -> mirror); every
                                        # notebook confirms "N of N R packages installed" at its start (results/PACKAGE_STATUS_R.csv)
ALLOW_NEGATIVE_COVARIATES <- FALSE                             # v20.54 (as Python): TRUE removes YOUR negative-covariate barrier
                                                               # (negative Rain / temperature stay as they are); re-run R_P00
ZERO_RULE_EXCEPT    <- character(0)                            # v20.54 (as Python): covariates whose exported 0 is a real value, e.g. "Rain"

SEASON_LABEL <- c("0" = "Yearly", "1" = "Kharif", "2" = "Rabi", "3" = "Zaid")
dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)

# v20.55: the package chain and the run-time confirmation (install_package_chain, ensure_packages, confirm_packages, need)
source(file.path(R_HOME_DIR, "lib", "reward_packages.R"), local = environment())
# v20.57: your fund workbook as each sub-watershed's treatment timing and dose (used by every model when it runs)
source(file.path(R_HOME_DIR, "lib", "reward_fund.R"), local = environment())
