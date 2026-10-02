# reward_diagnostics.R -- v20.52: WHY an effect does (not) show. Every number is measured on YOUR panel; nothing assumed.
# effect_diagnostics(outcomes) writes to results/DIAGNOSTICS/: one CSV per check and EFFECT_DIAGNOSTICS.md (the verdict).
#  1 history-filled rows   GapFilled / Coverage by year and group: post values blended with pre-period history shrink the DiD
#  2 optical source        SrcOpt by year and season: MODIS (500 m) or projected windows cannot separate the core from ring 1
#  3 resolution            distinct values per pixel: a coarse product repeats one value over hundreds of 10 m pixels
#  4 ring gradient         the raw change of the core against EACH ring, and of each ring against the farthest (spillover)
#  5 seasons               the raw DiD per season (works that store water act in Rabi / Zaid, the annual mean dilutes them)
#  6 tails                 quantiles of the pixel change, core vs control (an effect on a few treated fields hides in the mean)
#  7 land use              the raw DiD by land-use class (built-up, water, forest dilute a farm-level effect)
#  8 dose                  the raw DiD by fund-intensity tercile (more money, more effect?)
#  9 scale                 the range of each outcome by year (a unit or scaling change between exports)
suppressPackageStartupMessages({ library(data.table) })

.diag_frame <- function(outcome, d) {
  cols <- intersect(unique(c("pixel_id", "site_id", "Year", "Season", "buff_km", "LandUse", "GapFilled", "Coverage",
                             "SrcOpt", "dose_intensity_per_ha", "dose_amount_sws", "dose_share_of_target", outcome, "site_check", "sws_export")), panel_names())
  x <- panel_read(cols)                                                    # every ring: the gradient needs them all (a diagnostic of the rings)
  if ("site_id" %in% names(x)) {                                           # v20.58: the LOCATION rule -- the processed sub-watershed(s) only
    loc <- location_table_R(); S <- d$processed %||% processing_set_R(loc, d$sub_watersheds %||% "data", d$fragment_min_share %||% 0.05)$sites
    dc <- c(if (identical(d$fragment_rule %||% "drop", "drop")) 1:2, if (identical(d$overlap_rows %||% "drop", "drop")) 3:4)
    if (length(dc)) x <- x[!location_codes_R(x, loc, S) %in% dc]
  }
  x <- x[is.finite(get(outcome))]
  x <- design_columns(x, d)                                                # v20.57: post per row -- the timing in force (fund / registry / fixed)
  x <- attach_dose_R(x, d); x[, dose_intensity_per_ha := dose]            # the fund dose (DOSE_VARIABLE), 0 on the rings and before treatment
  setnames(x, outcome, "y"); x[, grp := fifelse(is.na(buff_km), "outside rings", fifelse(buff_km == 0, "core", paste0("ring", buff_km)))]
  x
}
.did <- function(x, g1, g0) {                                              # raw DiD of group means (years pooled)
  m <- x[grp %in% c(g1, g0), .(m = mean(y), n = .N), by = .(grp, post)]
  v <- function(g, p) m[grp == g & post == p, m]
  if (nrow(m) < 4) return(NA_real_)
  (v(g1, 1) - v(g1, 0)) - (v(g0, 1) - v(g0, 0))
}

