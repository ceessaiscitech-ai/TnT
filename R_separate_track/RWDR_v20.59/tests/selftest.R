# selftest.R -- run the WHOLE R pipeline on a small synthetic export with a KNOWN effect (+0.05), inside the real
# Haligeri polygons, in a temporary folder. Takes a few minutes. Run it once after 00_SETUP.R (RStudio: Source).
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
tryCatch({
tmp <- file.path(tempdir(), "reward_selftest"); unlink(tmp, recursive = TRUE); dir.create(tmp)
Sys.setenv(REWARD_R_ROOT = tmp, REWARD_FUND_PATH = file.path(tmp, "no_fund_file.xlsx"))   # (your fund file is not part of the test)
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
suppressPackageStartupMessages(library(sf)); set.seed(1)
poly <- st_read(SHAPEFILE, quiet = TRUE); h <- poly[poly$SWSiD_All == 7, ]                            # Haligeri: core + rings 1-5
pts <- do.call(rbind, lapply(0:5, function(r) { p <- st_sample(h[h$buff_km == r, ], 150); st_sf(buff_km = r, geometry = p) }))
ll <- st_coordinates(st_transform(pts, 4326)); rng <- pts$buff_km
dir.create(file.path(tmp, "Haligeri"))
for (y in 2016:2025) {
  eff <- ifelse(rng == 0 & y >= 2022, 0.05, 0); shock <- rnorm(1, 0, 0.004)
  d <- data.table(latitude = ll[, 2], longitude = ll[, 1], buff_km = rng, SWSiD_All = 7, SubwshedID = "U1",
                  NDVI = 0.30 + 0.01 * (y - 2016) + shock + eff + rnorm(length(rng), 0, 0.01), Rain = 600 + rnorm(length(rng), 0, 30),
                  Tmax = 33, Tmean = 26 + rnorm(length(rng), 0, 0.5), Tmin = 19, LandUse = 1 + (seq_along(rng) %% 3))
  fwrite(d, file.path(tmp, "Haligeri", sprintf("CSV_%d_yearly_tile0.csv", y)))
}
run_prep(); d <- prepare_design()
r <- run_model_R("M01", "NDVI", d)
ok_ <- is.numeric(r$estimate) && length(r$estimate) == 1L && is.finite(r$estimate) && abs(r$estimate - 0.05) < 0.01   # v20.58: no estimate = FAIL, said
cat(sprintf("\nSELF-TEST: estimate %s (truth 0.0500) -> %s\n", if (is.numeric(r$estimate) && length(r$estimate) == 1L) sprintf("%.4f", r$estimate) else "none",
            if (ok_) "PASS" else paste("FAIL -- send this output", if (!is.null(r$error)) paste0("(", r$error, ")") else "")))
for (m in c("M02", "M16", "M23")) run_model_R(m, "NDVI", d)
}, finally = .restore_env())
