# reward_prep.R -- the DATA PREPARATION pipeline in R (v20.45; v20.55: step for step the Python P00).
#   run_prep()  -> ROOT/output/did_panel_full.parquet (+ reports), then the design every model inherits.
# YOUR RULE (v20.55): the data are structured EXACTLY as the Python pipeline structures them. Every rule below names the
# Python function it mirrors; `validate_r_parity.py` (Python project) runs both pipelines on one set of exports and
# compares the panel and the estimation samples row for row.
suppressPackageStartupMessages({ library(data.table) })

OUTCOME_VARS_CORE <- c("NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE")     # _prep_common.OUTCOME_VARS
DROUGHT_VARS      <- c("ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI")
OUTCOME_VARS   <- c("NDVI", "EVI", "SAVI", "LAI", "NDRE", "NDMI", "LSWI", "NDWI", "SMDI", "VCI", "TCI", "VHI", "ESI", "WSI", "WSSI", "RUSLE", "AGB")
WEATHER_VARS   <- c("Rain", "Tmax", "Tmean", "Tmin")
DESCRIPTOR_VARS <- c("LandUse", "GapFilled", "Coverage", "OptTier", "SrcOpt")
# v20.58: a panel for a SUBSET of the models (PIPELINE_MODELS, reward_paths.R) leaves out the columns only other models read -- the land use
# (M10's third difference, the ML models' effect splits), as _prep_common.panel_columns_left_out
PANEL_COLUMNS_USED_BY_R <- c(LandUse = "M10 M26 M39-M45", LandUseDW = "M10 M39-M45")
panel_columns_left_out_R <- function(models = if (exists("PIPELINE_MODELS")) PIPELINE_MODELS else NULL) {
  if (is.null(models) || !length(models)) return(character(0))
  names(PANEL_COLUMNS_USED_BY_R)[!vapply(PANEL_COLUMNS_USED_BY_R, function(u) any(models_named(u) %in% models), logical(1))]
}   # v20.52: SrcOpt = the optical source (1 S2 SR, 2 S2 TOA, 3 Landsat, 4 MODIS 500 m, 5 projected)
EXTRA_VARS     <- c("DataYear", "SrcET", "NObsV", "NObsT", "YrRel", "LandUseDW", "ESI_Anom")            # kept as Python keeps them (QC; NObsV ranks duplicates)
ZERO_RULE_VARS <- c(OUTCOME_VARS_CORE, DROUGHT_VARS, WEATHER_VARS)                                        # _prep_common.ZERO_RULE_VARS
INPUT_EXTENSIONS <- c(".csv", ".csv.gz", ".tsv", ".parquet", ".pq", ".feather", ".xlsx", ".xlsm", ".xls")   # _prep_common.INPUT_EXTENSIONS
CANONICAL <- c("UID", "Year", "Season", "SubwshedID", "SWSiD_All", "SWS_Name", "Treat", "latitude", "longitude", "buff_km", "LandUse",
               OUTCOME_VARS_CORE, WEATHER_VARS, DROUGHT_VARS, "DataYear", "Coverage", "SrcOpt", "SrcET", "NObsV", "NObsT", "YrRel",
               "LandUseDW", "ESI_Anom", "GapFilled", "OptTier")
ALIASES <- c(lat = "latitude", lon = "longitude", long = "longitude", lng = "longitude",                       # _prep_common.ALIASES (the same list)
             swsid_all = "SWSiD_All", swsid = "SWSiD_All", sws_id = "SWSiD_All", site_id = "SWSiD_All", siteid = "SWSiD_All", sws = "SWSiD_All",
             subwshed = "SWS_Name", sws_name = "SWS_Name", swsname = "SWS_Name", sub_watershed_name = "SWS_Name", subwatershed_name = "SWS_Name",
             sws_nm = "SWS_Name", subwshed_name = "SWS_Name", sub_watershed_id = "SubwshedID", subwatershedid = "SubwshedID", sub_wshed_id = "SubwshedID",
             watershedid = "SubwshedID", treatment = "Treat", is_treated = "Treat", buffer_km = "buff_km", bufferkm = "buff_km", land_use = "LandUse",
             landuse_dw = "LandUseDW", pixel_uid = "UID", point_id = "UID", rainfall_mm = "Rain", rainfallmm = "Rain",
             soil_moisture_drought_idx = "SMDI", soilmoisturedroughtindex = "SMDI", distance = "buff_km", seasons = "Season", season_code = "Season",
             years = "Year", yr = "Year", buff = "buff_km", buffer = "buff_km", buffkms = "buff_km", lat_dd = "latitude", lon_dd = "longitude")
ESSENTIAL_COLS <- c("Year", "Season", "SubwshedID", "Treat", "latitude", "longitude", "buff_km")       # _prep_common.ESSENTIAL_COLS
SEASON_CODE <- c(yearly = 0L, annual = 0L, kharif = 1L, monsoon = 1L, rabi = 2L, winter = 2L, zaid = 3L, summer = 3L)   # _SEASON_ALIAS + SEASON_CODE
VALID_BUFFERS <- 0:5
DROP_ROWS_WITHOUT_OUTCOME <- TRUE                                                                      # _prep_common.DROP_ROWS_WITHOUT_OUTCOME
NEAR_DUPLICATE_PIXELS <- TRUE; DEDUP_PRIORITY <- "newer"                                               # _prep_common (P00_Settings)
DEDUP_FILL_FROM_DUPLICATES <- FALSE   # v20.58 (your rule): a REPEATED row (the same pixel, year and season in another export) is dropped WHOLE --
                                      # none of its values enters the panel, not even into a gap of the kept row | TRUE = fill the kept row's
                                      # gaps from it (exports split by variable; until v20.57 always on). As _prep_common.DEDUP_FILL_FROM_DUPLICATES
norm_col <- function(x) gsub("[^a-z0-9]", "", tolower(x))

# ---------------------------------------------------------------- 1. the export files  (_prep_common.discover_input_files, parse_filename)
input_ext <- function(f) { low <- tolower(f); for (e in INPUT_EXTENSIONS[order(-nchar(INPUT_EXTENSIONS))]) if (endsWith(low, e)) return(e); NA_character_ }
parse_export_name <- function(base) {
  # 1) the exact export convention CSV_[Site_]YYYY_Season_tileN[_subN].ext; 2) a year 2010-2039 and a season word anywhere
  # in the name (any separators, synonyms monsoon / winter / summer / annual). NA where the name does not say.
  m <- regmatches(base, regexec("^CSV_(?:([A-Za-z][A-Za-z0-9-]*)_)?([0-9]{4})_([A-Za-z]+)_tile([0-9]+)(?:_sub([0-9]+))?\\.(csv|parquet|xlsx|xlsm|xls|feather|tsv|gz)$", base, ignore.case = TRUE))[[1]]
  if (length(m) > 1 && tolower(m[4]) %in% names(SEASON_CODE)) return(list(Year = as.integer(m[3]), Season = unname(SEASON_CODE[tolower(m[4])]), site = if (nzchar(m[2])) m[2] else NA_character_, how = "strict"))
  stem <- base; for (e in INPUT_EXTENSIONS[order(-nchar(INPUT_EXTENSIONS))]) if (endsWith(tolower(stem), e)) { stem <- substr(stem, 1, nchar(stem) - nchar(e)); break }
  ys <- unique(regmatches(stem, gregexpr("(?<![0-9])20[1-3][0-9](?![0-9])", stem, perl = TRUE))[[1]])
  ss <- unique(tolower(regmatches(stem, gregexpr("(?<![A-Za-z])(kharif|rabi|zaid|yearly|annual|summer|monsoon|winter)(?![A-Za-z])", stem, perl = TRUE, ignore.case = TRUE))[[1]]))
  list(Year = if (length(ys) == 1) as.integer(ys) else NA_integer_, Season = if (length(ss) == 1) unname(SEASON_CODE[ss]) else NA_integer_, site = NA_character_, how = "loose")
}
season_of <- function(x) vapply(x, function(z) parse_export_name(z)$Season, integer(1), USE.NAMES = FALSE)   # kept (v20.45 name)
discover_exports <- function() {
  f <- list.files(ROOT, recursive = TRUE, full.names = TRUE, all.files = FALSE)
  f <- f[!is.na(vapply(f, input_ext, character(1))) & !grepl("^(\\.|~\\$)", basename(f))]
  out_n <- normalizePath(OUTPUT_DIR, winslash = "/", mustWork = FALSE)
  f <- f[!startsWith(normalizePath(f, winslash = "/", mustWork = FALSE), out_n)]
  f <- f[!normalizePath(f, winslash = "/", mustWork = FALSE) %in% normalizePath(c(CROSSWALK_PATH, FUND_RELEASE_PATH), winslash = "/", mustWork = FALSE)]
  b <- basename(f); pm <- lapply(b, parse_export_name)
  rel <- substring(normalizePath(f, winslash = "/", mustWork = FALSE), nchar(normalizePath(ROOT, winslash = "/", mustWork = FALSE)) + 2L)
  x <- data.table(file = f, Year = vapply(pm, function(z) z$Year, integer(1)), Season = vapply(pm, function(z) z$Season, integer(1)),
                  sws_hint = vapply(pm, function(z) z$site, character(1)), folder = basename(dirname(f)), relpath = rel, mtime = as.numeric(file.mtime(f)))
  ids <- sws_names(); nm <- match_sws_name(x$sws_hint); nm[is.na(nm)] <- match_sws_name(x$relpath[is.na(nm)])   # v20.49: the 80 % rule
  x[, sws_file := as.integer(names(ids)[match(nm, ids)])]
  by <- table(vapply(f, input_ext, character(1)))
  ok(sprintf("%d export files under %s (%s)%s", nrow(x), ROOT, paste(sprintf("%d %s", by, names(by)), collapse = ", "),
             if (any(is.na(x$Year) | is.na(x$Season))) sprintf(" -- %d file name(s) carry no Year/Season: read from the columns inside", sum(is.na(x$Year) | is.na(x$Season))) else ""))
  x
}

