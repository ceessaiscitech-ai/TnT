# reward_fund.R -- v20.57: YOUR FUND WORKBOOK AS EACH SUB-WATERSHED'S TREATMENT TIMING AND DOSE (as python/_fund.py, step for step;
# validate_r_parity.py compares the tables).
#   amount     the CORRECTED cumulative amount released (the file's "Progress"): a later downward revision corrects the earlier
#              reports, so the amount at a month = the smallest amount reported at that month or any later month
#   dose/ha    amount / the treatment area ("Area in Hectare (Cohort Size)" row; the registry's core area when absent) -- YOUR DEFINITION
#   timing     FUND_START_RULE: "backcast" (default: the releases before the file extrapolated back at the rate observed over the
#              file's first FUND_RATE_MONTHS months -- a PROXY), "share" (the amount reaches FUND_START_SHARE x Target), "file_start"
#   The treatment starts in the SEASON AFTER the start month (no anticipation); the export calendar: Zaid Y = Mar-May, Kharif Y =
#   Jun-Sep, Rabi Y = Oct Y - Feb Y+1, the annual composite = Jan-Dec Y. Per row the cohort = the first Year its own series is treated.
#   Dose per season = the amount by the end of the PREVIOUS season / area; 0 before the start; on the back-cast line between the
#   start and the file (dose_estimated = 1; FUND_DOSE_BEFORE_FILE = "missing" leaves them out); the annual row = the mean over its
#   12 calendar months of the dose in effect.
if (!exists("FUND_START_RULE")) FUND_START_RULE <- "backcast"
if (!exists("FUND_START_SHARE")) FUND_START_SHARE <- 0.10
if (!exists("FUND_RATE_MONTHS")) FUND_RATE_MONTHS <- 12L
if (!exists("FUND_DOSE_BEFORE_FILE")) FUND_DOSE_BEFORE_FILE <- "backcast"
SEASON_RANK <- c("3" = 0L, "1" = 1L, "2" = 2L); RANK_SEASON <- c("0" = 3L, "1" = 1L, "2" = 2L)
SEASON_NAME <- c("0" = "Yearly", "1" = "Kharif", "2" = "Rabi", "3" = "Zaid")

month_index <- function(d) as.integer(format(d, "%Y")) * 12L + as.integer(format(d, "%m")) - 1L
month_label <- function(mi) ifelse(is.na(mi), "", sprintf("%d-%02d", mi %/% 12L, mi %% 12L + 1L))
season_of_month <- function(mi) {
  y <- mi %/% 12L; m <- mi %% 12L + 1L
  ifelse(m >= 3L & m <= 5L, 3L * y, ifelse(m >= 6L & m <= 9L, 3L * y + 1L, ifelse(m >= 10L, 3L * y + 2L, 3L * (y - 1L) + 2L)))
}
last_month_of_season <- function(q) { y <- q %/% 3L; r <- q %% 3L; ifelse(r == 0L, 12L * y + 4L, ifelse(r == 1L, 12L * y + 8L, 12L * (y + 1L) + 1L)) }
q_of <- function(year, season) 3L * as.integer(year) + SEASON_RANK[as.character(season)]

read_crosswalk <- function(path = CROSSWALK_PATH) {                       # _prep_common.load_subwshed_crosswalk: District -> Sub Watershed Name
  for (sh in readxl::excel_sheets(path)) {
    raw <- suppressMessages(readxl::read_excel(path, sheet = sh, col_names = FALSE, .name_repair = "minimal"))
    if (!nrow(raw)) next
    for (hr in seq_len(min(6L, nrow(raw)))) {
      v <- tolower(trimws(as.character(unlist(raw[hr, ])))); dc <- which(grepl("district", v))[1]; sc <- which(grepl("sub", v) & grepl("watershed", v))[1]
      if (!is.na(dc) && !is.na(sc)) {
        x <- data.table(district = trimws(as.character(unlist(raw[-(1:hr), dc]))), sws = trimws(as.character(unlist(raw[-(1:hr), sc]))))
        return(x[!is.na(district) & !is.na(sws) & district != "NA" & sws != "NA"])
      }
    }
  }
  stop("no sheet in ", path, " has both 'District' and 'Sub Watershed Name' columns")
}

