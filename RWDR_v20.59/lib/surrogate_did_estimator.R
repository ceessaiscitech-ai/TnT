# ================================================================ Spec 2 -- synthetic DiD (two-level) and surrogate-index DiD (the R twin of
# surrogate_did_estimator.py: the same objectives, the same deterministic jackknife standard errors, the same standardised output)
.simplex_project <- function(v) { u <- sort(v, decreasing = TRUE); css <- cumsum(u); k <- seq_along(v); rho <- max(which(u * k > (css - 1))); theta <- (css[rho] - 1) / rho; pmax(v - theta, 0) }
.clean_weights <- function(w) { w[w < 1e-9] <- 0; s <- sum(w); if (s > 0) w / s else w }     # solver residue (1e-30-sized) is not weight: the same rows carry weight in Python
simplex_ridge_weights_R <- function(A, b, zeta = 0, max_iter = 5000L, tol = 1e-12) {
  # min_w ||b - A' w||^2 + zeta^2 T0 ||w||^2  s.t. sum w = 1, w >= 0.  A: N0 x T0, b: T0.  quadprog when available (an exact QP solve), the
  # projected gradient (the same objective) otherwise or beyond 400 units
  A <- as.matrix(A); b <- as.numeric(b); N0 <- nrow(A); T0 <- ncol(A); reg <- zeta^2 * T0
  f <- function(w) { r <- drop(t(A) %*% w) - b; sum(r * r) + reg * sum(w * w) }
  w0 <- rep(1 / N0, N0)
  if (N0 <= 400L && requireNamespace("quadprog", quietly = TRUE)) {
    D <- 2 * (A %*% t(A) + diag(reg, N0)); D <- (D + t(D)) / 2 + diag(1e-12, N0); dv <- 2 * drop(A %*% b)
    Am <- cbind(rep(1, N0), diag(N0)); bv <- c(1, rep(0, N0))
    w <- tryCatch(.clean_weights(.simplex_project(quadprog::solve.QP(D, dv, Am, bv, meq = 1)$solution)), error = function(e) NULL)
    if (!is.null(w) && f(w) <= f(w0) + 1e-12) return(w)
  }
  w <- w0; L <- 2 * (norm(A, "2")^2 + reg); step <- 1 / max(L, 1e-12)
  for (i in seq_len(max_iter)) { g <- 2 * drop(A %*% (drop(t(A) %*% w) - b)) + 2 * reg * w; wn <- .simplex_project(w - step * g); if (max(abs(wn - w)) < tol) { w <- wn; break }; w <- wn }
  .clean_weights(w)
}
compute_sdid_regularization_R <- function(Yc_pre, n_treated, t_post) { d <- as.numeric(t(apply(Yc_pre, 1, diff))); (n_treated * t_post)^0.25 * sd(d) }
aggregate_cells_R <- function(x, outcome, cell = c("site_id", "buff_km", "Season")) {
  d <- x[is.finite(get(outcome))]; keys <- c(intersect(cell, names(d)), "Year")
  g <- d[, .(y = mean(get(outcome)), n = .N, n_pix = uniqueN(pixel_id), post = max(post)), by = keys]
  g[, treated := as.integer(buff_km == 0)]; g[, cell := do.call(paste, c(.SD, sep = "|")), .SDcols = intersect(cell, names(g))]; g
}
.sdid_on_matrix_R <- function(Y, treated, pre, zeta = NULL) {
  Yc <- Y[!treated, , drop = FALSE]; Yt <- Y[treated, , drop = FALSE]; N1 <- sum(treated); T1 <- sum(!pre)
  if (is.null(zeta)) zeta <- compute_sdid_regularization_R(Yc[, pre, drop = FALSE], N1, T1)
  omega <- simplex_ridge_weights_R(Yc[, pre, drop = FALSE], colMeans(Yt[, pre, drop = FALSE]), zeta)
  lam <- simplex_ridge_weights_R(t(Yc[, pre, drop = FALSE]), rowMeans(Yc[, !pre, drop = FALSE]), 1e-6)
  tr_post <- mean(Yt[, !pre]); tr_pre <- sum(lam * colMeans(Yt[, pre, drop = FALSE]))
  do_post <- sum(omega * rowMeans(Yc[, !pre, drop = FALSE])); do_pre <- sum(omega * drop(Yc[, pre, drop = FALSE] %*% lam))
  fit <- drop(t(Yc[, pre, drop = FALSE]) %*% omega)
  list(tau = (tr_post - tr_pre) - (do_post - do_pre), omega = omega, lam = lam, pre_rmspe = sqrt(mean((colMeans(Yt[, pre, drop = FALSE]) - fit)^2)), zeta = zeta)
}
synthetic_did_two_level_R <- function(x, outcome, season = NULL, cell = c("site_id", "buff_km", "Season"), zeta = NULL, pixel_level = TRUE, cluster_col = "cluster_id", say = TRUE) {
  d <- if (is.null(season)) x else x[Season == as.integer(season)]
  if (!nrow(d)) stop(sprintf("synthetic DiD: no rows of %s%s", outcome, if (is.null(season)) "" else paste0(" in season ", season)))
  g <- aggregate_cells_R(d, outcome, cell); rows <- list(); wrows <- list(); lrows <- list()
  for (se_ in sort(unique(g$Season))) {
    gs <- g[Season == se_]; piv <- dcast(gs, cell ~ Year, value.var = "y"); full <- piv[complete.cases(piv)]
    cells <- full$cell; Y <- as.matrix(full[, -1]); yrs <- as.integer(colnames(Y))
    meta <- unique(gs, by = "cell"); meta <- meta[match(cells, meta$cell)]; treated <- meta$treated == 1L
    py <- gs[, .(post = max(post)), by = Year]; pre <- vapply(yrs, function(y) py[Year == y, post] == 0L, TRUE)
    if (sum(treated) == 0 || sum(!treated) < 2 || sum(pre) < 2 || sum(!pre) < 1) { rows[[length(rows) + 1]] <- data.table(Season = se_, status = sprintf("skipped: %d treated / %d donor cells, %d pre / %d post years", sum(treated), sum(!treated), sum(pre), sum(!pre))); next }
    r <- .sdid_on_matrix_R(Y, treated, pre, zeta); donors <- which(!treated); jk <- c()
    for (j in donors) { keep <- rep(TRUE, nrow(Y)); keep[j] <- FALSE; v <- tryCatch(.sdid_on_matrix_R(Y[keep, , drop = FALSE], treated[keep], pre, r$zeta)$tau, error = function(e) NA_real_); if (is.finite(v)) jk <- c(jk, v) }
    se <- if (length(jk) >= 2) sqrt((length(jk) - 1) / length(jk) * sum((jk - mean(jk))^2)) else NA_real_
    rows[[length(rows) + 1]] <- data.table(Season = se_, status = "fitted", ATT = r$tau, se = se, pre_rmspe = r$pre_rmspe, zeta = r$zeta, n_treated_cells = sum(treated), n_donor_cells = length(donors),
                                           pre_years = sum(pre), post_years = sum(!pre), treated_pixels = sum(meta$n_pix[treated]), donor_pixels = sum(meta$n_pix[!treated]))
    wrows[[length(wrows) + 1]] <- data.table(Season = se_, cell = cells[donors], site_id = meta$site_id[donors], buff_km = meta$buff_km[donors], unit_weight = r$omega, n_pix = meta$n_pix[donors])
    lrows[[length(lrows) + 1]] <- data.table(Season = se_, Year = yrs[pre], time_weight = r$lam)
  }
  tab <- rbindlist(rows, fill = TRUE); fit <- tab[status == "fitted"]
  if (!nrow(fit)) stop(paste("synthetic DiD: no season block with >= 1 treated cell, >= 2 donor cells, >= 2 pre and >= 1 post year --", paste(tab$status, collapse = "; ")))
  wgt <- fit$treated_pixels / sum(fit$treated_pixels); att <- sum(wgt * fit$ATT); se <- if (all(is.finite(fit$se))) sqrt(sum(wgt^2 * fit$se^2)) else NA_real_
  p <- if (is.finite(se) && se > 0) 2 * pnorm(-abs(att / se)) else NA_real_
  out <- list(estimator = "synthetic_did_two_level", outcome = outcome, att = att, se = se, p_value = p, pre_rmspe = sum(wgt * fit$pre_rmspe), n_fits = nrow(fit),
              n_treated_cells = sum(fit$n_treated_cells), n_donor_cells = sum(fit$n_donor_cells), n_rows = nrow(d),
              se_how = "leave-one-donor-cell-out jackknife per season block, combined with the treated-pixel weights of the blocks",
              unit_weights = rbindlist(wrows), time_weights = rbindlist(lrows), blocks = tab)
  if (pixel_level) out$pixel_wls <- weighted_twfe_from_weights_R(d, outcome, out$unit_weights, out$time_weights, cluster_col = cluster_col)
  if (say) info(sprintf("synthetic DiD (two-level, %s%s): ATT %+.6f (jackknife se %.6f, p %.3g), pre-RMSPE %.5f, %d treated / %d donor cells in %d block(s)%s", outcome, if (is.null(season)) "" else paste0(", season ", season),
                        att, se, p, out$pre_rmspe, out$n_treated_cells, out$n_donor_cells, out$n_fits,
                        if (pixel_level) sprintf("; pixel-level weighted TWFE %+.6f (se %.6f, %d clusters)", out$pixel_wls$beta, out$pixel_wls$se, out$pixel_wls$n_clusters) else ""))
  out
}
weighted_demean_two_way_R <- function(y, u, t, w, tol = 1e-11, max_iter = 500L) {
  su <- rowsum(w, u)[, 1]; st <- rowsum(w, t)[, 1]; nu <- names(su); nt <- names(st)
  for (i in seq_len(max_iter)) { y0 <- y; y <- y - (rowsum(w * y, u)[, 1] / pmax(su, 1e-300))[match(u, nu)]; y <- y - (rowsum(w * y, t)[, 1] / pmax(st, 1e-300))[match(t, nt)]; if (max(abs(y - y0)) < tol) break }
  y
}
weighted_twfe_R <- function(dt, y, x, unit, period, w, cluster) {
  keep <- is.finite(w) & w > 0; d <- dt[keep]; w <- w[keep]
  u <- as.character(d[[unit]]); tt <- as.character(d[[period]]); cl <- as.character(d[[cluster]])
  yd <- weighted_demean_two_way_R(as.numeric(d[[y]]), u, tt, w); xd <- weighted_demean_two_way_R(as.numeric(d[[x]]), u, tt, w)
  sxx <- sum(w * xd * xd); if (sxx <= 0) stop("weighted TWFE: the DiD term does not vary within the weighted units and periods")
  beta <- sum(w * xd * yd) / sxx; e <- yd - beta * xd; S <- rowsum(w * xd * e, cl)[, 1]; G <- length(S); n <- nrow(d)
  L <- c(uniqueN(u), uniqueN(tt)); nest <- c(all(rowsum(as.numeric(!duplicated(paste(u, cl))), u)[, 1] == 1), all(rowsum(as.numeric(!duplicated(paste(tt, cl))), tt)[, 1] == 1))
  k_fe <- { ka <- sum(L) - 1; if (any(nest)) ka - sum(L[nest]) + sum(nest) else ka }; K <- 1 + k_fe
  se <- sqrt(sum(S^2) / sxx^2 * (G / max(G - 1, 1)) * ((n - 1) / max(n - K, 1))); p <- if (se > 0) 2 * pt(abs(beta / se), max(G - 1, 1), lower.tail = FALSE) else NA_real_
  list(beta = beta, se = se, p_value = p, n = n, n_clusters = G, cluster = cluster, sum_weights = sum(w))
}
weighted_twfe_from_weights_R <- function(d, outcome, unit_weights, time_weights, cluster_col = "cluster_id") {
  d <- copy(d); d[, `:=`(cell_ = paste(site_id, buff_km, Season, sep = "|"))]
  uw <- setNames(unit_weights$unit_weight / unit_weights$n_pix, unit_weights$cell); tw <- setNames(time_weights$time_weight, paste(time_weights$Season, time_weights$Year))
  tr <- d$treat == 1L; post <- d$post == 1L
  n_tr <- d[tr == TRUE, .(k = uniqueN(pixel_id)), by = Season]; n_post <- d[post == TRUE, .(k = uniqueN(Year)), by = Season]
  wu <- ifelse(tr, 1 / n_tr$k[match(d$Season, n_tr$Season)], { v <- uw[d$cell_]; v[is.na(v)] <- 0; v })
  wt <- ifelse(post, 1 / n_post$k[match(d$Season, n_post$Season)], { v <- tw[paste(d$Season, d$Year)]; v[is.na(v)] <- 0; v })
  if (!"did" %in% names(d)) d[, did := treat * post]
  r <- weighted_twfe_R(d, outcome, "did", "unit", "period", wu * wt, cluster_col)
  r$weights_how <- "unit weight of the cell / pixels of the cell (donors), 1 / treated pixels (treated) x time weight of the year (pre), 1 / post years (post)"; r
}
surrogate_index_did_R <- function(x, outcome, surrogates, outcome_seasons = c(2L, 3L), surrogate_season = 1L, ridge = 1e-3, cluster_col = "cluster_id", say = TRUE) {
  sur <- surrogates[surrogates %in% names(x)]
  if (!length(sur)) stop(sprintf("surrogate index: none of the surrogates %s is in the sample", paste(surrogates, collapse = ",")))
  yo <- x[Season %in% outcome_seasons & is.finite(get(outcome))]
  Y <- yo[, .(y = mean(get(outcome)), treated = max(treat), post = max(post), cl = as.character(get(cluster_col))[1]), by = .(pixel_id, Year)]
  xs <- x[Season == surrogate_season, lapply(.SD, mean), by = .(pixel_id, Year), .SDcols = sur]
  D <- merge(Y, xs, by = c("pixel_id", "Year")); D <- D[complete.cases(D[, c("y", sur), with = FALSE])]
  if (nrow(D) < 30) stop(sprintf("surrogate index: only %d pixel-years carry both the dry-season %s and the season-%d surrogates", nrow(D), outcome, surrogate_season))
  yrs <- sort(unique(D$Year)); ns <- length(sur)
  design <- function(fr) cbind(as.matrix(fr[, sur, with = FALSE]), vapply(yrs, function(yy) as.numeric(fr$Year == yy), numeric(nrow(fr))))
  fit_predict <- function(train, pred) {
    X <- design(train); yv <- train$y; mu <- colMeans(X[, 1:ns, drop = FALSE]); sdv <- apply(X[, 1:ns, drop = FALSE], 2, sd) + 1e-12
    Xs <- X; Xs[, 1:ns] <- sweep(sweep(Xs[, 1:ns, drop = FALSE], 2, mu), 2, sdv, "/"); P <- rep(1e-8 * nrow(train), ncol(X)); P[1:ns] <- ridge * nrow(train)
    beta <- solve(crossprod(Xs) + diag(P, ncol(X)), crossprod(Xs, yv)); Xp <- design(pred); Xp[, 1:ns] <- sweep(sweep(Xp[, 1:ns, drop = FALSE], 2, mu), 2, sdv, "/")
    list(yhat = drop(Xp %*% beta), beta = drop(beta))
  }
  ctrl <- D[treated == 0L]; trt <- D[treated == 1L]
  if (!nrow(trt) || !nrow(ctrl)) stop("surrogate index: the sample lacks treated or control pixel-years")
  fp <- fit_predict(ctrl, trt); res <- trt$y - fp$yhat; pre <- trt$post == 0L
  if (!any(pre) || all(pre)) stop("surrogate index: the treated pixel-years lack a pre or a post period")
  att <- mean(res[!pre]) - mean(res[pre]); pre_rmspe <- sqrt(mean(res[pre]^2)); cls <- sort(unique(D$cl)); jk <- c()
  for (cc_ in cls) { Dc <- D[cl != cc_]; cc <- Dc[treated == 0L]; tt <- Dc[treated == 1L]; if (nrow(cc) < 10 || !nrow(tt)) next
    r_ <- tt$y - fit_predict(cc, tt)$yhat; pr <- tt$post == 0L; if (any(pr) && any(!pr)) jk <- c(jk, mean(r_[!pr]) - mean(r_[pr])) }
  se <- if (length(jk) >= 2) sqrt((length(jk) - 1) / length(jk) * sum((jk - mean(jk))^2)) else NA_real_
  p <- if (is.finite(se) && se > 0) 2 * pt(abs(att / se), max(length(jk) - 1, 1), lower.tail = FALSE) else NA_real_
  cf <- fit_predict(ctrl, ctrl)$yhat; r2 <- 1 - sum((ctrl$y - cf)^2) / max(sum((ctrl$y - mean(ctrl$y))^2), 1e-300)
  out <- list(estimator = "surrogate_index_did", outcome = outcome, surrogates = sur, outcome_seasons = outcome_seasons, surrogate_season = surrogate_season, att = att, se = se, p_value = p,
              pre_rmspe = pre_rmspe, surrogate_r2_control = r2, n_pixel_years = nrow(D), n_treated_pixel_years = nrow(trt), n_control_pixel_years = nrow(ctrl), n_clusters = length(cls),
              cluster = cluster_col, ridge = ridge, coefficients = setNames(as.list(fp$beta[1:ns]), sur), se_how = sprintf("leave-one-cluster-out jackknife over %d clusters (%s)", length(cls), cluster_col))
  if (say) info(sprintf("surrogate-index DiD (%s in seasons %s from %s of season %d): ATT %+.6f (jackknife se %.6f, p %.3g), pre-RMSPE %.5f, control-pool R2 %.3f, %s pixel-years, %d clusters",
                        outcome, paste(outcome_seasons, collapse = ","), paste(sur, collapse = ","), surrogate_season, att, se, p, pre_rmspe, r2, format(nrow(D), big.mark = ","), length(cls)))
  out
}
standard_row_R <- function(res) data.table(estimator = res$estimator, outcome = res$outcome, att = res$att, se = res$se, p_value = res$p_value, pre_rmspe = res$pre_rmspe,
                                           n = res$n_rows %||% res$n_pixel_years, se_how = res$se_how %||% "")
save_outputs_R <- function(res, dir, outcome) {
  dir.create(dir, recursive = TRUE, showWarnings = FALSE); tag <- res$estimator
  sc <- res[!vapply(res, function(v) is.data.frame(v) || is.list(v), TRUE)]; if (!is.null(res$surrogates)) sc$surrogates <- paste(res$surrogates, collapse = ";")
  fwrite(as.data.table(sc), file.path(dir, sprintf("%s_%s_R.csv", tag, outcome)))
  for (k in c("unit_weights", "time_weights", "blocks")) if (is.data.frame(res[[k]]) && nrow(res[[k]])) fwrite(res[[k]], file.path(dir, sprintf("%s_%s_%s_R.csv", tag, k, outcome)))
  if (is.list(res$pixel_wls)) fwrite(as.data.table(c(list(outcome = outcome), res$pixel_wls)), file.path(dir, sprintf("%s_pixel_wls_%s_R.csv", tag, outcome)))
  invisible(NULL)
}