# ---------------------------------------------------------------- 2-3. read, harmonise, keys, buffers, missing values, negative covariates
read_export_raw <- function(file) {                                                  # every format the Python pipeline reads
  ext <- input_ext(file)
  if (is.na(ext)) stop("unsupported export format: ", basename(file))
  if (ext %in% c(".csv", ".tsv")) return(fread(file, showProgress = FALSE, sep = if (ext == ".tsv") "\t" else "auto"))
  if (ext == ".csv.gz") return(if (requireNamespace("R.utils", quietly = TRUE)) fread(file, showProgress = FALSE)
                              else fread(cmd = sprintf("gzip -dc %s", shQuote(file)), showProgress = FALSE))
  if (ext %in% c(".parquet", ".pq")) { if (!requireNamespace("arrow", quietly = TRUE)) stop("install arrow to read ", basename(file)); return(as.data.table(arrow::read_parquet(file))) }
  if (ext == ".feather") { if (!requireNamespace("arrow", quietly = TRUE)) stop("install arrow to read ", basename(file)); return(as.data.table(arrow::read_feather(file))) }
  if (!requireNamespace("readxl", quietly = TRUE)) stop("install readxl to read ", basename(file))
  sh <- lapply(readxl::excel_sheets(file), function(s) as.data.table(suppressMessages(readxl::read_excel(file, sheet = s))))
  sh <- Filter(function(d) { nm <- harmonise_names(names(d)); all(c("latitude", "longitude") %in% nm) }, sh)     # data sheets only
  if (!length(sh)) stop("no sheet with pixel latitude/longitude in ", basename(file))
  rbindlist(sh, fill = TRUE)
}
harmonise_names <- function(cols) {                                                  # _prep_common.harmonize_columns + dedupe_mapping
  canon <- setNames(CANONICAL, norm_col(CANONICAL)); out <- cols
  for (i in seq_along(cols)) {
    n <- norm_col(cols[i])
    if (cols[i] == "uid_final") out[i] <- "external_uid_final"
    else if (n %in% names(canon)) out[i] <- canon[[n]]
    else if (n %in% names(ALIASES)) out[i] <- ALIASES[[n]]
    else { d <- adist(n, names(canon)); j <- which.min(d)                     # a close spelling (difflib cutoff 0.8)
           if (length(j) && 1 - d[j] / max(nchar(n), nchar(names(canon)[j])) >= 0.8) out[i] <- canon[[j]] }
  }
  seen <- character(0)
  for (i in seq_along(out)) { if (out[i] %in% seen && out[i] != cols[i]) out[i] <- sprintf("%s__dup_%s", out[i], cols[i]); seen <- c(seen, out[i]) }
  out
}
harmonise <- function(dt) { setnames(dt, harmonise_names(names(dt))); dt }
recode_buff_km <- function(v) {                                                      # _prep_common.recode_buff_km
  num <- suppressWarnings(as.numeric(v)); txt <- is.na(num) & !is.na(v)
  if (any(txt)) { s <- as.character(v[txt]); mag <- suppressWarnings(as.numeric(regmatches(s, regexpr("[0-9]+(\\.[0-9]+)?", s))))
                  mag <- ifelse(grepl("^\\s*-", s), -mag, mag); num[txt] <- if (length(mag) == sum(txt)) mag else NA_real_ }
  r <- round(num); okv <- is.finite(r) & abs(num - r) <= 0.01 & r %in% VALID_BUFFERS
  as.integer(ifelse(okv, r, -1L))
}
drop_rows_without_outcome <- function(dt) {                                         # _prep_common.drop_rows_without_outcome
  oc <- intersect(OUTCOME_VARS, names(dt))
  if (!length(oc)) return(dt)
  any_ok <- rowSums(is.finite(as.matrix(dt[, ..oc]))) > 0
  attr_n <- sum(!any_ok); out <- dt[any_ok]; attr(out, "rows_dropped_no_outcome") <- attr_n; out
}
apply_missing_policy <- function(dt, drop_empty = TRUE) {                            # _prep_common.apply_missing_policy (stage "file")
  # v20.58 (second pass, the poison test with cloud gaps): drop_empty = FALSE keeps the rows with no usable outcome -- run_prep drops them only
  # AFTER resolve_duplicates. Dropped per file (before it), a newer export's row that a cloud left empty was gone before the duplicates were
  # compared, and the OLDER repeated row of that pixel-year-season took its place (a repeated row reached every model)
  for (v in intersect(ZERO_RULE_VARS, names(dt))) if (!v %in% ZERO_RULE_EXCEPT) { x <- suppressWarnings(as.numeric(dt[[v]])); x[x == 0] <- NA; set(dt, j = v, value = x) }
  if (DROP_ROWS_WITHOUT_OUTCOME && isTRUE(drop_empty)) dt <- drop_rows_without_outcome(dt)
  for (v in intersect(WEATHER_VARS, names(dt))) {                                    # the negative-covariate barrier, no-data first
    x <- as.numeric(dt[[v]])
    x[x <= -100] <- NA; if (v != "Rain") x[x == -10] <- NA                        # fill values and the -10 C clamp are missing
    if (!isTRUE(ALLOW_NEGATIVE_COVARIATES)) x[is.finite(x) & x < 0] <- 0        # your switch (Python: ALLOW_NEGATIVE_COVARIATES)
    set(dt, j = v, value = x)
  }
  dt
}
read_export <- function(file, Year, Season, hint, folder, sws_file = NA_integer_, mtime = NA_real_) {
  dt <- harmonise(read_export_raw(file))
  # the block key: the file NAME for what it states, the columns inside for the rest (the name wins)  -- load_and_harmonize
  for (k in c("Year", "Season")) {
    from_name <- if (k == "Year") Year else Season
    if (!is.na(from_name)) { set(dt, j = k, value = as.integer(from_name)) }
    else if (k %in% names(dt)) {
      col <- suppressWarnings(as.numeric(dt[[k]]))
      if (k == "Season") { lab <- SEASON_CODE[tolower(trimws(as.character(dt[[k]])))]; col <- ifelse(is.na(col), lab, col) }
      if (anyNA(col)) stop(k, " missing in the file name and not readable for ", sum(is.na(col)), " rows of the ", k, " column")
      set(dt, j = k, value = as.integer(col))
    } else stop("cannot determine ", k, " -- not in the file name and no ", k, " column")
  }
  treat_in_file <- "Treat" %in% names(dt)                                                              # v20.59: input_audit_R says when it is not
  if (!treat_in_file) dt[, Treat := as.numeric(Year >= TREATMENT_YEAR)]                              # a file without the column: the Year rule (said)
  miss <- setdiff(ESSENTIAL_COLS, names(dt))
  if (length(miss)) stop("REJECTED, missing essential columns ", paste(miss, collapse = ", "))
  keep <- intersect(c("latitude", "longitude", "buff_km", "SubwshedID", "SWSiD_All", "SWS_Name", "Year", "Season", "Treat",
                      OUTCOME_VARS, WEATHER_VARS, DESCRIPTOR_VARS, EXTRA_VARS), names(dt))
  dt <- dt[, ..keep]
  for (v in setdiff(OUTCOME_VARS, names(dt))) set(dt, j = v, value = NA_real_)                       # outcome columns the source lacks: NaN
  for (v in intersect(c(OUTCOME_VARS, WEATHER_VARS), names(dt))) if (!is.numeric(dt[[v]])) set(dt, j = v, value = suppressWarnings(as.numeric(dt[[v]])))
  dt[, buff_km := recode_buff_km(buff_km)]
  dt[, `:=`(latitude = as.numeric(latitude), longitude = as.numeric(longitude))]
  # v20.59 -- YOUR RULE, confirmed per file: Treat 1 = post / 0 = pre, buff_km 0 = the treatment area / 1-5 = the control rings (input_audit_R);
  # under PERIOD_RULE = "both" a row whose Treat flag and Year rule disagree (or whose flag is not 0 / 1) LEAVES here, before the duplicates
  # are resolved (another export's consistent row of the same pixel-period can then stand in) -- as _prep_common.audit_and_apply_period_rule
  aud <- input_audit_R(dt, file, treat_in_file)
  if (identical(period_rule_R(), "both")) {
    tv <- suppressWarnings(as.numeric(dt$Treat)); drop <- !(tv %in% c(0, 1)) | as.integer(tv) != as.integer(dt$Year >= TREATMENT_YEAR); drop[is.na(drop)] <- TRUE
    if (any(drop)) { dt <- dt[!drop]; aud[, rows_dropped_period_disagree := sum(drop)] }
  }
  dt <- apply_missing_policy(dt, drop_empty = FALSE)                                # v20.58: empty rows leave after the dedup (run_prep)
  dt[, `:=`(sws_hint = hint, folder = folder, src_file = basename(file), sws_file = sws_file,
            file_mtime = if (is.na(mtime)) as.numeric(file.mtime(file)) else mtime,
            schema_vintage = if ("DataYear" %in% names(dt)) "2026plus" else "2015_2025")]
  setattr(dt, "input_audit", aud)                                                    # v20.59: read by run_prep / ooc_task_p00_read (before any subset)
  dt
}

# ---------------------------------------------------------------- 4-5. pixel ids; the sub-watershed from the shapefile (confirm or correct)
pixel_ids <- function(lat, lon) sprintf("%d_%d", as.integer(round((lat + 90) * 1e5)), as.integer(round((lon + 180) * 1e5)))   # assign_pixel_ids: the same rounding
sws_names <- function() { s <- fread(SITES_CSV); setNames(as.character(s$name), s$SWSiD_All) }
NAME_MATCH_THRESHOLD <- 0.80; NAME_MATCH_MARGIN <- 0.05              # YOUR RULE: >= 80 % similar = the same sub-watershed
NON_PROGRAMME <- c("gadag", "hanchinal", "hosahalli", "kohalli", "itgi", "haralahalli", "holali", "kandgul", "laxmisagara",
                   "mattikote", "nagagondanahalli", "narayanghatta", "virupasandra")   # never matched to a programme name