fund_monthly <- function(path = FUND_RELEASE_PATH) {
  if (!file.exists(path) || !requireNamespace("readxl", quietly = TRUE)) return(NULL)
  flat <- tryCatch(as.data.table(suppressMessages(readxl::read_excel(path, .name_repair = "minimal"))), error = function(e) NULL)
  long <- NULL; layout <- NA_character_
  if (!is.null(flat) && ncol(flat)) {
    nm <- tolower(names(flat)); pick <- function(k) names(flat)[which(grepl(k, nm))[1]]
    c_sws <- pick("sws|sub.?water"); c_date <- pick("date|month"); c_prog <- pick("progress|release|amount")
    if (!any(is.na(c(c_sws, c_date, c_prog))) && length(unique(c(c_sws, c_date, c_prog))) == 3) {
      dd <- suppressWarnings(as.Date(flat[[c_date]]))
      if (mean(!is.na(dd)) >= 0.5) {
        c_area <- pick("area"); c_tgt <- pick("target")
        long <- data.table(sws = as.character(flat[[c_sws]]), district = "", date = dd, amount_reported = suppressWarnings(as.numeric(flat[[c_prog]])),
                           target = if (!is.na(c_tgt)) suppressWarnings(as.numeric(flat[[c_tgt]])) else NA_real_,
                           area_ha = if (!is.na(c_area)) suppressWarnings(as.numeric(flat[[c_area]])) else NA_real_)
        layout <- "flat table"
      }
    }
  }
  if (is.null(long)) {
    w <- tryCatch(read_fund_workbook(path), error = function(e) { warn("fund file could not be read: ", conditionMessage(e)); NULL })
    if (is.null(w) || !nrow(w)) return(NULL)
    layout <- attr(w, "layout"); mets <- unique(w$metric)
    prog_m <- mets[grepl("^progress", tolower(mets))][1]; tgt_m <- mets[grepl("^target", tolower(mets))][1]
    if (is.na(prog_m)) { warn("fund file (layout ", layout, "): no Progress metric"); return(NULL) }
    if (all(is.na(w$sws)) && file.exists(CROSSWALK_PATH)) {                                  # v1: district only -> the crosswalk
      xw <- tryCatch(read_crosswalk(CROSSWALK_PATH), error = function(e) NULL)
      if (!is.null(xw)) w[, sws := xw$sws[match(tolower(trimws(district)), tolower(trimws(xw$district)))]]
    }
    area_by <- w[is.finite(area), .(area_ha = area[1]), by = .(sws, district)]                # the area sits under ONE metric column of each block
    long <- merge(w[metric == prog_m, .(sws, district, date, amount_reported = value)],
                  if (!is.na(tgt_m)) w[metric == tgt_m, .(sws, district, date, target = value)] else w[metric == prog_m, .(sws, district, date, target = NA_real_)],
                  by = c("sws", "district", "date"), all.x = TRUE)
    long <- merge(long, area_by, by = c("sws", "district"), all.x = TRUE)
  }
  long <- long[!is.na(date)]
  ids <- sws_names(); nmx <- match_sws_name(long$sws)
  long[, site_id := as.integer(names(ids)[match(nmx, ids)])]
  unmatched <- sort(setdiff(unique(long[is.na(site_id), sws]), NA))
  long <- long[!is.na(site_id)]
  long[, sws_name := unname(ids[as.character(site_id)])]
  long[, month := month_index(date)]
  reg <- fread(SITES_CSV); core <- setNames(as.numeric(reg$core_area), reg$SWSiD_All)
  long[, a_file := { a <- area_ha[is.finite(area_ha)]; if (length(a)) a[1] else NA_real_ }, by = site_id]
  long[, area_source := fifelse(is.finite(a_file), "fund file", "sites.csv core_area")]
  long[, area_ha := fifelse(is.finite(a_file), a_file, unname(core[as.character(site_id)]))][, a_file := NULL]
  setorder(long, site_id, month)
  attr(long, "layout") <- layout; attr(long, "unmatched") <- unmatched
  ok(sprintf("fund file (%s): %d sub-watersheds matched by the 80 %% name rule, %d months %s -> %s%s", layout, uniqueN(long$site_id), uniqueN(long$month),
             month_label(min(long$month)), month_label(max(long$month)), if (length(unmatched)) paste0("; NOT matched: ", paste(unmatched, collapse = ", ")) else ""))
  long
}

