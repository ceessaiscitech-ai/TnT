# Model Guide — category-wise: what each model answers, when it is the best fit, what data it needs

**Verified citations** are marked ✔ (checked against IDEAS/RePEc, CRAN, or the authors' own pages
during this project). The single best entry point for reviewers is the practitioners' guide by the
field's leading authors: Baker, Callaway, Cunningham, Goodman-Bacon & Sant'Anna, *Journal of
Economic Literature* 62(2):498–557, 2026 ✔.

Legend — **Data**: what must be present · **Fit**: when this is the right choice · **Ready**: on your
Artal test panel (single site, single cohort)

---

## 02 · Core DiD models

| # | Model | Answers | Best fit when | Data needed | Ready | Citation |
|---|---|---|---|---|---|---|
| M01 | Static TWFE | one average effect | **benchmark for every paper** | panel + `did_term` | ✔ | Goodman-Bacon 2021 *J.Econ* 225(2):254-277 ✔; SE: Bertrand-Duflo-Mullainathan 2004 *QJE* 119(1):249-275 ✔ |
| M02 | Event study | effect by year relative to treatment; **pre-trends visible** | always, alongside M01 | ≥2 pre-years | ✔ | Callaway & Sant'Anna 2021 §2 ✔ |
| M03 | Doubly-robust DiD | effect adjusted for covariate imbalance | treated/control differ on observables | Rain, Tmean, LandUse | ✔ | Sant'Anna & Zhao 2020 *J.Econ* 219(1) |
| M04 | Changes-in-Changes | effect on the whole *distribution*, not the mean | effect is multiplicative or non-linear | — | ✔ | Athey & Imbens 2006 *Econometrica* 74(2) |
| M05 | Callaway-Sant'Anna | ATT by cohort × period; clean comparisons | **≥2 treatment cohorts** (staggered) | `first_treat_agri_year` varying | needs >1 site | Callaway & Sant'Anna 2021 *J.Econ* 225(2):200-230 ✔ |
| M06 | Dose-response | effect per unit of fund completion | treatment intensity varies | `dose_per_subwshed` | ✔ | Callaway, Goodman-Bacon & Sant'Anna (continuous DiD) |
| M07 | Surrogate index | long-run outcome via satellite proxies | ground-truth yield exists for a subsample | **survey: yield/income** | blocked | Athey, Chetty, Imbens & Kang 2019 |
| M08 | Instrumented DiD | effect when treatment assignment is endogenous | a credible rollout instrument exists | **survey: instrument** | blocked | 2SLS-DiD |
| M09 | Sun & Abraham | dynamic effects robust to cohort heterogeneity | staggered + dynamics | ≥2 cohorts | needs >1 site | Sun & Abraham 2021 *J.Econ* 225(2):175-199 ✔ |
| M10 | Triple difference | nets out a shock common to a third dimension | a comparable untreated stratum exists (LandUse) | LandUse | ✔ | Gruber 1994 |
| M11 | Synthetic DiD | effect for one/few treated units vs weighted donors | few treated sub-watersheds | ≥1 treated + several never-treated units | needs >1 site | Arkhangelsky et al. 2021 *AER* 111(12):4088-4118 ✔ |
| M12 | Chained DiD | effect when the panel is badly unbalanced | pixel overlap across years is poor | — | ✔ | Bellégo, Benatia & Dortet-Bernadet |
| M13 | Switcher DiD | effect when treatment can switch off | reversible treatment | time-varying `treatment` | n/a (absorbing) | de Chaisemartin & D'Haultfœuille 2020 *AER* 110(9):2964-2996 ✔ |
| M14 | PSM-DiD | effect on matched treated/control pixels | strong observable imbalance | covariates | ✔ | Rosenbaum & Rubin 1983; caliper: Austin 2011 *Pharm.Stat.* 10:150-161 ✔ |
| M15 | Placebo timing | **is there a spurious "effect" before treatment?** | always | ≥2 pre-years | ✔ | standard |
| M16 | Joint pre-trends F-test | formal test of parallel pre-trends | always, before trusting M01 | ≥2 pre-years | ✔ | Roth 2022; Callaway & Sant'Anna 2021 §4 ✔ |