effect_diagnostics <- function(outcomes = OUTCOMES, d = load_design(), main = outcomes[1]) {
  od <- file.path(RESULTS_DIR, "DIAGNOSTICS"); dir.create(od, recursive = TRUE, showWarnings = FALSE)
  outcomes <- intersect(outcomes, panel_names())
  # v20.55: the panel carries every outcome column (an index the exports lack is NaN throughout, as in Python) -- only those with data
  outcomes <- outcomes[vapply(outcomes, function(o) any(is.finite(panel_read(o)[[o]])), logical(1))]
  if (!length(outcomes)) stop("none of these outcomes has data in the panel")
  far <- max(d$control_rings); ctrl <- paste0("ring", d$control_rings)
  R <- list(gap = list(), src = list(), res = list(), grad = list(), seas = list(), tail = list(), lu = list(), dose = list(), scale = list(), plaus = list())
  for (o in outcomes) {
    x <- .diag_frame(o, d); x[, is_ctrl := grp %in% ctrl]
    # 1 history-filled rows (BEFORE they are left out) -- by year and group
    gf <- rep(FALSE, nrow(x)); if ("GapFilled" %in% names(x)) gf <- gf | (!is.na(x$GapFilled) & x$GapFilled > 0)
    if ("Coverage" %in% names(x)) gf <- gf | (!is.na(x$Coverage) & x$Coverage <= 0)
    x[, filled := gf]
    R$gap[[o]] <- x[grp == "core" | is_ctrl, .(rows = .N, filled = sum(filled), share_filled = round(mean(filled), 4)),
                    by = .(Year, group = fifelse(grp == "core", "core", "control"))][order(Year, group)]
    xs <- x[!(filled)]                                                     # the rows an estimate uses
    # 2 optical source by year and season
    if ("SrcOpt" %in% names(xs)) R$src[[o]] <- xs[, .(rows = .N), by = .(Year, Season, SrcOpt)][
      , share := round(rows / sum(rows), 4), by = .(Year, Season)][order(Year, Season, SrcOpt)]
    # 3 resolution: distinct values per 100 pixels in the core and ring 1 (a coarse product repeats values)
    R$res[[o]] <- xs[grp %in% c("core", "ring1"), .(pixels = .N, distinct = uniqueN(round(y, 6))), by = .(Year, Season)][
      , distinct_per_100_pixels := round(100 * distinct / pixels, 2)][order(Year, Season)]
    # 4-8 from each pixel x season series' OWN change against its pre-period mean, compared YEAR BY YEAR (then averaged
    # over the post years): neither a pixel missing in some years nor a year missing for some pixels (history-filled rows
    # left out, the 2025 grid) can move the comparison -- the raw analogue of pixel and year fixed effects
    pre <- xs[post == 0, .(pre = mean(y)), by = .(pixel_id, Season)]
    keep <- intersect(c("pixel_id", "site_id", "Season", "Year", "grp", "y", "LandUse", "dose_intensity_per_ha"), names(xs))
    ch <- merge(xs[post == 1, ..keep], pre, by = c("pixel_id", "Season"))[, dy := y - pre]
    if (!"LandUse" %in% names(ch)) ch[, LandUse := NA_real_]
    ch[, dose := if ("dose_intensity_per_ha" %in% names(ch)) dose_intensity_per_ha else NA_real_][!is.finite(dose), dose := NA_real_]
    ch[, ctrl := grp %in% ctrl]
    dd <- function(z, a1, a0) {                                            # mean over post years of the yearly group difference
      z <- data.table(Year = z$Year, dy = z$dy, a1 = a1, a0 = a0)
      yy <- z[, .(v = if (any(a1) && any(a0)) mean(dy[a1]) - mean(dy[a0]) else NA_real_), by = Year][is.finite(v)]
      if (nrow(yy)) mean(yy$v) else NA_real_
    }
    for (s in sort(unique(ch$Season))) {                                  # 4 the core against each ring; each ring against the farthest
      z <- ch[Season == s]; fr <- paste0("ring", far)
      R$grad[[paste(o, s)]] <- rbindlist(lapply(sort(unique(z$grp[z$grp != "core"])), function(r) data.table(Season = s, ring = r,
        did_core_vs_ring = dd(z, z$grp == "core", z$grp == r), did_ring_vs_farthest = if (r == fr) 0 else dd(z, z$grp == r, z$grp == fr))))
    }
    cc <- ch[grp == "core" | ctrl]
    R$seas[[o]] <- cc[, .(did = dd(.SD, grp == "core", ctrl), core_rows = sum(grp == "core"), control_rows = sum(ctrl)), by = Season][order(Season)]   # 5
    q <- c(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)                                                                                                         # 6
    cc[, dy_net := dy - mean(dy[ctrl]), by = .(Year, Season)]
    ser <- cc[, .(dy_net = mean(dy_net)), by = .(pixel_id, Season, core = grp == "core")]
    R$tail[[o]] <- data.table(q = q, core = as.numeric(quantile(ser[(core), dy_net], q)), ctrl = as.numeric(quantile(ser[!(core), dy_net], q)))[, core_minus_ctrl := core - ctrl]
    if (any(!is.na(cc$LandUse))) R$lu[[o]] <- cc[!is.na(LandUse), .(did = dd(.SD, grp == "core", ctrl), core_rows = sum(grp == "core"), control_rows = sum(ctrl)), by = LandUse][order(LandUse)]   # 7
    pdz <- cc[grp == "core" & is.finite(dose), .(dose = mean(dose)), by = site_id]                                                                    # 8
    if (nrow(pdz) >= 1) {
      br <- unique(quantile(pdz$dose, c(0, 1/3, 2/3, 1))); pdz[, tercile := if (length(br) > 1) cut(dose, br, include.lowest = TRUE, labels = FALSE) else 1L]
      R$dose[[o]] <- rbindlist(lapply(sort(unique(pdz$tercile)), function(t) { z <- cc[site_id %in% pdz[tercile == t, site_id]]
        data.table(dose_tercile = t, sub_watersheds = nrow(pdz[tercile == t]), mean_dose = mean(pdz[tercile == t, dose]), did = dd(z, z$grp == "core", z$ctrl)) }))
    }
    # 10 plausibility of an optical index: a whole-sub-watershed mean below 0.10 in a season is what clouds, haze or water
    # give, not vegetation (the monsoon season should be the GREENEST, not the lowest)
    if (o %in% c("NDVI", "EVI", "SAVI")) {
      sm <- xs[grp == "core", .(m = mean(y)), by = .(Season, Year)]
      low <- sm[m < 0.10]; bySeason <- sm[, .(mean = mean(m)), by = Season][order(-mean)]
      if (nrow(low)) R$plaus[[o]] <- data.table(note = sprintf("%s: the core's mean is below 0.10 in %d season-year(s) (%s); season means %s -- values like these come from clouds, haze or water, not crops: that season cannot show an effect and should be re-exported cloud-free.",
        o, nrow(low), paste(sprintf("S%s %d: %.3f", low$Season, low$Year, low$m), collapse = ", "), paste(sprintf("S%s %.3f", bySeason$Season, bySeason$mean), collapse = ", ")))
    }
    # 9 scale by year
    R$scale[[o]] <- xs[, .(min = min(y), p01 = quantile(y, 0.01), median = median(y), p99 = quantile(y, 0.99), max = max(y)), by = .(Year)][order(Year)]
    if (o == main) {                                                       # the picture: raw yearly means by ring and season
      mm <- xs[, .(mean = mean(y)), by = .(Year, Season, grp)]
      fwrite(mm, file.path(od, sprintf("DIAG_raw_means_%s.csv", o)))
      if (requireNamespace("ggplot2", quietly = TRUE)) try({
        g <- ggplot2::ggplot(mm, ggplot2::aes(Year, mean, colour = grp)) + ggplot2::geom_line() + ggplot2::geom_point(size = 0.8) +
          ggplot2::geom_vline(xintercept = as.integer(d$treatment_year %||% TREATMENT_YEAR) - 0.5, linetype = 2) +
          ggplot2::facet_wrap(~ Season, scales = "free_y", labeller = ggplot2::label_both) + ggplot2::labs(title = paste(o, ": raw yearly means, core vs rings"), y = o)
        ggplot2::ggsave(file.path(od, sprintf("DIAG_raw_means_%s.png", o)), g, width = 11, height = 6, dpi = 120) }, silent = TRUE)
    }
    rm(x, xs, ch, cc); gc(verbose = FALSE)
  }
  tabs <- lapply(R, function(l) rbindlist(lapply(names(l), function(k) { z <- as.data.table(l[[k]]); if (!"outcome" %in% names(z)) z[, outcome := rep(sub(" .*$", "", k), nrow(z))]; setcolorder(z, "outcome"); z }), fill = TRUE))
  for (k in names(tabs)) if (nrow(tabs[[k]])) fwrite(tabs[[k]], file.path(od, sprintf("DIAG_%s.csv", k)))
  md <- .diag_verdict(tabs, d, far); writeLines(md, file.path(od, "EFFECT_DIAGNOSTICS.md")); cat(md, sep = "\n")
  invisible(tabs)
}