fund_series <- function(long) {
  s <- unique(long, by = c("site_id", "month"), fromLast = TRUE)[order(site_id, month)]
  s[, rep := { v <- as.numeric(amount_reported); for (i in seq_along(v)[-1]) if (is.na(v[i])) v[i] <- v[i - 1L]; v[is.na(v)] <- 0; v }, by = site_id]
  s[, amount := rev(cummin(rev(rep))), by = site_id]                                          # later downward revisions correct the earlier reports
  s[, `:=`(release = c(amount[1], diff(amount)), revised_down_by = rep - amount), by = site_id]
  s[, `:=`(share_of_target = amount / fifelse(target > 0, target, NA_real_), dose_per_ha = amount / fifelse(area_ha > 0, area_ha, NA_real_))]
  s[, rep := NULL][]
}

fund_timing <- function(s, rule = FUND_START_RULE, share = FUND_START_SHARE, rate_months = FUND_RATE_MONTHS) {
  rbindlist(lapply(split(s, by = "site_id"), function(g) {
    g <- g[order(month)]; mm <- g$month; a <- g$amount; m0 <- mm[1]; m1 <- mm[length(mm)]; a0 <- a[1]
    tgt <- { v <- g$target[is.finite(g$target)]; if (length(v)) v[1] else NA_real_ }; area <- { v <- g$area_ha[is.finite(g$area_ha)]; if (length(v)) v[1] else NA_real_ }
    j <- min(length(mm), as.integer(rate_months))
    rate <- if (j > 1 && mm[j] > mm[1]) (a[j] - a[1]) / (mm[j] - mm[1]) else NA_real_
    if (a0 > 0 && is.finite(rate) && rate > 0) { k <- as.integer(ceiling(a0 / rate - 1e-9)); bs <- m0 - k + 1L; note <- sprintf("back-cast at %.4g per month over the file's first %d months", rate, j) }
    else if (a0 > 0) { k <- 1L; bs <- m0; note <- "no release after the first month to extrapolate: the file's first month (a lower bound)" }
    else { pos <- which(a > 0); k <- 0L; bs <- if (length(pos)) mm[pos[1]] else NA_integer_; note <- "first release observed in the file" }
    if (rule == "share") {
      thr <- share * tgt; start <- NA_integer_; how <- sprintf("first month the amount reaches %.0f%% of the target (%.4g)", 100 * share, thr)
      if (is.finite(thr)) {
        if (a0 >= thr && a0 > 0 && !is.na(bs) && bs < m0 && k > 0) { start <- as.integer(bs + max(0, ceiling(thr / a0 * k - 1e-9) - 1)); how <- paste(how, "(on the back-cast line)") }
        else if (a0 >= thr) start <- m0
        else { hit <- which(a >= thr); if (length(hit)) start <- mm[hit[1]] }
      }
    } else if (rule == "file_start") { start <- if (a0 > 0) m0 else bs; how <- "the file's first month (a lower bound of the start)"
    } else { start <- bs; how <- note }
    out <- data.table(site_id = g$site_id[1], sws_name = g$sws_name[1], district = g$district[1], area_ha = area, area_source = g$area_source[1], target = tgt,
                      first_month = month_label(m0), last_month = month_label(m1), amount_first_month = a0, share_first_month = if (is.finite(tgt) && tgt > 0) a0 / tgt else NA_real_,
                      rate_per_month = rate, months_before_file = k, backcast_start = month_label(bs), backcast_start_index = bs, start_rule = rule,
                      start_month = month_label(start), start_index = start, start_how = how, censored = a0 > 0 && rule != "backcast" && isTRUE(start == m0),
                      amount_last_month = a[length(a)], share_last_month = if (is.finite(tgt) && tgt > 0) a[length(a)] / tgt else NA_real_,
                      revisions_down = sum(g$revised_down_by > 1e-9), largest_revision = max(g$revised_down_by), file_first_index = m0, file_last_index = m1)
    if (!is.na(start)) {
      qs <- season_of_month(start) + 1L; ys <- qs %/% 3L; rs <- qs %% 3L
      out[, `:=`(first_treated_year = ys, first_treated_season = unname(RANK_SEASON[as.character(rs)]),
                 first_treated_label = paste(SEASON_NAME[as.character(RANK_SEASON[as.character(rs)])], ys), cohort_annual = ys + as.integer(rs == 2L))]
    } else out[, `:=`(first_treated_year = NA_integer_, first_treated_season = NA_integer_, first_treated_label = "not reached in the file", cohort_annual = NA_integer_)]
    out
  }))
}