norm_sws <- function(x) gsub("[^a-z]", "", gsub("\\(.*?\\)|sub[ _-]*watershed|\\bsws\\b|control", "", tolower(x), perl = TRUE))
name_similarity <- function(a, b) 1 - drop(adist(a, b)) / pmax(nchar(a), nchar(b))    # 1 - Levenshtein / longer length (as Python)
SWS_ALIASES <- c(artal = "Artal", begur = "Beguru", beguru = "Beguru", chatrakodihalli = "Chhatrakodihalli", chhatrakodihalli = "Chhatrakodihalli",
  chittaragi = "Chittharagi", chittharagi = "Chittharagi", doddenahalli = "Doddenahalli", gummalapalli = "Gummlapalli", gummlapalli = "Gummlapalli",
  halligera = "Haligeri", haligeri = "Haligeri", honnutagi = "Honnutagi", hunsehadagli = "Hunasehadagi", hunasehadagi = "Hunasehadagi",
  jammapura = "Jammapur", jammapur = "Jammapur", jantapur = "Jantapur", kodihalli = "Kodihalli", koranahalli = "Koranahalli",
  kytagondanahalli = "Kyatagondanahalli", kyatagondanahalli = "Kyatagondanahalli", maidalakere = "Maidalakere", mydalakere = "Maidalakere",
  mallainupura = "Mallainupura", murlapura = "Murlapura", nilagunda = "Nilgund", nilgunda = "Nilgund", nilgund = "Nilgund",
  pashapur = "Pashapur", shirur = "Sirur", sirur = "Sirur")
# v20.49: the SAME rule as Python (_names.py + _sws_geometry.site_id_for_name), for export folder / file names and the
# fund file: 1) a known spelling; 2) the longest known name CONTAINED in the text ("REWARD_Artal_Exports_final",
# "CSV_Sirur_v107_2025_Rabi_..."; "Chhatrakodihalli" never resolves to "Kodihalli"); 3) a WORD >= 80 % similar to ONE
# sub-watershed (>= 5 points ahead of the next). A known non-programme name (controls in the BM files) never matches.
match_one_sws <- function(x) {
  if (is.na(x) || !nzchar(x)) return(NA_character_)
  n <- norm_sws(x); keys <- names(SWS_ALIASES)
  if (nzchar(n) && n %in% keys) return(unname(SWS_ALIASES[n]))
  if (nzchar(n) && any(startsWith(n, NON_PROGRAMME))) return(NA_character_)
  low <- tolower(x); k <- gsub("[^a-z0-9]", "", low)
  hit <- keys[nchar(keys) >= 4 & vapply(keys, function(a) grepl(a, k, fixed = TRUE), logical(1))]
  if (length(hit)) return(unname(SWS_ALIASES[hit[which.max(nchar(hit))]]))
  toks <- unique(c(regmatches(low, gregexpr("[a-z]{4,}", low))[[1]], n)); toks <- toks[nzchar(toks)]; toks <- toks[order(-nchar(toks))]
  for (t in toks) {
    if (any(startsWith(t, NON_PROGRAMME))) next
    best <- sort(tapply(name_similarity(t, keys), unname(SWS_ALIASES), max), decreasing = TRUE)
    if (best[1] >= NAME_MATCH_THRESHOLD && (length(best) < 2 || best[1] - best[2] >= NAME_MATCH_MARGIN)) return(names(best)[1])
  }
  NA_character_
}
match_sws_name <- function(x) vapply(as.character(x), match_one_sws, character(1), USE.NAMES = FALSE)

# v20.59 -- YOUR RULE (as Python's tag_sites): the sub-watershed of every row is where its latitude / longitude falls (the core or a control
# ring of the shapefile) -- the file's id only labels. SITE_GEOMETRY_CHECK <- FALSE trusts the file's id instead (site_check 4 = not checked).
overlay_or_trust <- function(px) {
  if (isTRUE(.opt("SITE_GEOMETRY_CHECK", TRUE))) return(overlay_sws(px))
  out <- cbind(px, data.table(site_id = fifelse(is.na(px$sws_export), 0L, as.integer(px$sws_export)), ring_poly = NA_integer_, site_check = 4L))
  info("overlay: SITE_GEOMETRY_CHECK = FALSE -- the sub-watershed id of the input files is trusted (", format(nrow(out), big.mark = ","), " pixels not checked)")
  out
}
ring_from_polygon_codes <- function() if (isTRUE(.opt("BUFF_FROM_GEOMETRY", FALSE))) c(0L, 1L, 2L) else c(1L, 2L)   # BUFF_FROM_GEOMETRY: confirmed rows too
working_sws_line <- function(dt) {
  # ONE sub-watershed processed = the one holding the majority of the rows (SUB_WATERSHEDS = "data": every sub-watershed with >= FRAGMENT_MIN_SHARE of
  # the largest one's own rows; the rest are fragments); SEVERAL = every row in the sub-watershed its coordinates put it in.
  tb <- dt[!is.na(site_id) & site_id > 0, .N, by = site_id][order(-N)]; if (!nrow(tb)) return(invisible(NULL))
  nm <- tryCatch(sws_names(), error = function(e) NULL); top <- tb[1]
  info(sprintf("working sub-watershed rule (v20.59): every row belongs to the sub-watershed its latitude / longitude falls in (core or control ring); the largest here is %s with %s rows (%.1f %%) -- a single-sub-watershed run processes it and codes the rest as fragments (SUB_WATERSHEDS = \"data\", FRAGMENT_RULE); a pooled run keeps every row in its own sub-watershed",
               if (!is.null(nm)) nm[as.character(top$site_id)] else top$site_id, format(top$N, big.mark = ","), 100 * top$N / sum(tb$N)))
  invisible(tb)
}
overlay_sws <- function(px) {                                                        # _sws_geometry.SWSLocator.tag
  suppressPackageStartupMessages(library(sf))
  poly <- st_read(SHAPEFILE, quiet = TRUE)[, c("SWSiD_All", "SUBWSHED", "buff_km")]
  pts <- st_transform(st_as_sf(px, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE), st_crs(poly))
  hits <- st_intersects(pts, poly)
  pr <- data.table(i = rep(seq_along(hits), lengths(hits)), k = unlist(hits))
  pr[, `:=`(sid = as.integer(poly$SWSiD_All[k]), ring = as.integer(poly$buff_km[k]), ind = px$sws_export[i])]
  conf <- pr[!is.na(ind) & sid == ind][order(i, ring)][!duplicated(i)][, .(i, site_id = sid, ring_poly = ring, site_check = 0L)]
  rest <- pr[!i %in% conf$i][order(i, ring, sid)][!duplicated(i)][, .(i, site_id = sid, ring_poly = ring, site_check = fifelse(is.na(ind) | ind <= 0L, 2L, 1L))]   # core first, then the lower id
  res <- rbind(conf, rest)
  ind0 <- fifelse(is.na(px$sws_export), 0L, as.integer(px$sws_export))
  out <- cbind(px, data.table(site_id = ind0, ring_poly = NA_integer_, site_check = 3L))      # in no polygon: the indicated site kept, flagged (as Python)
  out[res$i, `:=`(site_id = res$site_id, ring_poly = res$ring_poly, site_check = res$site_check)]
  n <- out[, .N, by = site_check][order(site_check)]
  info("overlay: ", paste(sprintf("%s %s", c("confirmed", "corrected", "assigned", "outside")[n$site_check + 1], format(n$N, big.mark = ",")), collapse = " | "))
  out
}