## 03 · Spatial, heterogeneity & diagnostics

| # | Model | Answers | Best fit when | Data needed | Ready | Citation |
|---|---|---|---|---|---|---|
| M17 | Global Moran's I | is the outcome spatially clustered? | describe spatial structure before modelling | lat/lon | ✔ | Moran 1950 *Biometrika* 37(1/2); Cliff & Ord 1981 |
| M18 | LISA hot/cold spots | *where* is it clustered? | map for the paper | lat/lon | ✔ | Anselin 1995 *Geog. Analysis* 27(2) |
| M19 | Variance decomposition (ICC) | how much variation is between sub-watersheds? | justify the clustering level | `subwshed_id` | ✔ | Snijders & Bosker 2012 |
| M20 | Treatment-effect heterogeneity Q/I² | do effects differ across sub-watersheds? | **≥2 sub-watersheds** with own estimates | ≥2 sites | needs >1 site | Cochran 1954; Higgins & Thompson 2002 *Stat.Med.* 21:1539-1558 ✔ |
| M21 | Aggregation-bias check | does season→annual averaging bias the estimate? | you report annual numbers | — | ✔ | connects to continuous-DiD |
| M22 | Goodman-Bacon decomposition | which 2×2 comparisons drive TWFE? | staggered; diagnose TWFE bias | ≥2 cohorts | needs >1 site | Goodman-Bacon 2021 ✔ — **use R02 for exact weights** |
| M23 | Wild cluster bootstrap | valid inference with few clusters | **<40 clusters — your case** | `subwshed_id` | ✔ | Cameron, Gelbach & Miller 2008 *ReStat* 90(3):414-427 ✔ |
| M24 | Spillover ring gradient | does treatment leak into near control rings? | **run before choosing control zones** | `buff_km` 1–5 | ✔ | built for your design |
| M25 | Permutation inference | inference valid with very few treated units | few treated sub-watersheds | — | ✔ | Fisher randomisation |
| M26 | Treatment × covariate | does the effect differ by rainfall / land use / (survey traits)? | heterogeneity questions | covariates | ✔ | interaction spec |

## 04 · Advanced staggered & robustness

| # | Model | Answers | Best fit when | Data needed | Ready | Citation |
|---|---|---|---|---|---|---|
| M27 | BJS imputation | ATT robust to heterogeneous dynamic effects | staggered; many pre-periods | ≥2 cohorts | needs >1 site | Borusyak, Jaravel & Spiess 2024 *ReStud* — impl. confirmed equivalent by NBER w29691 |
| M28 | Gardner two-stage | same, regression form | staggered | ≥2 cohorts | ✔ (1 cohort ok) | Gardner 2021 |
| M29 | Exposure duration | **does the effect grow with years of exposure? — your lag** | physical works with delayed response | ≥2 post-years | ✔ | Gardner residualisation |
| M30 | Cohort heterogeneity | early vs late adopters | staggered | ≥2 cohorts | needs >1 site | — |
| M31 | Stacked DiD | clean cohort-specific comparisons | staggered | ≥2 cohorts | needs >1 site | Cengiz et al. 2019 style |
| M32 | ETWFE | saturated cohort×period regression | staggered, regression preferred | ≥2 cohorts | needs >1 site | Wooldridge 2021 |
| M33 | Entropy balancing | exact covariate balance without discarding controls | observable imbalance; alternative to M14 | covariates | ✔ | Hainmueller 2012 *Pol.Analysis* 20(1) |
| M34 | Honest DiD | **how large a pre-trend violation can the result survive?** | every headline number | M02 output | ✔ | Rambachan & Roth 2023 *ReStud* ✔ — **R01 gives the full CS** |
| M35 | Quantile DiD | effect at the 10th/50th/90th percentile | distributional question | — | ✔ | Athey & Imbens 2006 |
| M36 | Interactive FE | effect net of *unobserved* time-varying confounders | drought cycles hit sites differently | ≥4 sub-watersheds | needs >1 site | Bai 2009 *Econometrica* 77(4) |
| M37 | Matrix completion | counterfactual without parallel trends | low-rank outcome surface | ≥3 units | needs >1 site | Athey et al. 2021 *JASA* 116(536) |
| M38 | Generalised synthetic control | factor-model counterfactual per treated unit | few treated + donors | never-treated donors | needs >1 site | Xu 2017 *Pol.Analysis* 25(1) |
| M39 | ML-CATE | pixel-level effects from covariates | many effect modifiers | covariates | ✔ | double-ML style |