fund_amount_at <- function(t, s, mi, before_file = FUND_DOSE_BEFORE_FILE) {
  if (mi > t$file_last_index) return(list(NA_real_, FALSE))
  if (mi >= t$file_first_index) return(list(s[month <= mi, amount[.N]], FALSE))
  bs <- t$backcast_start_index; k <- t$months_before_file
  if (is.na(bs) || k <= 0) return(list(0, FALSE))
  if (mi < bs) return(list(0, FALSE))
  if (identical(before_file, "missing")) return(list(NA_real_, TRUE))
  list(t$amount_first_month * (mi - bs + 1) / k, TRUE)
}

fund_season_dose <- function(s, tim, years, before_file = FUND_DOSE_BEFORE_FILE) {
  rbindlist(lapply(seq_len(nrow(tim)), function(i) {
    t <- tim[i]; ss <- s[site_id == t$site_id]; cache <- new.env()
    dq <- function(q) { key <- as.character(q); if (is.null(cache[[key]])) cache[[key]] <- fund_amount_at(t, ss, last_month_of_season(q - 1L), before_file); cache[[key]] }
    rbindlist(lapply(years, function(y) {
      se <- rbindlist(lapply(c(3L, 1L, 2L), function(code) { v <- dq(q_of(y, code)); data.table(Season = code, dose_amount_sws = v[[1]], dose_estimated = v[[2]]) }))
      mv <- lapply(1:12, function(m) dq(season_of_month(12L * y + m - 1L)))
      vals <- vapply(mv, `[[`, 0, 1); ests <- vapply(mv, `[[`, TRUE, 2)
      rbind(se, data.table(Season = 0L, dose_amount_sws = if (all(is.finite(vals))) mean(vals) else NA_real_, dose_estimated = any(ests)))[, Year := as.integer(y)]
    }))[, `:=`(site_id = t$site_id, area_ha = t$area_ha, target = t$target)]
  }))[, `:=`(dose_intensity_per_ha = dose_amount_sws / fifelse(area_ha > 0, area_ha, NA_real_), dose_share_of_target = dose_amount_sws / fifelse(target > 0, target, NA_real_),
             dose_estimated = as.integer(dose_estimated))][, .(site_id, Year, Season, dose_amount_sws, dose_estimated, dose_intensity_per_ha, dose_share_of_target)]
}

# per row: the first Year in which THIS row's series (pixel x season) is treated; site_start: data.table(site_id, year, season)
row_cohort <- function(site_id, Season, site_start, default_year) {
  ys <- rep(as.integer(default_year), length(site_id)); rs <- rep(0L, length(site_id))
  if (!is.null(site_start) && nrow(site_start)) {
    k <- match(site_id, site_start$site_id); h <- !is.na(k)
    ys[h] <- as.integer(site_start$year[k[h]]); rs[h] <- unname(SEASON_RANK[as.character(site_start$season[k[h]])])
  }
  rr <- unname(SEASON_RANK[as.character(Season)]); rr[is.na(rr)] <- -1L
  later <- ifelse(Season == 0L, rs == 2L, rr >= 0L & rr < rs)
  ys + as.integer(later)
}

build_fund_tables <- function(years, out_dir = RESULTS_DIR, path = FUND_RELEASE_PATH) {
  long <- fund_monthly(path); if (is.null(long) || !nrow(long)) { info("fund file not found or unreadable (", path, "): no fund timing or dose"); return(NULL) }
  s <- fund_series(long); tim <- fund_timing(s); dose <- fund_season_dose(s, tim, years)
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  fwrite(tim[, !c("backcast_start_index", "start_index", "file_first_index", "file_last_index")], file.path(out_dir, "FUND_TIMING.csv"))
  fwrite(dose, file.path(out_dir, "FUND_SEASON_DOSE.csv"))
  fwrite(copy(s)[, month := month_label(month)], file.path(out_dir, "FUND_MONTHLY.csv"))
  ok("fund timing and dose -> FUND_TIMING.csv, FUND_SEASON_DOSE.csv in ", out_dir, " (start rule ", FUND_START_RULE, ")")
  list(timing = tim, dose = dose, series = s)
}