# ---------------------------------------------------------------- 6. pixels whose footprints overlap >= PIXEL_OVERLAP_MIN are ONE pixel
# The Python algorithm (_prep_common.pixel_registry / near_duplicate_pairs / canonical_pixel_map), step for step: a registry of
# every pixel (mean coordinates, newest file, rows, usable outcome cells); every pair of different pixels whose 10 m squares
# overlap >= the threshold (3 x 3 neighbouring bins); a greedy, chain-free assignment in priority order (DEDUP_PRIORITY
# "newer": newest file, then completeness, then rows, then id) -- a pixel is merged only into a pixel it overlaps directly.
pixel_registry <- function(dt) {
  oc <- intersect(OUTCOME_VARS_CORE, names(dt))
  d <- dt[, c("pixel_id", "latitude", "longitude", "file_mtime", "src_file", oc), with = FALSE]
  d[, n_ok := rowSums(is.finite(as.matrix(.SD))), .SDcols = oc]
  setorder(d, file_mtime)
  d[, .(lat = mean(latitude), lon = mean(longitude), mtime = max(file_mtime), n_rows = .N, n_ok = sum(n_ok), src = src_file[.N]), by = pixel_id][
    , completeness := n_ok / pmax(n_rows, 1)][]
}
near_duplicate_pairs <- function(reg, size_m = PIXEL_SIZE_M, overlap_min = PIXEL_OVERLAP_MIN) {
  if (nrow(reg) < 2) return(data.table(i = integer(0), j = integer(0), overlap = numeric(0)))
  lat <- reg$lat; lon <- reg$lon; lat_ref <- median(lat, na.rm = TRUE)
  x <- lon * 111320 * cos(lat_ref * pi / 180); y <- lat * 110574
  bx <- floor((x - min(x, na.rm = TRUE)) / size_m) + 1; by <- floor((y - min(y, na.rm = TRUE)) / size_m) + 1
  base <- data.table(bx = bx, by = by, i = seq_len(nrow(reg)))
  found <- list()
  for (ox in -1:1) for (oy in -1:1) {
    sh <- data.table(bx = bx + ox, by = by + oy, j = seq_len(nrow(reg)))
    m <- merge(base, sh, by = c("bx", "by"), allow.cartesian = TRUE)[i < j]
    if (!nrow(m)) next
    dx <- (lon[m$i] - lon[m$j]) * 111320 * cos(0.5 * (lat[m$i] + lat[m$j]) * pi / 180); dy <- (lat[m$i] - lat[m$j]) * 110574
    ov <- pmax(0, 1 - abs(dx) / size_m) * pmax(0, 1 - abs(dy) / size_m)
    k <- ov >= overlap_min - 1e-12
    if (any(k)) found[[length(found) + 1]] <- data.table(i = m$i[k], j = m$j[k], overlap = ov[k])
  }
  if (!length(found)) return(data.table(i = integer(0), j = integer(0), overlap = numeric(0)))
  unique(rbindlist(found), by = c("i", "j"))
}
canonical_pixel_map <- function(reg, pairs, priority = DEDUP_PRIORITY) {
  if (!nrow(pairs)) return(data.table(pixel_id = character(0), canonical_pixel_id = character(0), canonical_lat = numeric(0), canonical_lon = numeric(0), overlap = numeric(0)))
  ord <- if (priority == "complete") order(-reg$completeness, -reg$mtime, -reg$n_rows, reg$pixel_id) else order(-reg$mtime, -reg$completeness, -reg$n_rows, reg$pixel_id)
  pos <- integer(nrow(reg)); pos[ord] <- seq_len(nrow(reg))                      # rank in priority order (1 = highest)
  hi <- ifelse(pos[pairs$i] < pos[pairs$j], pairs$i, pairs$j); lo <- ifelse(pos[pairs$i] < pos[pairs$j], pairs$j, pairs$i)
  o <- order(pos[hi], pos[lo]); hi <- hi[o]; lo <- lo[o]; ov <- pairs$overlap[o]
  assigned <- integer(nrow(reg)); ovr <- numeric(nrow(reg))                     # 0 = not yet assigned
  for (r in seq_along(hi)) {
    h <- hi[r]; l <- lo[r]
    if (assigned[h] == 0L) assigned[h] <- h                                      # the higher-priority pixel becomes canonical ...
    if (assigned[h] == h && assigned[l] == 0L) { assigned[l] <- h; ovr[l] <- ov[r] }   # ... and takes its unassigned direct neighbours
  }
  q <- which(assigned != 0L & assigned != seq_len(nrow(reg)))
  data.table(pixel_id = reg$pixel_id[q], canonical_pixel_id = reg$pixel_id[assigned[q]], canonical_lat = reg$lat[assigned[q]], canonical_lon = reg$lon[assigned[q]], overlap = ovr[q])
}
merge_near_duplicate_pixels <- function(dt) {
  if (!isTRUE(NEAR_DUPLICATE_PIXELS)) return(dt)
  cmap <- near_dup_map_R(pixel_registry(dt))
  if (nrow(cmap)) dt[cmap, on = "pixel_id", `:=`(pixel_id = i.canonical_pixel_id, latitude = i.canonical_lat, longitude = i.canonical_lon)]
  dt
}
# v20.58: the map from the registry (shared with R_P00 block by block, whose registry is merged from the export files): pairs, the canonical
# pixels, the reports and what was merged
near_dup_map_R <- function(reg) {
  pairs <- near_duplicate_pairs(reg); cmap <- canonical_pixel_map(reg, pairs)
  rep <- data.table(pixels_in_registry = nrow(reg), pairs_at_or_above_threshold = nrow(pairs), pixels_merged = nrow(cmap),
                    canonical_pixels_receiving = uniqueN(cmap$canonical_pixel_id), overlap_min = PIXEL_OVERLAP_MIN, pixel_size_m = PIXEL_SIZE_M, priority = DEDUP_PRIORITY)
  fwrite(rep, file.path(OUTPUT_DIR, "pixel_overlap_report.csv"))
  if (nrow(cmap)) {
    fwrite(cmap, file.path(OUTPUT_DIR, "pixel_overlap_map.csv"))
    ok(sprintf("near-duplicate pixels: %s pixels, %s pairs overlapping >= %.0f %% -> %s pixels merged onto their %s counterpart",
               format(nrow(reg), big.mark = ","), format(nrow(pairs), big.mark = ","), 100 * PIXEL_OVERLAP_MIN, format(nrow(cmap), big.mark = ","),
               if (DEDUP_PRIORITY == "newer") "newer" else "more complete"))
  } else ok(sprintf("near-duplicate pixels: %s pixels, no pair overlaps >= %.0f %%", format(nrow(reg), big.mark = ","), 100 * PIXEL_OVERLAP_MIN))
  cmap
}
link_shifted_grid <- function(dt, before = TREATMENT_YEAR) {                        # v20.45 (superseded by merge_near_duplicate_pixels; kept)
  if (!requireNamespace("RANN", quietly = TRUE)) { warn("install RANN to link shifted grids"); return(dt) }
  u <- dt[, .(latitude = latitude[1], longitude = longitude[1], first = min(Year)), by = pixel_id]
  old <- u[first < before]; new <- u[first >= before]
  if (!nrow(old) || !nrow(new)) return(dt)
  lat0 <- mean(u$latitude); xy <- function(t) cbind(t$longitude * 111320 * cos(lat0 * pi / 180), t$latitude * 110540)
  nn <- RANN::nn2(xy(old), xy(new), k = 1)
  d <- xy(new) - xy(old)[nn$nn.idx[, 1], , drop = FALSE]
  ov <- pmax(0, 1 - abs(d[, 1]) / PIXEL_SIZE_M) * pmax(0, 1 - abs(d[, 2]) / PIXEL_SIZE_M)
  map <- data.table(pixel_id = new$pixel_id, to = old$pixel_id[nn$nn.idx[, 1]])[ov >= PIXEL_OVERLAP_MIN]
  if (nrow(map)) { dt[map, on = "pixel_id", pixel_id := i.to]; ok(sprintf("%s later pixels linked to their earlier pixel (footprint overlap >= %.2f)", format(nrow(map), big.mark = ","), PIXEL_OVERLAP_MIN)) }
  dt
}

# ---------------------------------------------------------------- 7. one row per (site, pixel, Year, Season)   (_prep_common.resolve_duplicates)
resolve_duplicates <- function(dt, keys = c("site_id", "pixel_id", "Year", "Season"), recency_margin_seconds = 1.0, say = TRUE) {   # say = FALSE: a block of R_P00 out of core
  # 1 the NEWER FILE wins (mtime within 1 s of the newest = equally new); 2 fewer missing outcome values (the 10 core
  # outcomes); 3 higher NObsV; 4 newer schema; 5 file name. (v20.45-v20.54 R averaged the duplicates -- not the Python rule.)
  # v20.58 (your rule "repeated rows are dropped"): the kept row is taken AS IT IS -- until v20.57 its missing core outcomes were FILLED
  # from the dropped rows, so a cloud gap of the newer export took the older export's value (the poison test found it). The fill is
  # now DEDUP_FILL_FROM_DUPLICATES = TRUE only; otherwise the values it would have taken are counted and reported as NOT used.
  keys <- intersect(keys, names(dt)); oc <- intersect(OUTCOME_VARS_CORE, names(dt))
  # v20.58: a pixel OUTSIDE every polygon (site_check 3) has no sub-watershed of its own -- its id is only what the file's NAME said, and a
  # named export and an unnamed tile of the same place disagree (13 and 0 in your Koranahalli exports): its copies are ONE pixel-year-season
  # (the newer file wins, as always). Until v20.57 both stayed in the panel (Python's P00 check: "duplicate pixel-Year-Season rows").
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
  if ("fragment" %in% names(g)) first[g[, .(.fm = min(fragment)), by = keys], on = keys, fragment := i..fm]   # v20.57: any file's own data -> major
  n_fill <- 0L; n_unused <- 0L; by_var <- integer(0); fill <- isTRUE(DEDUP_FILL_FROM_DUPLICATES)
  for (v in oc) {                                                                    # first finite value per group, in priority order
    don <- g[is.finite(get(v)), .(.don = get(v)[1L]), by = keys]
    first[don, on = keys, .don := i..don]
    gap <- !is.finite(first[[v]]) & is.finite(first$.don)
    if (any(gap)) {
      if (fill) { set(first, which(gap), v, first$.don[gap]); n_fill <- n_fill + sum(gap) }
      else { n_unused <- n_unused + sum(gap); by_var[v] <- sum(gap) }                 # v20.58: counted, NOT used
    }
    first[, .don := NULL]
  }
  first[, c(".gmax", ".newest", ".nmiss", ".nobs", ".vr") := NULL]
  out <- rbind(r, first, fill = TRUE); if (".site_key" %in% names(out)) out[, .site_key := NULL]
  attr(out, "dedup") <- list(groups = nrow(first), removed = nrow(g) - nrow(first), filled = n_fill, not_used = n_unused, not_used_by_variable = by_var)
  if (say) ok(sprintf("%s rows shared a (sub-watershed, pixel, year, season) with another file (a pixel outside every polygon: the same pixel, year and season, whatever id the files gave it) -> %s kept (the %s file wins, then the more complete row)%s",
             format(nrow(g), big.mark = ","), format(nrow(first), big.mark = ","), if (DEDUP_PRIORITY == "complete") "more complete" else "newer",
             if (fill) sprintf("; %s missing values FILLED from the dropped rows (DEDUP_FILL_FROM_DUPLICATES = TRUE)", format(n_fill, big.mark = ",")) else "; each kept AS IT IS, the repeated rows dropped whole"))
  if (n_unused && say) ok(sprintf("repeated rows DROPPED WHOLE: their %s value(s) where the kept row has a gap were NOT used (%s) -- DEDUP_FILL_FROM_DUPLICATES = FALSE (your rule). If your exports are SPLIT by variable (one file NDVI, another LAI of the same pixel-period), set DEDUP_FILL_FROM_DUPLICATES <- TRUE (lib/reward_prep.R) and re-run R_P00",
                           format(n_unused, big.mark = ","), paste(sprintf("%s %s", names(by_var), format(by_var, big.mark = ",")), collapse = ", ")))
  out
}