.diag_verdict <- function(T, d, far) {
  ty <- as.integer(d$treatment_year %||% TREATMENT_YEAR); L <- c("# Why the effect is what it is -- measured on your panel", "",
    sprintf("Design: treatment %d, control rings %s, seasons %s. Every figure below comes from the CSV files beside this report.", ty,
            paste(d$control_rings, collapse = ","), paste(d$seasons, collapse = ",")), "")
  g <- T$gap; if (nrow(g)) {
    gp <- g[Year >= ty, .(share = sum(filled) / sum(rows)), by = .(outcome, group)]
    worst <- gp[order(-share)][1]
    L <- c(L, sprintf("1. **History-filled rows** (left out of every estimate since v20.52; Python since v20.35): up to %.1f %% of the post-year %s rows (%s). Before v20.52 R estimated on them -- post values partly equal to pre-period history, pulled toward zero.",
                      100 * worst$share, worst$group, worst$outcome))
  }
  s <- T$src; if (nrow(s)) {
    ms <- s[SrcOpt %in% c(4, 5), .(share = sum(rows)), by = .(Year, Season)][, .N]
    tot <- s[SrcOpt %in% c(4, 5), sum(rows)] / s[, sum(rows)]
    L <- c(L, sprintf("2. **Optical source**: %.1f %% of the rows used come from MODIS (500 m) or a projected window, in %d year x season combination(s) (DIAG_src.csv). A 500 m value spans the core boundary and ring 1: it cannot show a core-vs-ring difference.", 100 * tot, ms))
  }
  r <- T$res; if (nrow(r)) {
    cr <- r[, .(dpp = median(distinct_per_100_pixels)), by = outcome][order(dpp)]
    coarse <- cr[dpp < 20, outcome]
    L <- c(L, sprintf("3. **Resolution**: median distinct values per 100 pixels (core + ring 1): %s. %s", paste(sprintf("%s %.0f", cr$outcome, cr$dpp), collapse = ", "),
                      if (length(coarse)) paste0("COARSE (one value repeated over many pixels): ", paste(coarse, collapse = ", "), " -- these outcomes cannot separate the core from its rings at 1 km.") else "No outcome is coarse."))
  }
  gr <- T$grad; if (nrow(gr)) {
    fr <- paste0("ring", far); g1 <- gr[ring == "ring1"]
    fl <- gr[, { cf <- did_core_vs_ring[ring == fr]; r1 <- did_ring_vs_farthest[ring == "ring1"]; mid <- did_ring_vs_farthest[!ring %in% c("ring1", fr)]
                 nz <- if (length(mid) >= 2) stats::sd(mid) else NA_real_       # ring-to-ring noise: a flag needs a real core change
                 .(flag = length(cf) == 1 && length(r1) == 1 && is.finite(cf) && is.finite(r1) && sign(r1) == sign(cf) && abs(r1) >= 0.5 * abs(cf) &&
                          (is.na(nz) || abs(cf) > 3 * nz)) }, by = .(outcome, Season)]
    spill <- fl[(flag)]
    L <- c(L, sprintf("4. **Ring gradient** (DIAG_grad.csv): ring 1 moved like the core, against ring %d, in %d of %d outcome x season combination(s). Where it does, ring 1 is not a clean control (spillover) and the core-vs-rings estimate is diluted -- use rings 2-5 as controls (DESIGN_MODE manual).",
                      far, nrow(spill), nrow(g1)))
  }
  se <- T$seas; if (nrow(se)) {
    best <- se[order(-abs(did))][, .SD[1], by = outcome]
    L <- c(L, sprintf("5. **Seasons**: the largest raw DiD per outcome -- %s (Season 0 = annual, 1 Kharif, 2 Rabi, 3 Zaid). An annual mean dilutes an effect that exists in one season only.",
                      paste(sprintf("%s: season %s %+.4g", best$outcome, best$Season, best$did), collapse = "; ")))
  }
  tl <- T$tail; if (nrow(tl)) {
    tt <- tl[q %in% c(0.5, 0.9), .(outcome, q, core_minus_ctrl)]
    L <- c(L, sprintf("6. **Tails** (pixel change, core minus control): %s. A larger difference at the 90th percentile than at the median = an effect concentrated on a minority of treated pixels (the works), averaged away over the whole sub-watershed.",
                      paste(sprintf("%s q%.0f %+.4g", tt$outcome, 100 * tt$q, tt$core_minus_ctrl), collapse = "; ")))
  }
  lu <- T$lu; if (nrow(lu)) L <- c(L, sprintf("7. **Land use**: raw DiD by class -- %s (DIAG_lu.csv). The programme acts on farmland: classes without it dilute the average.",
                                             paste(sprintf("%s/class %s %+.4g", lu$outcome, lu$LandUse, lu$did), collapse = "; ")))
  ds <- T$dose; if (nrow(ds)) L <- c(L, sprintf("8. **Dose**: raw DiD by fund-intensity tercile -- %s.", paste(sprintf("%s T%d %+.4g", ds$outcome, ds$dose_tercile, ds$did), collapse = "; ")))
  else L <- c(L, "8. **Dose**: no fund intensity on the core (fund file not read, or no release in the post years).")
  pl <- T$plaus; if (!is.null(pl) && nrow(pl)) L <- c(L, sprintf("10. **Plausibility of the optical values**: %s", paste(pl$note, collapse = " ")))
  sc <- T$scale; if (nrow(sc)) {
    jump <- sc[, .(ratio = max(median, na.rm = TRUE) / pmax(min(abs(median), na.rm = TRUE), 1e-12)), by = outcome][ratio > 20]
    L <- c(L, sprintf("9. **Scale**: %s", if (nrow(jump)) paste("the yearly median jumps more than 20x for", paste(jump$outcome, collapse = ", "), "-- a unit / scaling change between exports.") else "no outcome changes scale between years."))
  }
  c(L, "", "Files: DIAG_gap.csv, DIAG_src.csv, DIAG_res.csv, DIAG_grad.csv, DIAG_seas.csv, DIAG_tail.csv, DIAG_lu.csv, DIAG_dose.csv, DIAG_scale.csv, DIAG_raw_means_<outcome>.csv/.png")
}