## 05 · Causal AI / ML

| # | Model | Answers | Best fit when | Data needed | Ready | Citation |
|---|---|---|---|---|---|---|
| M40 | Double / debiased ML | ATE with ML-controlled confounding | high-dimensional covariates | covariates | ✔ | Chernozhukov et al. 2018 *Econometrics J.* 21(1):C1-C68 |
| M41 | S / T / X meta-learners | heterogeneous effects | imbalanced arms (**X-learner**) | covariates | ✔ | Künzel et al. 2019 *PNAS* 116(10):4156-4165 |
| M42 | DR-learner | heterogeneous effects, doubly robust | model uncertainty | covariates | ✔ | Kennedy 2023 |
| M43 | Honest causal forest | **where did the programme work best, and why** | targeting future investment | covariates (+survey) | ✔ | Wager & Athey 2018 *JASA* 113(523):1228-1242; R `grf` is the reference |
| M44 | BART-style | flexible response surface | non-linear effects | covariates | ✔ (point est.) | Hill 2011 *JCGS* 20(1) — **R03 for posteriors** |
| M45 | Elastic-net synthetic control | sparse donor selection | many donors, few pre-periods | donors | needs >1 site | Doudchenko & Imbens 2016 style |

## 06 · Validation (run after ANY edit)

`V00_RUN_ALL_VALIDATIONS.py` (29 checks: DiD columns, closed-form identities, every estimator vs
known truth, real-file loaders, no undefined names) · `V00b_STREAMING_CHECKS.py` (8 checks at
1B-row scale) · `V01–V05` notebooks.

## 07 · R canonical modules — **primary for headline numbers**

| R | Package | Written by | Replaces limitation in |
|---|---|---|---|
| R01 | `HonestDiD` ✔ CRAN | Rambachan & Roth | M34 |
| R02 | `bacondecomp` | reference | M22 |
| R03 | `bartCause` | reference | M44 |
| R04 | `did` | Callaway & Sant'Anna | cross-check M05 |
| R05 | `synthdid` | Arkhangelsky et al. | cross-check M11 |
| R06 | `fixest` | fastest FE solver; Conley spatial SE | **the 1B-row headline regression** |
| R07 | `didimputation` | reference | cross-check M27 |

---

## Recommended reporting set for a high-impact submission

1. **M01** benchmark → **M16 + M15** pre-trends (report both) → **M23** wild-bootstrap p-values
   (you have < 40 clusters — asymptotic SEs will be challenged)
2. Main estimator: **R04 (`did`)** once ≥2 cohorts exist; until then **M01/M28**
3. **M29** exposure-duration profile — this is the biophysical-lag story for ponds/bunding
4. **M24** spillover gradient → justify the control-ring choice
5. **R01 Honest DiD** breakdown value next to every headline number
6. **M43** causal forest → the policy-targeting result
7. Season-stratified versions (M05 `by_season=True`) — Kharif and Rabi respond differently