# ---------------------------------------------------------------- 8. v20.59 -- YOUR REQUEST: the DiD design columns IN THE PANEL
# treat (1 = the treatment area, buff_km 0; 0 = a ring), control (1 = a control ring 1-5), post (1 = post, 0 = pre: the EXPORTS' Treat flag --
# the exporter writes 1 for every pixel from its treatment year on; a row without a usable flag takes the rule Year >= TREATMENT_YEAR, counted
# and said), pre (1 - post) and did (treat x post). They are the panel's DEFAULT design (the exporter's timing) -- as Python's P00 writes
# treat / treatment, control, pre, post, did / did_term (POST_FROM_EXPORT_TREAT). Every model applies ITS OWN design when it runs
# (design_columns: the fund timing, TREATMENT_YEAR, the transition year -- your settings) and says on how many rows the two differ
# ("DESIGN vs PANEL", load_panel_R); the model's columns are what it estimates on, never these.
PANEL_DESIGN_COLS <- c("treat", "control", "pre", "post", "did")
POST_FROM_EXPORT_TREAT <- TRUE           # the older switch (kept): FALSE = "year" while PERIOD_RULE is "treat"; period_rule_R() gives the rule in effect
PERIOD_RULES <- c("treat", "year", "both")
PERIOD_RULE_TEXT <- c(treat = "post / pre = the exports' Treat column (1 = post, 0 = pre)", year = "post / pre = the rule Year >= TREATMENT_YEAR",
                      both = "post / pre = the exports' Treat column, which must AGREE with the rule Year >= TREATMENT_YEAR (a disagreeing row leaves)")
period_rule_R <- function() {
  # v20.59 -- YOUR RULE: the rule in effect for the panel's post / pre: "treat" (the exports' Treat column: 1 = post, 0 = pre), "year" (the rule
  # Year >= TREATMENT_YEAR) or "both" (the column and the rule must agree; a row where they disagree leaves the panel). PERIOD_RULE
  # (lib/reward_paths.R) decides; the older POST_FROM_EXPORT_TREAT = FALSE still means "year" while PERIOD_RULE is left at "treat".
  r <- if (exists("PERIOD_RULE") && !is.null(PERIOD_RULE)) tolower(trimws(as.character(PERIOD_RULE)[1])) else "treat"
  if (!r %in% PERIOD_RULES) stop("PERIOD_RULE must be one of ", paste(shQuote(PERIOD_RULES), collapse = ", "), " (lib/reward_paths.R), not ", shQuote(r))
  if (r == "treat" && !isTRUE(POST_FROM_EXPORT_TREAT)) r <- "year"
  r
}
input_audit_R <- function(dt, file, treat_in_file = TRUE) {
  # v20.59 -- YOUR RULE, confirmed on EVERY input file (one row per file -> input_design_audit_R.csv): the Treat column carries 1 = post /
  # 0 = pre (rows of each, rows with another value), buff_km / distance carries 0 = the treatment area and 1-5 = the control rings (rows of
  # each, rows outside 0-5), and on how many rows the Treat flag and the rule Year >= TREATMENT_YEAR disagree. As _prep_common.input_design_audit.
  n <- nrow(dt); tv <- if ("Treat" %in% names(dt)) suppressWarnings(as.numeric(dt$Treat)) else rep(NA_real_, n)
  bk <- if ("buff_km" %in% names(dt)) suppressWarnings(as.numeric(dt$buff_km)) else rep(NA_real_, n)
  yr <- suppressWarnings(as.numeric(dt$Year)); rule <- as.integer(yr >= TREATMENT_YEAR)
  n_post <- sum(tv == 1, na.rm = TRUE); n_pre <- sum(tv == 0, na.rm = TRUE); n_b0 <- sum(bk == 0, na.rm = TRUE); n_b15 <- sum(bk %in% 1:5)
  data.table(file = basename(file), rows = n, treat_column_in_file = isTRUE(treat_in_file) && "Treat" %in% names(dt),
             treat_post_rows = n_post, treat_pre_rows = n_pre, treat_unusable_rows = n - n_post - n_pre,
             year_min = if (any(is.finite(yr))) min(yr[is.finite(yr)]) else NA_real_, year_max = if (any(is.finite(yr))) max(yr[is.finite(yr)]) else NA_real_,
             year_rule_post_rows = sum(rule == 1L, na.rm = TRUE),
             treat_vs_year_disagree_rows = sum(is.finite(tv) & (tv == 0 | tv == 1) & as.integer(tv) != rule, na.rm = TRUE),
             buff0_treatment_rows = n_b0, buff1to5_control_rows = n_b15, buff_outside_0to5_rows = n - n_b0 - n_b15,
             period_rule = period_rule_R(), rows_dropped_period_disagree = 0L)
}
input_audit_report_R <- function(aud, write = TRUE) {
  # v20.59: the confirmation of the input files, said once and written -> input_design_audit_R.csv (as Python's input_design_audit.csv)
  if (is.null(aud) || !nrow(aud)) return(invisible(NULL))
  if (write) fwrite(aud, file.path(OUTPUT_DIR, "input_design_audit_R.csv"))
  s <- function(k) sum(as.numeric(aud[[k]]), na.rm = TRUE); fm <- function(x) format(x, big.mark = ","); r <- period_rule_R()
  n_no <- sum(!as.logical(aud$treat_column_in_file), na.rm = TRUE)
  ok(sprintf("input files CONFIRMED (%d files, %s rows): Treat column 1 = post on %s rows, 0 = pre on %s rows%s; buff_km 0 = the treatment area on %s rows, 1-5 = the control rings on %s rows%s; PERIOD_RULE = '%s': %s -> input_design_audit_R.csv",
             nrow(aud), fm(s("rows")), fm(s("treat_post_rows")), fm(s("treat_pre_rows")),
             if (s("treat_unusable_rows")) sprintf(", %s rows with another value", fm(s("treat_unusable_rows"))) else "",
             fm(s("buff0_treatment_rows")), fm(s("buff1to5_control_rows")),
             if (s("buff_outside_0to5_rows")) sprintf(", %s rows outside 0-5 (in neither group)", fm(s("buff_outside_0to5_rows"))) else "", r, PERIOD_RULE_TEXT[[r]]))
  if (n_no) warn(sprintf("%d file(s) carry NO Treat column: 1 = post / 0 = pre was derived from the rule Year >= %d for them (input_design_audit_R.csv)", n_no, TREATMENT_YEAR))
  d <- s("treat_vs_year_disagree_rows")
  if (d) warn(sprintf("%s rows in %d file(s) where the Treat flag and the rule Year >= %d DISAGREE (an export made with another treatment year or rule) -- %s",
                      fm(d), sum(aud$treat_vs_year_disagree_rows > 0, na.rm = TRUE), TREATMENT_YEAR,
                      switch(r, treat = "the panel's post / pre FOLLOW THE FLAG (PERIOD_RULE = 'treat')", year = "the panel's post / pre follow the YEAR RULE (PERIOD_RULE = 'year')",
                             both = sprintf("they LEFT the panel (%s rows dropped; PERIOD_RULE = 'both')", fm(s("rows_dropped_period_disagree"))))))
  else if (s("rows_dropped_period_disagree")) warn(sprintf("%s rows without a usable Treat flag (not 0 / 1) LEFT the panel (PERIOD_RULE = 'both')", fm(s("rows_dropped_period_disagree"))))
  if (s("buff_outside_0to5_rows")) warn(sprintf("%s rows carry a buffer code outside 0-5: in NEITHER group (input_design_audit_R.csv)", fm(s("buff_outside_0to5_rows"))))
  invisible(aud)
}
panel_design_columns_R <- function(dt, treatment_year = TREATMENT_YEAR, say = TRUE) {
  pr <- period_rule_R(); n0 <- nrow(dt)
  if (identical(pr, "both") && "Treat" %in% names(dt)) {              # the column and the rule must AGREE (read_export already dropped these; confirmed here)
    tv0 <- suppressWarnings(as.numeric(dt$Treat)); drop <- !(tv0 %in% c(0, 1)) | as.integer(tv0) != as.integer(dt$Year >= as.integer(treatment_year)); drop[is.na(drop)] <- TRUE
    if (any(drop)) dt <- dt[!drop]
  }
  n <- nrow(dt); rule <- as.integer(dt$Year >= as.integer(treatment_year))
  tv <- if ("Treat" %in% names(dt) && !identical(pr, "year")) suppressWarnings(as.numeric(dt$Treat)) else rep(NA_real_, n)
  from_flag <- is.finite(tv) & (tv == 0 | tv == 1)
  post_v <- fifelse(from_flag, as.integer(tv), rule)                 # a local vector (never the name of a column: data.table would read the column)
  set(dt, j = "treat", value = as.integer(dt$buff_km == 0L)); set(dt, j = "control", value = as.integer(dt$buff_km %in% 1:5)); set(dt, j = "post", value = post_v)
  set(dt, j = "pre", value = 1L - post_v); set(dt, j = "did", value = as.integer(dt$treat * post_v))
  chk <- list(rows = n, from_flag = sum(from_flag), from_rule = sum(!from_flag), flag_vs_rule_differ = sum(from_flag & post_v != rule),
              treatment_year = as.integer(treatment_year), period_rule = pr, rows_dropped = n0 - n,
              xtab = dt[, .(rows = .N), by = .(Year, Season, treat, control, pre, post, did)][order(Year, Season, -treat, control, post)])
  setattr(dt, "design_check", chk)
  if (say) panel_design_report_R(chk)
  dt
}
panel_design_merge_R <- function(parts) {                          # the blocks' checks (R_P00 out of core) -> one check, as in memory
  parts <- Filter(Negate(is.null), parts); if (!length(parts)) return(NULL)
  xt <- rbindlist(lapply(parts, `[[`, "xtab"))[, .(rows = sum(rows)), by = .(Year, Season, treat, control, pre, post, did)][order(Year, Season, -treat, control, post)]
  s <- function(k) sum(vapply(parts, function(p) as.numeric(p[[k]] %||% 0), 0))
  list(rows = s("rows"), from_flag = s("from_flag"), from_rule = s("from_rule"), flag_vs_rule_differ = s("flag_vs_rule_differ"), treatment_year = parts[[1]]$treatment_year,
       period_rule = parts[[1]]$period_rule %||% period_rule_R(), rows_dropped = s("rows_dropped"), xtab = xt)
}
panel_design_report_R <- function(chk, write = TRUE) {
  if (is.null(chk)) return(invisible(NULL))
  if (write) fwrite(chk$xtab, file.path(OUTPUT_DIR, "panel_design_check_R.csv"))
  g <- chk$xtab[, .(rows = sum(rows)), by = .(group = fifelse(treat == 1L, "treatment (buffer 0)", fifelse(control == 1L, "control (buffer 1-5)", "neither (invalid buffer)")), period = fifelse(post == 1L, "post", "pre"))]
  pr <- chk$period_rule %||% period_rule_R()
  if (identical(pr, "year"))
    ok(sprintf("DiD design columns in the panel: treat (buffer 0 = the treatment area) / control (rings 1-5); post = the rule Year >= %d on every row (PERIOD_RULE = 'year'); pre = 1 - post; did = treat x post -> panel_design_check_R.csv", chk$treatment_year))
  else
    ok(sprintf("DiD design columns in the panel: treat (buffer 0 = the treatment area) / control (rings 1-5); post = the exports' Treat column (1 = post, 0 = pre; PERIOD_RULE = '%s') on %s rows%s; pre = 1 - post; did = treat x post -> panel_design_check_R.csv",
               pr, format(chk$from_flag, big.mark = ","),
               if (identical(pr, "both")) sprintf(", every one AGREEING with the rule Year >= %d%s", chk$treatment_year, if (chk$rows_dropped %||% 0) sprintf(" (%s disagreeing rows left)", format(chk$rows_dropped, big.mark = ",")) else "")
               else if (chk$from_rule) sprintf(", the rule Year >= %d on %s rows without a usable flag", chk$treatment_year, format(chk$from_rule, big.mark = ",")) else ""))
  info("rows per group x period: ", paste(sprintf("%s %s %s", g$group, g$period, format(g$rows, big.mark = ",")), collapse = " | "))
  if (chk$flag_vs_rule_differ) info(sprintf("%s rows' exported Treat flag differs from the rule Year >= %d (an export made with another treatment year or rule): the panel FOLLOWS THE FLAG (PERIOD_RULE = 'treat'); every model applies its own design when it runs and says on how many rows it differs",
                                          format(chk$flag_vs_rule_differ, big.mark = ","), chk$treatment_year))
  invisible(chk)
}

# v20.59: does the panel carry PIXEL variation? Per variable x year x season: finite rows, mean, SD across pixels, min, max ->
# panel_variation_by_block.csv. A year-season whose value is the same for every pixel is a FILL value, not a measurement: the outcome screen of
# every model leaves it out (OUTCOME_SCREEN), and this table shows it right after R_P00 -- before any model runs. The parts are exact moments
# (n, mean, M2 about it, min, max) so R_P00's blocks and pixel groups (out of core) merge to the same numbers as one pass in memory.
panel_variation_R <- function(dt, vars = OUTCOME_VARS) {
  vs <- intersect(vars, names(dt)); if (!length(vs)) return(NULL)
  rbindlist(lapply(vs, function(v) {
    x <- dt[is.finite(get(v)), { z <- as.numeric(get(v)); mu <- mean(z); .(finite = .N, mean = mu, m2 = sum((z - mu)^2), min = min(z), max = max(z)) }, by = .(Year, Season)]
    x[, variable := rep(v, nrow(x))]; x }), use.names = TRUE, fill = TRUE)      # an outcome with no finite value: an empty part with the same columns
}
# v20.59 -- YOUR RULE: the panel KEEPS every row and value. Fill cells (one value for every pixel) and gap-filled rows stay IN the panel; what a
# MODEL estimates on is ITS decision (OUTCOME_SCREEN, EXCLUDE_GAPFILLED in its notebook), never R_P00's. Said once, with the counts.
panel_kept_report_R <- function(vt, n_gapfilled = 0L) {
  n_fill <- if (is.null(vt) || !nrow(vt)) 0L else sum(vt$constant_across_pixels, na.rm = TRUE)
  ok(sprintf("the panel KEEPS every row and value: %s outcome x year-season fill cell(s) and %s gap-filled row(s) (GapFilled = 1) are IN the panel -- each model decides with OUTCOME_SCREEN (\"drop\" | \"keep\" | \"off\") and EXCLUDE_GAPFILLED (TRUE | FALSE) in its own notebook; the defaults of this run: OUTCOME_SCREEN \"%s\", EXCLUDE_GAPFILLED %s",
             format(n_fill, big.mark = ","), format(n_gapfilled, big.mark = ","), screen_rule_R(), isTRUE(.opt("EXCLUDE_GAPFILLED", TRUE))))
  invisible(list(fill_cells = n_fill, gapfilled_rows = n_gapfilled))
}
panel_variation_report_R <- function(parts, write = TRUE) {
  vt <- rbindlist(Filter(Negate(is.null), if (is.data.frame(parts)) list(parts) else parts), use.names = TRUE)
  if (!nrow(vt)) return(invisible(NULL))
  vt[, `:=`(sn = sum(finite)), by = .(variable, Year, Season)]; vt[, mu := sum(finite * mean) / sn, by = .(variable, Year, Season)]
  vt <- vt[, .(finite = sum(finite), mean = mu[1], m2 = sum(m2) + sum(finite * (mean - mu)^2), min = min(min), max = max(max)), by = .(variable, Year, Season)]
  vt[, sd_across_pixels := fifelse(finite > 1, sqrt(m2 / (finite - 1)), 0)]; vt[, m2 := NULL]
  vt[, constant_across_pixels := finite > 1 & sd_across_pixels <= 1e-9 * pmax(1, abs(mean))]
  setcolorder(vt, c("variable", "Year", "Season", "finite", "mean", "sd_across_pixels", "min", "max", "constant_across_pixels")); setorder(vt, variable, Year, Season)
  if (write) fwrite(vt, file.path(OUTPUT_DIR, "panel_variation_by_block.csv"))
  k <- vt[constant_across_pixels == TRUE]
  if (nrow(k)) warn(sprintf("%d of %d outcome x year-season cells hold ONE value for every pixel (a fill value, not pixel data: the outcome screen of every model leaves them out unless OUTCOME_SCREEN <- \"keep\"): %s%s -> panel_variation_by_block.csv",
                            nrow(k), nrow(vt), paste(sprintf("%s %d %s = %s", k$variable, k$Year, SEASON_LABEL[as.character(k$Season)], formatC(k$mean, digits = 6, format = "g"))[seq_len(min(8, nrow(k)))], collapse = "; "), if (nrow(k) > 8) "; ..." else ""))
  else ok(sprintf("pixel variation CONFIRMED in every outcome x year-season cell (%d cells, no fill value) -> panel_variation_by_block.csv", nrow(vt)))
  invisible(vt)
}

# ---------------------------------------------------------------- 9. the dose: funds released to a sub-watershed, from the NEXT season
next_season <- function(date) {                    # the export calendar: Kharif Jun-Sep, Rabi Oct-Feb, Zaid Mar-May
  m <- as.integer(format(date, "%m")); y <- as.integer(format(date, "%Y"))
  o_s <- ifelse(m %in% 6:9, 1L, ifelse(m %in% c(10:12, 1:2), 2L, 3L)); o_y <- ifelse(m %in% 1:2, y - 1L, y)
  data.table(Year = ifelse(o_s == 2L, o_y + 1L, o_y), Season = ifelse(o_s == 1L, 2L, ifelse(o_s == 2L, 3L, 1L)))
}
read_fund_workbook <- function(path) {
  # v20.51: your fund workbook as the Python pipeline reads it (_prep_common.load_fund_progress, verified on the real file):
  #   v3 (current) row 1 = "<SWS> SWS in <District>" (merged over its metric columns), row 2 = "Area in Hactare",
  #                row 3 = the metric (Target / Progress / Dose-Intensity), data from row 4, the date in column 1
  #   v2           row 2 = District, row 3 = "SWS: name", row 4 = metric, data from row 5
  #   v1           row 2 = District, row 3 = metric, data from row 4 (no sub-watershed names: not usable here)
  # v20.50 read it as a flat table, found no SWS / date / progress column and left the dose EMPTY in every R run.
  raw <- suppressMessages(readxl::read_excel(path, col_names = FALSE, col_types = "list", .name_repair = "minimal"))
  cell <- function(i, j) { v <- raw[[j]][[i]]; if (is.null(v) || !length(v)) NA else v }
  ctxt <- function(i, j) { v <- cell(i, j); if (length(v) != 1 || is.na(v)) NA_character_ else trimws(as.character(v)) }
  rtxt <- function(i) paste(na.omit(vapply(seq_along(raw), function(j) ctxt(i, j), "")), collapse = " ")
  as_day <- function(v) {
    if (inherits(v, c("POSIXct", "POSIXt", "Date"))) return(as.Date(v))
    if (is.numeric(v) && is.finite(v)) return(as.Date(v, origin = "1899-12-30"))
    if (is.character(v)) return(suppressWarnings(as.Date(v, tryFormats = c("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"), optional = TRUE)))
    as.Date(NA)
  }
  re <- "^\\s*(.+?)\\s+SWS\\s+in\\s+(.+?)\\s*$"
  if (any(grepl(re, vapply(seq_along(raw), function(j) ctxt(1, j), ""), ignore.case = TRUE, perl = TRUE))) {
    layout <- "v3"; hdr <- 1L; met <- 3L; first <- 4L; area_row <- if (grepl("area", tolower(rtxt(2)))) 2L else NA_integer_
  } else if (grepl("SWS", rtxt(3))) { layout <- "v2"; hdr <- 2L; met <- 4L; first <- 5L; area_row <- NA_integer_
  } else { layout <- "v1"; hdr <- 2L; met <- 3L; first <- 4L; area_row <- NA_integer_ }
  h <- vapply(seq_along(raw), function(j) ctxt(hdr, j), ""); for (j in seq_along(h)[-1]) if (is.na(h[j])) h[j] <- h[j - 1L]   # merged cells
  sws_row <- if (layout == "v2") vapply(seq_along(raw), function(j) ctxt(3L, j), "") else rep(NA_character_, length(raw))
  if (layout == "v2") for (j in seq_along(sws_row)[-1]) if (is.na(sws_row[j])) sws_row[j] <- sws_row[j - 1L]
  n <- length(raw[[1]]); days <- do.call(c, lapply(seq(first, n), function(i) as_day(cell(i, 1L))))
  recs <- list()
  for (j in seq_along(raw)[-1]) {
    m <- ctxt(met, j); if (is.na(h[j]) || is.na(m)) next
    if (layout == "v3" && grepl(re, h[j], ignore.case = TRUE, perl = TRUE)) {
      sws <- sub(re, "\\1", h[j], ignore.case = TRUE, perl = TRUE); dist <- sub(re, "\\2", h[j], ignore.case = TRUE, perl = TRUE)
    } else { dist <- sub("^SWS:\\s*", "", h[j]); sws <- if (layout == "v2") sub("^SWS:\\s*", "", sws_row[j]) else NA_character_ }
    a <- if (!is.na(area_row)) suppressWarnings(as.numeric(cell(area_row, j))) else NA_real_
    val <- vapply(seq(first, n), function(i) { v <- cell(i, j); if (is.numeric(v)) as.numeric(v) else suppressWarnings(as.numeric(v)) }, 0)
    recs[[length(recs) + 1L]] <- data.table(district = dist, sws = sws, date = days, metric = m, value = val, area = a)
  }
  long <- rbindlist(recs)[!is.na(date) & !grepl("total|toal", tolower(district))]
  attr(long, "layout") <- layout; long
}

fund_dose <- function() {
  if (!file.exists(FUND_RELEASE_PATH) || !requireNamespace("readxl", quietly = TRUE)) { info("fund file not found (or readxl missing): dose columns left empty"); return(NULL) }
  # a FLAT table (one row per sub-watershed and date: SWS / Date / Progress [/ Area] columns) is read as before;
  # otherwise the workbook layouts of the Python loader (v3 / v2)
  flat <- as.data.table(suppressMessages(readxl::read_excel(FUND_RELEASE_PATH, .name_repair = "minimal"))); nm <- tolower(names(flat))
  pick <- function(k) names(flat)[which(grepl(k, nm))[1]]
  c_sws <- pick("sws|sub.?water"); c_date <- pick("date|month"); c_prog <- pick("progress|release|amount"); c_area <- pick("area")
  if (!any(is.na(c(c_sws, c_date, c_prog)))) {
    f <- flat[, .(sws = get(c_sws), date = as.Date(get(c_date)), amount = as.numeric(get(c_prog)), area = if (!is.na(c_area)) as.numeric(get(c_area)) else NA_real_)]
    ok("fund file: a flat table (", uniqueN(f$sws), " sub-watersheds)")
  } else {
    long <- tryCatch(read_fund_workbook(FUND_RELEASE_PATH), error = function(e) { warn("fund file could not be read: ", conditionMessage(e)); NULL })
    if (is.null(long) || !nrow(long)) { warn("fund file: no rows read -- dose left empty"); return(NULL) }
    lay <- attr(long, "layout"); prog_m <- unique(long$metric)[grepl("progress", tolower(unique(long$metric)))][1]
    if (is.na(prog_m) || all(is.na(long$sws))) { warn("fund file (layout ", lay, "): no Progress metric or no sub-watershed names -- dose left empty"); return(NULL) }
    ok("fund file layout detected: ", lay, " (", uniqueN(long$sws), " sub-watersheds, ", uniqueN(long$date), " months, metric '", prog_m, "')")
    area_by <- long[is.finite(area), .(area = area[1]), by = sws]
    f <- merge(long[metric == prog_m, .(sws, date, amount = value)], area_by, by = "sws", all.x = TRUE)
  }
  f[, name := match_sws_name(sws)]; ids <- sws_names(); f[, site_id := as.integer(names(ids)[match(name, ids)])]
  f <- f[!is.na(site_id) & !is.na(date)][order(site_id, date)][, amount := cummax(fifelse(is.na(amount), 0, amount)), by = site_id]
  f <- cbind(f, next_season(f$date))
  f[, .(dose_amount_sws = max(amount), area = { a <- area[is.finite(area)]; if (length(a)) max(a) else NA_real_ }), by = .(site_id, Year, Season)][
    , dose_intensity_per_ha := dose_amount_sws / area][]
}

# ---------------------------------------------------------------- 10. the benchmark sites: THE MEAN OF A SUB-WATERSHED'S BM SITES REPRESENTS IT
bm_sws_means <- function() {
  # The SAME table the Python pipeline builds (python/_bm_means.py, validated against the harmonised 07 file): each
  # sub-watershed's value = the mean over its BM sites of each site's mean over visits and replicates; spellings
  # unified; blank / combined / code names resolved by where the sites lie; sites whose location contradicts their name
  # kept out (see BM_SITE_AUDIT.csv, BM_SWS_SUMMARY.md). A newer table in ROOT/output takes precedence.
  cand <- c(file.path(OUTPUT_DIR, "ground_sws_season_means.csv"), file.path(GROUND_DIR, "bm_sws_season_means.csv"))
  p <- cand[file.exists(cand)][1]
  if (is.na(p)) { info("BM sub-watershed means not found: ", paste(cand, collapse = " | ")); return(NULL) }
  m <- fread(p)
  need <- c("group", "site_id", "variable", "Year", "Season", "value")
  if (!all(need %in% names(m))) { warn("BM table ", p, " lacks ", paste(setdiff(need, names(m)), collapse = ", ")); return(NULL) }
  ok(sprintf("BM sub-watershed means (the mean of each sub-watershed's sites): %d programme + %d control sub-watersheds, variables %s -- %s",
             uniqueN(m[group == "programme", site_id]), uniqueN(m[group == "control", sws]), paste(sort(unique(m$variable)), collapse = ", "), p))
  m[group == "programme" & site_id > 0]
}

# ---------------------------------------------------------------- the pipeline (the Python P00, step for step)
run_prep <- function() {
  t0 <- Sys.time(); dir.create(OUTPUT_DIR, recursive = TRUE, showWarnings = FALSE)
  files <- discover_exports()
  # v20.58 -- YOUR 98 % RULE: exports that would not fit in RAM at once are built into the panel BLOCK BY BLOCK (year x season; out of core,
  # lib/reward_prep_ooc.R -- the same rules, the same panel row for row); below 98 % everything is read at once, exactly as before
  pm <- prep_mode_R(files)
  if (identical(pm$mode, "out_of_core")) return(invisible(run_prep_ooc(files, t0, pm$why)))
  info("reading ", nrow(files), " files (", N_THREADS, " threads)")
  parts <- lapply(seq_len(nrow(files)), function(i) with(files[i], tryCatch(read_export(file, Year, Season, sws_hint, folder, sws_file, mtime),
                  error = function(e) { warn(basename(file), ": ", conditionMessage(e)); NULL })))
  n_bad <- sum(vapply(parts, is.null, logical(1)))
  aud <- rbindlist(Filter(Negate(is.null), lapply(parts, function(p) if (is.null(p)) NULL else attr(p, "input_audit"))), fill = TRUE)   # v20.59
  dt <- rbindlist(parts, fill = TRUE)
  if (!nrow(dt)) stop("no export could be read under ", ROOT)
  input_audit_report_R(aud)                                                                      # v20.59: Treat 1 / 0 and buff_km 0 / 1-5 CONFIRMED per file
  ok(sprintf("%s rows read from %d files%s", format(nrow(dt), big.mark = ","), nrow(files) - n_bad, if (n_bad) sprintf(" (%d unreadable, see above)", n_bad) else ""))
  dt[, pixel_id := pixel_ids(latitude, longitude)]                                                 # PASS A: the id from the coordinates
  ids <- sws_names()
  dt[, sws_export := suppressWarnings(as.integer(if ("SWSiD_All" %in% names(dt)) SWSiD_All else NA_integer_))]
  dt[is.na(sws_hint), sws_hint := ""]
  dt[is.na(sws_export), sws_export := sws_file]                                                # v20.49: the name the FILE carries
  nm_tab <- unique(dt[, .(src_file, sws_file)])[, .(files = .N), by = sws_file]
  info("sub-watershed named by the export files (>= 80 % rule): ", paste(sprintf("%s %d file(s)", fifelse(is.na(nm_tab$sws_file), "none", ids[as.character(nm_tab$sws_file)]), nm_tab$files), collapse = " | "))
  px <- unique(dt[, .(pixel_id, latitude, longitude, sws_export)], by = c("pixel_id", "sws_export"))
  info("overlaying ", format(nrow(px), big.mark = ","), " pixel locations on the 20 sub-watersheds x rings")
  px <- overlay_or_trust(px)                                                                        # v20.59: SITE_GEOMETRY_CHECK
  fwrite(px[, .N, by = .(site_id, site_check)][order(site_id)], file.path(OUTPUT_DIR, "site_tagging_by_sws.csv"))
  dt <- merge(dt, px[, .(pixel_id, sws_export, site_id, ring_poly, site_check)], by = c("pixel_id", "sws_export"), all.x = TRUE)
  dt[site_check %in% ring_from_polygon_codes() & !is.na(ring_poly), buff_km := ring_poly]           # corrected / assigned: the ring of that SWS (BUFF_FROM_GEOMETRY: confirmed too)
  working_sws_line(dt)                                                                              # v20.59: your rule, said with the numbers
  dt[, sws_name := ids[as.character(site_id)]]
  # v20.57 -- YOUR RULE: the major sub-watershed data are processed, smaller fragments of other sub-watersheds are dropped. Every row
  # is coded per export file (reward_design.R file_codes, as python/_fragments.py): 0 its file's own sub-watershed, 1 inside another
  # one's polygon, 2 outside every polygon with another id. The panel keeps every row with its code; FRAGMENT_RULE is applied by the
  # MODELS (so it can be changed without re-running R_P00).
  dt[, fragment := file_codes(site_id, site_check), by = src_file]
  ft <- dt[, .(rows = .N, file_sws = { m <- file_major(fifelse(is.na(site_id), 0L, as.integer(site_id)), fifelse(is.na(site_check), 4L, as.integer(site_check))); if (is.na(m)) 0L else m },
               fragment_rows_other_sws = sum(fragment == 1L), fragment_rows_outside_other_id = sum(fragment == 2L)), by = src_file]
  setorder(ft, src_file)                                                       # v20.58: in file-name order (the same file in memory and block by block)
  fwrite(ft, file.path(OUTPUT_DIR, "site_tagging_by_file.csv"))
  if (any(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id > 0))
    info(sprintf("fragments of other sub-watersheds inside the export files: %s rows in %d file(s) (coded; FRAGMENT_RULE in the models drops them) -> site_tagging_by_file.csv",
                 format(sum(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id), big.mark = ","), sum(ft$fragment_rows_other_sws + ft$fragment_rows_outside_other_id > 0)))
  dt <- merge_near_duplicate_pixels(dt)                                                            # PASS B: >= PIXEL_OVERLAP_MIN = one pixel (before dedup)
  dt <- resolve_duplicates(dt)                                                                     # one row per (site, pixel, year, season)
  dd_stats <- attr(dt, "dedup")                                                                     # v20.58: recorded with the panel below
  if (DROP_ROWS_WITHOUT_OUTCOME) {                                                                 # v20.58: only NOW -- after the newer export's
    n0 <- nrow(dt); dt <- drop_rows_without_outcome(dt)                                            #   (empty) row claimed its pixel-year-season
    if (n0 > nrow(dt)) info(sprintf("%s rows without any outcome left the panel (after the duplicates were resolved: a newer export's empty row is not replaced by an older repeated one)",
                                    format(n0 - nrow(dt), big.mark = ",")))
  }
  # v20.58 -- YOUR RULE: repeated rows and pixels are dropped AND CONFIRMED (checked on the result, never assumed)
  nk <- anyDuplicated(dt, by = c("site_id", "pixel_id", "Year", "Season"))
  if (nk) stop(sprintf("duplicate removal FAILED: (site %s, pixel %s, %s, season %s) is still repeated -- please report this", dt$site_id[nk], dt$pixel_id[nk], dt$Year[nk], dt$Season[nk]))
  no <- dt[site_check == 3L, anyDuplicated(.SD), .SDcols = c("pixel_id", "Year", "Season")]
  if (no) stop("duplicate removal FAILED: a pixel outside every polygon is still repeated in a year-season -- please report this")
  n2 <- nrow(dt) - uniqueN(dt, by = c("pixel_id", "Year", "Season"))
  if (n2) info(sprintf("%s pixel-year-season(s) lie in the polygons of TWO sub-watersheds (their zones overlap): kept once per sub-watershed -- the location rule of the models keeps each in its own sub-watershed only", format(n2, big.mark = ",")))
  if (isTRUE(NEAR_DUPLICATE_PIXELS)) {
    reg2 <- pixel_registry(dt); left <- nrow(near_duplicate_pairs(reg2))
    (if (left) warn else ok)(sprintf("near-duplicate pixels CONFIRMED: %s pixel(s) remain whose footprints overlap >= %.0f %% among %s pixels%s", format(left, big.mark = ","),
                                     100 * PIXEL_OVERLAP_MIN, format(nrow(reg2), big.mark = ","), if (left) " (a chain the one-to-one merge cannot join) -- the models leave the smaller of each pair out (OVERLAP_ROWS)" else ""))
  }
  ok(sprintf("duplicates CONFIRMED removed: %s rows, every (sub-watershed, pixel, year, season) exactly once", format(nrow(dt), big.mark = ",")))
  dt <- panel_design_columns_R(dt)                                                                  # v20.59: treat / control / pre / post / did in the panel
  vt <- panel_variation_report_R(panel_variation_R(dt))                                             # v20.59: pixel variation per outcome x year-season
  panel_kept_report_R(vt, if ("GapFilled" %in% names(dt)) sum(dt$GapFilled > 0, na.rm = TRUE) else 0L)   # v20.59: the panel KEEPS every row and value
  keep_cols <- intersect(c("pixel_id", "site_id", "Year", "Season", "latitude", "longitude", "buff_km", "sws_export", "site_check", "sws_name",
                           "fragment", "SubwshedID", "Treat", PANEL_DESIGN_COLS, OUTCOME_VARS, WEATHER_VARS, DESCRIPTOR_VARS, EXTRA_VARS), names(dt))
  keep_cols <- setdiff(keep_cols, panel_columns_left_out_R())                                    # v20.58: the project's models' columns
  dt <- dt[, ..keep_cols]
  # v20.57: NOTHING of the design a MODEL chooses is baked into the panel -- the timing (fund / registry / fixed), the unit and period fixed
  # effects (POOLED_FE), event_time / cohort and the dose are computed by every MODEL when it runs (reward_design.R model_design +
  # load_panel_R), from the settings in ITS notebook. Until v20.56 they were fixed here, so a change of TREATMENT_YEAR or POOLED_FE needed
  # this hours-long step again. v20.59: the panel carries the EXPORTS' design (treat / control / pre / post / did, panel_design_columns_R)
  # as the default every model compares its own design with -- the model's columns are the ones it estimates on.
  n_sites <- uniqueN(dt$site_id[dt$site_id > 0 & dt$fragment == 0L])
  info(sprintf("%d sub-watershed(s) in the panel after the fragment rule (the pooled design, POOLED_FE and the clusters are set by each model)", n_sites))
  ftab <- tryCatch(build_fund_tables(sort(unique(dt$Year)), out_dir = file.path(RESULTS_DIR, "FUND")), error = function(e) { warn("fund tables: ", conditionMessage(e)); NULL })
  if (!is.null(ftab)) print(ftab$timing[, .(site_id, sws_name, area_ha, first_month, amount_first_month, backcast_start, first_treated_label, cohort_annual)])
  bm <- if (!exists("PIPELINE_MODELS") || !length(PIPELINE_MODELS) || "M07" %in% PIPELINE_MODELS) bm_sws_means() else NULL   # v20.58: M07's input only
  if (!is.null(bm)) {                                                                                  # BM sub-watershed means, per season
    bm[, bm_var := paste0("BM_", variable)]
    w <- dcast(bm, site_id + Year + Season ~ bm_var, value.var = "value")
    dt <- merge(dt, w, by = c("site_id", "Year", "Season"), all.x = TRUE)
  }
  setorder(dt, Year, Season, site_id, pixel_id)
  panel_write(dt)                                                                                 # arrow, else CSV
  # v20.58: how this panel was built (as Python's panel_build_settings.json) -- load_panel_R says so when a panel's repeated rows filled gaps
  fwrite(data.table(setting = c("engine_policy", "dedup_priority", "dedup_fill_from_duplicates", "dedup_values_filled", "dedup_values_not_used",
                                "near_duplicate_pixels", "pixel_overlap_min", "period_rule", "period_rows_dropped", "written"),
                    value = c("v20.59", DEDUP_PRIORITY, as.character(isTRUE(DEDUP_FILL_FROM_DUPLICATES)), as.character(dd_stats$filled %||% 0L),
                              as.character(dd_stats$not_used %||% 0L), as.character(isTRUE(NEAR_DUPLICATE_PIXELS)), as.character(PIXEL_OVERLAP_MIN),
                              period_rule_R(), as.character(if (nrow(aud)) sum(aud$rows_dropped_period_disagree, na.rm = TRUE) else 0L),   # v20.59
                              format(Sys.time(), "%Y-%m-%d %H:%M:%S"))), file.path(OUTPUT_DIR, "panel_build_settings_R.csv"))
  bal <- dt[, .(pixels = uniqueN(pixel_id)), by = .(Year, Season)][order(Year, Season)]
  fwrite(bal, file.path(OUTPUT_DIR, "panel_balance_by_block.csv"))
  ok(sprintf("panel: %s rows, %s pixels, %d sub-watershed(s), %d year-seasons (pixels per year-season %s-%s: an unbalanced panel is kept as it is; a missing pixel-period leaves only the estimations that need it) -> %s (%.1f min)",
             format(nrow(dt), big.mark = ","), format(uniqueN(dt$pixel_id), big.mark = ","), uniqueN(dt$site_id[dt$site_id > 0]), nrow(bal), min(bal$pixels), max(bal$pixels),
             PANEL_PATH, as.numeric(difftime(Sys.time(), t0, units = "mins"))))
  invisible(dt)
}

# ---------------------------------------------------------------- the design every model inherits (v20.57: each model applies its own)
prepare_design <- function() {
  # v20.57: the design is set in each MODEL notebook and applied when the model runs (model_design + load_panel_R). This shows the
  # design the DEFAULTS give (lib/reward_paths.R), writes DESIGN_RECOMMENDATION.md and caches the data-driven choices the models
  # use for the options set to "data"; R_design.json is informational (no model reads it any more).
  d <- model_design(verbose = TRUE, force = TRUE)
  save_design(d); ok("design with the default settings saved -> ", DESIGN_PATH, " | ", scenario_tag(d))
  idt <- tryCatch(outcome_identities_R(verbose = TRUE), error = function(e) { warn("outcome identities: ", conditionMessage(e)); NULL })   # v20.58
  if (!is.null(idt) && !nrow(idt)) ok("outcome identities: no two outcomes are the same variable in this panel")
  invisible(d)
}

# v20.58: R_P00 beyond 98 % of the RAM -- the panel block by block (lib/reward_prep_ooc.R)
source(file.path(R_HOME_DIR, "lib", "reward_prep_ooc.R"), local = environment())
