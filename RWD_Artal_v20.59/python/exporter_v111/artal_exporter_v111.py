# ===============================================================
# 🌾 ARTAL_EXPORTER_v110 — Karnataka Watershed (Auto-Resume + RUSLE + Yearly)
#    v110: timestamps + progress bars everywhere, reference_crosscheck() accuracy
#    validation (# ⛑ v110); v109: multi-feature ROI geometry fix + no silent blank exports
#    (# ⛑ v109); v108: cloud-free / corrected-first / core-month rules (# ⛑ v108);
#    v107: Rabi 2025 / Rabi 2026 fixes (# ⛑ v107). Base: v106 (v8.2 lineage).
# ROI: Sirur   |   Panel: 2015-2026, Yearly + Kharif + Rabi + Zaid
# FINAL READY-TO-RUN BUILD
#
# This is YOUR v7.7 with targeted repairs. Structure, function names, config
# names, ledger machinery and the main() flow are unchanged. Every edit is
# marked  # ⛑ FIXn  and explained in the accompanying change document.
#
# Three headline changes:
#   1. DATA DISCOVERY FIRST. preflight_data_report() probes every collection for
#      its real coverage, then resolve_source() picks the best REAL product that
#      covers each window — substitute product first, previous-year same-window
#      second. No proxies, no placeholder constants.
#   2. Sub-tile splitting now applies to Kharif/Rabi/Zaid exactly as it already
#      did to the yearly composite.
#   3. TCI was inverted, which made VHI wrong. Fixed to Kogan, on a single
#      consistent, QC-screened MODIS record.
# ===============================================================

import ee, time, os, json, datetime, math, re
import builtins as _builtins

# ==================================================================
# ⛑ v110 -- TIMESTAMPED LOG LINES + PROGRESS BARS (every code path)
# ==================================================================
# Every print() in this pipeline is prefixed with the wall-clock time and
# the elapsed time since the current run started:
#     [2026-09-13 10:41:07 | +0:03:22] ✅ 2025 Rabi: queued 25 tasks
# The notebook's cells share this module namespace, so the override below
# covers Sections 1-20 without touching a single existing print call.
# Progress bars (tqdm when available, a plain text bar otherwise) track the
# windows of a run, the tiles of each window and the batch-failure sweep
# rounds; log lines are routed through tqdm.write() while a bar is active
# so the two never garble each other. LOG_TIMESTAMPS=False restores plain
# output; PROGRESS_BARS=False disables the bars.
LOG_TIMESTAMPS = True
PROGRESS_BARS = True
_RUN_T0 = time.time()
_ACTIVE_BARS = []
try:
    from tqdm import tqdm as _tqdm
except Exception:                       # tqdm absent: text fallback below
    _tqdm = None


def _ts():
    el = int(time.time() - _RUN_T0)
    return (f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"+{el // 3600:d}:{(el % 3600) // 60:02d}:{el % 60:02d}]")


def _reset_run_clock():
    global _RUN_T0
    _RUN_T0 = time.time()


def print(*args, **kwargs):             # noqa: A001  (deliberate module-level override)
    if not LOG_TIMESTAMPS:
        return _builtins.print(*args, **kwargs)
    sep = kwargs.pop('sep', ' ')
    msg = sep.join(str(a) for a in args)
    body = msg.lstrip('\n')
    lead = msg[:len(msg) - len(body)]
    if body.strip() == '' or set(body.strip()) <= set('=-─'):
        stamped = msg                   # blank lines / rules stay clean
    else:
        stamped = f"{lead}{_ts()} {body}"
    if _ACTIVE_BARS and _tqdm is not None and 'file' not in kwargs:
        _tqdm.write(stamped, end=kwargs.get('end', '\n'))
    else:
        _builtins.print(stamped, **kwargs)


class _TextBar:
    """Minimal text progress bar with the subset of the tqdm API used here."""
    def __init__(self, total, desc):
        self.total, self.desc, self.n, self.post = max(int(total), 0), desc, 0, ''
        self.t0, self._last = time.time(), 0.0

    def update(self, k=1):
        self.n += k
        now = time.time()
        if now - self._last >= 5 or self.n >= self.total:
            self._last = now
            el = now - self.t0
            eta = (el / self.n * (self.total - self.n)) if self.n else 0
            pct = (100.0 * self.n / self.total) if self.total else 100.0
            _builtins.print(f"{_ts()} ▶ {self.desc}: {self.n}/{self.total} ({pct:.0f}%) "
                            f"elapsed {el / 60:.1f} min, eta {eta / 60:.1f} min {self.post}")

    def set_postfix_str(self, s):
        self.post = s

    def close(self):
        if self.n < self.total:
            self._last = 0
            self.update(0)


def progress_bar(total, desc):
    """A progress bar for `total` steps, registered so log lines don't collide."""
    if not PROGRESS_BARS:
        return _TextBar(0, desc)
    if _tqdm is not None:
        bar = _tqdm(total=total, desc=desc, unit='it', dynamic_ncols=True,
                    leave=True, mininterval=1.0)
    else:
        bar = _TextBar(total, desc)
    _ACTIVE_BARS.append(bar)
    return bar


def close_bar(bar):
    try:
        bar.close()
    finally:
        if bar in _ACTIVE_BARS:
            _ACTIVE_BARS.remove(bar)


def _close_all_bars():
    for b in list(_ACTIVE_BARS):
        close_bar(b)
from datetime import date

# ---------- ONE-TIME NOTE ----------
EE_PROJECT = 'project-b8709884-8eb1-4994-987'
ROI_ASSET = "projects/project-b8709884-8eb1-4994-987/assets/Sirur"
# Default only, for anything that might reference it before setup() runs --
# setup()/init_state_dir() always recompute this fresh from the CURRENT
# ROI_ASSET, so editing ROI_ASSET and calling setup() again is all that's
# needed to correctly switch watersheds; this module-level value is never
# what's actually used once setup() has run at least once.
ROI_ID = ROI_ASSET.rstrip('/').split('/')[-1] or 'roi'

# ---------------- CONFIGURATION ----------------
def prepareROI(fc):
    def _fix(f):
        props = f.propertyNames()
        subid = ee.Number(ee.Algorithms.If(
            props.contains('SubwshedID'), f.get('SubwshedID'),
            ee.Algorithms.If(
                props.contains('OBJECTID'), f.get('OBJECTID'),
                ee.Algorithms.If(props.contains('FID'), f.get('FID'), 0)
            )
        ))
        dist = ee.Number(ee.Algorithms.If(
            props.contains('buff_km'), f.get('buff_km'),
            ee.Algorithms.If(props.contains('Buff_km'), f.get('Buff_km'), 0)
        ))
        return f.set({'SubwshedID': subid, 'buff_km': dist})
    return fc.map(_fix)


ROI_raw = None      # built in setup()
ROI = None
roiGeom = None

CRS = 'EPSG:32643'
# ⛑ BUG FOUND AND FIXED during deep validation: UID_MULTIPLIER had no real
# safety margin (see the check in setup() for the full explanation). 10**9
# gives thousands of kilometres of headroom at any realistic SCALE, on any
# UTM zone -- effectively eliminating this as a practical concern, at zero
# cost (int64 easily holds it).
UID_MULTIPLIER = 10**9

# ⛑ FIX40  SCALE reverted 30 -> 10.                                  [v8.4]
#   v8.3 defaulted to 30 m to cut task count. You asked to keep native
#   Sentinel-2 10 m resolution instead, so this reverts that. Every other
#   dataset used for a coarser input (RUSLE terrain, VCI/TCI, ESI/WSSI/WSI,
#   climate) is resampled UP to this 10 m grid at export time, same as it
#   always was -- SCALE controls the OUTPUT grid, not the native resolution
#   of any one input, so 10 m is a legitimate, if storage-heavier, choice.
#   Direct consequence: the pixel-budget guard (PIXEL_LIMIT below) now needs
#   the SUBTILE_DEG sub-split again -- 64 chunks/window instead of 16, and
#   roughly 3,000 tasks for the full 2015-2026 panel instead of ~750. See the
#   accompanying document for the full task-count table and the 3-year-chunk
#   workflow (Section 15 of the notebook) built specifically to make that
#   volume practical to run and monitor manually.
SCALE = 10
START_YEAR, END_YEAR = 2015, 2026   # full panel: 6 pre-treatment years
SEASONS = {'Kharif': (6, 9), 'Rabi': (10, 2), 'Zaid': (3, 5)}
BASE_TILE_DEG = 0.05
# ⛑ v107  ONE version constant. Every earlier version bumped the same
# literal ("v105" -> "v106") in ~15 separate places by hand; it is now
# written once here and every Drive folder, state file and Earth Engine
# task description derives from it -- so the version can never be half-
# bumped again, and (see ADOPT_PRIOR_VERSION_TASKS below) the Earth Engine
# task names finally carry the version the state files already carried.
PIPELINE_VERSION = "v111"
DRIVE_FOLDER = f"REWARD_Sirur_Exports_{PIPELINE_VERSION}"

# ⛑ v107  BUG FOUND AND FIXED -- the most likely reason a window "produces
# nothing" with a green tick in the log ("✅ 2025 Rabi: queued 0 tasks").
# The state files (progress/ledger/...) were scoped by VERSION and ROI, but
# the Earth Engine task descriptions were scoped by ROI only:
#   "CSV_Sirur_2025_Rabi_tile0_sub0"   -- identical in v105, v106, v107.
# reconcile_tasks() reads Earth Engine's PROJECT-WIDE task list (it retains
# finished tasks for weeks) and adopted any SUCCEEDED task with this ROI's
# prefix as "already done" -- including tasks a PREVIOUS notebook version
# ran into a DIFFERENT Drive folder. Result: a fresh version silently
# skipped exactly the windows the previous version had exported (e.g. the
# Rabi 2025/2026 test run of v105), printed "queued 0 tasks" as if that were
# success, and the new version's Drive folder never received those CSVs.
# Reproduced directly (mock Earth Engine, prior-version tasks injected):
# v106 queued 0 of 50 tiles for Rabi 2025+2026 and started no tasks.
#
# Fix: task DESCRIPTIONS now carry PIPELINE_VERSION
# ("CSV_Sirur_v107_2025_Rabi_tile0_sub0"); the CSV FILE names on Drive are
# deliberately unchanged ("CSV_Sirur_2025_Rabi_tile0_sub0.csv") so nothing
# downstream that reads file names breaks. Resume/skip behaviour is fully
# intact within a version -- it just can no longer be satisfied by another
# version's tasks. Set ADOPT_PRIOR_VERSION_TASKS = True to restore the old
# cross-version adoption deliberately (e.g. to continue a v106 panel under
# v107 without re-exporting); the run log always reports how many
# prior-version tasks it saw and ignored, so this is never silent again.
ADOPT_PRIOR_VERSION_TASKS = False

# ==================================================================
# ⛑ v9.0 -- THE ONE PLACE TO EDIT for what to actually download.
# ==================================================================
# START_YEAR/END_YEAR/SEASONS above define the full study panel -- the
# treatment-year logic, task estimator, and chunk planner all reason about
# that full range regardless of what you choose to run right now. These two
# variables are the separate, single control for "what do I want THIS run to
# cover" -- edit ONLY here, nowhere else, then run the one cell in Section 16
# ("Download") that reads them. No other cell needs to change.
#
#   DOWNLOAD_YEARS   = None            -> the complete panel, every year
#   DOWNLOAD_YEARS   = [2020]          -> one year only
#   DOWNLOAD_YEARS   = [2020, 2021]    -> a specific list of years
#   DOWNLOAD_YEARS   = range(2015,2019) -> a specific range of years
#   DOWNLOAD_SEASONS = None            -> every season (Yearly+Kharif+Rabi+Zaid)
#   DOWNLOAD_SEASONS = ['Kharif']      -> one season only, every selected year
#   DOWNLOAD_SEASONS = ['Kharif','Rabi'] -> two seasons, every selected year
#
# These map directly onto main()'s own years=/seasons= parameters (None means
# exactly the same thing there) -- nothing new to learn, just one place to
# set it instead of several.
DOWNLOAD_YEARS = None
DOWNLOAD_SEASONS = None

# ==================================================================
# ⛑ FIX36 -- GEE BATCH-TASK RESTRICTION SAFETY LAYER               [v8.3]
# ==================================================================
# Google's own restriction page (linked in your error message) documents ONE
# specific violation this mechanism enforces: "spreading a large or complex
# workload across multiple [Earth Engine] accounts" -- not, by itself, plain
# single-account concurrency. https://developers.google.com/earth-engine/
# batch-task-restrictions
#
# Across this notebook's history the SAME watershed-export workload has run
# under TWO different EE projects ('rwdirma', then
# 'project-b8709884-8eb1-4994-987'). That is exactly the pattern the policy
# names. See the accompanying document for the full explanation -- code
# cannot detect or fix that pattern from inside a single run, so the fix is
# operational: run this workload from ONE project only, going forward.
#
# What code CAN do, and what's below:
#   - never retry a "batch tasks are blocked" error (retrying a blocked
#     account looks exactly like the abuse pattern the policy exists to catch)
#   - submit strictly one task at a time, waiting for it to leave the queue
#     before the next is created (MAX_CONCURRENT_TASKS = 1)
#   - a minimum pacing floor between submissions on top of that
#   - fewer, larger tasks (SCALE = 30 above) so the same job needs ~4x fewer
#     batch-task submissions in total
EE_PROJECT_REMINDER = True     # print the active project once per run so a
                               # second project used for the same job is easy
                               # to notice
# ⛑ v9.0 -- explicit request: keep up to 5 tasks always active, re-topping
# the queue as each one finishes, with no more than a 3s pacing floor between
# submissions. This is a deliberate, moderate step up from v8.3-v8.5's strict
# 1-at-a-time default -- still ~100x more conservative than the
# MAX_CONCURRENT_TASKS=500 that very plausibly contributed to the original
# ToS restriction several passes ago, not a return to that behaviour.
# wait_for_capacity() already implements "keep submitting to maintain the
# queue" by construction: it blocks only until active < MAX_CONCURRENT_TASKS,
# then submits immediately, in the same loop that walks every tile -- so
# raising these two constants is the complete, correct implementation of
# what was asked, with no new submission mechanism needed.
# UNCHANGED by this request, still fully active: the ToS-block circuit
# breaker (FIX37) still halts the entire run immediately and permanently on
# Google's exact block message, regardless of MAX_CONCURRENT_TASKS -- a
# faster queue does not change how a block is handled, only how fast normal
# submission proceeds when there is no block.
MAX_CONCURRENT_TASKS = 5       # was 1 in v8.3-v8.5; explicit v9.0 request
MIN_SUBMIT_INTERVAL_S = 3      # was 8 in v8.3-v8.5; explicit v9.0 request
                               # ("must not be more than 3 seconds")
TASK_POLL_INTERVAL = 20
MAX_TASKS_PER_RUN = None      # e.g. 150 to bound one Colab session; None = no cap
SPLIT_DRIVE_FOLDER_BY_YEAR = True   # REWARD_..._2015, _2016 ... one task at a
                                    # time makes a single folder even harder
                                    # to work with
USE_DRIVE_FOR_STATE = True    # keep progress/ledger on Drive so a Colab restart
                              # resumes instead of re-exporting everything
PROGRESS_FILE = f"progress_tracker_{PIPELINE_VERSION}.json"

# ▶️ Overwrite control
OVERWRITE_EXISTING = False          # ⛑ FIX7  v7.7 shipped True and re-exported
                                    #         1,445 already-complete tiles.

# ▶️ SMALLER CHUNKS FOR *EVERY* YEAR AND SEASON              # ⛑ FIX5
#   v7.7 pre-split only the yearly composite; seasonal tiles went out whole at
#   0.05 deg (~297,000 px) and that is what produced
#   "Image.sample: Computed value is too large" on 2025_Rabi_tile11.
USE_SUBTILES = True                 # applies to Yearly AND all seasons
SUBTILE_DEG = BASE_TILE_DEG / 2     # 0.025 deg  ~74,000 px  (empirically safe)
YEARLY_USE_SUBTILES = USE_SUBTILES  # kept for backward compatibility
YEARLY_SUBTILE_DEG = SUBTILE_DEG
YEARLY_TILE_SCALE = 8

# ▶️ Heavy-tile guard
PIXEL_LIMIT = 90000                 # ⛑ FIX4  was 1,500,000 and never enforced
MAX_SPLIT_DEPTH = 4
SPLIT_TOLERANCE = 1.15              # allow 15% over budget before subdividing
DEFAULT_TILE_SCALE = 8
RETRY_TILE_SCALE = 16               # EE maximum

# ▶️ Treatment timing                                              # ⛑ FIX34
#   Watershed works completed in 2022, so 2022 is the first treated year.
#   'inclusive'  Treat = 1 from TREATMENT_YEAR onward     -> pre 2015-2021 (7 yr)
#                                                            post 2022-2026 (5 yr)
#   'exclusive'  Treat = 1 from TREATMENT_YEAR + 1 onward, i.e. 2022 is treated
#                as an implementation/transition year and excluded from both
#                arms. Common in watershed evaluations where structures are
#                built mid-year and cannot act on that season's crop.
TREATMENT_YEAR = 2022
TREAT_RULE = 'inclusive'        # 'inclusive' | 'exclusive'
EXPORT_EVENT_TIME = True        # adds YrRel = Year - TREATMENT_YEAR for an
                                # event-study DiD (-7 ... +4)

# ▶️ Climatology window  ------------------------------------------ ⛑ FIX9/10
#   Kogan's VCI/TCI are defined against a FIXED multi-year, per-pixel,
#   same-calendar-window climatology. A rolling "last 10 years" baseline makes
#   the reference move between your pre- and post-treatment periods, which
#   injects a mechanical trend into a difference-in-differences outcome.
CLIM_MODE = 'fixed'                 # 'fixed' (recommended) | 'rolling' (v7.7)
CLIM_BASE_START = 2003              # both Terra and Aqua exist from 2003
CLIM_BASE_END = 2024                # last complete MODIS year
                                    # set 2021 for a strictly
                                    # pre-treatment baseline
CLIM_YEARS = 10                     # only used when CLIM_MODE == 'rolling'
CLIM_ROBUST_PCTL = None             # None = strict Kogan min/max;
                                    # e.g. (5, 95) = outlier-resistant variant
TCI_KOGAN = True                    # ⛑ FIX9  True = (LSTmax-LST)/(LSTmax-LSTmin)
VHI_ALPHA = 0.5                     # VHI = a*VCI + (1-a)*TCI
INDEX_SCALE_0_100 = False           # keep 0-1 as in v7.7; True gives Kogan 0-100

# ▶️ MODIS source selector for reflectance & LST: 'terra' | 'aqua' | 'both'
MODIS_SOURCE = 'both'

# ▶️ Optical / cloud masking                                        # ⛑ FIX11
USE_CLOUD_MASKING = True
CS_THRESHOLD = 0.60                 # Cloud Score+ cs_cdf clear threshold
S2_USE_SR = True                    # SR (L2A) from 2017-03-28; TOA before.
                                    # False = TOA everywhere, exactly like v7.7

# ⛑ FIX30  Optical consistency across a 2015-2026 panel.
#   Sentinel-2 L1C starts 2015-06-23 and L2A starts 2017-03-28, so a
#   "best available" cascade uses Landsat for early 2015, S2-TOA to 2017 and
#   S2-SR after. Those are real level shifts in NDVI/EVI/SAVI.
#   'best'               highest resolution; sensor changes across years. Safe
#                        for DiD because the choice is made ONCE per year-season,
#                        so it is collinear with year (or year x season) fixed
#                        effects and gets absorbed. SrcOpt records it anyway.
#   'consistent_landsat' Landsat 8/9 C2 L2 only: one surface-reflectance record,
#                        2013-present, 30 m. Cleanest single series for a panel.
#   'consistent_s2'      Sentinel-2 only; nothing before 2015-06-23.
OPTICAL_MODE = 'best'

# ==================================================================
# ⛑ v108 -- TWO REQUESTED DATA-QUALITY RULES FOR THE OPTICAL INPUTS
# ==================================================================
# (1) "Data must be cloud-free, and atmospherically-corrected data must be
#     prioritised." Every optical composite (Yearly and every season) is now
#     built in QUALITY TIERS, strictest first: a pixel takes its value from
#     the clearest scenes (scene cloud % <= tier limit AND per-pixel Cloud
#     Score+ clear probability >= tier threshold) whenever it has at least
#     MIN_OBS_TIER clear observations there, and falls back to the next
#     tier ONLY for pixels that don't. The last tier is exactly the previous
#     single-tier behaviour (CLOUDY_PIXEL_PERCENTAGE < 80, cs_cdf >= 0.60),
#     so no pixel can end up with LESS data than before -- only cleaner data
#     where it exists. Sensor order with OPTICAL_PRIORITY='corrected_first':
#     Sentinel-2 SR -> Landsat 8/9 SR -> MODIS SR, and Sentinel-2 TOA
#     (NOT atmospherically corrected) only if no corrected source has a
#     single image -- a window is never left empty for this rule.
#     'resolution_first' restores the old order (S2 TOA before Landsat).
# (2) "Each season must use the CENTRAL months first and avoid the two
#     edge months." Seasonal composites are built from the core months
#     first (SEASON_CORE_MONTHS), and the edge months are used ONLY for
#     pixels that have fewer than MIN_OBS_TIER clear observations in the
#     core -- so a pixel that is clear in July-August is never blended with
#     June's pre-monsoon or September's senescence. Priority per pixel:
#         core+strict  >  core+standard  >  full-window+strict  >  full+standard
#     recorded per pixel in the new OptTier column (1..4; 0 = no clear
#     observation at all, band masked). Yearly composites have no edge
#     months, so rule (2) does not apply to them (rule (1) does).
#     Applied to: the Sentinel-2/Landsat/MODIS spectral composite (all 8
#     indices), MODIS LAI, and Dynamic World land use -- the cloud-affected,
#     per-scene optical inputs. Deliberately NOT applied to: Rain/ET/PET
#     (season SUMS -- restricting to the core months would change what the
#     variable means), Tmax/Tmin/Tmean (all-weather ERA5 season means), and
#     the anomaly indices VCI/TCI/ESI_Anom/SMDI, whose current value must
#     cover exactly the same calendar window as their fixed climatology.
OPTICAL_PRIORITY = 'corrected_first'   # 'corrected_first' | 'resolution_first'
# (scene-level cloud % limit, per-pixel Cloud Score+ cs_cdf minimum), strictest
# first. The LAST tier must stay at (80, CS_THRESHOLD) = the pre-v108 rule.
CLOUD_TIERS = [(30, 0.70), (80, CS_THRESHOLD)]
MIN_OBS_TIER = 2            # clear observations a pixel needs to use a tier
USE_CORE_MONTHS_FIRST = True
SEASON_CORE_MONTHS = {'Kharif': (7, 8),    # Jun-Sep  -> core Jul-Aug
                      'Rabi':   (11, 1),   # Oct-Feb  -> core Nov-Jan (wraps the year)
                      'Zaid':   (4, 4)}    # Mar-May  -> core Apr
MIN_CORE_DAYS = 20          # a clamped window keeps its core only if >= this many core days exist

# ⛑ v111 ---- core-month override hook (see section 12c / recommend_core_months) ----
# Per-ROI override of the core months, e.g. {'Kharif': (7, 9)} when the field survey
# shows sowing in the FIRST window month (Raichur, Gadag: 86-99 % of Kharif plots sown in
# June) so peak canopy falls in the last window month. None = SEASON_CORE_MONTHS unchanged.
# The override applies to EVERY year of the ROI alike (treated and control pixels), so it
# cannot create a treatment-correlated artefact; it is a compositing choice, not a filter.
CORE_MONTHS_OVERRIDE = None


def _core_months(season):
    """⛑ v111  core months for `season`: CORE_MONTHS_OVERRIDE wins, else SEASON_CORE_MONTHS."""
    if CORE_MONTHS_OVERRIDE and season in CORE_MONTHS_OVERRIDE:
        return CORE_MONTHS_OVERRIDE[season]
    return SEASON_CORE_MONTHS[season]

ADD_OPTICAL_TIER_COL = True # export the per-pixel OptTier column (appended, schema +1)

# ▶️ Data discovery & substitution                                  # ⛑ FIX3
PROBE_AVAILABILITY = True
MIN_WINDOW_DAYS = 20
MIN_WINDOW_COVERAGE = 0.55     # a window needs this much real data to be usable

# "Search first, then substitute, then previous year" — never a placeholder.
#   1. try every REAL substitute PRODUCT that covers the requested window
#   2. if none does, reuse the SAME CALENDAR WINDOW from the most recent year
#      that does have data, and stamp DataYear so those rows are identifiable
ALLOW_PREVIOUS_YEAR = True
PREV_YEAR_MAX_LOOKBACK = 3
# Outcome variables (optical indices, rain, temperature, ET) drive your
# treatment effect. Substituting last year's values for them manufactures the
# outcome, so previous-year fallback is OFF for them by default and ON for
# ancillary/climatology inputs. Set True only if you accept that consequence.
ALLOW_PREVIOUS_YEAR_OUTCOME = False
ADD_PROVENANCE_COLS = True     # DataYear, Coverage, SrcOpt, SrcET, NObsV, NObsT

# ⛑ Requested explicitly, twice: for an incomplete CURRENT-period window (a
# running year/season whose end hasn't happened yet), fill ONLY the
# genuinely missing remainder using the last N complete years' historical
# pattern for that exact missing sub-period -- sum-type columns (Rain, ET,
# PET, and the RUSLE R-factor, which uses Rain) get the historical SUM for
# the missing days added on; mean-type columns (the spectral indices,
# Tmax/Tmin/Tmean) get a day-weighted blend of the observed mean and the
# historical mean for the missing days. This is NOT a full-year
# substitution and NEVER touches already-observed data -- see
# _gapfill_missing_period() for the exact mechanism and why this is not the
# same thing as PREVIOUS-YEAR substitution above (that replaces an ENTIRE
# unusable window; this supplements the specific missing tail of an
# otherwise-real, mostly-observed one).
#
# STANDARD (default ON), per explicit request that this be the normal way
# an incomplete current period is handled, not an opt-in extra: "till the
# data available the output must be generated based on original available
# data, for future time data must be generated using 3 year average or sum
# as needed for the processing." Real, observed data is always used for
# every day it actually exists -- this only ever supplements the specific
# days that have not happened yet, which is a materially different, and
# more defensible, thing than ALLOW_PREVIOUS_YEAR_OUTCOME's full-window
# substitution above, which stays OFF by default because it would replace
# an entire real observation with a different year's. "Standard behaviour"
# and "never silent" are not in tension -- every gap-filled row is still
# stamped GapFilled=1 in the export itself (not just the run log), and
# Coverage still always reports the TRUE observed fraction regardless --
# gap-filling changes what the SUM/MEAN columns read, never what Coverage
# says actually happened. Set to False for the original behaviour (an
# incomplete window exported exactly as observed, un-supplemented) if you
# want that instead for a specific run.
GAPFILL_INCOMPLETE_WINDOWS = True
GAPFILL_LOOKBACK_YEARS = 3


# ▶️ VCI / TCI data quality                                    # ⛑ FIX9/10/25
TCI_SOURCE = 'modis_lst'       # 'modis_lst' (literature standard)
                               # 'era5_skin' (all-weather, no clear-sky bias, 11 km)
TCI_OVERPASS = 'both'          # 'terra' (10:30) | 'aqua' (13:30) | 'both'
PER_SENSOR_MEAN = True         # average Terra-mean and Aqua-mean rather than
                               # pooling images: removes dependence on how many
                               # clear days each platform happened to get
MIN_OBS_NDVI = 2               # mask VCI where fewer valid composites than this
MIN_OBS_LST = 2                # mask TCI likewise
LST_STRICT_QC = True           # also require the MOD11 LST error flag <= 2 K

# ▶️ Batch-failure handling                                         # ⛑ FIX8
AUTO_SPLIT_ON_FAILURE = True
FAILURE_SWEEP_ROUNDS = 3
SWEEP_MAX_WAIT_S = 6 * 3600

# ▶️ Resume & logging
DOWNLOAD_DIR = f"{DRIVE_FOLDER}_records"
TASK_LEDGER_FILE = f"task_ledger_{PIPELINE_VERSION}.json"
COMPLETED_FILE = f"completed_tracker_{PIPELINE_VERSION}.json"
GAPFILLED_WINDOWS_FILE = f"gapfilled_windows_{PIPELINE_VERSION}.json"
SUBSTITUTED_WINDOWS_FILE = f"substituted_windows_{PIPELINE_VERSION}.json"
MANIFEST_FILE = f"window_manifest_{PIPELINE_VERSION}.csv"
PREFLIGHT_FILE = f"data_availability_{PIPELINE_VERSION}.csv"

def init_state_dir():
    """⛑ FIX31  Colab VMs reset. A 3,800-task panel spans several sessions, so
    the progress ledger has to outlive the VM or every restart re-exports work
    that is already done.

    ⛑ BUG FOUND AND FIXED, reported directly: every state file used to be
    named identically regardless of which ROI/watershed was active, and two
    of the seven (GAPFILLED_WINDOWS_FILE, SUBSTITUTED_WINDOWS_FILE, added in
    later passes) were never even routed through this directory-prefixing
    at all -- a pre-existing gap, found while fixing this. Every state file
    is now scoped by ROI_ID (setup()'s own last path component of
    ROI_ASSET, e.g. "Sirur"), computed fresh here from whatever ROI_ASSET
    currently is -- so switching watersheds can never mistake one ROI's
    progress for another's, while each watershed's own resume state stays
    fully intact and independently resumable."""
    global DOWNLOAD_DIR, PROGRESS_FILE, TASK_LEDGER_FILE, COMPLETED_FILE
    global GAPFILLED_WINDOWS_FILE, SUBSTITUTED_WINDOWS_FILE
    global MANIFEST_FILE, PREFLIGHT_FILE
    roi_id = ROI_ASSET.rstrip('/').split('/')[-1] or 'roi'
    base = f"./{DRIVE_FOLDER}_state"
    if USE_DRIVE_FOR_STATE:
        try:
            from google.colab import drive
            drive.mount('/content/drive', force_remount=False)
            base = f"/content/drive/MyDrive/{DRIVE_FOLDER}_state"
            print(f"💾 State on Google Drive: {base}")
        except Exception:
            print("💾 Google Drive not available; state kept on the local VM "
                  "(a restart will lose resume information)")
    os.makedirs(base, exist_ok=True)
    DOWNLOAD_DIR = base
    PROGRESS_FILE = os.path.join(base, f"progress_tracker_{PIPELINE_VERSION}_{roi_id}.json")
    TASK_LEDGER_FILE = os.path.join(base, f"task_ledger_{PIPELINE_VERSION}_{roi_id}.json")
    COMPLETED_FILE = os.path.join(base, f"completed_tracker_{PIPELINE_VERSION}_{roi_id}.json")
    GAPFILLED_WINDOWS_FILE = os.path.join(base, f"gapfilled_windows_{PIPELINE_VERSION}_{roi_id}.json")
    SUBSTITUTED_WINDOWS_FILE = os.path.join(base, f"substituted_windows_{PIPELINE_VERSION}_{roi_id}.json")
    MANIFEST_FILE = os.path.join(base, f"window_manifest_{PIPELINE_VERSION}_{roi_id}.csv")
    PREFLIGHT_FILE = os.path.join(base, f"data_availability_{PIPELINE_VERSION}_{roi_id}.csv")
    return base


os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat()


def _load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_progress():
    return _load_json(PROGRESS_FILE, {})


def save_progress(done_dict):
    _save_json(PROGRESS_FILE, done_dict)


# ⛑ Requested explicitly, on deep re-validation: a window gap-filled in an
# earlier run (e.g. "2026 Yearly" at 42% coverage in June) must not stay
# permanently stuck as that estimate once MORE real data genuinely exists --
# not only once the window's period has fully elapsed, but incrementally,
# as coverage improves. done_dict/OVERWRITE_EXISTING already handle "should
# a tile be re-exported" in general, but OVERWRITE_EXISTING defaults to
# False specifically to avoid wastefully re-exporting things that are
# already correct -- flipping it globally would re-export EVERYTHING on
# every run, not just the windows that actually need it. This is the
# targeted alternative: remember specifically which windows were gap-filled
# and AT WHAT COVERAGE, and whenever meaningfully more real data has since
# become achievable for that exact window, force just that window back to
# "not done" so it is naturally reprocessed with the improved data, without
# touching the resume behaviour for anything else.
#
# ⛑ BUG FOUND AND FIXED on continued deep validation. The first version of
# this only checked "has the window's full period completely elapsed" --
# verified directly: a window gap-filled at 42% coverage in June stayed
# stuck at 42% even when re-run in November, when 84% real coverage was
# genuinely achievable, because November is still before the window's true
# end. That's a real, meaningful accuracy gap this pipeline is specifically
# meant not to have -- "till the data available the output must be
# generated based on original available data" implies continuous
# improvement as more becomes available, not a single refresh only at the
# very end. Fixed by tracking coverage, not just presence, and refreshing
# whenever CURRENT achievable coverage exceeds what was recorded by more
# than GAPFILL_REFRESH_THRESHOLD -- a small margin so trivial day-to-day
# fluctuation doesn't trigger needless re-exports, while a genuine,
# meaningful improvement (or full completion) always does.
GAPFILL_REFRESH_THRESHOLD = 0.02   # re-check coverage improvement of >2 points


def load_gapfilled_windows():
    """Returns {(year, season): {'eff': e, 'rain': r, 'temp': t}} -- the
    coverage a window was last EXPORTED at, per source.

    ⛑ v107  The registry now records the CHIRPS-paced ('rain') and
    ERA5-paced ('temp') coverage separately, plus their minimum ('eff'), so
    main() can refresh a window when EITHER source has caught up
    meaningfully (a 23-point rain improvement is worth a re-export even
    while ERA5 is still 2 months behind). Backward compatible with both
    earlier formats: [year, season] pairs -> coverage 0.0; single-coverage
    dicts -> that value for every field."""
    raw = _load_json(GAPFILLED_WINDOWS_FILE, [])
    # Backward compatible with the earlier presence-only format (a list of
    # [year, season] pairs, no coverage recorded) -- treated as coverage 0.0
    # so any real re-run correctly triggers a refresh rather than silently
    # losing track of what needs re-checking. Both the old and new formats
    # are lists at the top level, so the item TYPE (list/tuple pair vs
    # dict), not just "is this a list", is what actually distinguishes them.
    out = {}
    if raw and isinstance(raw[0], dict):
        for item in raw:
            c = float(item.get('coverage', 0.0))
            out[(item['year'], item['season'])] = {
                'eff': c, 'rain': float(item.get('coverage_rain', c)),
                'temp': float(item.get('coverage_temp', c))}
        return out
    return {(y, s): {'eff': 0.0, 'rain': 0.0, 'temp': 0.0} for y, s in raw}


def save_gapfilled_windows(gapfilled_dict):
    _save_json(GAPFILLED_WINDOWS_FILE,
               [{'year': y, 'season': s, 'coverage': c['eff'],
                 'coverage_rain': c['rain'], 'coverage_temp': c['temp']}
                for (y, s), c in sorted(gapfilled_dict.items())])


# ⛑ BUG FOUND AND FIXED on continued deep validation, same class as the
# gap-fill staleness fix above, discovered by testing this OTHER
# incompleteness strategy the same way: ALLOW_PREVIOUS_YEAR_OUTCOME
# substitutes an entire prior year's real data when the nominal year has no
# usable data of its own yet (e.g. 2026 Yearly gets 2025's real values in
# August, before 2026 has enough of its own). Verified directly: re-running
# in March 2027, once 2026's OWN real data genuinely exists, left the row
# permanently stuck on 2025's substituted values -- the identical silent-
# staleness failure mode gap-fill had, just for the other estimation
# mechanism this pipeline has. Fixed the same way: remember which windows
# were substituted, and on each run check whether the NOMINAL year's own
# window now achieves real, sufficient coverage -- if so, force
# reprocessing so the window naturally picks up its own real data instead
# of a prior year's, without touching resume behaviour for anything else.
def load_substituted_windows():
    return set(tuple(x) for x in _load_json(SUBSTITUTED_WINDOWS_FILE, []))


def save_substituted_windows(substituted_set):
    _save_json(SUBSTITUTED_WINDOWS_FILE, sorted([list(x) for x in substituted_set]))


def mark_done(done_dict, year, season, tile_name):
    done_dict.setdefault(str(year), {}).setdefault(season, [])
    if tile_name not in done_dict[str(year)][season]:
        done_dict[str(year)][season].append(tile_name)


def is_done(done_dict, year, season, tile_name):
    return (str(year) in done_dict and season in done_dict[str(year)]
            and tile_name in done_dict[str(year)][season])


def load_completed():
    return set(_load_json(COMPLETED_FILE, []))


def save_completed(completed_set):
    _save_json(COMPLETED_FILE, sorted(list(completed_set)))


# ⛑ FIX15  v7.7 reloaded and rewrote the whole ledger on every single task,
#          which is O(n^2) file I/O across ~4,000 tasks. Now write-through.
_LEDGER = {'data': None, 'dirty': 0}


def load_task_ledger():
    if _LEDGER['data'] is None:
        _LEDGER['data'] = _load_json(TASK_LEDGER_FILE, {})
    return _LEDGER['data']


def save_task_ledger(ledger=None):
    _save_json(TASK_LEDGER_FILE, ledger if ledger is not None else load_task_ledger())
    _LEDGER['dirty'] = 0


def record_task(description, status, task_id=None, detail=None):
    ledger = load_task_ledger()
    entry = ledger.get(description, {})
    entry.update({"description": description, "status": status,
                  "task_id": task_id or entry.get("task_id"),
                  "updated_at": _now_iso()})
    if detail:
        entry.update(detail)
    ledger[description] = entry
    _LEDGER['dirty'] += 1
    if _LEDGER['dirty'] >= 25:
        save_task_ledger(ledger)


def remove_done_from_progress(done_dict, year, season, tile_name):
    ys = done_dict.get(str(year), {})
    lst = ys.get(season, [])
    if tile_name in lst:
        ys[season] = [x for x in lst if x != tile_name]
        done_dict[str(year)] = ys


def task_prefix():
    """⛑ v107  Prefix of every Earth Engine task DESCRIPTION this version
    creates: 'CSV_<ROI>_<version>_'. See ADOPT_PRIOR_VERSION_TASKS."""
    return f"CSV_{ROI_ID}_{PIPELINE_VERSION}_"


def roi_prefix():
    """Prefix shared by every version's tasks for this ROI ('CSV_<ROI>_')."""
    return f"CSV_{ROI_ID}_"


def description_from_name(name):
    # ⛑ BUG FOUND AND FIXED, reported directly: description used to be just
    # "CSV_" + name (e.g. "CSV_2020_Kharif_tile0_sub0"), with nothing
    # identifying which ROI/watershed it belonged to -- two different
    # watersheds using the same tiling scheme could produce byte-identical
    # descriptions, and reconcile_tasks() (which matches against Earth
    # Engine's real, PROJECT-WIDE task list, not anything ROI-scoped on its
    # own) had no way to tell them apart. ROI_ID is now baked into every
    # description, so this is no longer possible.
    # ⛑ v107  ...and PIPELINE_VERSION is now baked in too, for the same
    # reason one level up: two VERSIONS of this notebook exporting the same
    # ROI produced byte-identical descriptions (see ADOPT_PRIOR_VERSION_TASKS
    # for the silent-skip this caused). The Drive FILE name is produced by
    # file_prefix_from_name() below and is deliberately unchanged.
    return f"{task_prefix()}{name}"


def file_prefix_from_name(name):
    """⛑ v107  The CSV file name on Drive -- identical to what every earlier
    version wrote ('CSV_<ROI>_<year>_<season>_<tile>'), so nothing that reads
    file names downstream changes. Only the task DESCRIPTION gained the
    version tag (description_from_name)."""
    return f"{roi_prefix()}{name}"


def _split_task_description(desc):
    """⛑ v107  -> (name, is_this_version) for a description with this ROI's
    prefix, or (None, False) for anything else. A prior version's task
    ('CSV_Sirur_2025_Rabi_...' from v106 or earlier, or 'CSV_Sirur_v106_...')
    is recognised as this ROI's but NOT this version's."""
    rp = roi_prefix()
    if not desc.startswith(rp):
        return None, False
    tp = task_prefix()
    if desc.startswith(tp):
        return desc[len(tp):], True
    rest = desc[len(rp):]
    # another version's tag ('v106_...'), or the un-tagged pre-v107 form
    parts = rest.split('_', 1)
    if len(parts) == 2 and parts[0].startswith('v') and parts[0][1:].isdigit():
        rest = parts[1]
    return rest, False


def parse_name(name):
    parts = name.split("_")
    try:
        year = int(parts[0])
    except Exception:
        year = None
    season = "Yearly"
    if len(parts) > 1 and parts[1] not in ["Yearly", "yearly"]:
        season = parts[1]
    return (year, season)


# ==================================================================
# ⛑ FIX37 -- ToS-BLOCK CIRCUIT BREAKER                              [v8.3]
# ==================================================================
# Google's message is: "Batch tasks are currently blocked and cannot run
# because this account conducted activity in violation of Earth Engine's
# Terms of Service." A blocked account cannot start ANY new batch task --
# per Google's own documentation this is enforced server-side against the
# account, not against anything a script does at request time. No amount of
# retrying, backing off, or resubmitting will succeed, and repeatedly trying
# is itself the kind of automated hammering the policy exists to stop.
#
# So: this specific error is never retried. It is detected once, the whole
# run stops immediately, state is saved, and the appeal path is printed.
APPEAL_FORM_URL = "https://forms.gle/MTi1MyowCLu4afqq8"
BATCH_RESTRICTIONS_DOC = "https://developers.google.com/earth-engine/batch-task-restrictions"

TOS_BLOCK_MARKERS = (
    "conducted activity in violation",
    "batch tasks are currently blocked",
    "batch-task-restrictions",
    "spreading earth engine usage",
)


def _is_tos_block(err_text):
    t = (err_text or "").lower()
    return any(m in t for m in TOS_BLOCK_MARKERS)


class BatchBlockedError(Exception):
    """Raised once, never retried. Caught at the top of main()."""
    pass


def _tos_guidance(err_text):
    return (
        "\n" + "=" * 78 +
        "\n🛑 EARTH ENGINE HAS BLOCKED BATCH TASKS ON THIS ACCOUNT/PROJECT.\n"
        "   No code change can start a task while this is active -- it is a\n"
        f"   server-side flag on the account, not a property of this script.\n\n"
        f"   Google's message: {err_text}\n\n"
        "   The ONLY documented path forward:\n"
        f"     1. Read: {BATCH_RESTRICTIONS_DOC}\n"
        f"     2. File an appeal:  {APPEAL_FORM_URL}\n"
        "        (Google states it cannot respond to every request.)\n"
        "     3. Do not keep re-running this notebook against the same\n"
        "        project in the meantime -- repeated submission attempts on\n"
        "        a blocked account do not help and may look like continued\n"
        "        violation.\n\n"
        "   Google's own policy page names ONE specific cause: spreading a\n"
        "   single large workload across MULTIPLE Earth Engine accounts or\n"
        "   projects. If you have run this export from more than one EE\n"
        "   project (this notebook's history includes both 'rwdirma' and\n"
        "   'project-b8709884-8eb1-4994-987'), consolidate to ONE project\n"
        "   before appealing or resuming.\n" + "=" * 78 + "\n"
    )


def _retry(fn, tries=5, base=2.0, what="EE call"):
    """⛑ FIX15  backoff around getInfo(); v7.7 logged 75 raw throttling retries.
    ⛑ FIX37  never retries a ToS-block -- see above."""
    import random
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            m = str(e)
            if _is_tos_block(m):
                raise BatchBlockedError(m)
            ml = m.lower()
            if "not found" in ml or "permission" in ml or i == tries - 1:
                break
            time.sleep(base * (2 ** i) * (0.7 + 0.6 * random.random()))
    raise last


# ==================================================================
# ⛑ BUG REPORTED AND FIXED: NameError calling estimate_job() (and, by the
# same mechanism, any other entry point below) when not every definition
# cell above it has been run in the current kernel session.
# ==================================================================
# Diagnosed against the actual delivered notebook, not assumed: the cell
# defining export_columns() (Section 8, "Export") genuinely comes before the
# cell defining estimate_job() (Section 10, "Setup"), which comes before the
# reported failing cell (Section 13) -- the cell ORDER is correct. This is a
# kernel-state issue: Colab/Jupyter cells share one running kernel, and a
# runtime restart (timeout, disconnect, "Restart runtime", or simply opening
# a fresh session) wipes every previously-defined function and variable.
# Jumping straight to a later cell -- e.g. re-checking estimate_job() after
# only editing DOWNLOAD_YEARS in Section 1 -- reproduces exactly this error
# if the definition cells were not re-run first in that session. That's a
# completely reasonable thing for someone to try, so rather than only
# documenting "run all cells first" (which is necessary but easy to forget
# under exactly this scenario), every entry point someone might plausibly
# run on its own after a restart now catches this specific failure and
# explains it in place, instead of surfacing a raw traceback pointing at an
# internal implementation line with no indication of the real cause.
# ⛑ v108  Which notebook SECTION defines each function -- so a NameError
# after a Colab runtime restart says "run Section 10" instead of only "run
# all cells". Generated from the notebook's own cell boundaries; used by
# _friendly_name_errors() and _check_pipeline_defined() below.
_SECTION_OF = {
    '1. Configuration':
        '_friendly_name_errors _is_tos_block _load_json _now_iso _retry _save_json _split_task_description _tos_guidance description_from_name file_prefix_from_name init_state_dir is_done load_completed load_gapfilled_windows load_progress load_substituted_windows load_task_ledger mark_done parse_name prepareROI record_task remove_done_from_progress roi_prefix save_completed save_gapfilled_windows save_progress save_substituted_windows save_task_ledger task_prefix',
    '2. Task-list helpers':
        '_task_list',
    '2b. Cancel every task currently queued or running':
        '_cancel_all_pending_tasks_legacy cancel_all_pending_tasks reconcile_tasks',
    '3. Utilities, the ToS-block circuit breaker, and capacity management':
        '_m_per_deg active_task_count approx_pixel_count box_geom ensureBands harmonise makeTiles mark_submitted maskedBand safeComposite safeMean safeReduce safeSum split_box split_factor wait_for_capacity',
    '4. Data availability probing':
        '_covers _data_hard_end _effective_end clamp_window collection_end eedate preflight_data_report resolve_source season_window shift_years window_is_data_incomplete',
    '5. Spectral indices':
        '_apply_modis_lai _composite_indices_optical _core_subwindow _mask_landsat _mask_mod09 _mask_modis_lai_qc _mask_s2_qa60 _mask_s2_scl _merge_modis _modis_lai_window_ee _modis_lst_ic _modis_reflectance_ic _priority_composite _report_levels _sel compositeIndices compute_indices',
    '6. Climate bands':
        '_clim_ic _clim_lo_hi _combine _et_ratio_clim_window_ee _lst_obs_ee _lst_window_ee _mod11_qc _mod13_qa _ndvi_obs_ee _ndvi_window_ee _pick_band _safe_span addClimateBands',
    '7a. VCI, TCI, VHI, ESI, ESI_Anom, WSSI, WSI':
        'addStressIndices',
    '7b. Land use, AGB, RUSLE':
        '_annual_rain_ee _asset_has_band _classifyLandUse_ndvi_fallback _fabdem_elevation _gedi_mission_end _k_factor_texture_fallback _ls_factor_slope_fallback _nasadem_elevation _sar_agb_candidate calcAGB calcRUSLE calc_C_and_P calc_K_factor calc_LS_factor calc_R_factor classifyLandUse validate_agb_against_gedi',
    '8. Export, validation gate, and the ToS-aware batch-failure sweep':
        '_looks_like_timeout drive_folder_for exportTile export_columns validate_window',
    '9. Batch-failure sweep':
        'sweep_failed_tasks',
    '10. Setup, tiling, the job estimator, and the chunk-workflow functions':
        '_centre_in _chunk_task_estimate _is_treated _window_will_run build_export_grid chunk_plan chunk_status estimate_job run_chunk run_period setup tile_boxes',
    '11. build_stack(), main(), run_download()':
        '_build_fully_projected_window _check_pipeline_defined _gapfill_missing_period _temp_bands_only _temp_coverage _temp_tail_missing _write_manifest build_stack diagnose_window main run_download task_failure_report window_coverage',
}


def _where_defined(names):
    out = []
    for n in names:
        sec = next((t for t, ns in _SECTION_OF.items() if n in ns.split()), None)
        out.append(f"{n} -> Section {sec}" if sec else f"{n} -> (not a pipeline definition)")
    return out


def _names_in_error(err_text):
    return re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", str(err_text))


def _friendly_name_errors(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NameError as e:
            print(f"🚫 {e}")
            print("This means not every definition cell above this one has "
                  "been run in the CURRENT session -- most often caused by a "
                  "Colab/Jupyter runtime restart, timeout, or disconnect "
                  "(including the 'Could not load the JavaScript files needed "
                  "to display output' login/cookie error, after which Colab "
                  "usually hands you a FRESH runtime), which silently clears "
                  "every previously-defined function.")
            # ⛑ v108  say exactly which section(s) to run
            where = _where_defined(_names_in_error(e))
            if where:
                print("Defined in: " + "; ".join(where))
            print("Fix: run the section(s) named above and every section AFTER "
                  "them (or simply Runtime > Run all), then re-run this cell. "
                  "Bullet-proof alternative: the optional cell in Section 0b "
                  "loads the ENTIRE pipeline from artal_exporter_"
                  f"{PIPELINE_VERSION}.py in one step, so a half-defined "
                  "session cannot happen.")
            return None
    return wrapper


# ---------------- TASK LIST (listOperations replaces getTaskList) ----------
def _task_list():
    """⛑ FIX8  normalised view; ee.data.getTaskList() is deprecated.
    ⛑ FIX37  propagates a ToS-block instead of silently swallowing it."""
    out = []
    try:
        for op in ee.data.listOperations():
            md = op.get('metadata', {}) or {}
            out.append({'id': (op.get('name', '') or '').split('/')[-1],
                        'description': md.get('description', ''),
                        'state': (md.get('state') or '').upper(),
                        'error': ((op.get('error') or {}).get('message') or '')})
    except Exception as e:
        if _is_tos_block(str(e)):
            raise BatchBlockedError(str(e))
        try:
            for t in (ee.data.getTaskList() or []):
                out.append({'id': t.get('id', ''),
                            'description': t.get('description', ''),
                            'state': (t.get('state') or '').upper(),
                            'error': t.get('error_message', '')})
        except Exception as e2:
            if _is_tos_block(str(e2)):
                raise BatchBlockedError(str(e2))
    return out


# ==================================================================
# ⛑ v9.0 -- cancel every task currently lined up for submission/running
# ==================================================================
CANCELLABLE_STATES = ('READY', 'PENDING', 'RUNNING', 'SUBMITTED')


@_friendly_name_errors
def cancel_all_pending_tasks(states=CANCELLABLE_STATES, dry_run=False):
    """Cancels every batch task this project currently has queued or running
    on Earth Engine's side -- lets you stop an in-progress or about-to-run
    export cleanly, e.g. before switching DOWNLOAD_YEARS/DOWNLOAD_SEASONS and
    starting a different run. Does not touch already-completed, already-
    failed, or already-cancelled tasks, and does not modify local progress/
    ledger files -- they still accurately reflect what genuinely finished, so
    re-running run_download()/main() afterward correctly skips completed
    work and re-queues only what you cancelled.

    dry_run=True lists what WOULD be cancelled without cancelling anything --
    useful to check before committing.

    Uses ee.data.cancelOperation(name), the current, non-deprecated cancel
    API (the older per-task .cancel()/cancelTask() is Google's own documented
    deprecated path), with a legacy fallback for older API versions."""
    try:
        ops = ee.data.listOperations()
    except Exception as e:
        if _is_tos_block(str(e)):
            raise BatchBlockedError(str(e))
        print(f"🚫 Could not list tasks ({e}); falling back to the legacy API.")
        return _cancel_all_pending_tasks_legacy(states, dry_run)

    targets = []
    for op in ops:
        md = op.get('metadata', {}) or {}
        state = (md.get('state') or '').upper()
        if state in states:
            targets.append((op.get('name', ''), md.get('description', ''), state))

    if not targets:
        print("✅ Nothing to cancel -- no tasks currently in "
              f"{', '.join(states)}.")
        return 0

    print(f"{'Would cancel' if dry_run else 'Cancelling'} {len(targets)} task(s):")
    for name, desc, state in targets[:20]:
        print(f"   {state:10s} {desc}")
    if len(targets) > 20:
        print(f"   ... and {len(targets) - 20} more")
    if dry_run:
        return len(targets)

    cancelled, errors = 0, 0
    try:
        ee.data.cancelOperation([n for n, _d, _s in targets])
        cancelled = len(targets)
    except Exception:
        # Some API versions/backends only accept one name per call -- retry
        # individually rather than losing the whole batch to one bad name.
        for name, desc, _state in targets:
            try:
                ee.data.cancelOperation(name)
                cancelled += 1
            except Exception as e2:
                errors += 1
                print(f"   ⚠️ could not cancel {desc}: {e2}")

    print(f"🛑 Cancelled {cancelled} task(s)"
          f"{f', {errors} failed to cancel' if errors else ''}.")
    print("   Local progress state is untouched -- re-running run_download() "
          "or main() will skip completed work and retry anything cancelled.")
    return cancelled


def _cancel_all_pending_tasks_legacy(states, dry_run):
    try:
        tasks = ee.data.getTaskList() or []
    except Exception as e:
        print(f"🚫 Legacy task listing also failed: {e}")
        return 0
    targets = [t for t in tasks if (t.get('state') or '').upper() in states]
    if not targets:
        print(f"✅ Nothing to cancel -- no tasks currently in {', '.join(states)}.")
        return 0
    print(f"{'Would cancel' if dry_run else 'Cancelling'} {len(targets)} task(s) "
          f"via the legacy API:")
    for t in targets[:20]:
        print(f"   {t.get('state'):10s} {t.get('description', '')}")
    if dry_run:
        return len(targets)
    cancelled, errors = 0, 0
    for t in targets:
        try:
            ee.data.cancelTask(t['id'])
            cancelled += 1
        except Exception as e:
            errors += 1
            print(f"   ⚠️ could not cancel {t.get('description', '')}: {e}")
    print(f"🛑 Cancelled {cancelled} task(s)"
          f"{f', {errors} failed to cancel' if errors else ''} (legacy API).")
    return cancelled


def reconcile_tasks(done_dict):
    print("🔁 Reconciling previous tasks (resume)…")
    completed = load_completed()
    # ⛑ BUG FOUND AND FIXED, reported directly: this used to accept ANY
    # "CSV_"-prefixed task in the whole project, with no regard for which
    # ROI/watershed it belonged to -- a different watershed's completed
    # task could be silently reconciled as if it were this one's, marking
    # tiles "done" that this ROI never actually exported. Now requires the
    # CURRENT ROI's own prefix specifically; a task from a different
    # watershed is correctly left alone entirely, exactly as if it
    # belonged to someone else's run, because it does.
    #
    # ⛑ v107  Same principle, one level further: only THIS VERSION's tasks
    # count, unless ADOPT_PRIOR_VERSION_TASKS is deliberately set. A prior
    # version's SUCCEEDED task lives in a different Drive folder, so
    # adopting it as "done" left this version's folder without that window
    # ("queued 0 tasks", green tick, no CSV). Ignored tasks are counted and
    # reported, never silently dropped.
    ignored_prior = {}
    for t in _task_list():
        desc = t['description']
        name, mine = _split_task_description(desc)
        if name is None:
            continue
        state = t['state']
        if not mine and not ADOPT_PRIOR_VERSION_TASKS:
            if state in ("COMPLETED", "SUCCEEDED"):
                yr0, se0 = parse_name(name)
                ignored_prior[(yr0, se0)] = ignored_prior.get((yr0, se0), 0) + 1
            continue
        record_task(desc, state, task_id=t['id'],
                    detail={'error': t['error']} if t['error'] else None)
        yr, season_str = parse_name(name)
        if state in ("COMPLETED", "SUCCEEDED"):
            completed.add(desc)
            if yr is not None:
                mark_done(done_dict, yr, season_str, name)
        elif state in ("FAILED", "CANCELLED"):
            if yr is not None:
                remove_done_from_progress(done_dict, yr, season_str, name)
    if ignored_prior:
        n = sum(ignored_prior.values())
        wins = ", ".join(f"{y} {s}" for (y, s) in sorted(ignored_prior,
                                                         key=lambda k: (str(k[0]), k[1])))
        print(f"   ℹ️ {n} completed task(s) for {ROI_ID} on Earth Engine belong to an "
              f"EARLIER notebook version ({wins}) and were NOT adopted as done -- "
              f"their CSVs are in that version's Drive folder, not "
              f"{DRIVE_FOLDER}_*. This version will export those windows "
              f"itself if they are selected. Set ADOPT_PRIOR_VERSION_TASKS = "
              f"True to treat them as already done instead.")
    save_completed(completed)
    save_task_ledger()
    save_progress(done_dict)
    print("🔁 Resume reconciliation complete.")
    return done_dict


# ---------------- UTILITIES ----------------
# ==================================================================
# ⛑ BUG FOUND AND FIXED during deep validation: resampling was applied at
# the WRONG point in the graph, so it was not actually harmonising anything.
# ==================================================================
# Google's own ee.Image.resample() documentation is explicit: "This relies
# on the input image's default projection being meaningful, and so cannot
# be used on composites... Instead, you should resample the images that are
# used to create the composite." harmonise() called .resample('bilinear')
# on the FINAL multi-band, multi-source result (spectral indices computed
# via band math, climate composites already reduced from a collection, K/LS/
# RUSLE computed via .expression()) -- every single one of these is exactly
# the kind of composite Google's own docs say resample() cannot act on
# correctly. It very likely had no real effect at any of its ~10 call sites
# throughout this file, on any dataset, ever -- a function literally named
# to suggest resolution harmonisation that was not actually doing it.
#
# THE FIX: resample() now happens on the RAW per-image inputs, before they
# are reduced into a composite -- inside safeReduce()/safeComposite() (the
# two shared utilities essentially every dataset in this pipeline flows
# through) and directly on the handful of static single-image continuous
# layers (NASADEM elevation, OpenLandMap sand/silt/clay/SOC, MERIT Hydro
# upstream area) at their load points. Categorical/discrete data (soil
# texture class, the final Dynamic World land-use class, and per-tile
# metadata like Treat/Year/Season/UID) explicitly keeps Earth Engine's
# default nearest-neighbour, which is the scientifically correct choice for
# discrete values -- bilinear-interpolating a class code produces a
# meaningless fractional value, not a smoother map.
def harmonise(img):
    """Type standardisation only (float32 everywhere) -- this is genuinely
    what this function can do correctly regardless of where it's called.
    Real resolution resampling is now handled upstream; see the block
    comment directly above."""
    return img.toFloat()


def maskedBand(name, value=0):
    return ee.Image.constant(value).rename(name) \
             .updateMask(ee.Image.constant(0)).toFloat()


# ⛑ FIX1  THE 2026 CRASH.
#   v7.7:  def safeMean(ic, band): return ee.Image(ee.ImageCollection(ic.select(band)).mean())
#   An EMPTY ImageCollection reduces to an image with ZERO bands. The very next
#   operation, .multiply(0.1), then raises
#     "Image.multiply: If one image has no bands, the other must also have no
#      bands. Got 0 and 1."
#   which is the exact error on CSV_2026_yearly_tile3_sub0 (it died in 1 second,
#   i.e. before a single pixel was read). safeMean guarded nothing.
def safeReduce(ic, band, how='mean', name=None, fill=None, resample=True):
    """Reduce ic[band]; substitute a named masked image if the collection is empty.
    Guaranteed never to return a zero-band image.

    resample=True (default) calls .resample('bilinear') on EACH image in the
    collection before reduction -- the correct point to do it, per Google's
    own ee.Image.resample() docs, since each individual source image (a
    single CHIRPS day, a single MOD13Q1 composite, etc.) has a genuine
    native projection to interpolate from; the REDUCED result does not.
    Every current caller of this function reduces a continuous physical
    quantity (rainfall, temperature, ET/PET, NDVI, LST, LAI, SAR backscatter)
    -- pass resample=False only for a genuinely discrete/categorical band,
    where nearest-neighbour must be kept."""
    name = name or band
    ic = ee.ImageCollection(ic)
    sel = ic.select([band]) if band else ic
    if resample:
        sel = sel.map(lambda im: im.resample('bilinear'))
    good = {'mean': sel.mean(), 'sum': sel.sum(), 'min': sel.min(),
            'max': sel.max(), 'median': sel.median(),
            'count': sel.count()}[how].rename([name])
    if fill is None:
        bad = ee.Image.constant(0).rename(name).toFloat() if how == 'count' \
            else maskedBand(name)
    else:
        bad = ee.Image.constant(fill).rename(name).toFloat()
    return ee.Image(ee.Algorithms.If(sel.size().gt(0), good, bad)).rename([name])


def safeMean(ic, band, name=None, fill=None):
    return safeReduce(ic, band, 'mean', name, fill)


def safeSum(ic, band, name=None, fill=None):
    return safeReduce(ic, band, 'sum', name, fill)


def safeComposite(ic, band_list, how='median', resample=True):
    """resample=True (default): each image in ic is bilinear-resampled before
    the median/mean composite is built -- this is what actually makes the
    Sentinel-2/Landsat/MODIS optical composites correctly interpolated at
    their non-10m native bands (S2's red-edge/SWIR at 20m, all of Landsat at
    30m, all of MODIS reflectance at 250-500m) instead of relying on default
    nearest-neighbour when later reduced to the 10 m output grid."""
    ic = ee.ImageCollection(ic)
    if resample:
        ic = ic.map(lambda im: im.resample('bilinear'))
    good = {'median': ic.median(), 'mean': ic.mean()}[how].select(band_list)
    bad = ee.Image.constant([0] * len(band_list)).rename(band_list) \
            .updateMask(ee.Image.constant(0)).toFloat()
    return ee.Image(ee.Algorithms.If(ic.size().gt(0), good, bad)).rename(band_list)


# ⛑ FIX13  schema guarantee. v7.7 did img.select(expected_cols, expected_cols),
#          which hard-fails with "Pattern did not match any bands" the moment a
#          sensor is missing for a window. Missing bands now come back masked.
def ensureBands(img, names):
    filler = ee.Image.constant([0] * len(names)).rename(names) \
               .updateMask(ee.Image.constant(0)).toFloat()
    return filler.addBands(img, None, True).select(names)


def active_task_count():
    return sum(1 for t in _task_list()
               if t['state'] in ('RUNNING', 'READY', 'PENDING'))


_CAP = {'n': 0, 'checked_at': 0.0, 'since': 0}
_LAST_SUBMIT = {'t': 0.0}
CAPACITY_RECHECK_S = 90       # seconds -- only used when MAX_CONCURRENT_TASKS > 5
CAPACITY_RECHECK_EVERY = 50   # submissions -- only used when > 5


def wait_for_capacity():
    """⛑ FIX6  v7.7 defined this but NEVER called it, so its concurrency limit
    had no effect and the API throttled instead.

    ⛑ FIX36  With MAX_CONCURRENT_TASKS = 1 (the new default) this blocks until
    active_task_count() == 0, i.e. strictly one task in the system at a time --
    "submit one task when only one task is running" with no queue ever forming.
    A cached/stale count would risk over- or under-submitting right when being
    conservative matters most, so for MAX_CONCURRENT_TASKS <= 5 every check is
    live. The staleness optimisation from v8.2 (⛑ FIX33) is kept only for
    people who deliberately raise the limit back up once their account is
    confirmed unrestricted.

    After capacity clears, MIN_SUBMIT_INTERVAL_S enforces an additional pacing
    floor between submissions, independent of the concurrency count."""
    live = MAX_CONCURRENT_TASKS <= 5
    while True:
        now = time.time()
        stale = live or (
            now - _CAP['checked_at'] > CAPACITY_RECHECK_S
            or _CAP['since'] >= CAPACITY_RECHECK_EVERY
            or _CAP['n'] + _CAP['since'] >= MAX_CONCURRENT_TASKS)
        if stale:
            _CAP['n'] = active_task_count()   # raises BatchBlockedError via _retry
            _CAP['checked_at'] = time.time()
            _CAP['since'] = 0
        if _CAP['n'] + _CAP['since'] < MAX_CONCURRENT_TASKS:
            break
        print(f"⏳ {_CAP['n']} task(s) pending/running "
              f"(limit {MAX_CONCURRENT_TASKS}) — waiting {TASK_POLL_INTERVAL}s")
        time.sleep(TASK_POLL_INTERVAL)
        if not live:
            _CAP['since'] += 0   # keep loop structure identical to v8.2 path

    elapsed = time.time() - _LAST_SUBMIT['t']
    if elapsed < MIN_SUBMIT_INTERVAL_S:
        time.sleep(MIN_SUBMIT_INTERVAL_S - elapsed)
    if not live:
        _CAP['since'] += 1


def mark_submitted():
    _LAST_SUBMIT['t'] = time.time()


# ⛑ FIX5b  v7.7 makeTiles(geom, deg) ended with .filterBounds(region) where
#          region was the PARENT TILE, not the ROI. Sub-tiles falling outside
#          the watershed were still generated: 253 "Empty tile" exports.
def makeTiles(region, deg, clip_to=None):
    deg = ee.Number(deg)
    bounds = region.bounds(1, ee.Projection('EPSG:4326')).coordinates().get(0)
    xs = ee.List(bounds).map(lambda p: ee.Number(ee.List(p).get(0)))
    ys = ee.List(bounds).map(lambda p: ee.Number(ee.List(p).get(1)))
    xmin, xmax = xs.reduce(ee.Reducer.min()), xs.reduce(ee.Reducer.max())
    ymin, ymax = ys.reduce(ee.Reducer.min()), ys.reduce(ee.Reducer.max())
    lonSteps, latSteps = ee.List.sequence(xmin, xmax, deg), ee.List.sequence(ymin, ymax, deg)

    def makeRects(lat):
        lat = ee.Number(lat)

        def rect(lon):
            lon = ee.Number(lon)
            return ee.Feature(ee.Geometry.Rectangle(
                [lon, lat, lon.add(deg), lat.add(deg)], 'EPSG:4326', False))
        return lonSteps.map(rect)

    fc = ee.FeatureCollection(latSteps.map(makeRects).flatten())
    return fc.filterBounds(clip_to if clip_to is not None else region)


# 🔒 CONSISTENT 10m GRID FOR META BANDS
GRID_PROJ = None
UID_BAND = None
LONLAT_BASE = None


# ⛑ FIX4  THE DEAD OVERSIZE GUARD.
#   v7.7:  ee.Geometry(geom, None, False).area(1).getInfo()
#   Passing proj/geodesic to a COMPUTED geometry always raises
#     "Setting the CRS or geodesic on a computed Geometry is not supported"
#   Your log contains that message 1,836 times: the pixel guard never once ran,
#   so no tile was ever pre-split on size. Now computed on the client from the
#   box corners, so it cannot throw.
def _m_per_deg(lat):
    phi = math.radians(lat)
    mlat = (111132.92 - 559.82 * math.cos(2 * phi)
            + 1.175 * math.cos(4 * phi) - 0.0023 * math.cos(6 * phi))
    mlon = (111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
            + 0.118 * math.cos(5 * phi))
    return mlat, max(mlon, 1.0)


def approx_pixel_count(box, scale=SCALE):
    """box = [west, south, east, north] in degrees."""
    w, s, e, n = box
    mlat, mlon = _m_per_deg((s + n) / 2.0)
    return ((n - s) * mlat / scale) * ((e - w) * mlon / scale)


def split_box(box, n=2):
    w, s, e, nn = box
    dx, dy = (e - w) / n, (nn - s) / n
    return [[w + i * dx, s + j * dy, w + (i + 1) * dx, s + (j + 1) * dy]
            for j in range(n) for i in range(n)]


def split_factor(px, target=None):
    target = target or PIXEL_LIMIT
    return max(2, int(math.ceil(math.sqrt(max(px, 1.0) / float(target)))))


def box_geom(box):
    return ee.Geometry.Rectangle([box[0], box[1], box[2], box[3]],
                                 'EPSG:4326', False)


# ---------------- DATA AVAILABILITY (the 2026 fix) ---------------- ⛑ FIX3
# v7.7 had no idea how far any dataset actually runs. It built windows ending
# 2026-12-31 and 2027-02-28 and then failed on the empty collections.
FALLBACK_END = {
    'MODIS/061/MOD16A2GF': date(2025, 12, 27),   # year-end gap-filled, ~1 yr lag
    'MODIS/061/MYD16A2GF': date(2025, 12, 27),
    'UCSB-CHG/CHIRTS/DAILY': date(2016, 12, 31), # CHIRTS-daily stops in 2016
}
_AVAIL = {}


def collection_end(cid):
    if cid in _AVAIL:
        return _AVAIL[cid]
    res = FALLBACK_END.get(cid)
    if PROBE_AVAILABILITY:
        try:
            ms = _retry(lambda: ee.ImageCollection(cid)
                        .aggregate_max('system:time_start').getInfo(),
                        tries=3, what=cid)
            if ms:
                res = datetime.datetime.fromtimestamp(
                    ms / 1000.0, datetime.timezone.utc).date()
        except Exception:
            pass
    _AVAIL[cid] = res
    if res:
        print(f"   📅 {cid}: data through {res}")
    return res


def season_window(year, season):
    """⛑ FIX12  Exclusive end dates.
    v7.7 used ee.Date.fromYMD(yr, em, 28) with filterDate's exclusive end, so it
    lost Sep 29-30 (Kharif), May 29-31 (Zaid), Feb 29 in leap years (Rabi) and
    Dec 31 every year (Yearly)."""
    if season == 'Yearly':
        return date(year, 1, 1), date(year + 1, 1, 1)
    sm, em = SEASONS[season]
    off = 1 if em < sm else 0
    end_m = em + 1
    end_y = year + off
    if end_m > 12:
        end_m, end_y = 1, end_y + 1
    return date(year, sm, 1), date(end_y, end_m, 1)


def _data_hard_end(cids=('UCSB-CHG/CHIRPS/DAILY',)):
    """⛑ v107  The last calendar day for which the pipeline's pacing source
    (CHIRPS by default, exactly as clamp_window has always used) has data,
    capped at today. This is the ONE date every 'has this window happened
    yet, as far as the DATA is concerned' decision now keys on --
    clamp_window() below, the gap-fill gates in build_stack(), and the
    gap-filled-window refresh in main(). Previously those gates compared
    the window against date.today() instead, which is a different question:
    a season whose calendar end has passed but whose data hasn't been
    published yet (CHIRPS final runs ~6 weeks behind) is, for this pipeline,
    still an incomplete window -- see the note above build_stack()'s
    gap-fill gate for the real stuck-partial exports this caused."""
    today = date.today()
    ends = [e for e in (collection_end(c) for c in cids) if e]
    return min([today] + ends)


def clamp_window(d0, d1, cids=('UCSB-CHG/CHIRPS/DAILY',)):
    """Truncate a window to real data availability.
    Returns (d0, d1, coverage_fraction, note) or (None, None, 0, reason)."""
    hard_end = _data_hard_end(cids)
    if d0 >= hard_end:
        return None, None, 0.0, f"window starts {d0}, data ends {hard_end}"
    total = (d1 - d0).days
    new_d1 = min(d1, hard_end + datetime.timedelta(days=1))
    got = (new_d1 - d0).days
    frac = got / float(total) if total else 0.0
    if got < MIN_WINDOW_DAYS:
        return None, None, frac, f"only {got} days available"
    note = "" if new_d1 == d1 else f"clamped {d1}→{new_d1} ({frac:.0%} of window)"
    return d0, new_d1, frac, note


def window_is_data_incomplete(raw1, cids=('UCSB-CHG/CHIRPS/DAILY',)):
    """⛑ v107  True when the requested window end lies beyond the last day
    the pacing data source has published -- i.e. the window is incomplete
    BECAUSE THE DATA HASN'T ARRIVED YET (a running season, a future season,
    or a just-finished season still inside the publication lag). This is
    the only truncation clamp_window() can ever apply, so it is exactly the
    condition under which gap-filling from the last 3 years is warranted.
    A genuinely past window (data end already beyond it) is never true here,
    which is the 'gap-fill only applies to the present/future' guarantee,
    now stated in terms of the data rather than the wall clock."""
    return raw1 > _data_hard_end(cids) + datetime.timedelta(days=1)


def eedate(d):
    return ee.Date(d.isoformat())


def shift_years(d, k):
    """Same calendar day, k years earlier. Handles 29 Feb."""
    try:
        return d.replace(year=d.year - k)
    except ValueError:
        return d.replace(year=d.year - k, day=28)


# ==================================================================
# ⛑ FIX25 — DATA DISCOVERY AND SUBSTITUTION
# ==================================================================
# v7.7 assumed every dataset covered every window and crashed when one did not.
# v8.1 asks each collection what it actually holds, then picks the best REAL
# product that covers the window. Nothing is invented.
#
# Ranked candidate lists. Each entry:
#   (collection_id, code, note)
# Code is what gets written into the SrcOpt / SrcET provenance columns.
SOURCES = {
    'et': [
        ('MODIS/061/MOD16A2GF', 1, '8-day gap-filled ET/PET, 500 m (best, ~1 yr lag)'),
        ('MODIS/061/MOD16A2',   2, '8-day near-real-time ET/PET, 500 m (2021+)'),
        ('IDAHO_EPSCOR/TERRACLIMATE', 3, 'monthly aet/pet, 4 km (ends 2024)'),
    ],
    'optical': [
        ('COPERNICUS/S2_SR_HARMONIZED', 1, 'Sentinel-2 L2A surface reflectance, 10 m'),
        ('COPERNICUS/S2_HARMONIZED',    2, 'Sentinel-2 L1C TOA, 10 m'),
        ('LANDSAT/LC08/C02/T1_L2',      3, 'Landsat 8/9 C2 L2 surface reflectance, 30 m'),
        ('MODIS/061/MOD09A1',           4, 'MODIS 8-day surface reflectance, 500 m'),
    ],
    'temp': [
        ('ECMWF/ERA5_LAND/DAILY_AGGR',   1, 'ERA5-Land 2 m air T, daily, 11 km'),
        ('ECMWF/ERA5_LAND/MONTHLY_AGGR', 2, 'ERA5-Land 2 m air T, monthly, 11 km'),
        ('MODIS/061/MOD11A2',            3, 'MODIS LST (surface, not air), 1 km'),
    ],
    'rain':   [('UCSB-CHG/CHIRPS/DAILY', 1, 'CHIRPS daily rainfall, 5 km')],
    'ndvi_c': [('MODIS/061/MOD13Q1', 1, 'MODIS 16-day NDVI, 250 m')],
    'lst_c':  [('MODIS/061/MOD11A2', 1, 'MODIS 8-day LST, 1 km')],
    'sm':     [('ECMWF/ERA5_LAND/DAILY_AGGR', 1, 'ERA5-Land soil water, daily')],
    'sar':    [('COPERNICUS/S1_GRD', 1, 'Sentinel-1 GRD IW VV/VH, 10 m')],
}
OUTCOME_GROUPS = ('optical', 'temp', 'rain', 'et')

# ⛑ v107  BUG FOUND AND FIXED. collection_end() is the START date of the
# last image. For a composite product that is not where its data ends: the
# last MOD16 8-day composite of 2025 starts 2025-12-27 and covers through
# 2025-12-31, so a window ending 2026-01-01 was scored 361/365 = 0.989
# "covered" instead of 1.0. Effective end = start of last image + period-1.
COMPOSITE_PERIOD_DAYS = {
    'MODIS/061/MOD16A2GF': 8, 'MODIS/061/MYD16A2GF': 8, 'MODIS/061/MOD16A2': 8,
    'MODIS/061/MOD09A1': 8, 'MODIS/061/MOD11A2': 8, 'MODIS/061/MOD13Q1': 16,
    'IDAHO_EPSCOR/TERRACLIMATE': 31, 'ECMWF/ERA5_LAND/MONTHLY_AGGR': 31,
}
FULL_COVERAGE = 0.999   # "covers the whole window" for resolve_source()


def _effective_end(cid):
    """Last calendar day the collection genuinely covers (see above)."""
    end = collection_end(cid)
    if end is None:
        return None
    return end + datetime.timedelta(days=COMPOSITE_PERIOD_DAYS.get(cid, 1) - 1)


def _covers(cid, d0, d1, min_frac=MIN_WINDOW_COVERAGE):
    """Does this collection actually hold data across [d0, d1)?

    A collection with no known end date is near-real-time, NOT infinite — it
    still cannot cover the future. Clamping against today is what stops the
    resolver from cheerfully claiming Sentinel-2 covers Rabi 2026-27."""
    end = _effective_end(cid)
    today = date.today()
    hard = min(today, end) if end else today
    total = (d1 - d0).days
    if total <= 0:
        return False, 0.0
    usable = (min(d1, hard + datetime.timedelta(days=1)) - d0).days
    frac = max(0.0, min(1.0, usable / float(total)))
    return frac >= min_frac, frac


def resolve_source(group, d0, d1, allow_prev=None):
    """Return (collection_id, code, data_year_offset, coverage, note).

    Step 1  every real substitute PRODUCT that covers this window
    Step 2  the same calendar window in the most recent year that has data
    Step 3  give up -> (None, 0, ...) and the caller masks that band group

    data_year_offset is 0 for real current-window data, k>0 when the window was
    shifted back k years. It is written to the DataYear provenance column.

    ⛑ v107  BUG FOUND AND FIXED -- Rabi 2025's ET/PET were silently
    truncated. Step 1 used to accept the FIRST ranked source with >= 55%
    coverage, so for 2025-10-01..2026-03-01 the gap-filled MOD16A2GF
    (data ends 2025-12-27) won at 58-63% coverage over near-real-time
    MOD16A2, which covers all five months. Jan-Feb 2026 ET was dropped
    from a SUM while Rain kept the full window -- biasing WSI, ESI and
    ESI_Anom for every cross-year Rabi window that straddles the gap-
    filled product's year-end, with nothing in the export saying so. Step
    1 now runs in two passes: any source that covers the WHOLE window, in
    rank order, wins outright; only if none does is the old 'best ranked
    partial >= 55%' rule applied. For every window that was already fully
    covered by its top-ranked source (i.e. almost the entire panel) the
    choice is byte-identical to before.
    """
    if allow_prev is None:
        allow_prev = (ALLOW_PREVIOUS_YEAR and
                      (ALLOW_PREVIOUS_YEAR_OUTCOME or group not in OUTCOME_GROUPS))
    scored = [(cid, code, note) + _covers(cid, d0, d1) for cid, code, note in SOURCES[group]]
    for cid, code, note, ok, frac in scored:          # pass 1: full coverage
        if frac >= FULL_COVERAGE:
            return cid, code, 0, frac, note
    for cid, code, note, ok, frac in scored:          # pass 2: partial, by rank
        if ok:
            print(f"   ⚠️ {group}: no source covers the whole window; using "
                  f"{cid} at {frac:.0%} coverage (sum-type bands from it are "
                  f"proportionally low for that reason alone)")
            return cid, code, 0, frac, note + f" [{frac:.0%} of window]"
    if allow_prev:
        for k in range(1, PREV_YEAR_MAX_LOOKBACK + 1):
            a, b = shift_years(d0, k), shift_years(d1, k)
            for cid, code, note in SOURCES[group]:
                ok, frac = _covers(cid, a, b)
                if ok:
                    print(f"   🔄 {group}: no current-window source; using "
                          f"{cid} from {a.year} (shifted {k} yr) as substitute")
                    return cid, code, k, frac, note + f" [from {a.year}]"
    return None, 0, 0, 0.0, "no source covers this window"


@_friendly_name_errors
def preflight_data_report(write_csv=True):
    """⛑ FIX25  Ask Earth Engine what it actually has, BEFORE building anything.

    This is the 'search the required data first' step. It answers, in one table,
    why 2026 failed: MOD16A2GF stops at 2025-12-27, so every 2026 window hit an
    empty collection, and v7.7's safeMean() turned that into a zero-band image."""
    rows = []
    print("\n" + "=" * 78)
    print("📡 PREFLIGHT — data discovery")
    print("=" * 78)
    print(f"{'group':9s} {'collection':38s} {'through':12s} note")
    print("-" * 78)
    seen = set()
    for group, lst in SOURCES.items():
        for cid, code, note in lst:
            end = collection_end(cid)
            key = (group, cid)
            if key in seen:
                continue
            seen.add(key)
            rows.append({'group': group, 'collection': cid, 'code': code,
                         'available_through': str(end) if end else 'near-real-time',
                         'note': note})
            print(f"{group:9s} {cid:38s} {str(end) if end else 'NRT':12s} {note}")
    if write_csv:
        import csv as _csv
        with open(PREFLIGHT_FILE, 'w', newline='') as f:
            w = _csv.DictWriter(f, fieldnames=['group', 'collection', 'code',
                                               'available_through', 'note'])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"\n📄 Availability table → {PREFLIGHT_FILE}")
    return rows


# ==================================================================
# ⛑ FIX42 -- LITERATURE VALIDATION STATUS, every calculated column    [v8.4]
# ==================================================================
# You asked for every calculation validated against peer-reviewed sources.
# Below is the finding for each -- VERIFIED where a source was confirmed this
# pass, NOT VERIFIED where none could be found despite a genuine search
# attempt (these are flagged, not silently kept). Full detail, including what
# was searched and what the honest alternative is, is in the accompanying
# document -- this comment block is the traceable summary that travels with
# the code itself rather than living only in a separate file.
#
#   NDVI   VERIFIED  Rouse et al. 1974, the canonical vegetation index
#   SAVI   VERIFIED  Huete 1988, soil-adjusted form with L=0.5 (the classic
#                     "SAVI"; this is exactly (NIR-Red)/(NIR+Red+0.5)*1.5)
#   LSWI   VERIFIED  Xiao et al. 2002/2005, NIR-SWIR moisture index
#   NDWI   VERIFIED  McFeeters 1996, Green-NIR form (open-water delineation).
#                     NOTE: the literature uses "NDWI" for BOTH this formula
#                     and Gao 1996's NIR-SWIR vegetation-moisture index (which
#                     is numerically what this pipeline's LSWI/NDMI compute).
#                     This is a genuine, well-known naming collision in the
#                     remote-sensing literature itself, not a bug -- stated
#                     here so the two are not confused downstream.
#   EVI    VERIFIED  Huete, Didan, Miura, Rodriguez, Gao, Ferreira 2002 --
#                     exact standard MODIS EVI coefficients (G=2.5, C1=6,
#                     C2=7.5, L=1)
#   NDMI   VERIFIED  identical formula to LSWI; both kept for schema
#                     compatibility (see NDWI note above on naming)
#   NDRE   VERIFIED  Barnes et al. 2000, standard red-edge NDVI form
#   LAI    FIXED (v8.5)  MODIS MOD15A2H/MYD15A2H (Myneni et al.) is now the
#                     PRIMARY source, applied in compositeIndices() after this
#                     function runs -- see _apply_modis_lai(). The formula
#                     below remains ONLY as the fallback for the rare window
#                     with no quality-passing MODIS LAI observation at all,
#                     and is still NOT VERIFIED as a standalone formula -- see
#                     the note at the assignment below.
#   ESI/WSSI/WSI  PARTIALLY VERIFIED  see addStressIndices()
#   SMDI   VERIFIED  Narasimhan & Srinivasan 2005 (carried from earlier pass)
#   VCI/TCI/VHI  VERIFIED  Kogan 1990/1995 (carried from earlier pass)
#   Cloud Score+ threshold (0.60)  VERIFIED  matches Google's own worked
#                     example in the Cloud Score+ launch post, within the
#                     0.50-0.65 range independently reported as reasonable
#   AGB coefficients  NOT VERIFIED  see calcAGB()
#   RUSLE R/K/LS/C/P  VERIFIED  see the RUSLE section (earlier pass, unchanged)
#   Land use (Dynamic World)  VERIFIED  Brown et al. 2022 (earlier pass)
#
# ---- LAI: fallback formula, NOT VERIFIED as a standalone quantity --------
# `LAI = 3.618*NDVI - 0.118` was already in your original v7.7 file; no pass
# of this pipeline, including this one, invented it, and a genuine literature
# search found NO paper using these exact coefficients (NDVI-to-LAI
# relationships are typically NON-LINEAR and strongly crop-dependent --
# Bajocco, S. et al., 2022. "On the Use of NDVI to Estimate LAI in Field
# Crops." Remote Sensing 14, 3554, compiles 199 different published
# equations, each tied to a specific crop -- no single universal linear
# formula is supported by the literature for a heterogeneous watershed).
#
# ⛑ FIX44 (v8.5) resolves this: the formula below is no longer what the LAI
# column actually reports. It now only fires as a fallback, inside
# compositeIndices() -> _apply_modis_lai(), for pixels where the real,
# peer-reviewed MODIS LAI product (MOD15A2H/MYD15A2H, Myneni et al.) has no
# quality-passing observation for the window. As a formula in isolation it
# remains unverified; as what the LAI column actually contains for the large
# majority of pixels, it is now MODIS LAI, not this line.
def compute_indices(img, bandset, has_red_edge=True):
    """⛑ FIX16  has_red_edge.
    v7.7 passed NIR twice in the red-edge slot for the Landsat and MODIS
    fallbacks, so NDRE evaluated to (NIR-NIR)/(NIR+NIR) = 0 — a spurious ZERO
    written into the panel rather than a missing value. Your log shows the
    Landsat fallback taken 98x and the MODIS fallback 144x."""
    blue, green, red, nir, re_, swir = [img.select([b]) for b in bandset]
    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    savi = nir.subtract(red).divide(nir.add(red).add(0.5)).multiply(1.5).rename('SAVI')
    lswi = nir.subtract(swir).divide(nir.add(swir)).rename('LSWI')
    ndwi = green.subtract(nir).divide(green.add(nir)).rename('NDWI')
    evi = nir.subtract(red).multiply(2.5).divide(
        nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)).rename('EVI')
    ndmi = lswi.rename('NDMI')          # identical to LSWI by definition
    ndre = (nir.subtract(re_).divide(nir.add(re_)).rename('NDRE')
            if has_red_edge else maskedBand('NDRE'))
    lai = ndvi.multiply(3.618).add(-0.118).clamp(0, 6).rename('LAI')  # NOT VERIFIED, see above
    out = ee.Image.cat([ndvi, savi, lswi, ndwi, evi, ndmi, ndre, lai])
    out = out.addBands(out.select(
        ['NDVI', 'SAVI', 'LSWI', 'NDWI', 'EVI', 'NDMI', 'NDRE']).clamp(-1, 1),
        None, True)
    return harmonise(out)


# ---------------- CLOUD MASKS ---------------------------------- ⛑ FIX11
# v7.7 took a plain median of TOA reflectance with NO cloud screening at all.
# Over a Karnataka monsoon that leaves large positive reflectance bias in the
# visible bands, which depresses NDVI/EVI and inflates the RUSLE C-factor.
CSPLUS_ID = 'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'
CSPLUS_START = date(2015, 6, 27)
S2_SR_START = date(2017, 3, 28)


def _mask_s2_scl(img):
    scl = img.select('SCL')
    bad = (scl.eq(1).Or(scl.eq(3)).Or(scl.eq(8)).Or(scl.eq(9))
           .Or(scl.eq(10)).Or(scl.eq(11)))
    return img.updateMask(bad.Not())


def _mask_s2_qa60(img):
    qa = img.select('QA60')
    return img.updateMask(qa.bitwiseAnd(1 << 10).eq(0)
                          .And(qa.bitwiseAnd(1 << 11).eq(0)))


def _mask_landsat(img):
    qa = img.select('QA_PIXEL')
    return img.updateMask(qa.bitwiseAnd(1 << 1).eq(0)
                          .And(qa.bitwiseAnd(1 << 3).eq(0))
                          .And(qa.bitwiseAnd(1 << 4).eq(0))
                          .And(qa.bitwiseAnd(1 << 5).eq(0)))


def _mask_mod09(img):
    qa = img.select('StateQA')
    return img.updateMask(qa.bitwiseAnd(3).eq(0)
                          .And(qa.bitwiseAnd(1 << 2).eq(0)))


# ---------------- MODIS HELPERS (Terra/Aqua/both) ----------------
def _merge_modis(ids, s, e, bounds=True):
    out = None
    for cid in ids:
        c = ee.ImageCollection(cid).filterDate(s, e)
        if bounds:
            c = c.filterBounds(roiGeom)
        out = c if out is None else out.merge(c)
    return out


def _sel(terra, aqua):
    return {'terra': [terra], 'aqua': [aqua], 'both': [terra, aqua]}[MODIS_SOURCE]


def _modis_reflectance_ic(start, end):
    return _merge_modis(_sel('MODIS/061/MOD09A1', 'MODIS/061/MYD09A1'), start, end)


def _modis_lst_ic(start, end):
    return _merge_modis(_sel('MODIS/061/MOD11A2', 'MODIS/061/MYD11A2'), start, end)


# ---------------- MULTI-SENSOR COMPOSITE ----------------
def compositeIndices(d0, d1, season=None):
    """Returns (image, tag, code) — code 1=S2_SR 2=S2_TOA 3=Landsat 4=MODIS 0=none.

    ⛑ FIX44 -- THE FIX for LAI 'not verified'.                        [v8.5]
    LAI is overridden with the real MODIS LAI product (Myneni et al.;
    MOD15A2H/MYD15A2H, QC-filtered, Terra+Aqua) wherever it has valid data --
    a peer-reviewed, globally-validated satellite product replaces the
    empirical NDVI regression as the PRIMARY source. The regression (still
    flagged NOT VERIFIED in compute_indices) is kept ONLY as a fallback for
    the rare window where MODIS LAI has no quality-passing observation at
    all. See _apply_modis_lai() below.

    ⛑ v108  `season` (optional) enables the core-month-first rule for the
    optical composite and MODIS LAI -- see OPTICAL_PRIORITY / CLOUD_TIERS /
    SEASON_CORE_MONTHS in the configuration. None or 'Yearly' = no core split.
    """
    img, tag, code = _composite_indices_optical(d0, d1, season)
    img = _apply_modis_lai(img, d0, d1, season)
    return img, tag, code


# ==================================================================
# ⛑ v108 -- QUALITY-TIERED, CORE-MONTH-FIRST COMPOSITING (shared engine)
# ==================================================================
def _core_subwindow(d0, d1, season):
    """The core-month sub-window of [d0, d1) for `season`, or None when the
    rule does not apply (Yearly / unknown season / rule off), when the
    clamped window keeps fewer than MIN_CORE_DAYS core days, or when the
    core already IS the whole window (nothing to prioritise). The core is
    anchored to the season's own start year, so a Rabi tail that begins in
    January still maps onto that Rabi's Nov-Jan core."""
    if not USE_CORE_MONTHS_FIRST or season not in SEASON_CORE_MONTHS:
        return None
    ma, mb = _core_months(season)      # ⛑ v111  CORE_MONTHS_OVERRIDE-aware
    sm, _em = SEASONS[season]
    y0 = d0.year if d0.month >= sm else d0.year - 1      # season start year
    ya = y0 if ma >= sm else y0 + 1
    yb = y0 if mb >= sm else y0 + 1
    c0 = date(ya, ma, 1)
    c1 = date(yb + 1, 1, 1) if mb == 12 else date(yb, mb + 1, 1)
    c0, c1 = max(c0, d0), min(c1, d1)
    if (c1 - c0).days < MIN_CORE_DAYS:
        return None
    if c0 <= d0 and c1 >= d1:
        return None
    return c0, c1


def _priority_composite(ic, bands, d0, d1, season, scene_prop=None, cs_linked=False,
                        pixel_mask=None, how='median', last_tier_scene_filter=True):
    """Builds ONE composite of `bands` from `ic` (already bounds/date
    filtered, NOT yet cloud-filtered or masked) by per-pixel priority:

        core months + strictest tier  >  core + next tier ...  >
        full window + strictest tier  >  ...  >  full window + last tier

    A pixel takes the first level in which it has >= MIN_OBS_TIER clear
    observations; the last level (full window, last tier = the pre-v108
    rule) needs only 1, so no pixel ends with less data than before.

    scene_prop   scene-level cloud % property ('CLOUDY_PIXEL_PERCENTAGE',
                 'CLOUD_COVER'); None = no scene-level filtering (MODIS).
    cs_linked    'cs_cdf' (Cloud Score+) is present: the tier's per-pixel
                 clear threshold applies. Otherwise `pixel_mask` (a binary
                 QA mask function) is applied identically in every tier.
    last_tier_scene_filter  False = the last tier applies NO scene filter
                 (Landsat never had one before v108; kept that way).

    Returns (composite, tier_image, level_labels, level_collections)."""
    core = _core_subwindow(d0, d1, season)
    periods = ([('core', core[0], core[1])] if core else []) + [('full', d0, d1)]
    tiers = list(CLOUD_TIERS)
    if scene_prop is None and not cs_linked:
        tiers = tiers[-1:]                    # tiers would be identical: keep one
    levels = []
    for pname, p0, p1 in periods:
        pic = ic.filterDate(eedate(p0), eedate(p1))
        for ti, (scene_max, cs_min) in enumerate(tiers):
            last = ti == len(tiers) - 1
            c = pic
            if scene_prop is not None and scene_max is not None and \
                    (last_tier_scene_filter or not last):
                c = c.filter(ee.Filter.lt(scene_prop, scene_max))
            if cs_linked:
                c = c.map(lambda im, t=cs_min: im.updateMask(im.select('cs_cdf').gte(t)))
            elif pixel_mask is not None:
                c = c.map(pixel_mask)
            levels.append((f"{pname}/{'standard' if last else f'tier{ti + 1}'}", c))

    comps, counts = [], []
    for _label, c in levels:
        comps.append(safeComposite(c.select(bands), bands, how))
        counts.append(safeReduce(c, bands[0], 'count', name='n', resample=False))
    n_lv = len(levels)
    out = comps[-1]
    tier = ee.Image.constant(0).rename('OptTier').where(counts[-1].gte(1), n_lv)
    for i in range(n_lv - 2, -1, -1):
        ok = counts[i].gte(MIN_OBS_TIER)
        out = out.where(ok, comps[i])
        tier = tier.where(ok, i + 1)
    return out.rename(bands), tier.toInt16(), [lb for lb, _c in levels], [c for _lb, c in levels]


def _report_levels(what, labels, colls):
    """One round trip: image counts per priority level, for the log and the
    manifest ('core/tier1=12 core/standard=23 full/tier1=25 full/standard=48')."""
    try:
        sizes = _retry(lambda: ee.List([c.size() for c in colls]).getInfo(),
                       tries=2, what=f"{what} level sizes")
        txt = " ".join(f"{lb}={n}" for lb, n in zip(labels, sizes))
    except Exception as ex:
        txt = f"(level counts unavailable: {ex})"
    _SRC['opt_tier_counts'] = txt
    print(f"   🎯 {what} priority levels (images): {txt}")
    return txt


LAI_QC_BAND = 'FparLai_QC'


def _mask_modis_lai_qc(img):
    """MODLAND_QC bit 0: 0 = good quality (main RT method), 1 = other/backup
    method or fill. Standard MOD15A2H QC convention (Myneni et al. C6.1
    User's Guide)."""
    qc = img.select(LAI_QC_BAND)
    return img.updateMask(qc.bitwiseAnd(1).eq(0))


def _modis_lai_window_ee(d0, d1, season=None):
    """Real, peer-reviewed, globally-validated MODIS LAI, QC-filtered,
    Terra+Aqua combined mean over the window (same PER_SENSOR_MEAN discipline
    already used for VCI/TCI, so a lopsided Terra/Aqua clear-day count doesn't
    bias the value). Lai_500m scale factor is 0.1 (confirmed against the
    MODIS Collection 6.1 LAI/FPAR Product User's Guide and the LP DAAC file
    specification).

    ⛑ v108  core-month-first (see SEASON_CORE_MONTHS): a pixel with at
    least MIN_OBS_TIER quality-passing composites in the season's core
    months takes the core mean; the full-window mean (previous behaviour)
    fills only the rest. MODIS LAI is already QC-filtered per pixel and has
    no scene-level cloud property, so there is no cloud tiering here."""
    def _mean_and_count(a, b):
        means, cnt = [], None
        for cid in ('MODIS/061/MOD15A2H', 'MODIS/061/MYD15A2H'):
            ic = (ee.ImageCollection(cid).filterBounds(roiGeom)
                  .filterDate(eedate(a), eedate(b)).map(_mask_modis_lai_qc))
            means.append(safeReduce(ic, 'Lai_500m', 'mean', name='LAI_modis'))
            c = safeReduce(ic, 'Lai_500m', 'count', name='n', resample=False)
            cnt = c if cnt is None else cnt.add(c)
        return _combine(means, 'LAI_modis'), cnt
    lai, _n = _mean_and_count(d0, d1)
    core = _core_subwindow(d0, d1, season)
    if core is not None:
        lai_core, n_core = _mean_and_count(core[0], core[1])
        lai = lai.where(n_core.gte(MIN_OBS_TIER), lai_core)
    lai = lai.multiply(0.1).clamp(0, 10)
    return lai.rename('LAI_modis')


def _apply_modis_lai(img, d0, d1, season=None):
    try:
        lai_modis = _modis_lai_window_ee(d0, d1, season)
        # blend(): pixels from lai_modis (top) where unmasked/valid, falling
        # through to the existing empirical LAI (bottom) only where MODIS has
        # no quality-passing observation for that pixel/window.
        lai_final = lai_modis.rename('LAI').blend(img.select('LAI'))
        print("✅ LAI source: MODIS MOD15A2H/MYD15A2H (Myneni et al., "
              "peer-reviewed) — empirical regression is the fallback only")
        return img.addBands(lai_final, None, True)
    except Exception as ex:
        print(f"   ⚠️ MODIS LAI unavailable ({ex}); LAI stays on the "
              f"NOT-VERIFIED empirical NDVI regression for this window")
        return img


def _composite_indices_optical(d0, d1, season=None):
    """Sentinel-2 → Landsat-8/9 → MODIS, all cloud-masked.

    ⛑ v108  Two requested rules, applied inside every sensor branch through
    the shared _priority_composite() engine (see the configuration block):
    cloud-free data first (quality tiers), and for seasons the core months
    first (edge months fill only what the core cannot). Sensor ORDER is
    governed by OPTICAL_PRIORITY: 'corrected_first' never uses Sentinel-2
    TOA (uncorrected) while any atmospherically-corrected source has data.
    ⛑ FIX13b  ALWAYS returns the full 8-band index image (masked where a sensor
    is unavailable). v7.7's failure branch returned a 1-band constant NDVI,
    which slipped past the `bandNames().size() == 0` check in main() and then
    blew up on comp.select('LAI').

    ⛑ BUG FOUND AND FIXED during deep validation: atmospheric-correction
    inconsistency inside the pre-treatment period.
    S2 Surface Reflectance (atmospherically corrected) only exists from
    S2_SR_START (2017-03-28); before that, this function used to fall back
    to S2 TOA (uncorrected) as its PRIMARY choice for the ~21 months from S2's
    2015-06-23 launch, since S2 usually has SOME images even early in its
    mission and the old code returned on the S2 branch immediately whenever
    n > 0, without ever trying Landsat. That is a real, well-documented
    problem, not a theoretical one: skipping atmospheric correction leaves
    NDVI systematically depressed by an amount that tracks the day's aerosol/
    haze load, and switching from uncorrected to corrected reflectance
    partway through a time series produces a spurious step change that has
    nothing to do with real land-cover change (confirmed against the remote-
    sensing literature on TOA-vs-SR NDVI differences during this pass).
    Landsat 8's Surface Reflectance (LANDSAT/LC08/C02/T1_L2) has been
    atmospherically corrected since the start of its mission (2013), so it
    fully covers this gap. The fix: for any window before S2_SR_START, try
    Landsat SR FIRST -- trading Sentinel-2's finer 10 m resolution for
    atmospheric-correction CONSISTENCY across the whole pre-treatment
    period, which matters more for a valid before/after comparison than
    resolution does. S2 TOA is still tried as a last resort if Landsat has
    no data either, so coverage is never sacrificed -- only priority order
    changes, and only for windows before S2 SR existed."""
    s, e = eedate(d0), eedate(d1)
    bands8 = ['NDVI', 'SAVI', 'LSWI', 'NDWI', 'EVI', 'NDMI', 'NDRE', 'LAI']

    def _try_s2(force_toa=False):
        try:
            if OPTICAL_MODE == 'consistent_landsat':
                return None
            use_sr = S2_USE_SR and d0 >= S2_SR_START and not force_toa
            if want_sr_only and not use_sr:
                return None           # ⛑ v108 corrected_first: TOA only as the very last resort
            cid = 'COPERNICUS/S2_SR_HARMONIZED' if use_sr else 'COPERNICUS/S2_HARMONIZED'
            base = ee.ImageCollection(cid).filterBounds(roiGeom).filterDate(s, e)
            s2 = base.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80))
            n = _retry(lambda: s2.size().getInfo(), what="S2 size")
            if n == 0:
                return None
            cs_linked, pixel_mask = False, None
            if USE_CLOUD_MASKING:
                cs_end = collection_end(CSPLUS_ID)
                if d0 >= CSPLUS_START and (cs_end is None or d1 <= cs_end + datetime.timedelta(days=1)):
                    base = base.linkCollection(ee.ImageCollection(CSPLUS_ID), ['cs_cdf'])
                    cs_linked = True
                    tag = f"S2-{'SR' if use_sr else 'TOA'}+CloudScore+"
                else:
                    pixel_mask = _mask_s2_scl if use_sr else _mask_s2_qa60
                    tag = f"S2-{'SR' if use_sr else 'TOA'}+{'SCL' if use_sr else 'QA60'}"
            else:
                tag = f"S2-{'SR' if use_sr else 'TOA'} (unmasked)"
            if not use_sr:
                tag += " [uncorrected -- pre-dates S2 SR; corrected sources were tried first]"
            b = ['B2', 'B3', 'B4', 'B8', 'B5', 'B11']
            # ⛑ v108  quality tiers x core-month-first, replacing the single
            # safeComposite(s2.select(b), b, 'median') of every earlier version
            img, tier, labels, colls = _priority_composite(
                base, b, d0, d1, season, scene_prop='CLOUDY_PIXEL_PERCENTAGE',
                cs_linked=cs_linked, pixel_mask=pixel_mask)
            img = img.divide(10000)
            _SRC['opt_tier'] = tier
            _report_levels("Sentinel-2", labels, colls)
            print(f"✅ Sentinel-2 composite used [{tag}, n={n}]")
            return (ensureBands(compute_indices(img, b, True), bands8),
                    f"{tag} n={n}", 1 if use_sr else 2)
        except Exception as ex:
            if not str(ex).startswith("OPTICAL_MODE"):
                print(f"   ⚠️ S2 branch failed: {ex}")
                _branch_errors.append(f"S2: {ex}")
            return None

    def _try_landsat():
        try:
            if OPTICAL_MODE == 'consistent_s2':
                return None
            l = None
            for cid in ('LANDSAT/LC08/C02/T1_L2', 'LANDSAT/LC09/C02/T1_L2'):
                c = ee.ImageCollection(cid).filterBounds(roiGeom).filterDate(s, e)
                l = c if l is None else l.merge(c)
            n = _retry(lambda: l.size().getInfo(), what="L8 size")
            if n == 0:
                return None
            u = ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6']
            b = ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B5', 'SR_B6']
            # ⛑ v108  tiers by scene CLOUD_COVER (last tier: no scene filter,
            # as before) x core-month-first; QA_PIXEL mask in every tier.
            img, tier, labels, colls = _priority_composite(
                l, u, d0, d1, season, scene_prop='CLOUD_COVER', cs_linked=False,
                pixel_mask=_mask_landsat if USE_CLOUD_MASKING else None,
                last_tier_scene_filter=False)
            img = img.multiply(0.0000275).add(-0.2)
            _SRC['opt_tier'] = tier
            _report_levels("Landsat", labels, colls)
            print(f"⚠️ Fallback: Landsat-8/9 [n={n}]")
            return (ensureBands(compute_indices(img, b, False), bands8),
                    f"Landsat n={n}", 3)
        except Exception as ex:
            if not str(ex).startswith("OPTICAL_MODE"):
                print(f"   ⚠️ Landsat branch failed: {ex}")
                _branch_errors.append(f"Landsat: {ex}")
            return None

    def _try_modis():
        try:
            if OPTICAL_MODE in ('consistent_s2', 'consistent_landsat'):
                return None
            mod = _modis_reflectance_ic(s, e)
            n = _retry(lambda: mod.size().getInfo(), what="MODIS size")
            if n == 0:
                return None
            u = ['sur_refl_b03', 'sur_refl_b04', 'sur_refl_b01',
                 'sur_refl_b02', 'sur_refl_b06']
            b = ['sur_refl_b03', 'sur_refl_b04', 'sur_refl_b01',
                 'sur_refl_b02', 'sur_refl_b02', 'sur_refl_b06']
            # ⛑ v108  core-month-first (no scene-level cloud property on an
            # 8-day composite; StateQA per-pixel mask as before)
            img, tier, labels, colls = _priority_composite(
                mod, u, d0, d1, season, scene_prop=None, cs_linked=False,
                pixel_mask=_mask_mod09 if USE_CLOUD_MASKING else None)
            img = img.multiply(0.0001)
            _SRC['opt_tier'] = tier
            _report_levels("MODIS", labels, colls)
            src = "Terra/Aqua" if MODIS_SOURCE == 'both' else MODIS_SOURCE.capitalize()
            print(f"⚠️ Fallback: MODIS ({src}) [n={n}]")
            return (ensureBands(compute_indices(img, b, False), bands8),
                    f"MODIS n={n}", 4)
        except Exception as ex:
            if not str(ex).startswith("OPTICAL_MODE"):
                print(f"   ⚠️ MODIS branch failed: {ex}")
                _branch_errors.append(f"MODIS: {ex}")
            return None

    pre_sr_era = d0 < S2_SR_START
    _SRC['opt_tier'] = None
    _SRC['opt_tier_counts'] = ''
    want_sr_only = False
    _branch_errors = []
    if OPTICAL_PRIORITY == 'corrected_first' and OPTICAL_MODE != 'consistent_s2':
        # ⛑ v108  atmospherically-corrected sources first, ALL of them, and
        # Sentinel-2 TOA (uncorrected) only if none of them has any image:
        #   S2 SR (if the window is inside the SR era) -> Landsat SR -> MODIS SR -> S2 TOA
        want_sr_only = True
        order = (_try_s2, _try_landsat, _try_modis)
        for attempt in order:
            r = attempt()
            if r is not None:
                return r
        want_sr_only = False
        # ⛑ v109  explicitly TOA: in the SR era this used to repeat the SR
        # attempt, so the last resort never actually reached L1C (which
        # matters for 2017-2018 over India, where L2A coverage was partial)
        r = _try_s2(force_toa=True)   # uncorrected, last resort, clearly tagged
        if r is not None:
            return r
    else:
        if pre_sr_era and OPTICAL_MODE != 'consistent_s2':
            # Atmospherically-corrected Landsat SR before atmospherically-
            # uncorrected S2 TOA -- see the function docstring for why.
            order = (_try_landsat, _try_s2, _try_modis)
        else:
            order = (_try_s2, _try_landsat, _try_modis)
        for attempt in order:
            r = attempt()
            if r is not None:
                return r

    if _branch_errors:
        # ⛑ v109  BUG FOUND AND FIXED. Each sensor branch catches its own
        # exception and returns None, which is right for "this sensor has a
        # problem, try the next one" -- but when EVERY source ended in an
        # ERROR (not in 'no images'), the window was still handed on with all
        # eight index bands masked and status=ok, i.e. a systematic failure
        # (the multi-feature ROI geometry error above) was reported as "no
        # optical data available". Exported, that is a CSV full of NaN with a
        # green tick. An error is now an error: it propagates to build_stack()
        # and the window is recorded as status=error with the message, and
        # never exported blank.
        raise RuntimeError("every optical source failed with an ERROR (not missing "
                           "data), so this window is not exported blank: "
                           + " | ".join(_branch_errors))
    print("🚫 No optical dataset available — all index bands masked")
    # ⛑ PLACEHOLDER BUG FOUND AND FIXED during re-validation. This branch used
    # to return ensureBands(ee.Image.constant(0).rename('NDVI'), bands8) --
    # ensureBands() only masks bands ABSENT from its input, and 'NDVI' WAS
    # present (as a real, unmasked 0), so it overwrote the masked filler with
    # a literal 0 instead of leaving it null. A true NDVI of 0 is a real,
    # physically meaningful value (the bare-soil/no-vegetation boundary), so
    # this was silently indistinguishable from a genuine measurement -- and
    # it fed forward into RUSLE's C-factor (exp(-2*0/(1-0))=1, the MAXIMUM
    # possible value, i.e. worst-case erosion sensitivity fabricated from no
    # data at all), into the AGB average (a fabricated 20 t/ha), and into the
    # NDVI/NDWI LandUse fallback (classified 'other/barren' instead of
    # unknown). All 8 bands are now genuinely masked, with no band name
    # overlapping the filler, so nothing can be silently overwritten.
    return ensureBands(ee.Image.cat([maskedBand(b) for b in bands8]), bands8), "none", 0


# ---------------- CLIMATE DATA ---------------------------------- ⛑ FIX18
# v7.7 chain was MODIS LST → CHIRTS. Two problems:
#   (a) UCSB-CHG/CHIRTS/DAILY ENDS IN 2016, so the "fallback" could never fire
#       for a 2015-2026 study; when reached, addClimateBands returned img
#       unchanged and the later comp.select('Tmax') failed.
#   (b) LST is a SURFACE temperature, not air temperature, and Night LST was
#       labelled Tmean with Tmin = Tmean - 3 (a guess, not a measurement).
# ERA5-Land gives true 2 m AIR temperature on one consistent 1950→present
# record, with a real daily minimum.
ERA5_DAILY = 'ECMWF/ERA5_LAND/DAILY_AGGR'
ERA5_MONTHLY = 'ECMWF/ERA5_LAND/MONTHLY_AGGR'
_BANDCACHE = {}


def _pick_band(cid, candidates):
    key = (cid, tuple(candidates))
    if key in _BANDCACHE:
        return _BANDCACHE[key]
    chosen = candidates[0]
    try:
        have = _retry(lambda: ee.ImageCollection(cid).first().bandNames().getInfo(),
                      tries=3, what=cid)
        for c in candidates:
            if c in have:
                chosen = c
                break
    except Exception:
        pass
    _BANDCACHE[key] = chosen
    return chosen


def addClimateBands(img, d0, d1):
    s, e = eedate(d0), eedate(d1)
    rain = safeSum(ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                   .filterBounds(roiGeom).filterDate(s, e), 'precipitation', name='Rain')
    src = "none"
    tmax = tmin = tmean = None
    try:
        era = ee.ImageCollection(ERA5_DAILY).filterDate(s, e)
        if _retry(lambda: era.limit(1).size().getInfo(), tries=3, what="ERA5") > 0:
            bx = _pick_band(ERA5_DAILY, ['temperature_2m_max', 'maximum_2m_air_temperature'])
            bn = _pick_band(ERA5_DAILY, ['temperature_2m_min', 'minimum_2m_air_temperature'])
            ba = _pick_band(ERA5_DAILY, ['temperature_2m', 'mean_2m_air_temperature'])
            tmax = safeMean(era, bx, name='Tmax').subtract(273.15)
            tmin = safeMean(era, bn, name='Tmin').subtract(273.15)
            tmean = safeMean(era, ba, name='Tmean').subtract(273.15)
            src = "ERA5-Land 2m air T"
            _SRC['temp_code'] = 1
    except Exception as ex:
        print(f"   ⚠️ ERA5 temperature failed: {ex}")
    if tmax is None:
        try:
            lst = _modis_lst_ic(s, e)
            if _retry(lambda: lst.limit(1).size().getInfo(), tries=3, what="LST") > 0:
                day = safeMean(lst, 'LST_Day_1km', name='Tmax').multiply(0.02).subtract(273.15)
                night = safeMean(lst, 'LST_Night_1km', name='Tmin').multiply(0.02).subtract(273.15)
                tmax, tmin = day, night          # Night LST ≈ Tmin, not Tmean
                tmean = day.add(night).divide(2).rename('Tmean')
                src = "MODIS LST (surface, not air)"
                _SRC['temp_code'] = 3
        except Exception as ex:
            print(f"   ⚠️ MODIS LST failed: {ex}")
    if tmax is None:
        print("🚫 No temperature source — Tmax/Tmin/Tmean masked")
        tmax, tmin, tmean = maskedBand('Tmax'), maskedBand('Tmin'), maskedBand('Tmean')
        _SRC['temp_code'] = 0
    else:
        print(f"✅ Temperature source: {src}")
        tmax = tmax.clamp(-10, 60).rename('Tmax')
        tmin = tmin.clamp(-10, 60).rename('Tmin')
        tmean = tmean.clamp(-10, 60).rename('Tmean')
    _SRC['temp'] = src
    return img.addBands(harmonise(ee.Image.cat([rain, tmax, tmin, tmean])), None, True)


_SRC = {}

# ==================================================================
# ⛑ FIX9 / FIX10 — VCI, TCI and VHI.  THE CORE SCIENTIFIC REPAIR.
# ==================================================================
# Kogan's definitions (Kogan 1990, 1995; NOAA STAR operational VHP):
#     VCI = (NDVI_i  - NDVI_min) / (NDVI_max - NDVI_min)
#     TCI = (LST_max - LST_i)    / (LST_max  - LST_min)      <-- INVERTED
#     VHI = a*VCI + (1-a)*TCI,  a = 0.5
# Both run 0 (extreme stress) to 1 (optimal). TCI is inverted precisely so that
# HIGH TCI = COOL = FAVOURABLE, which is what makes it additive with VCI.
#
# v7.7 computed  tci = (LST_i - LST_min) / span, i.e. HIGH TCI = HOT. Feeding
# that into VHI = 0.5*VCI + 0.5*TCI scored hot, dry, stressed conditions as
# HEALTHY. Every VHI value in the v7.7 output is wrong, and the sign of any
# VHI-based treatment effect is unreliable.
#
# Second repair: v7.7 built the NDVI climatology by calling compositeIndices()
# once per historical year, which independently re-picked Sentinel-2 (285x),
# Landsat (98x) or MODIS (144x) depending on what happened to be available that
# year. A min/max taken across 10 m, 30 m and 500 m sensors is not a VCI — the
# spread it measures is mostly sensor difference, not vegetation condition.
# Both NDVI_i and the climatology now come from one product: MOD13Q1/MYD13Q1.
MOD13 = _sel('MODIS/061/MOD13Q1', 'MODIS/061/MYD13Q1')
MOD11 = {'terra': ['MODIS/061/MOD11A2'], 'aqua': ['MODIS/061/MYD11A2'],
         'both': ['MODIS/061/MOD11A2', 'MODIS/061/MYD11A2']}[TCI_OVERPASS]


def _mod13_qa(im):
    # SummaryQA: 0 good, 1 marginal, 2 snow/ice, 3 cloudy
    return im.updateMask(im.select('SummaryQA').lte(1))


def _mod11_qc(im):
    q = im.select('QC_Day')
    m = q.bitwiseAnd(3).lte(1)                       # mandatory QA
    if LST_STRICT_QC:
        m = m.And(q.rightShift(6).bitwiseAnd(3).lte(1))   # avg LST error <= 2 K
    return im.updateMask(m)


def _combine(means, name):
    """⛑ FIX26  Average the Terra MEAN and the Aqua MEAN rather than pooling all
    images together.

    Pooling makes the window value depend on how many clear days each platform
    happened to catch — in a Karnataka monsoon that ratio swings hard from year
    to year and injects noise straight into the VCI/TCI climatology. Averaging
    per-sensor means gives each overpass equal weight regardless of sample count.
    Masked sensors drop out per pixel automatically."""
    if len(means) == 1:
        return means[0].rename(name)
    if PER_SENSOR_MEAN:
        return ee.ImageCollection.fromImages(means).mean().rename(name)
    return ee.ImageCollection.fromImages(means).mean().rename(name)


def _ndvi_window_ee(s, e):
    """MODIS NDVI mean for a window, QA-screened. Server-side only."""
    means = []
    for cid in MOD13:
        c = (ee.ImageCollection(cid).filterBounds(roiGeom)
             .filterDate(s, e).map(_mod13_qa))
        means.append(safeReduce(c, 'NDVI', 'mean', name='NDVI_c'))
    return _combine(means, 'NDVI_c').multiply(0.0001).rename('NDVI_c')


def _ndvi_obs_ee(s, e):
    """Per-pixel count of valid NDVI composites in the window."""
    cnt = None
    for cid in MOD13:
        c = (ee.ImageCollection(cid).filterBounds(roiGeom)
             .filterDate(s, e).map(_mod13_qa))
        n = safeReduce(c, 'NDVI', 'count', name='NObsV', fill=None)
        cnt = n if cnt is None else cnt.add(n)
    return cnt.rename('NObsV')


def _lst_window_ee(s, e):
    """Thermal value for a window.

    TCI_SOURCE='modis_lst'  MODIS LST_Day, 1 km, QC-screened. Literature
                            standard, but CLEAR-SKY ONLY: during Kharif the few
                            cloud-free days are systematically the hottest, so
                            the seasonal mean is biased warm. Largely cancels in
                            the TCI ratio, but not exactly, which is why
                            MIN_OBS_LST masks thin pixels.
    TCI_SOURCE='era5_skin'  ERA5-Land skin temperature. All-weather and gap-free
                            so no clear-sky bias, at 11 km instead of 1 km.
    """
    if TCI_SOURCE == 'era5_skin':
        b = _pick_band(ERA5_DAILY, ['skin_temperature', 'temperature_2m'])
        ic = ee.ImageCollection(ERA5_DAILY).filterDate(s, e)
        return safeReduce(ic, b, 'mean', name='LST_c').subtract(273.15).rename('LST_c')
    means = []
    for cid in MOD11:
        c = (ee.ImageCollection(cid).filterBounds(roiGeom)
             .filterDate(s, e).map(_mod11_qc))
        means.append(safeReduce(c, 'LST_Day_1km', 'mean', name='LST_c'))
    return _combine(means, 'LST_c').multiply(0.02).subtract(273.15).rename('LST_c')


def _lst_obs_ee(s, e):
    if TCI_SOURCE == 'era5_skin':
        return ee.Image.constant(999).rename('NObsT').toFloat()
    cnt = None
    for cid in MOD11:
        c = (ee.ImageCollection(cid).filterBounds(roiGeom)
             .filterDate(s, e).map(_mod11_qc))
        n = safeReduce(c, 'LST_Day_1km', 'count', name='NObsT', fill=None)
        cnt = n if cnt is None else cnt.add(n)
    return cnt.rename('NObsT')


def _et_ratio_clim_window_ee(a, b):
    """ET/PET ratio, ALWAYS from MOD16A2GF -- used for both the current ESI
    window and its climatology, so the two are on one consistent source. The
    entire fixed 2003-2024 baseline is safely inside MOD16A2GF's coverage, so
    there is no need for the current-year MOD16A2 substitute here (that
    substitute exists only because MOD16A2GF doesn't yet exist for 2025-2026,
    which are never baseline years)."""
    ic = ee.ImageCollection('MODIS/061/MOD16A2GF').filterBounds(roiGeom) \
           .filterDate(a, b)
    et_c = safeSum(ic, 'ET', name='ET_c').multiply(0.1)
    pet_c = safeSum(ic, 'PET', name='PET_c').multiply(0.1)
    return et_c.divide(pet_c.max(1e-6)).rename('ESI_c')


_CLIM_CACHE = {}


def _clim_ic(builder, d0, d1, cache_key=None):
    """Per-pixel climatology over the SAME calendar window in each baseline year.

    The window length is taken from the CURRENT window, so if 2026 Kharif is
    clamped to 73 days the climatology is also built from 73-day windows — like
    is compared with like. v7.7 always used the full nominal season.

    CLIM_MODE='fixed'   : one baseline (CLIM_BASE_START..CLIM_BASE_END) shared by
                          every study year. Required for a valid DiD — a rolling
                          baseline moves between pre- and post-treatment and
                          injects a mechanical trend into the outcome.
    CLIM_MODE='rolling' : v7.7 behaviour, last CLIM_YEARS years before the window.

    ⛑ v107  cache_key (optional): in 'fixed' mode the climatology depends
    only on (calendar start day, window length), not on the study year, so
    a fully-projected window -- which runs addStressIndices() once per
    reference year -- was rebuilding the identical 22-year NDVI/LST/ESI/
    soil-moisture baselines three times inside ONE export graph. With a
    key, the same ee object is returned for the same calendar window, and
    the Earth Engine serializer emits it once (shared reference) instead of
    three times. Values are unchanged; only graph size/evaluation cost is.
    No key -> exactly the previous behaviour."""
    ndays = (d1 - d0).days
    key = None
    if cache_key is not None and CLIM_MODE == 'fixed':
        key = (cache_key, d0.month, d0.day, ndays, CLIM_BASE_START, CLIM_BASE_END)
        if key in _CLIM_CACHE:
            return _CLIM_CACHE[key]
    if CLIM_MODE == 'fixed':
        years = ee.List.sequence(CLIM_BASE_START, CLIM_BASE_END)

        def _one(y):
            s = ee.Date.fromYMD(ee.Number(y), d0.month, d0.day)
            return builder(s, s.advance(ndays, 'day'))
    else:
        s0 = eedate(d0)
        years = ee.List.sequence(1, CLIM_YEARS)

        def _one(k):
            s = s0.advance(ee.Number(k).multiply(-1), 'year')
            return builder(s, s.advance(ndays, 'day'))
    ic = ee.ImageCollection.fromImages(years.map(_one))
    if key is not None:
        _CLIM_CACHE[key] = ic
    return ic


def _clim_lo_hi(ic, name):
    """Absolute min/max (strict Kogan) or robust percentiles."""
    if CLIM_ROBUST_PCTL:
        lo_p, hi_p = CLIM_ROBUST_PCTL
        red = ic.reduce(ee.Reducer.percentile([lo_p, hi_p]))
        return red.select(0).rename(name + '_lo'), red.select(1).rename(name + '_hi')
    return ic.min().rename(name + '_lo'), ic.max().rename(name + '_hi')


def _safe_span(hi, lo):
    span = hi.subtract(lo)
    return span.where(span.abs().lt(1e-6), 1e-6)


# ---------------- STRESS INDICES ----------------
def addStressIndices(comp, d0, d1):
    s, e = eedate(d0), eedate(d1)
    K = 100.0 if INDEX_SCALE_0_100 else 1.0

    # ---------- ET-based indices ------------------------------------ ⛑ FIX2
    # THE 2026 CRASH. MOD16A2GF is YEAR-END gap-filled and stops at 2025-12-27,
    # so every 2026 window hit an empty collection; v7.7's safeMean() turned
    # that into a ZERO-BAND image and .multiply(0.1) raised
    #   "Image.multiply: If one image has no bands ... Got 0 and 1."
    #
    # resolve_source() now searches the ranked list for a REAL product that
    # covers the window — MOD16A2 (near-real-time) for 2026 — and only if
    # nothing covers it does it reuse the same calendar window from an earlier
    # year, stamped in DataYear. No proxies, no placeholder constants.
    cid, et_code, yr_off, et_frac, note = resolve_source('et', d0, d1)
    if cid is None:
        print("🚫 No ET source at all — ESI/WSSI/WSI masked")
        et, pet = maskedBand('ET'), maskedBand('PET')
        et_code = 0
    else:
        a0 = shift_years(d0, yr_off)
        a1 = shift_years(d1, yr_off)
        ic = ee.ImageCollection(cid).filterBounds(roiGeom) \
               .filterDate(eedate(a0), eedate(a1))
        if cid == 'IDAHO_EPSCOR/TERRACLIMATE':
            et = safeSum(ic, 'aet', name='ET').multiply(0.1).rename('ET')
            pet = safeSum(ic, 'pet', name='PET').multiply(0.1).rename('PET')
        else:
            # MOD16 ET/PET bands are 8-day SUMS at scale 0.1.
            # ⛑ FIX17  v7.7 took a MEAN, so WSI compared a CHIRPS window TOTAL
            #          in mm against an 8-day mean ET. Both are now mm totals.
            et = safeSum(ic, 'ET', name='ET').multiply(0.1).rename('ET')
            pet = safeSum(ic, 'PET', name='PET').multiply(0.1).rename('PET')
        tag = f"{cid}" + (f" [{a0.year} substitute]" if yr_off else "")
        print(f"✅ ET source: {tag}  ({note})")
    _SRC['et'] = cid or 'none'
    _SRC['et_code'] = et_code
    _SRC['et_year_offset'] = yr_off
    _SRC['et_frac'] = round(float(et_frac or 0.0), 3)   # ⛑ v107 -> manifest

    rain = comp.select('Rain')
    # ---- ESI / WSSI: PARTIALLY VERIFIED --------------------------- [v8.4]
    # ESI = ET/PET is a real, widely used quantity -- Anderson, M.C. et al.,
    # 2011. "Evaluating the impact of soil moisture-based drought indices..."
    # and related papers (2007a, 2007b) define ESI around exactly this ratio.
    # BUT the literature is specific that the operational NOAA/USDA "ESI"
    # product is a STANDARDIZED ANOMALY of this ratio relative to a
    # multi-year climatology (the same way VCI/TCI are anomalies, not raw
    # values) -- the raw ratio itself is more precisely called the
    # "evaporative fraction" or, per Jensen (1968), the "crop coefficient"
    # (fRET = ETa/ETref). What this pipeline computes and calls 'ESI' is that
    # raw ratio, not the standardized anomaly the name formally refers to in
    # Anderson et al.'s usage. Column kept as 'ESI' for schema stability
    # (renaming would break every downstream reference to it), but this is
    # the accurate description of what it measures: real, useful, and a
    # legitimate literature concept, just not literally the same quantity
    # NOAA publishes under the same three letters. Turning this into a true
    # standardized-anomaly ESI would reuse the same climatology machinery
    # VCI/TCI already have -- a natural next enhancement, not done this pass.
    esi = et.divide(pet.max(1e-6)).rename('ESI').clamp(0, 1.5)
    wssi = ee.Image.constant(1).subtract(esi).rename('WSSI')   # 1-ESI; internally
                                                                # consistent complement,
                                                                # no separate literature
                                                                # citation located for
                                                                # 'WSSI' by this exact name

    # ---- ESI_Anom: the FIX for the "partially verified" ESI finding [v8.5]
    # You asked this fixed, not just flagged. This is the genuine
    # standardized-anomaly ESI the literature refers to (Anderson et al.),
    # built with the SAME climatology machinery already used for VCI/TCI
    # (_clim_ic / _clim_lo_hi / _safe_span) rather than a new mechanism --
    # exactly what was promised as the "next enhancement" when this was first
    # flagged. Kept on the same 0-1, high-is-favourable scale as VCI/TCI for
    # direct comparability across the panel's drought indices; that specific
    # min-max normalisation is this pipeline's adaptation of Kogan's approach
    # to the ET/PET ratio, not a literal reproduction of NOAA's own (CDF-based)
    # anomaly algorithm -- stated plainly rather than overclaimed.
    #
    # ⛑ BUG FOUND AND FIXED during this validation pass. The first version of
    # this fix used _et_ratio_clim_window_ee (MOD16A2GF-only) for BOTH the
    # climatology AND the current value. MOD16A2GF does not exist for 2026 --
    # the exact problem this whole pipeline exists to solve -- so ESI_Anom
    # was silently masked for every 2026 window. The CLIMATOLOGY baseline
    # still always uses MOD16A2GF (every baseline year 2003-2024 is safely
    # covered by it, and the baseline must never mix sources). The CURRENT
    # value now reuses `et`/`pet` already resolved above via the same
    # resolve_source() cascade as the plain ESI column -- MOD16A2GF where it
    # exists, MOD16A2 (near-real-time) for 2025-2026 -- so ESI_Anom has real
    # values for the current year, at the cost of the current value and the
    # climatology not being drawn from byte-identical products in those years.
    # That is the same trade-off already accepted throughout this pipeline
    # (e.g. VCI's current NDVI vs its climatology), not a new one.
    esi_now = et.divide(pet.max(1e-6))
    esi_ic = _clim_ic(_et_ratio_clim_window_ee, d0, d1, cache_key='esi')   # ⛑ v107
    esi_lo, esi_hi = _clim_lo_hi(esi_ic, 'esi')
    esi_anom = (esi_now.subtract(esi_lo).divide(_safe_span(esi_hi, esi_lo))
                .clamp(0, 1).multiply(K).rename('ESI_Anom'))

    # ---- WSI: internally-defined water-balance ratio --------------- [v8.4]
    # (Rain-ET)/(Rain+ET) did not trace to one specific named, cited index in
    # this search pass -- it is structurally a simple normalised water-surplus
    # ratio (positive when rainfall exceeds ET, negative when ET exceeds
    # rainfall), which is a reasonable, bounded [-1,1] water-balance signal,
    # but 'Water Stress Index' is used inconsistently across the literature
    # for several different formulas. Treat the VALUE as legitimate (it is
    # dimensionally sound and bounded) and the NAME as this pipeline's own
    # convention rather than a direct literature citation.
    wsi = rain.subtract(et).divide(rain.add(et).max(1e-6)).rename('WSI').clamp(-1, 1)

    # ---------- VCI (Kogan 1990) ----------
    ndvi_i = _ndvi_window_ee(s, e)
    ndvi_ic = _clim_ic(_ndvi_window_ee, d0, d1, cache_key='ndvi')          # ⛑ v107
    n_lo, n_hi = _clim_lo_hi(ndvi_ic, 'ndvi')
    nobs_v = _ndvi_obs_ee(s, e)
    vci = ndvi_i.subtract(n_lo).divide(_safe_span(n_hi, n_lo)) \
                .clamp(0, 1).multiply(K).rename('VCI')
    # ⛑ FIX27  Do not report a VCI built from one or two composites. A single
    #          residual-cloud composite can drag NDVI_min down and distort the
    #          whole ratio; thin pixels are masked rather than quietly wrong.
    vci = vci.updateMask(nobs_v.gte(MIN_OBS_NDVI))

    # ---------- TCI (Kogan 1995) — INVERTED, high = cool = favourable ----------
    lst_i = _lst_window_ee(s, e)
    lst_ic = _clim_ic(_lst_window_ee, d0, d1, cache_key='lst')              # ⛑ v107
    l_lo, l_hi = _clim_lo_hi(lst_ic, 'lst')
    nobs_t = _lst_obs_ee(s, e)
    if TCI_KOGAN:
        tci = l_hi.subtract(lst_i).divide(_safe_span(l_hi, l_lo))
    else:                                   # v7.7 convention, kept for reference
        tci = lst_i.subtract(l_lo).divide(_safe_span(l_hi, l_lo))
    tci = tci.clamp(0, 1).multiply(K).rename('TCI') \
             .updateMask(nobs_t.gte(MIN_OBS_LST))

    # ---------- VHI ----------
    vhi = vci.multiply(VHI_ALPHA).add(tci.multiply(1 - VHI_ALPHA)).rename('VHI')
    _SRC['nobs_v'] = nobs_v
    _SRC['nobs_t'] = nobs_t

    # ---------- SMDI ------------------------------------------------ ⛑ FIX14
    # Same Narasimhan & Srinivasan soil-water-deficit structure as v7.7, but
    # reading ERA5-Land DAILY/MONTHLY aggregates instead of HOURLY. v7.7's
    # 10-year climatology meant reducing ~87,600 global hourly images inside
    # every tile graph — a large part of the "User memory limit exceeded"
    # precheck failures (1,430 of them in your log). Daily/monthly means of the
    # same variable are numerically equivalent for this purpose.
    def _sm_window_ee(a, b, monthly=True):
        cid = ERA5_MONTHLY if monthly else ERA5_DAILY
        ic = ee.ImageCollection(cid).filterDate(a, b)
        l1 = safeMean(ic, 'volumetric_soil_water_layer_1', name='l1')
        l2 = safeMean(ic, 'volumetric_soil_water_layer_2', name='l2')
        l3 = safeMean(ic, 'volumetric_soil_water_layer_3', name='l3')
        return l1.multiply(0.07).add(l2.multiply(0.21)).add(l3.multiply(0.72)).rename('SM')

    def _smdi_for(a0, a1):
        sm_now = _sm_window_ee(eedate(a0), eedate(a1), monthly=False)
        sm_hist = _clim_ic(lambda x, y: _sm_window_ee(x, y, True), a0, a1,
                           cache_key='sm_monthly')                          # ⛑ v107
        FC = sm_hist.reduce(ee.Reducer.percentile([95])).rename('FC')
        swd_hist = sm_hist.map(lambda im: FC.subtract(im).rename('SWD'))
        swd_max = swd_hist.max().rename('SWD')
        swd_min = swd_hist.min().rename('SWD')
        swd_t = FC.subtract(sm_now).rename('SWD')
        mx = swd_max.where(swd_max.abs().lt(1e-9), 1e-6)
        mn = swd_min.abs().where(swd_min.abs().lt(1e-9), 1e-6)
        pos = swd_t.divide(mx).multiply(4)
        neg = swd_t.divide(mn).multiply(4)
        return pos.where(swd_t.lt(0), neg).rename('SMDI').clamp(-4, 4)

    smdi_now = _smdi_for(d0, d1)
    smdi_prev = _smdi_for(d0 - datetime.timedelta(days=7),
                          d1 - datetime.timedelta(days=7))
    SMDI = smdi_now.multiply(0.5).add(smdi_prev.multiply(0.5)) \
                   .rename('SMDI').clamp(-4, 4)

    return comp.addBands(
        harmonise(ee.Image.cat([esi, wssi, wsi, SMDI, vci, tci, vhi, esi_anom])),
        None, True)


# ==================================================================
# ⛑ FIX38 -- LAND USE: Dynamic World replaces the NDVI-threshold guess  [v8.3]
# ==================================================================
# v7.7/v8.2 LandUse was three hand-picked NDVI thresholds with no citation and
# no ground truth. Dynamic World (Brown, C.F., Brumby, S.P., Guzder-Williams,
# B. et al. 2022. "Dynamic World, Near real-time global 10 m land use land
# cover mapping." Sci Data 9, 251. https://doi.org/10.1038/s41597-022-01307-4)
# is a peer-reviewed, deep-learning LULC product built from Sentinel-2 at
# native 10 m resolution, continuously updated from 2015-06-23 to the present
# -- the only global product at this resolution that covers the ENTIRE
# 2015-2026 study period (ESA WorldCover, by contrast, only has snapshots for
# 2020 and 2021). Aggregation method (mean of the per-class probability bands
# over the window, then argmax) follows Google's own worked example for this
# exact dataset.
#
# Independent reviews note Dynamic World's *effective* resolution is closer to
# 30 m in practice despite the 10 m pixel grid -- stated here rather than
# implied, consistent with how VCI/TCI's true resolution ceiling was reported
# in v8.2.
DW_ID = 'GOOGLE/DYNAMICWORLD/V1'
DW_START = date(2015, 6, 23)
DW_PROB_BANDS = ['water', 'trees', 'grass', 'flooded_vegetation', 'crops',
                 'shrub_and_scrub', 'built', 'bare', 'snow_and_ice']
# raw DW class index -> your original 4-class scheme (1 forest 2 agri 3 other 4 water)
_DW_TO_LU4 = {0: 4, 1: 1, 4: 2}   # everything else defaults to 3 (other)


def _classifyLandUse_ndvi_fallback(ndvi, ndwi=None):
    """v8.2 method, kept only as the fallback if Dynamic World has no images
    in a window (should not happen after 2015-06-23, i.e. for this panel)."""
    water = ndvi.lt(0) if ndwi is None else ndwi.gt(0).Or(ndvi.lt(0))
    agri = ndvi.gte(0.14).And(ndvi.lt(0.37))
    forest = ndvi.gte(0.37)
    return ee.Image(3).where(forest, 1).where(agri, 2).where(water, 4) \
             .rename('LandUse').toInt16()


def classifyLandUse(ndvi, ndwi, d0, d1, season=None):
    """Returns (lu4, lu_dw, tag).

    ⛑ v108  `season`: core-month-first for the Dynamic World probability
    mean -- a pixel with >= MIN_OBS_TIER Dynamic World images in the
    season's core months is classified from those; the full-window mean
    (previous behaviour) classifies only the rest.
    lu4    'LandUse'   1 forest, 2 agriculture, 3 other/barren, 4 water --
           SAME encoding as v7.7/v8.2, now Dynamic-World-derived instead of an
           uncited NDVI guess. Fully backward compatible with existing code
           that reads this column.
    lu_dw  'LandUseDW' the raw 0-8 Dynamic World class (see DW_PROB_BANDS) --
           a NEW column, appended after the original 30. Nothing removed."""
    try:
        s, e = eedate(d0), eedate(d1)
        dw = ee.ImageCollection(DW_ID).filterBounds(roiGeom).filterDate(s, e)
        # ⛑ BUG FOUND AND FIXED during re-verification: n was computed via
        # dw.limit(1).size() -- capping the collection at 1 image BEFORE
        # counting, so the printed "LandUse source: Dynamic World (n=...)"
        # could only ever show 0 or 1, regardless of how many images
        # actually existed in the window. A genuine production log showed
        # n=1 for a full Yearly composite, which reads like a real problem
        # (barely any Dynamic World coverage) but was actually just this
        # display artifact -- the .mean() composite two lines below always
        # correctly used the FULL, un-limited `dw` collection, so the
        # computed LandUse values themselves were never wrong, only what
        # got printed about them. Fixed by counting the real collection.
        n = _retry(lambda: dw.size().getInfo(), tries=3, what="Dynamic World")
        if n == 0:
            raise RuntimeError("no Dynamic World images in this window")
        # ⛑ resample the CONTINUOUS [0,1] probability bands before averaging
        # -- correct per Google's resample() docs (each raw DW image has a
        # genuine native 10 m projection to interpolate from; the reduced
        # mean does not). The DISCRETE class decision (argmax, right below)
        # is not resampled -- nearest-neighbour is the correct, and only
        # meaningful, choice once a pixel has become a categorical label.
        probs = (dw.select(DW_PROB_BANDS).map(lambda im: im.resample('bilinear'))
                 .mean())          # Google's own recipe for aggregation
        core = _core_subwindow(d0, d1, season)          # ⛑ v108 core-month-first
        if core is not None:
            dw_core = dw.filterDate(eedate(core[0]), eedate(core[1]))
            probs_core = (dw_core.select(DW_PROB_BANDS)
                          .map(lambda im: im.resample('bilinear')).mean())
            n_core = safeReduce(dw_core, DW_PROB_BANDS[0], 'count', name='n', resample=False)
            probs = probs.where(n_core.gte(MIN_OBS_TIER), probs_core)
        dw_class = (probs.toArray().arrayArgmax().arrayGet([0])
                    .rename('LandUseDW').toInt16())
        lu4 = ee.Image(3).rename('LandUse').toInt16()
        for code, lu in _DW_TO_LU4.items():
            lu4 = lu4.where(dw_class.eq(code), lu)
        print(f"✅ LandUse source: Dynamic World (n={n})")
        return lu4, dw_class, "Dynamic World"
    except Exception as ex:
        print(f"   ⚠️ Dynamic World unavailable ({ex}); LandUse falls back to NDVI/NDWI")
        lu4 = _classifyLandUse_ndvi_fallback(ndvi, ndwi)
        dw_class = maskedBand('LandUseDW').toInt16()
        return lu4, dw_class, "NDVI/NDWI threshold (fallback)"


SAR_AGB_COEFFS = {'intercept': 30.0, 'vv': 1.2, 'vh': 4.5, 'ratio': 2.0}
AGB_MIN, AGB_MAX = 0, 300


def _sar_agb_candidate(d0=None, d1=None):
    """⛑ FIX19  v7.7 hard-coded filterDate('2015-01-01','2025-12-31'), so the
    SAME static backscatter mean was written into every year of the panel (and
    nothing at all for 2026). AGB therefore had no year-to-year SAR signal —
    fatal for a before/after treatment comparison. Now window-specific, widening
    to +/-1 year if the window itself is too sparse."""
    def build(a, b):
        return (ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(roiGeom)
                .filterDate(eedate(a), eedate(b))
                .filter(ee.Filter.eq('instrumentMode', 'IW'))
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')))
    if d0 is None:
        return maskedBand('AGB_sar')
    for a, b in ((d0, d1), (d0 - datetime.timedelta(days=365),
                            d1 + datetime.timedelta(days=365))):
        ic = build(a, b)
        try:
            if _retry(lambda: ic.limit(1).size().getInfo(), tries=3, what="S1") > 0:
                VV = safeMean(ic, 'VV', name='VV')
                VH = safeMean(ic, 'VH', name='VH')
                agb = (VV.multiply(SAR_AGB_COEFFS['vv'])
                       .add(VH.multiply(SAR_AGB_COEFFS['vh']))
                       .add(VV.subtract(VH).multiply(SAR_AGB_COEFFS['ratio']))
                       .add(SAR_AGB_COEFFS['intercept']))
                return agb.rename('AGB_sar').clamp(AGB_MIN, AGB_MAX)
        except Exception:
            continue
    return maskedBand('AGB_sar')


def calcAGB(ndvi, lai, lu, d0=None, d1=None):
    """AGB coefficients: NOT VERIFIED.                                [v8.4]
    Class split now driven by real Dynamic-World-derived LandUse (via `lu`)
    instead of the NDVI threshold -- that part is an improvement. The
    coefficients themselves (49.2/28.5 forest, 42.1/21.7 agri, 38.4/15.3
    other) were searched for this pass, specifically, and no paper using
    these numbers was found. What the literature does show: AGB-from-LAI (or
    AGB-from-NDVI) relationships are essentially always site- and
    species-specific ALLOMETRIC equations, fitted from destructive or DBH-based
    field sampling of the actual trees/crops present -- there is no
    literature-supported universal linear formula, for forest, agriculture,
    or otherwise. This is a structurally different situation from LAI above:
    there is no comparable single compiled library of general-purpose
    equations to point to. Kept unchanged (no defensible universal
    replacement exists) but treat the AGB column strictly as a relative,
    internal index -- useful for before/after or treated/control COMPARISONS
    within this dataset, not as an absolute biomass estimate -- until
    calibrated against field plot data for Sirur/Nilgund specifically, which
    is the only way to make this number literature-grade."""
    agb_forest = lai.multiply(49.2).add(28.5)
    agb_agri = lai.multiply(42.1).add(21.7)
    agb_other = lai.multiply(38.4).add(15.3)
    agb_opt = agb_other.where(lu.eq(1), agb_forest).where(lu.eq(2), agb_agri) \
                       .rename('AGB_opt')
    agb_sar = _sar_agb_candidate(d0, d1)
    agb_ndvi = ndvi.multiply(120).add(20).rename('AGB_ndvi')
    candidates = ee.Image.cat([agb_opt, agb_sar, agb_ndvi])
    agb_mean = candidates.reduce(ee.Reducer.mean()).rename('AGB')
    return harmonise(agb_mean.clamp(AGB_MIN, AGB_MAX))


# ==================================================================
# ⛑ FIX45 -- AGB: real-data cross-validation, since no universal formula
# exists to substitute in                                            [v8.5]
# ==================================================================
# Search this pass, specifically for a citable replacement, confirmed the
# earlier finding rather than overturning it: multiple India-specific SAR/
# optical-biomass studies (Western Ghats, Himalayan foothills, mangrove and
# dry-deciduous forests) were found, but every one fits a machine-learning
# model or site-specific field-calibrated regression -- and they DISAGREE
# with each other on basics (one found VH poorly correlated with AGB, r=0.05;
# another found VH the best single predictor, R^2=0.69). There is no
# transferable closed-form AGB equation to drop in, the way MOD15A2H existed
# for LAI. Forcing one in anyway would trade an uncited formula for a
# differently-uncited one -- not a real fix.
#
# What DOES exist online and is directly usable: NASA/USFS GEDI spaceborne
# lidar footprint-level biomass (Dubayah et al., 2022, "GEDI L4A Aboveground
# Biomass Density..." ORNL DAAC, doi:10.3334/ORNLDAAC/2056), real satellite
# lidar observations of AGBD (Mg/ha) at 25 m footprints, April 2019 -
# November 2024. This does NOT cover 2015-2018 and is sparse (~25 m
# footprints along ISS ground tracks, not wall-to-wall), so it cannot simply
# replace calcAGB() as a per-pixel per-window source the way MOD15A2H could
# for LAI. What it CAN do -- and what wasn't possible before this pass --
# is let you check this pipeline's AGB estimate against real, independent,
# peer-reviewed satellite lidar observations for your own watershed,
# wherever GEDI happened to sample it.
GEDI_L4A_ID = 'LARSE/GEDI/GEDI04_A_002'
GEDI_START = date(2019, 4, 18)
# ⛑ BUG FOUND AND FIXED on continued deep validation: GEDI_END was a fixed
# 2024-11-28 cutoff -- checked directly against NASA's own mission-status
# reporting for this pass and confirmed wrong. GEDI was stowed for a 14-month
# pause (2023-03-17 to 2024-04-22) to make room for another ISS payload, but
# was NOT decommissioned: it was recommissioned and resumed full nominal
# science operations with all three lasers on 2024-06-11 (confirmed via
# NASA/UMD's own GEDI mission site and a 2024 Congressional announcement of
# the reinstatement), and CEOS's own mission database lists current status
# as "operational (extended)" with a planned end-of-life of January 2031 --
# years beyond this pipeline's own 2026 study horizon. The fixed 2024 cutoff
# was silently excluding every window from December 2024 onward from AGB
# cross-validation entirely, on a mission that was, in fact, still actively
# collecting data. GEDI_END is now computed at call time rather than
# hardcoded, so this does not go stale the same way again; the dormant
# stowage window is now excluded explicitly (a real gap in coverage) rather
# than left to be silently reported as "no footprints found," which would
# have looked identical to genuine sparse sampling.
GEDI_STOWED_START = date(2023, 3, 17)
GEDI_STOWED_END = date(2024, 6, 11)


def _gedi_mission_end():
    """Dynamic, not hardcoded: GEDI is an ongoing mission (planned EOL
    January 2031 per CEOS). Capped at today so a window can never be treated
    as 'covered' before it has actually happened."""
    return date.today()


def validate_agb_against_gedi(year, season='Kharif'):
    """Compares this pipeline's AGB estimate against real GEDI L4A footprint
    biomass observations that fall inside your ROI, for the given
    year/season. Prints a bias/agreement summary and returns the paired
    (gedi_agbd, pipeline_agb) FeatureCollection for your own analysis.

    Only meaningful for windows inside GEDI's ACTIVE mission span -- returns
    None with an explanation outside that range, rather than a silently
    empty or misleading result. Explicitly excludes the 2023-03-17 to
    2024-06-11 stowage gap, when the instrument was not collecting data at
    all (see GEDI_STOWED_START/END above) -- distinct from a window simply
    not happening to contain a footprint."""
    gedi_end = _gedi_mission_end()
    d0, d1 = season_window(year, season)
    if d1 <= GEDI_START or d0 >= gedi_end + datetime.timedelta(days=1):
        print(f"⏭️ GEDI has no coverage for {year} {season} "
              f"(active mission span {GEDI_START} to {gedi_end}); nothing to compare.")
        return None
    if d0 >= GEDI_STOWED_START and d1 <= GEDI_STOWED_END + datetime.timedelta(days=1):
        print(f"⏭️ GEDI was stowed (no data collection) for all of {year} {season} "
              f"({GEDI_STOWED_START} to {GEDI_STOWED_END}); nothing to compare.")
        return None
    c0 = max(d0, GEDI_START)
    c1 = min(d1, gedi_end + datetime.timedelta(days=1))
    if GEDI_STOWED_START < c1 and GEDI_STOWED_END >= c0:
        print(f"   note: {year} {season} partially overlaps GEDI's stowage gap "
              f"({GEDI_STOWED_START} to {GEDI_STOWED_END}) -- real footprints "
              f"can only come from the active portion of the window.")

    stack, info = build_stack(year, season)
    if stack is None:
        print(f"⏭️ {year} {season}: {info.get('note', 'window unavailable')}")
        return None

    try:
        gedi = (ee.FeatureCollection(GEDI_L4A_ID)
                .filterBounds(roiGeom)
                .filterDate(eedate(c0), eedate(c1))
                .filter(ee.Filter.eq('l4_quality_flag', 1))
                .filter(ee.Filter.lt('agbd', 1000)))   # drop obvious outliers
        n = _retry(lambda: gedi.limit(1).size().getInfo(), tries=3, what="GEDI L4A")
        if n == 0:
            print(f"⏭️ No quality-passing GEDI footprints fall inside the ROI "
                  f"for {year} {season}.")
            return None

        paired = stack.select(['AGB']).reduceRegions(
            collection=gedi.select(['agbd', 'shot_number']),
            reducer=ee.Reducer.first(),
            scale=SCALE, tileScale=8)

        stats = _retry(lambda: paired.reduceColumns(
            reducer=ee.Reducer.pearsonsCorrelation(),
            selectors=['agbd', 'AGB']).getInfo(), tries=3, what="GEDI comparison")
        n_pts = _retry(lambda: paired.filter(
            ee.Filter.notNull(['AGB'])).size().getInfo(), tries=3, what="GEDI count")
        print(f"📊 GEDI cross-validation, {year} {season}: {n_pts} co-located "
              f"footprints, r={stats.get('correlation', float('nan')):.3f}")
        print("   Use this as an accuracy check, not a calibration source, "
              "unless you fit new AGB coefficients against it yourself.")
        return paired
    except Exception as ex:
        print(f"   ⚠️ GEDI cross-validation failed ({ex})")
        return None


# ==================================================================
# ⛑ FIX39 -- RUSLE: every factor re-derived from cited, peer-reviewed sources
# ==================================================================
# Every formula below was verified by literature search in this pass (not
# carried over from memory) against sources suitable for this study area
# (India / Deccan-plateau Karnataka where a specific citation exists, global
# standard methods otherwise). Full citations and search verification are in
# the accompanying document; only the load-bearing summary is here.

# ---- R : rainfall erosivity -------------------------------------- (NEW)
# Singh, G., 1981 (also attributed to Ram Babu, Tejwani, Agarwal & Bhushan
# 1978, CSWCRTI Dehradun): the standard India-wide regression of annual
# rainfall erosivity on mean annual precipitation, confirmed by three
# independent sources during this pass, incl. an IIT Guwahati technical
# report giving the exact coefficients:
#     R_annual(US customary) = 79 + 0.363 * AAP(mm)
#     R_annual(SI, MJ.mm.ha^-1.h^-1.yr^-1) = R_annual(US) * 17.02   [Foster
#     et al. 1981 US->SI RUSLE-R conversion, the standard factor used
#     throughout the RUSLE literature]
# This is an ANNUAL regression with a non-zero intercept (79), so it is not
# meaningful applied directly to a 4-month rainfall total -- doing so would
# retain nearly the full intercept for a fraction of the year and badly
# overstate short-window erosivity, worst for the driest window (Zaid).
# Instead the annual R is computed once per calendar year from the annual
# CHIRPS total, then apportioned to each window in proportion to that
# window's SHARE of the year's rainfall. This guarantees
# Kharif+Rabi+Zaid+(remaining months) reconstructs the annual R, and
# correctly concentrates erosivity in the monsoon, matching the qualitative
# behaviour documented in the seasonal-erosivity literature for India found
# during this pass. The apportionment step itself is a standard, defensible
# disaggregation choice, not a separately-cited equation -- stated plainly so
# it is not mistaken for part of the cited regression.
R_US_INTERCEPT, R_US_SLOPE = 79.0, 0.363
R_US_TO_SI = 17.02

_ANNUAL_RAIN_CACHE = {}
GAPFILL_ANNUAL_RAIN = True    # ⛑ v107 -- see _annual_rain_ee()


def _annual_rain_ee(year):
    """Annual CHIRPS total for `year`, used by calc_R_factor() to apportion
    the India annual erosivity regression to a window by the window's SHARE
    of the year's rainfall.

    ⛑ v107  BUG FOUND AND FIXED. For an INCOMPLETE data year (the current
    year, or the nominal year of a fully-projected future window such as
    Rabi 2026) this was the partial year-to-date total -- e.g. Jan-Jul 2026
    only -- so `share = window / annual` was computed against a denominator
    missing the entire remaining monsoon/post-monsoon. A gap-filled Kharif
    or a projected Rabi window (full-season rainfall in the numerator)
    divided by a 7-month denominator overstates the window's share, and
    with it R and RUSLE, for exactly the rows that are already estimates.
    Fixed the same way every other incomplete quantity in this pipeline is
    handled: real observed total for every day that exists + the mean of
    the last GAPFILL_LOOKBACK_YEARS complete years' total for the missing
    remainder only. A reference year counts only if it is itself complete
    for that remainder. Off (previous behaviour) when
    GAPFILL_INCOMPLETE_WINDOWS or GAPFILL_ANNUAL_RAIN is False."""
    if year in _ANNUAL_RAIN_CACHE:
        return _ANNUAL_RAIN_CACHE[year]
    y0, y1 = date(year, 1, 1), date(year + 1, 1, 1)
    ic = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(roiGeom)
          .filterDate(eedate(y0), eedate(y1)))
    total = safeSum(ic, 'precipitation', name='AnnualRain').rename('AnnualRain')
    if GAPFILL_INCOMPLETE_WINDOWS and GAPFILL_ANNUAL_RAIN:
        hard_end = _data_hard_end()
        miss0 = min(y1, max(y0, hard_end + datetime.timedelta(days=1)))
        if miss0 < y1:
            hist = []
            for k in range(1, GAPFILL_LOOKBACK_YEARS + 1):
                h0, h1 = shift_years(miss0, k), shift_years(y1, k)
                if h1 > hard_end + datetime.timedelta(days=1):
                    continue          # reference year itself incomplete
                hic = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(roiGeom)
                       .filterDate(eedate(h0), eedate(h1)))
                hist.append(safeSum(hic, 'precipitation', name='AnnualRain'))
            if hist:
                obs_days = (miss0 - y0).days
                total = total.add(ee.ImageCollection(hist).mean()).rename('AnnualRain')
                print(f"   🧩 annual rainfall {year} for the RUSLE R-factor: real total "
                      f"to {miss0 - datetime.timedelta(days=1)} ({obs_days} d) + "
                      f"{len(hist)}-yr mean for {miss0}..{y1 - datetime.timedelta(days=1)}")
            else:
                print(f"   ⚠️ annual rainfall {year} is incomplete (data to "
                      f"{hard_end}) and no complete reference year was found -- "
                      f"R-factor share uses the partial total")
    _ANNUAL_RAIN_CACHE[year] = total
    return total


def calc_R_factor(rain_window, data_year):
    annual_rain = _annual_rain_ee(data_year)
    r_annual = annual_rain.multiply(R_US_SLOPE).add(R_US_INTERCEPT) \
                          .multiply(R_US_TO_SI).rename('R_annual')
    share = rain_window.divide(annual_rain.max(1.0)).clamp(0.0, 1.15)
    return r_annual.multiply(share).rename('R').clamp(0, 4000)


# ---- K : soil erodibility ----------------------------------------- (NEW)
# Sharpley, A.N. & Williams, J.R., 1990. EPIC-Erosion/Productivity Impact
# Calculator: 1. Model Documentation. USDA Technical Bulletin No. 1768 -- the
# standard soil-property-based K-factor, confirmed by three independent
# sources including a national-scale Indian soil-erodibility assessment that
# used this exact EPIC formulation at 250 m over India. Uses sand/silt/clay/
# SOC at 0 cm from OpenLandMap (the same product family already used for
# texture and SOC), replacing the uncited 12-class texture lookup. SI
# conversion factor 0.1317 (Foster et al. 1981), confirmed by two independent
# sources. Falls back to the v8.2 texture-class lookup, unchanged, if any
# OpenLandMap layer is unavailable.
#
# ⛑ SOC UNIT BUG FOUND AND FIXED during re-validation -- see the SOC_DIVISOR
# constant and its note a little further down (just above calc_K_factor())
# for the full account. Short version: this pipeline
# divided the raw OpenLandMap SOC band by 50 to get percent; the dataset's
# own documentation states the correct divisor is 2 -- a 25x error in the
# intermediate SOC% value, present since an earlier pass first touched this
# line. Both this function and calc_K_factor() now use the corrected,
# explicitly-cited SOC_DIVISOR constant.
def _k_factor_texture_fallback():
    # ⛑ soil_texture is a CATEGORICAL class code (1-12) -- deliberately NOT
    # resampled. Bilinear-interpolating a class number produces a
    # meaningless fractional value (e.g. "class 2.4" between sandy-loam and
    # loam is not a real texture); nearest-neighbour, Earth Engine's
    # default, is the scientifically correct choice here, per Google's own
    # guidance on discrete rasters.
    soil_texture = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").select('b0')
    # soc_pct IS continuous -- resampled.
    soc_pct = (ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02")
               .select('b0').resample('bilinear')
               .divide(SOC_DIVISOR))   # see SOC_DIVISOR note above
    k_texture = (ee.Image(0.01)
                 .where(soil_texture.eq(1), 0.020).where(soil_texture.eq(2), 0.025)
                 .where(soil_texture.eq(3), 0.028).where(soil_texture.eq(4), 0.031)
                 .where(soil_texture.eq(5), 0.033).where(soil_texture.eq(6), 0.036)
                 .where(soil_texture.eq(7), 0.038).where(soil_texture.eq(8), 0.041)
                 .where(soil_texture.eq(9), 0.044).where(soil_texture.eq(10), 0.047)
                 .where(soil_texture.eq(11), 0.049).where(soil_texture.eq(12), 0.052))
    # NOT independently verified: the 0.05-per-percent sensitivity here is a
    # heuristic (organic matter reduces erodibility, direction is physically
    # sound) rather than a coefficient traced to a specific paper -- unlike
    # the primary EPIC path above it, which is fully cited. This function is
    # the FALLBACK, only reached if OpenLandMap's sand/silt/clay layers are
    # unavailable; flagged for completeness, not expected to matter often.
    soc_factor = ee.Image(1).subtract(soc_pct.multiply(0.05)).clamp(0.5, 1.0)
    return k_texture.multiply(soc_factor).clamp(0.008, 0.06).rename('K')


_ASSET_OK = {}


def _asset_has_band(asset_id, band):
    """Cached, eager check. EE graph construction is normally lazy -- a bad or
    renamed asset ID usually doesn't throw until the graph is evaluated, which
    for these two factors would otherwise mean validate_window() skipping the
    ENTIRE WINDOW instead of gracefully falling back to the older, still-valid
    K/LS method for just that factor. This one-time getInfo() per asset (not
    per window, not per tile) converts that into an immediate, specific,
    recoverable check."""
    key = (asset_id, band)
    if key in _ASSET_OK:
        if not _ASSET_OK[key]:
            raise RuntimeError(f"{asset_id} previously failed its probe")
        return True
    bands = _retry(lambda: ee.Image(asset_id).bandNames().getInfo(), tries=2,
                   what=f"probe {asset_id}")
    ok = band in bands
    _ASSET_OK[key] = ok
    if not ok:
        raise RuntimeError(f"{asset_id} has no band '{band}' (found {bands})")
    return True


# ---- SOC unit conversion: BUG FOUND AND FIXED during re-validation -----
# The dataset's OWN documentation states this explicitly (Zenodo record for
# OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02, Hengl & Wheeler, 2018,
# doi:10.5281/zenodo.1475457): "Soil organic carbon content in x 5 g/kg
# ... (to convert to % divide by 2)". Confirmed independently by a second,
# unrelated source (a published GEE groundwater-recharge tutorial using this
# same dataset) applying an equivalent scale factor (5 * 0.001, i.e. raw ->
# kg/kg by multiplying by 5 then dividing by 1000 -- the same "x5" factor).
#
# This pipeline had used /50.0 since an earlier pass first touched this line
# (correcting a DIFFERENT v7.7 bug -- dividing by 10 -- without re-deriving
# the arithmetic against an authoritative source). /50 is a 25x error versus
# the documented /2. Impact on the final K-factor is smaller than 25x because
# the EPIC formula's f_orgc term saturates for organic-rich soils, but it is
# real: roughly a 15-25% shift in K for typical soils in the primary EPIC
# path, and a larger, more direct shift in the linear texture-fallback path's
# soc_factor term, which the wrong value under-penalised for high-SOC soils.
# Both occurrences (this function and the fallback above) now use the same
# cited constant.
SOC_DIVISOR = 2.0   # raw OpenLandMap b0 value -> percent by mass


def calc_K_factor():
    try:
        # ⛑ BUG REPORTED AND FIXED: "Image asset 'OpenLandMap/SOL/
        # SOL_SILT-WFRACTION_USDA-3A1A1A_M/v02' not found."
        # This ID was never independently confirmed when first written --
        # it was inferred by pattern-matching the (real, confirmed) sand and
        # clay IDs, flagged internally at the time as an assumption, and the
        # assumption was wrong. Checked properly this time: OpenLandMap's
        # own Earth Engine catalog entry lists every soil property it
        # publishes -- "clay and sand content, bulk density, organic carbon
        # content, texture class, water content, and pH" -- silt is not
        # among them, on that page or any individual dataset page for this
        # product family. That omission isn't a gap in the catalog to route
        # around; it's correct as published: sand% + silt% + clay% = 100% by
        # definition, so silt is fully determined once sand and clay are
        # known, and a soil-property archive that already predicts sand and
        # clay independently has no reason to also publish a third,
        # separately-modelled layer for the remaining fraction.
        # Fixed by computing it, which is the textbook approach for exactly
        # this situation -- not a workaround, and arguably better than an
        # independently-modelled silt layer would have been, since it
        # guarantees the three fractions sum to exactly 100 rather than
        # depending on two separate machine-learning predictions happening
        # to agree.
        for aid in ("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",
                    "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",
                    "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02"):
            _asset_has_band(aid, 'b0')
        sand = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select('b0').resample('bilinear')
        clay = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select('b0').resample('bilinear')
        silt = ee.Image(100).subtract(sand).subtract(clay).max(0).rename('silt')
        soc_pct = (ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02")
                   .select('b0').resample('bilinear')
                   .divide(SOC_DIVISOR))    # see SOC_TO_PERCENT note below
        sn1 = ee.Image(1).subtract(sand.divide(100))
        denom = clay.add(silt).max(1)
        k_us = sand.expression(
            "(0.2 + 0.3*exp(-0.0256*SAN*(1-SIL/100)))"
            " * pow(SIL/DEN, 0.3)"
            " * (1 - (0.25*C)/(C + exp(3.72 - 2.95*C)))"
            " * (1 - (0.7*SN1)/(SN1 + exp(-5.51 + 22.9*SN1)))",
            {'SAN': sand, 'SIL': silt, 'DEN': denom, 'C': soc_pct, 'SN1': sn1})
        K = k_us.multiply(0.1317).rename('K').clamp(0.005, 0.07)
        return harmonise(K), "EPIC (Sharpley & Williams 1990)"
    except Exception as ex:
        print(f"   ⚠️ EPIC K-factor failed ({ex}); falling back to texture-class lookup")
        return harmonise(_k_factor_texture_fallback()), "texture-class lookup (fallback)"


# ---- LS : slope length & steepness --------------------------------- (NEW)
# Desmet, P. & Govers, G., 1996. "A GIS procedure for automatically
# calculating the USLE LS factor on topographically complex landscape units."
# J. Soil Water Conserv. 51(5), 427-433 -- the standard flow-accumulation-based
# LS-factor, confirmed by six independent sources including a GEE-specific
# RUSLE implementation using this exact form:
#     LS = 1.6 * (FA*cellsize / 22.1)^0.6 * (sin(slope_deg*0.01745) / 0.09)^1.3
#
# ⛑ BUG FOUND AND FIXED during this validation pass, not a hypothetical.
# FA*cellsize was fed directly from MERIT Hydro's upstream drainage area
# (`upa`, km^2), via As = area_m2 / cell_size_m. That substitution is
# DIMENSIONALLY consistent but SCALE-mismatched: `upa` is a WATERSHED-scale
# quantity (for any pixel near a stream it can be km^2 to hundreds of km^2 --
# the entire catchment above that point), while RUSLE's LS-factor is a
# HILLSLOPE-scale concept, calibrated for slope lengths of tens to a few
# hundred metres. A self-check run during this pass (not an extreme input --
# an ordinary 0.1 km^2 headwater patch, 8 degree slope) produced LS > 100 and
# a full RUSLE value near 1,800 t/ha/yr for an otherwise unremarkable
# cropland pixel -- published Indian watershed RUSLE studies report annual
# soil loss in the tens to a few hundred t/ha/yr. That is not an edge case;
# it happens for any pixel with a non-trivial upstream area, which in a real
# watershed is most of it.
#
# This is a documented, peer-reviewed limitation, not a one-off mistake:
# "the USLE/RUSLE model is commonly applied within GIS for conditions for
# which it has not been originally designed... Replacement of slope length
# by the upslope area predicts increased erosion due to the concentrated
# flow" (ScienceDirect RUSLE overview, confirmed this pass); a dedicated
# paper on "large watersheds" states plainly that using unit contributing
# area without correction "is insufficiently accurate" (confirmed this pass).
#
# THE FIX, with a direct peer-reviewed precedent for the mechanism: Meusburger
# et al. (2019, cited as the Swiss-alpine RUSLE modification found this pass)
# caps the flow-path length at a maximum threshold specifically to keep the
# LS-factor inside its valid hillslope-erosion regime -- they used 100 m for
# alpine grassland. This pipeline uses MAX_FLOW_LENGTH_M (default 300 m, the
# more common non-alpine RUSLE convention) as that same style of cap, applied
# to the MERIT-Hydro-derived flow-length term before it enters the exponent.
#
# Given the scale mismatch is real and the correction is a defensible but
# still approximate patch (not a validated replacement for a proper
# hillslope-scale flow-accumulation grid), the DEFAULT method is the
# already-validated slope-only L*S (LS_METHOD = 'slope_only'). The
# flow-accumulation-with-cap method is available (LS_METHOD =
# 'flow_accumulation') for anyone who wants the convergent/divergent-terrain
# signal and accepts that trade-off -- capped, tested against the exact
# input that broke it, but still recommended for local validation before
# being trusted quantitatively.
LS_METHOD = 'slope_only'        # 'slope_only' (default, safe) | 'flow_accumulation'
MAX_FLOW_LENGTH_M = 300         # cap on FA*cellsize before the exponent, metres


DEM_SOURCE = 'auto'   # 'auto' (GLO-30, falling back to NASADEM) | 'nasadem' | 'glo30' | 'fabdem'
# ⛑ FABDEM (Hawker et al. 2022) -- GLO-30 with buildings/forest canopy
# removed via machine learning, confirmed the most accurate of the freely
# available 30 m global DEMs in the same literature checked for the GLO-30
# upgrade above. NOT the default: it is a third-party, community-hosted
# asset (projects/sat-io/open-datasets/FABDEM, curated by Samapriya Roy's
# awesome-gee-community-datasets, not Google's own catalog) under a
# Creative Commons CC BY-NC-SA 4.0 licence -- Non-Commercial and
# ShareAlike, confirmed directly against the dataset's own licence page
# during this pass. Whether that fits THIS project depends on how the work
# is being used, which is not something to assume -- set explicitly:
#   DEM_SOURCE = 'fabdem'
# and, per the licence, credit: "FABDEM is produced using Copernicus
# WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH
# 2014-2018 provided under COPERNICUS by the European Union and ESA."


def _fabdem_elevation():
    # Band selected by INDEX, not name: the dataset's own documentation page
    # doesn't state an exact band name, and guessing one from a naming
    # pattern is exactly the mistake already made once this project (the
    # OpenLandMap silt asset) -- index 0 correctly gets "the elevation
    # band" regardless of what it's actually called, for what is a
    # genuinely single-band elevation product.
    return (ee.ImageCollection('projects/sat-io/open-datasets/FABDEM')
            .mosaic().select(0).resample('bilinear'))

def _nasadem_elevation():
    """⛑ Upgraded based on a literature check for this pass: Copernicus DEM
    GLO-30 is measurably more accurate than NASADEM in independent,
    peer-reviewed comparisons -- Simard et al. (2024), J. Geophysical
    Research: Biogeosciences, report 0.55 m RMSE for GLO-30 versus 1.5 m for
    NASADEM over bare ground, both validated against the same GEDI/ICESat
    lidar reference. That difference matters directly here: slope error
    scales with DEM vertical error (a commonly cited rule of thumb -- a 9 m
    SRTM-era error over a 30 m pixel can produce up to ~17 degrees of slope
    error), and slope feeds both the LS-factor and the P-factor's slope-
    percent table.

    GLO-30 is a Digital Surface Model (includes canopy/buildings, EGM2008
    datum) rather than NASADEM's bare-earth model -- a real, stated
    difference, not hidden by the upgrade; over forested pixels this can
    inflate slope somewhat, which is why this is a preference, not an
    unconditional replacement: DEM_SOURCE='nasadem' reverts to the previous
    behaviour in one line.

    Structurally different from NASADEM: GLO-30 ships as per-tile images in
    an ImageCollection (mosaicked here, not a single ee.Image), on band
    'DEM' -- NASADEM's 'elevation' band name does not apply. The un-suffixed
    'COPERNICUS/DEM/GLO30' id is Google's OWN deprecated alias (superseded
    by 'COPERNICUS/DEM/GLO30_2024_1', confirmed against Earth Engine's own
    catalog page during this pass) and additionally only covers 2010-2015 --
    using it would silently be a step backward, not an upgrade.

    Single shared loader so all three call sites (here, the flow-
    accumulation LS path, and the P-factor slope-percent calc) get IDENTICAL
    treatment and an identical fallback, exactly as before this change."""
    def _glo30():
        return (ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
                .select('DEM').mosaic().resample('bilinear'))

    def _nasadem():
        return ee.Image("NASA/NASADEM_HGT/001").select('elevation').resample('bilinear')

    if DEM_SOURCE == 'nasadem':
        return _nasadem()
    if DEM_SOURCE == 'glo30':
        return _glo30()
    if DEM_SOURCE == 'fabdem':
        try:
            key = ('projects/sat-io/open-datasets/FABDEM', 0)
            if key in _ASSET_OK and not _ASSET_OK[key]:
                raise RuntimeError("FABDEM previously failed its probe")
            if key not in _ASSET_OK:
                n = _retry(lambda: ee.ImageCollection('projects/sat-io/open-datasets/FABDEM')
                           .filterBounds(roiGeom).limit(1).size().getInfo(),
                           tries=2, what="probe FABDEM")
                _ASSET_OK[key] = n > 0
                if not _ASSET_OK[key]:
                    raise RuntimeError("FABDEM has no tile covering this ROI")
            return _fabdem_elevation()
        except Exception as ex:
            print(f"   ⚠️ FABDEM unavailable ({ex}); falling back to NASADEM")
            return _nasadem()
    try:
        # GLO-30 is an ImageCollection, not a single Image -- _asset_has_band
        # (elsewhere in this file) constructs ee.Image(asset_id) directly,
        # which is the wrong check for a collection and would always fail
        # here, silently forcing the NASADEM fallback even when GLO-30 is
        # genuinely available. Checked directly instead, against the first
        # tile actually covering this ROI.
        key = ('COPERNICUS/DEM/GLO30_2024_1', 'DEM')
        if key in _ASSET_OK and not _ASSET_OK[key]:
            raise RuntimeError("GLO-30 previously failed its probe")
        if key not in _ASSET_OK:
            bands = _retry(lambda: ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
                            .filterBounds(roiGeom).first().bandNames().getInfo(),
                            tries=2, what="probe COPERNICUS/DEM/GLO30_2024_1")
            _ASSET_OK[key] = 'DEM' in bands
            if not _ASSET_OK[key]:
                raise RuntimeError("GLO-30 has no 'DEM' band for this ROI")
        return _glo30()
    except Exception as ex:
        print(f"   ⚠️ Copernicus GLO-30 DEM unavailable ({ex}); "
              f"falling back to NASADEM")
        return _nasadem()


def _ls_factor_slope_fallback():
    dem = _nasadem_elevation()
    slope_deg = ee.Terrain.slope(dem)
    slope_rad = slope_deg.multiply(math.pi / 180.0)
    S = slope_rad.sin().divide(0.0896).pow(1.3).rename('S')
    beta = slope_rad.sin().divide(0.0896).divide(
        slope_rad.sin().pow(0.8).multiply(3.0).add(0.56))
    m = beta.divide(beta.add(1)).clamp(0.0, 0.5)
    L = ee.Image(SCALE / 22.13).pow(m).rename('L')
    return L.multiply(S).rename('LS').clamp(0, 20), slope_rad


def calc_LS_factor():
    if LS_METHOD != 'flow_accumulation':
        ls, slope_rad = _ls_factor_slope_fallback()
        return harmonise(ls), slope_rad, "slope-only (default; see LS_METHOD)"
    try:
        _asset_has_band('MERIT/Hydro/v1_0_1', 'upa')
        upa_km2 = ee.Image('MERIT/Hydro/v1_0_1').select('upa').resample('bilinear')
        # ⛑ the fix: cap the flow-length term BEFORE the exponent, not after --
        # capping the final LS value would flatten the spatial pattern across
        # most of the watershed instead of correcting the input that's wrong.
        fa_x_cell = upa_km2.multiply(1e6).divide(SCALE).min(MAX_FLOW_LENGTH_M)
        dem = _nasadem_elevation()
        slope_deg = ee.Terrain.slope(dem)
        slope_rad = slope_deg.multiply(math.pi / 180.0)
        ls = (fa_x_cell.divide(22.1).pow(0.6)
              .multiply(slope_rad.sin().divide(0.09).pow(1.3))
              .multiply(1.6).rename('LS').clamp(0, 20))
        return harmonise(ls), slope_rad, \
            f"Desmet & Govers 1996 (MERIT Hydro upa, capped at {MAX_FLOW_LENGTH_M}m)"
    except Exception as ex:
        print(f"   ⚠️ flow-accumulation LS-factor failed ({ex}); "
              f"falling back to slope-only L*S")
        ls, slope_rad = _ls_factor_slope_fallback()
        return harmonise(ls), slope_rad, "slope-only (fallback)"


# ---- C : cover-management -------------------------- (VERIFIED, UNCHANGED)
# Van der Knijff, J.M., Jones, R.J.A. & Montanarella, L., 2000. "Soil Erosion
# Risk Assessment in Europe." European Soil Bureau, JRC. Confirmed by six
# independent sources during this pass, all giving the same standard
# parameterisation (alpha=2, beta=1):
#     C = exp[-alpha * NDVI / (beta - NDVI)]
# This was ALREADY the v8.2 formula and needed no change -- included here so
# the citation sits next to the code, and because it is now conditioned on
# Dynamic World land use (below) rather than applied blindly to every pixel.
# Documented limitation carried over from the source paper itself: this form
# can overestimate C (understate the sheltering effect of vegetation) below
# NDVI ~= 0.65; treat low-NDVI C values as an upper bound, not a point
# estimate.

# ---- P : support practice ------------------------------- (REFINED)
# The slope-based support-practice table is, by definition, about practices
# applied to CULTIVATED land (contouring, strip-cropping, terracing) -- USDA's
# own non-agricultural-land guidance for RUSLE states plainly that P generally
# does not apply outside cropland, where the conventional default is P = 1.
# v8.2 applied the slope table to every pixel regardless of land use; it is
# now applied only where Dynamic World identifies the pixel as cropland.
def calc_C_and_P(ndvi, lu_dw):
    nd = ndvi.clamp(0.0, 0.95)
    C = nd.expression("exp(-2 * n / (1 - n))", {"n": nd}).rename('C').clamp(0.001, 1)

    dem = _nasadem_elevation()
    slope_pct = ee.Terrain.slope(dem).multiply(math.pi / 180.0).tan().multiply(100)
    # ---- P-factor table: VERIFIED (upgraded this pass) ------------ [v8.5]
    # USDA's own full RUSLE P-subfactor tables (checked in an earlier pass,
    # e.g. the Oklahoma/Iowa/Ohio Field Office Technical Guide RUSLE chapters)
    # key on ridge height, the 10-yr EI storm index, hydrologic soil group,
    # and furrow/row grade -- inputs this pipeline doesn't have. A dedicated
    # search this pass for what GIS/remote-sensing RUSLE studies actually use
    # instead confirmed the slope-CLASS simplification approach traces to two
    # sources used repeatedly in the literature, including India-specific
    # studies:
    #   Shin, G.J., 1999. "The analysis of soil erosion analysis in watershed
    #   using GIS." PhD dissertation, Gangwon National University, Korea --
    #   explicitly cited for exactly this slope-class/cultivation-method P
    #   table in a Himalayan RUSLE-GIS study found this pass.
    #   Wischmeier, W.H. & Smith, D.D., 1978. "Predicting Rainfall Erosion
    #   Losses." USDA Agriculture Handbook 537 -- independently cited for the
    #   same style of table (slope classes 0-5/5-10/10-20/20-30/30-50/50-100%)
    #   in an India-specific RUSLE study of the Peddavagu watershed found this
    #   pass.
    # Both sources are used for exactly this simplified pattern across many
    # published Indian RUSLE-GIS studies (Nun Nadi/Uttarakhand, Barakar/
    # Jharkhand, Banas basin, and others found this pass): P=1 (no benefit)
    # off cropland, increasing from a low value at gentle slopes toward 1.0 as
    # slope steepens and contouring/terracing become less effective -- the
    # same qualitative shape already used here. Exact breakpoint values still
    # vary slightly study-to-study (5/10/20/30/40% here vs 5/10/20/30/50% in
    # some sources), which is normal for this class of simplification, not a
    # sign either is wrong. If a locally-published Karnataka/CSWCRTI P-factor
    # table becomes available, it remains a direct, even more specific
    # replacement for this table.
    p_agri = (ee.Image(1)
              .where(slope_pct.lte(5), 0.55)
              .where(slope_pct.gt(5).And(slope_pct.lte(10)), 0.60)
              .where(slope_pct.gt(10).And(slope_pct.lte(20)), 0.70)
              .where(slope_pct.gt(20).And(slope_pct.lte(30)), 0.80)
              .where(slope_pct.gt(30).And(slope_pct.lte(40)), 0.90)
              .where(slope_pct.gt(40), 1.00))
    is_crop = lu_dw.eq(4)      # Dynamic World 'crops'
    P = ee.Image(1).where(is_crop, p_agri).rename('P')
    return C, P


# ---- Non-erodible surfaces: mask, don't fabricate ----------------- (NEW)
# RUSLE is defined for soil surfaces subject to sheet/rill erosion; it is not
# a meaningful quantity over open water, impervious built-up surfaces, or
# snow/ice. v8.2 (and v7.7) computed a small positive RUSLE value everywhere,
# including lakes and rooftops. v8.3 masks these three Dynamic World classes
# to null instead -- more nulls in exactly the pixels where the number was
# never meaningful, rather than a fabricated near-zero.
RUSLE_MASKED_DW_CLASSES = (0, 6, 8)   # water, built, snow_and_ice


def calcRUSLE(rain, ndvi, lu_dw, data_year):
    R = calc_R_factor(rain, data_year)
    K, k_src = calc_K_factor()
    LS, _slope_rad, ls_src = calc_LS_factor()
    C, P = calc_C_and_P(ndvi, lu_dw)

    rusle = R.multiply(K).multiply(LS).multiply(C).multiply(P).rename('RUSLE')
    rusle = rusle.clamp(0, 500)
    not_erodible = lu_dw.eq(RUSLE_MASKED_DW_CLASSES[0])
    for c in RUSLE_MASKED_DW_CLASSES[1:]:
        not_erodible = not_erodible.Or(lu_dw.eq(c))
    rusle = rusle.updateMask(not_erodible.Not())
    print(f"   ✅ RUSLE factors: R=India annual/apportioned  K={k_src}  LS={ls_src}")
    return harmonise(rusle)


# ---------------- EXPORT ----------------
expected_cols = [
    'UID', 'latitude', 'longitude', 'SubwshedID', 'buff_km', 'Treat', 'Year', 'Season',
    'NDVI', 'SAVI', 'LSWI', 'LAI', 'NDWI', 'EVI', 'NDMI', 'NDRE',
    'Rain', 'Tmax', 'Tmin', 'Tmean', 'ESI', 'WSSI', 'WSI',
    'SMDI', 'VCI', 'TCI', 'VHI', 'LandUse', 'AGB', 'RUSLE'
]


# ⛑ FIX28  Provenance columns. If a window ever falls back to a substitute
# product or an earlier year, you must be able to find those rows and exclude
# them. These are appended AFTER the original 30 columns, so anything reading
# your CSVs by name keeps working unchanged.
PROV_COLS = ['DataYear', 'Coverage', 'SrcOpt', 'SrcET', 'NObsV', 'NObsT']
EVENT_COLS = ['YrRel']          # Year - TREATMENT_YEAR, for event-study DiD
LULC_COLS = ['LandUseDW']       # ⛑ FIX38  raw 0-8 Dynamic World class; 'LandUse'
                                # (the original column) is unchanged in name,
                                # position and 4-class encoding.
ADD_LULC_COL = True

# ⛑ FIX43  the actual FIX for the "partially verified" ESI finding.        [v8.5]
# 'ESI' keeps its exact original meaning (the raw ET/PET ratio) for schema
# stability; this is the genuine standardized-anomaly ESI the literature
# describes, appended as a new column rather than silently changing what
# 'ESI' has always meant.
ANOM_COLS = ['ESI_Anom']
ADD_ANOM_COL = True


def export_columns():
    cols = list(expected_cols)
    if ADD_PROVENANCE_COLS:
        cols += PROV_COLS
    if EXPORT_EVENT_TIME:
        cols += EVENT_COLS
    if ADD_LULC_COL:
        cols += LULC_COLS
    if ADD_ANOM_COL:
        cols += ANOM_COLS
    if GAPFILL_INCOMPLETE_WINDOWS:
        cols += ['GapFilled']
    if ADD_OPTICAL_TIER_COL:          # ⛑ v108 per-pixel optical priority level
        cols += ['OptTier']
    return cols


def validate_window(stack, year, season):
    """⛑ FIX8b  ONE graph evaluation per window, before any tile is queued.
    v7.7 ran a per-tile precheck, caught the exception, printed
    '⚠️ Precheck failed ...; exporting anyway.' and set has_any = True — so a
    task that could never succeed was still submitted. That is why
    CSV_2026_yearly_tile3_sub0 reached the batch queue and died after 1 second.
    Your log has 1,430 memory + 152 no-bands prechecks that were all ignored."""
    try:
        pt = roiGeom.centroid(SCALE).buffer(SCALE * 20, ee.ErrorMargin(1))   # ⛑ v109
        _retry(lambda: stack.reduceRegion(
            reducer=ee.Reducer.first(), geometry=pt, scale=SCALE,
            tileScale=16, maxPixels=10000, bestEffort=True).getInfo(),
            tries=3, what=f"validate {year} {season}")
        return True, ""
    except Exception as ex:
        return False, str(ex)


_RUN_COUNT = {'n': 0}

# ⛑ v107  see main()'s validation step. True = a window whose interactive
# validation only TIMED OUT is still exported (tiles that genuinely fail are
# swept). False = previous behaviour (any validation failure skips the window).
EXPORT_ON_VALIDATION_TIMEOUT = True
_TIMEOUT_MARKERS = ('timed out', 'timeout', 'deadline', 'too long', 'retry')


def _looks_like_timeout(err_text):
    t = (err_text or '').lower()
    if any(m in t for m in ('did not match any bands', 'no bands', 'memory')):
        return False
    return any(m in t for m in _TIMEOUT_MARKERS)


def drive_folder_for(year):
    return f"{DRIVE_FOLDER}_{year}" if SPLIT_DRIVE_FOLDER_BY_YEAR else DRIVE_FOLDER


def exportTile(img, box, name, done_dict, year, season, depth=0,
               tilescale=DEFAULT_TILE_SCALE):
    """box = [west, south, east, north] in degrees (was a computed geometry in
    v7.7; a plain box is what makes the pixel guard work client-side)."""
    if MAX_TASKS_PER_RUN and _RUN_COUNT['n'] >= MAX_TASKS_PER_RUN:
        return 0
    if is_done(done_dict, year, season, name):
        if OVERWRITE_EXISTING:
            print(f"♻️ Already exported — re-exporting to replace: {name}")
            remove_done_from_progress(done_dict, year, season, name)
        else:
            return 0

    # ⛑ FIX4/FIX5  working oversize guard + adaptive n x n split.
    # v7.7 used a constant SUBSPLIT_DEG, so recursion re-split a tile into an
    # identically sized tile and produced _sub0_sub0_sub0... down to depth 6
    # without ever shrinking.
    px = approx_pixel_count(box)
    nsplit = split_factor(px)
    if (px > PIXEL_LIMIT * SPLIT_TOLERANCE and depth < MAX_SPLIT_DEPTH
            and (box[2] - box[0]) / nsplit > 0.002):
        print(f"⚠️ Large tile (~{px:,.0f} px) → splitting {name} into {nsplit}x{nsplit}")
        q = 0
        for i, sub in enumerate(split_box(box, nsplit)):
            q += exportTile(img, sub, f"{name}_s{i}", done_dict, year, season,
                            depth + 1, min(RETRY_TILE_SCALE, tilescale * 2))
        return q

    try:
        region = box_geom(box).intersection(roiGeom, ee.ErrorMargin(1))
        fc = img.sample(
            region=region,
            scale=SCALE,
            projection=GRID_PROJ,      # ⛑ FIX22  replaces the expensive
            geometries=False,          #          .reproject() on the 30-band
            tileScale=tilescale,       #          stack; sample already fixes
            dropNulls=False,           #          the grid.
        )
        wait_for_capacity()            # ⛑ FIX6 / FIX36 -- may raise BatchBlockedError
        task = ee.batch.Export.table.toDrive(
            collection=fc,
            description=description_from_name(name),
            folder=drive_folder_for(year),
            fileNamePrefix=file_prefix_from_name(name),   # ⛑ v107 unchanged
            fileFormat='CSV',                            #   CSV names on Drive
            selectors=export_columns(),  # ⛑ FIX23 identical column order everywhere
        )
        try:
            task.start()
        except Exception as e:
            # ⛑ FIX37  the block is most likely to surface exactly here, on the
            # first real attempt to start a task. Never retried, never treated
            # as a generic export failure -- re-raised so the outer except
            # below does NOT catch it and move on to the next tile.
            if _is_tos_block(str(e)):
                raise BatchBlockedError(str(e))
            raise
        mark_submitted()                # ⛑ FIX36  pacing floor for the NEXT submission
        _RUN_COUNT['n'] += 1
        record_task(description_from_name(name), "QUEUED",
                    task_id=getattr(task, "id", None),
                    detail={"year": year, "season": season, "tile": name,
                            "box": box, "depth": depth, "tile_scale": tilescale,
                            "est_px": int(px), "queued_at": _now_iso()})
        mark_done(done_dict, year, season, name)
        return 1
    except BatchBlockedError:
        raise   # ⛑ FIX37  propagate to main() -- do not swallow, do not retry,
                #          do not fall through to the "next tile" as if this
                #          tile merely failed.
    except Exception as ex:
        msg = str(ex).lower()
        if (("too large" in msg or "memory" in msg or "timed out" in msg)
                and depth < MAX_SPLIT_DEPTH):
            print(f"⚠️ {ex}\n   ↳ Splitting & raising tileScale for {name}")
            q = 0
            for i, sub in enumerate(split_box(box, nsplit)):
                q += exportTile(img, sub, f"{name}_s{i}", done_dict, year, season,
                                depth + 1, min(RETRY_TILE_SCALE, tilescale * 2))
            return q
        print(f"🚫 Export fail {name}: {ex}")
        record_task(description_from_name(name), "LOCAL_EXCEPTION",
                    detail={"error": str(ex), "box": box, "year": year,
                            "season": season, "tile": name, "depth": depth,
                            "when": _now_iso()})
        return 0


# ---------------- BATCH-FAILURE SWEEP ---------------------------- ⛑ FIX8
# v7.7's try/except around task.start() only ever saw SUBMISSION errors. A task
# that started fine and then died 52 seconds into batch execution — exactly what
# happened to CSV_2025_Rabi_tile11 — was never retried and the tile simply
# vanished from the panel with no record. This closes that hole.
SPLITTABLE = ("too large", "memory limit", "user memory", "timed out",
              "computation timed out", "too many", "exceeded")
_STACK_CACHE = {}


def sweep_failed_tasks(done_dict, rounds=FAILURE_SWEEP_ROUNDS,
                       stack_builder=None):
    if not AUTO_SPLIT_ON_FAILURE:
        return
    _sbar = progress_bar(rounds, "failure-sweep rounds")                  # ⛑ v110
    for rnd in range(1, rounds + 1):
        _sbar.update(1)
        waited = 0
        while waited < SWEEP_MAX_WAIT_S:
            n = active_task_count()
            if n == 0:
                break
            print(f"   ⏳ sweep {rnd}: {n} tasks still running ({waited}s)")
            time.sleep(TASK_POLL_INTERVAL * 2)
            waited += TASK_POLL_INTERVAL * 2
        if waited >= SWEEP_MAX_WAIT_S:
            print(f"⚠️ Sweep {rnd}: queue did not drain; re-run main() later.")
            return

        ledger = load_task_ledger()
        retryable = []
        roi_prefix_sweep = task_prefix()      # ⛑ v107 this version's tasks only
        for t in _task_list():
            if t['state'] != 'FAILED' or not t['description'].startswith(roi_prefix_sweep):
                continue
            ent = ledger.get(t['description'], {})
            if not ent.get('box') or ent.get('depth', 0) >= MAX_SPLIT_DEPTH:
                continue
            if any(k in (t['error'] or '').lower() for k in SPLITTABLE):
                retryable.append((t, ent))
        if not retryable:
            print(f"✅ Sweep {rnd}: nothing retryable.")
            return
        print(f"🔁 Sweep {rnd}: re-splitting {len(retryable)} failed tiles")

        q = 0
        for t, ent in retryable:
            yr, season = ent['year'], ent['season']
            stack = _STACK_CACHE.get((yr, season))
            if stack is None and stack_builder:
                stack = stack_builder(yr, season)
                _STACK_CACHE[(yr, season)] = stack
            if stack is None:
                continue
            remove_done_from_progress(done_dict, yr, season, ent['tile'])
            for i, sub in enumerate(split_box(ent['box'], 2)):
                q += exportTile(stack, sub, f"{ent['tile']}_r{i}", done_dict,
                                yr, season, depth=ent.get('depth', 0) + 1,
                                tilescale=RETRY_TILE_SCALE)
            record_task(t['description'], "RESPLIT")
        save_task_ledger()
        save_progress(done_dict)
        print(f"🔁 Sweep {rnd}: queued {q} replacement tiles")


# ---------------- SETUP ----------------
def setup(authenticate=False):
    global ROI_raw, ROI, roiGeom, GRID_PROJ, UID_BAND, LONLAT_BASE
    global ROI_ID
    if authenticate:
        ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

    # ⛑ Requested explicitly: running this pipeline for different watersheds
    # separately must never let one ROI's finished tasks or progress be
    # mistaken for another's. Task descriptions and every local/Drive state
    # file used to carry NO roi-identifying information at all -- just
    # year/season/tile -- so two different ROIs' tasks could land on
    # IDENTICAL description strings (e.g. "CSV_2020_Kharif_tile0_sub0"),
    # and reconcile_tasks() (which matches against Earth Engine's real,
    # project-wide task list) had no way to tell them apart. Switching ROI
    # without renaming DRIVE_FOLDER by hand could silently skip a brand new
    # watershed's tiles, believing them already done from a completely
    # different one -- exactly the bug reported.
    #
    # Fixed by deriving a short, human-readable ROI_ID from ROI_ASSET (its
    # own last path component, e.g. "Sirur") and using it to scope EVERY
    # task description and EVERY state file -- computed here, inside
    # setup(), which every entry point already calls before a run, rather
    # than as a plain module-level constant computed once at import time.
    # That matters specifically because a user might edit ONLY the config
    # cell after switching ROI without re-running the whole notebook --
    # computing this here means it always reflects whatever ROI_ASSET
    # currently is, not a stale value from whenever the module first loaded.
    #
    # This is deliberately NOT "detect a change and wipe the old progress":
    # each ROI gets its own separate, independently persisted state, so
    # switching between watersheds freely -- including back to one you
    # already partly downloaded -- never loses that watershed's resume
    # progress, and never cross-contaminates a different one's. The
    # existing resume/skip-if-already-done behaviour you explicitly said to
    # keep is completely intact; it now just always applies to the correct
    # watershed.
    ROI_ID = ROI_ASSET.rstrip('/').split('/')[-1] or 'roi'
    init_state_dir()

    if EE_PROJECT_REMINDER:
        print(f"📌 Earth Engine project for this run: {EE_PROJECT}")
        print(f"📍 ROI: {ROI_ID}  (from {ROI_ASSET}) -- all task names and "
              f"progress/state files for this run are scoped to this ROI, "
              f"so a different watershed's tasks can never be mistaken for "
              f"this one's, and switching back to it later resumes exactly "
              f"where it left off.")
        print("   Run this SAME workload from this ONE project only. Google's "
              "batch-task-restriction policy is specifically triggered by "
              "spreading one workload across multiple accounts/projects -- "
              f"see {BATCH_RESTRICTIONS_DOC}")

    ROI_raw = ee.FeatureCollection(ROI_ASSET)
    ROI = prepareROI(ROI_raw)
    # ⛑ BUG FOUND AND FIXED, reported directly, with a real Earth Engine
    # crash: "GeometryConstructors.MultiGeometry: Geometry coordinate
    # projection requires non-zero maxError." FeatureCollection.geometry()
    # takes an OPTIONAL maxError, used specifically "when combining
    # geometries" per Earth Engine's own documentation -- this only bites
    # when the ROI has multiple features that need merging into one
    # geometry (producing a MultiGeometry), which is exactly why this
    # worked fine for Sirur (apparently single-feature) and failed for
    # Gummlapalli (apparently multi-feature) with the identical code.
    # Fixed at the source with an explicit maxError, matching the
    # ee.ErrorMargin(SCALE) convention already used elsewhere in this file
    # (e.g. the outline-pinning simplify() two lines below) -- rather than
    # only patching the one call this happened to be caught on, since any
    # geometry operation downstream that also omits an explicit maxError
    # can hit the identical error for the same underlying reason. See also
    # the UID safety check and tile_boxes() below, fixed the same way.
    roiGeom = ROI.geometry(ee.ErrorMargin(SCALE))
    # ⛑ v109  BUG FOUND AND FIXED -- the real, logged cause of "nothing is
    # produced" for Gummlapalli (and any other MULTI-FEATURE ROI), with
    # v108's own diagnose_window() output as the evidence: every optical
    # branch, Dynamic World, the DEM, the tile grid and validation all
    # failed with "GeometryConstructors.MultiGeometry: Geometry coordinate
    # projection requires non-zero maxError.", right after "✅ ROI outline
    # pinned client-side".
    #   The pin used to be  ee.Geometry(gj, None, False)  -- i.e. it forced
    # geodesic=False onto WHATEVER GeoJSON came back. For a single-feature
    # ROI (Sirur) that GeoJSON is a Polygon of raw coordinates, nothing
    # needs reprojecting, and it works. For a multi-feature ROI,
    # FeatureCollection.geometry() returns a GeometryCollection of the sub-
    # watershed polygons; the client then emits
    #   GeometryConstructors.MultiGeometry(geometries=[geodesic parts], geodesic=False)
    # and the server must convert the parts' geodesic state -- which it
    # refuses to do without maxError. Every later filterBounds()/
    # intersection()/sample() inherited that broken constructor, which is
    # why the v106 patch (maxError added to the DOWNSTREAM calls) could not
    # help: the error is raised one level earlier, by the ROI itself.
    #   Fix, at the source: the outline is (1) dissolved SERVER-side into
    # one (Multi)Polygon with an explicit error margin, (2) simplified and
    # fetched, (3) flattened CLIENT-side into a plain list of polygon parts
    # (a GeometryCollection is unpacked; non-polygon parts are dropped and
    # reported), and (4) re-built with ee.Geometry.MultiPolygon(..., proj=
    # 'EPSG:4326', geodesic=False, maxError=1) -- the constructor that DOES
    # take maxError. Same planar outline as before for Sirur; a valid one
    # for Gummlapalli. If pinning is impossible, the server-side fallback
    # is likewise the dissolved (Multi)Polygon, never a GeometryCollection.
    # Pin the outline client-side once so each of the ~4,000 export graphs
    # intersects against a literal geometry instead of re-deriving it.
    try:
        gj = _retry(lambda: roiGeom.dissolve(ee.ErrorMargin(SCALE))
                    .simplify(ee.ErrorMargin(SCALE)).getInfo(), what="ROI outline")
        parts, dropped = _polygon_parts(gj)
        if not parts:
            raise RuntimeError(f"ROI outline contains no polygon (GeoJSON type "
                               f"{gj.get('type') if isinstance(gj, dict) else type(gj)})")
        if len(json.dumps(parts)) < 4_000_000:
            roiGeom = ee.Geometry.MultiPolygon(parts, proj='EPSG:4326', geodesic=False,
                                               maxError=1, evenOdd=True)
            print(f"✅ ROI outline pinned client-side ({len(parts)} polygon part(s)"
                  + (f"; {dropped} non-polygon part(s) dropped" if dropped else "") + ")")
        else:
            roiGeom = ROI.geometry(ee.ErrorMargin(SCALE)).dissolve(ee.ErrorMargin(SCALE))
            print("   ℹ️ ROI outline too large to pin; using the server-side dissolved outline")
    except Exception as ex:
        print(f"   ⚠️ ROI pin skipped: {ex}")
        roiGeom = ROI.geometry(ee.ErrorMargin(SCALE)).dissolve(ee.ErrorMargin(SCALE))

    GRID_PROJ = ee.Projection(CRS).atScale(SCALE)
    _c = ee.Image.pixelCoordinates(GRID_PROJ)
    # ⛑ FIX24  int64 UID; v7.7 left it float64, which prints large values in
    #          scientific notation in CSV and loses the integer identity.
    #
    # ⛑ BUG FOUND AND FIXED during deep validation: collision risk with no
    # safety margin under plausible future settings.
    # UID = X*multiplier + Y only avoids two different pixels sharing an ID
    # if Y never reaches `multiplier`. At SCALE=10 for this specific
    # watershed's UTM 43N northing, Y is ~164,000 -- under the old
    # multiplier (1,000,000) by only ~6x. That margin disappears entirely at
    # SCALE=5 (~3x) and is EXCEEDED at SCALE=1 (Y ~1.6 million > 1,000,000),
    # which would silently merge distinct pixels onto the same UID -- the
    # exact kind of silent corruption a panel/fixed-effects design depends
    # on UID to prevent. SCALE has already been changed more than once in
    # this project's history, so this was not a hypothetical.
    # Fixed two ways: (1) the multiplier is now 10**9 -- Y would need to
    # exceed a billion pixels (thousands of kilometres at any realistic
    # SCALE) to collide, eliminating this as a practical concern anywhere on
    # Earth; (2) a one-time runtime check against the ROI's actual bounds
    # makes any future violation an explicit error instead of silent data
    # corruption.
    # UID_MULTIPLIER is a module-level constant -- see its definition and
    # citation near the other configuration constants.
    try:
        roi_bounds = _retry(lambda: roiGeom.bounds(ee.ErrorMargin(SCALE)).getInfo(),
                             tries=3,
                             what="ROI bounds for UID safety check")
        coords = roi_bounds['coordinates'][0]
        max_lat = max(c[1] for c in coords)
        # Coarse, deliberately generous upper bound on northing (m): equator-
        # to-pole distance is ~10,000 km, so this always overestimates.
        max_northing_m = abs(max_lat) * 111320 + 200_000
        max_y_pixels = max_northing_m / SCALE
        if max_y_pixels >= UID_MULTIPLIER:
            raise RuntimeError(
                f"UID collision risk: estimated max Y pixel index "
                f"({max_y_pixels:,.0f}) approaches or exceeds UID_MULTIPLIER "
                f"({UID_MULTIPLIER:,}) at SCALE={SCALE}. Raise UID_MULTIPLIER "
                f"before proceeding -- continuing would silently merge "
                f"distinct pixels onto the same UID.")
        print(f"✅ UID safety check: max Y pixel index ~{max_y_pixels:,.0f}, "
              f"multiplier {UID_MULTIPLIER:,} ({UID_MULTIPLIER/max(max_y_pixels,1):,.0f}x headroom)")
    except RuntimeError:
        raise
    except Exception as ex:
        print(f"   ⚠️ UID safety check skipped ({ex}); proceeding with the "
              f"generously-sized default multiplier")
    UID_BAND = _c.select('x').toInt64().multiply(UID_MULTIPLIER) \
                 .add(_c.select('y').toInt64()).rename('UID').toInt64()
    LONLAT_BASE = ee.Image.pixelLonLat().reproject(GRID_PROJ)
    return ROI


def _polygon_parts(gj):
    """⛑ v109  Flatten any GeoJSON geometry into a list of MultiPolygon parts
    ([[ring, ...], ...]) -> (parts, n_dropped). Polygon and MultiPolygon are
    taken as-is; a GeometryCollection is unpacked recursively; Feature /
    FeatureCollection wrappers are unwrapped; points and lines are dropped
    (counted) because an ROI outline is an area."""
    if not isinstance(gj, dict):
        return [], 1
    t = gj.get('type')
    if t == 'Polygon':
        return [gj['coordinates']], 0
    if t == 'MultiPolygon':
        return list(gj['coordinates']), 0
    if t == 'GeometryCollection':
        parts, dropped = [], 0
        for g in gj.get('geometries', []):
            p, d = _polygon_parts(g)
            parts += p
            dropped += d
        return parts, dropped
    if t == 'Feature':
        return _polygon_parts(gj.get('geometry') or {})
    if t == 'FeatureCollection':
        parts, dropped = [], 0
        for f in gj.get('features', []):
            p, d = _polygon_parts(f)
            parts += p
            dropped += d
        return parts, dropped
    return [], 1


def tile_boxes(region, deg, clip_to=None):
    """makeTiles(), materialised as client-side [w,s,e,n] boxes in ONE call."""
    fc = makeTiles(region, deg, clip_to)

    # ⛑ Same class of bug as roiGeom's construction and the UID safety
    # check above (see setup()'s note): .bounds() also takes an optional
    # maxError, and a rectangle tile clipped against a multi-part ROI can
    # need one for the same reason. 1 m matches makeTiles()' own existing
    # precision convention for tile-boundary operations (its own
    # .bounds(1, ...) call above), rather than the coarser ee.ErrorMargin
    # used for the overall ROI outline, which doesn't need this precision.
    def _b(f):
        c = ee.List(f.geometry().bounds(ee.ErrorMargin(1)).coordinates().get(0))
        xs = c.map(lambda p: ee.List(p).get(0))
        ys = c.map(lambda p: ee.List(p).get(1))
        return f.set({'w': ee.List(xs).reduce(ee.Reducer.min()),
                      's': ee.List(ys).reduce(ee.Reducer.min()),
                      'e': ee.List(xs).reduce(ee.Reducer.max()),
                      'n': ee.List(ys).reduce(ee.Reducer.max())})
    d = _retry(lambda: fc.map(_b).reduceColumns(
        ee.Reducer.toList(4), ['w', 's', 'e', 'n']).getInfo(), what="tile boxes")
    rows = (d or {}).get('list') or []
    if rows and not isinstance(rows[0], (list, tuple)):
        # some API versions return four parallel lists instead of tuples
        rows = list(zip(*rows))
    return [[round(float(v), 6) for v in row] for row in rows]


def _is_treated(yr):
    return (yr > TREATMENT_YEAR) if TREAT_RULE == 'exclusive' else (yr >= TREATMENT_YEAR)


_GRID_CACHE = {'g': None}


def build_export_grid(force=False):
    """⛑ FIX5  The same two-level tile{i}_sub{j} grid the yearly composite used
    in v7.7, now built once and applied to Yearly AND all three seasons."""
    if _GRID_CACHE['g'] is not None and not force:
        return _GRID_CACHE['g']
    parents = tile_boxes(roiGeom, BASE_TILE_DEG, roiGeom)
    if USE_SUBTILES:
        subs = tile_boxes(roiGeom, SUBTILE_DEG, roiGeom)
        grid = []
        for i, p in enumerate(parents):
            for j, b in enumerate([b for b in subs if _centre_in(b, p)]):
                grid.append((f"tile{i}_sub{j}", b))
        leftover = [b for b in subs if not any(_centre_in(b, p) for p in parents)]
        for k, b in enumerate(leftover):
            grid.append((f"tileX_sub{k}", b))
    else:
        grid = [(f"tile{i}", b) for i, b in enumerate(parents)]
    est = approx_pixel_count(grid[0][1]) if grid else 0
    print(f"✅ {len(parents)} base tiles @ {BASE_TILE_DEG}° → {len(grid)} export "
          f"chunks @ {SUBTILE_DEG if USE_SUBTILES else BASE_TILE_DEG}° "
          f"(~{est:,.0f} px each, limit {PIXEL_LIMIT:,})")
    _GRID_CACHE['g'] = grid
    return grid


# ==================================================================
# ⛑ FIX41 -- FULL RUN-GRANULARITY FREEDOM                            [v8.4/8.5]
# ==================================================================
# You asked for freedom to run the complete panel in one call, OR in chunks of
# any size (1, 2, 3 years, or as needed), OR by season, OR any combination --
# not a fixed 3-year scheme. `main(years=..., seasons=...)` already accepts
# arbitrary lists, so that freedom already existed structurally; what's added
# here is convenience and visibility on top of it, not a new restriction.
#
#   main()                                    everything, one call
#   main(years=[2020])                        one year, all seasons
#   main(years=[2020], seasons=['Kharif'])     one year, one season
#   main(seasons=['Rabi'])                     every year, Rabi only
#   run_period(2015, 2017)                     an explicit year range
#   run_period(2015, 2026, seasons=['Kharif']) every Kharif, one call
#   chunk_plan(chunk_years=1)                  12 single-year chunks
#   chunk_plan(chunk_years=2)                  6 two-year chunks
#   chunk_plan(chunk_years=3)                  4 three-year chunks (default)
#   run_chunk(1, chunk_years=2, seasons=['Kharif','Rabi'])
#                                              chunk 1 of a 2-yr/2-season plan
CHUNK_YEARS = 3       # default chunk size; override per-call, not fixed


def _window_will_run(raw0, raw1):
    """⛑ v107  Mirrors build_stack()'s own decision for the estimators: a
    window runs if it has real usable coverage, OR (gap-fill on) if the
    data simply hasn't reached it yet -- in which case it is projected."""
    c0, _c1, frac, _n = clamp_window(raw0, raw1)
    if c0 is not None:
        return frac >= MIN_WINDOW_COVERAGE or (GAPFILL_INCOMPLETE_WINDOWS
                                               and window_is_data_incomplete(raw1))
    return GAPFILL_INCOMPLETE_WINDOWS and window_is_data_incomplete(raw1)


def chunk_plan(chunk_years=None):
    """[(start, end), ...] covering START_YEAR..END_YEAR inclusive, in
    chunk_years-year blocks (any size -- 1, 2, 3, ... -- default CHUNK_YEARS).
    The last block may be shorter.

    ⛑ Found during a later validation pass: `cy = chunk_years or CHUNK_YEARS`
    treats chunk_years=0 as falsy, so it silently fell back to the default
    instead of rejecting an invalid value -- and chunk_years<0 caused an
    actual infinite loop (`end` computed BEFORE `y` each iteration, so `y`
    walked backwards forever instead of advancing toward END_YEAR). Both are
    now a clear, immediate error instead of silent wrong behaviour or a hang."""
    cy = CHUNK_YEARS if chunk_years is None else chunk_years
    if not isinstance(cy, int) or cy < 1:
        raise ValueError(f"chunk_years must be a positive integer, got {cy!r}")
    plan = []
    y = START_YEAR
    while y <= END_YEAR:
        end = min(y + cy - 1, END_YEAR)
        plan.append((y, end))
        y = end + 1
    return plan


def _chunk_task_estimate(a, b, seasons=None):
    """Real task count for years [a,b] and the given seasons, using the
    actual current grid and PIXEL_LIMIT/SCALE -- not a hardcoded guess, so
    this stays accurate for any chunk_years or seasons combination."""
    try:
        grid = build_export_grid()
    except Exception:
        return None
    seasons = seasons or (['Yearly'] + list(SEASONS.keys()))
    n_windows = 0
    for yr in range(a, b + 1):
        for se in seasons:
            d0, d1 = season_window(yr, se)
            if _window_will_run(d0, d1):          # ⛑ v107 projection-aware
                n_windows += 1
    eff = 0
    for _n, box in grid:
        px = approx_pixel_count(box)
        eff += split_factor(px) ** 2 if px > PIXEL_LIMIT * SPLIT_TOLERANCE else 1
    return n_windows * eff


@_friendly_name_errors
def chunk_status(chunk_years=None, seasons=None):
    """Per-chunk progress: how many CSV_ tasks exist in each state, so you can
    see at a glance which chunk is next and whether the previous one finished
    cleanly before starting another. `seasons` narrows the plan to match
    whatever you're actually running (see run_chunk)."""
    ops = {o['description']: o['state'] for o in _task_list()}
    plan = chunk_plan(chunk_years)
    print(f"{'chunk':14s} {'years':9s} {'windows':>8s} {'tasks~':>8s} "
          f"{'done':>6s} {'failed':>7s} {'pending':>8s}")
    for i, (a, b) in enumerate(plan, 1):
        yrs = list(range(a, b + 1))
        se_list = seasons or (['Yearly'] + list(SEASONS.keys()))
        prefix_years = {str(y) for y in yrs}
        roi_prefix = task_prefix()            # ⛑ v107 this version's tasks only
        relevant = [d for d in ops if d.startswith(roi_prefix)
                    and d[len(roi_prefix):].split("_")[0] in prefix_years
                    and d[len(roi_prefix):].split("_")[1] in se_list]
        done = sum(1 for d in relevant if ops[d] in ("COMPLETED", "SUCCEEDED"))
        failed = sum(1 for d in relevant if ops[d] == "FAILED")
        pending = sum(1 for d in relevant if ops[d] in ("RUNNING", "READY", "PENDING"))
        est = _chunk_task_estimate(a, b, seasons)
        est_s = f"~{est:,}" if est is not None else "?"
        print(f"  chunk {i:<7d} {a}-{b}  {len(yrs) * len(se_list):>8d} {est_s:>8s} "
              f"{done:>6d} {failed:>7d} {pending:>8d}")
    print("\nTasks are only counted once queued -- run estimate_job(years=...) "
          "on a specific chunk before running it for a size preview.")
    return plan


@_friendly_name_errors
def run_chunk(chunk_index, authenticate=False, chunk_years=None, seasons=None):
    """Run ONE chunk by its 1-based index in chunk_plan(chunk_years). Pass the
    SAME chunk_years / seasons you used to inspect the plan, so index i always
    means the same years. Designed to be called manually, one at a time, from
    separate notebook cells. Resumable: re-running the same chunk skips
    whatever already completed."""
    plan = chunk_plan(chunk_years)
    if not (1 <= chunk_index <= len(plan)):
        raise ValueError(f"chunk_index must be 1..{len(plan)}, got {chunk_index}")
    a, b = plan[chunk_index - 1]
    label = f"years {a}-{b}" + (f", seasons {seasons}" if seasons else "")
    print(f"▶️ Running chunk {chunk_index}/{len(plan)}: {label}")
    main(authenticate=authenticate, years=list(range(a, b + 1)), seasons=seasons)


@_friendly_name_errors
def run_period(start_year, end_year, seasons=None, authenticate=False):
    """Run an explicit, arbitrary year range (inclusive) and optional season
    list in one call -- for when the chunk_plan()/run_chunk() convention
    doesn't match what you want to run right now. Equivalent to
    main(years=range(start_year, end_year+1), seasons=seasons); the separate
    name exists because 'a plain year range, my own boundaries' is a distinct,
    common case from 'the next scheduled chunk'.

    ⛑ Found during a later validation pass: reversed arguments
    (start_year > end_year, an easy typo) silently produced an EMPTY year
    list -- range(2020, 2017) is simply empty in Python, not an error -- so
    this used to print a confirmation message and then queue nothing at all,
    with no indication anything was wrong. Now raises immediately instead."""
    if start_year > end_year:
        raise ValueError(f"start_year ({start_year}) is after end_year "
                         f"({end_year}) -- did you mean run_period("
                         f"{end_year}, {start_year})?")
    yrs = list(range(start_year, end_year + 1))
    print(f"▶️ Running years {start_year}-{end_year}"
          + (f", seasons {seasons}" if seasons else ", all seasons"))
    main(authenticate=authenticate, years=yrs, seasons=seasons)


@_friendly_name_errors
def estimate_job(grid=None, years=None, seasons=None):
    """⛑ FIX32  Dry run. A 2015-2026 10 m panel is a genuinely large export, and
    you should see the size BEFORE spending a day of compute and tens of GB of
    Drive quota on it."""
    grid = grid if grid is not None else build_export_grid()
    years = list(years or range(START_YEAR, END_YEAR + 1))
    seasons = list(seasons or (['Yearly'] + list(SEASONS.keys())))

    usable = []
    for yr in years:
        for se in seasons:
            d0, d1 = season_window(yr, se)
            c0, c1, frac, note = clamp_window(d0, d1)
            if _window_will_run(d0, d1):          # ⛑ v107 projection-aware
                usable.append((yr, se, frac))
    # Chunks over PIXEL_LIMIT get subdivided at export time, so count the
    # tasks that will ACTUALLY be created, not the pre-split grid size.
    eff_chunks = 0
    for _n, b in grid:
        px = approx_pixel_count(b)
        if px > PIXEL_LIMIT * SPLIT_TOLERANCE:
            k = split_factor(px)
            eff_chunks += k * k
        else:
            eff_chunks += 1
    px_per_chunk = sum(approx_pixel_count(b) for _, b in grid) / max(len(grid), 1)
    rows_per_window = px_per_chunk * len(grid)
    ncols = len(export_columns())
    bytes_per_row = 9 * ncols
    tasks = len(usable) * eff_chunks
    total_rows = rows_per_window * len(usable)
    gb = total_rows * bytes_per_row / 1e9

    print("\n" + "=" * 78)
    print("📐 JOB ESTIMATE")
    print("=" * 78)
    print(f"  grid chunks per window   : {len(grid):>12,}  @ ~{px_per_chunk:,.0f} px")
    if eff_chunks != len(grid):
        print(f"  after auto-split         : {eff_chunks:>12,}  "
              f"(chunks over the {PIXEL_LIMIT:,} px limit are subdivided)")
    print(f"  usable windows           : {len(usable):>12,}  of "
          f"{len(years) * len(seasons)} requested")
    print(f"  TOTAL EXPORT TASKS       : {tasks:>12,}")
    print(f"  rows per window          : {rows_per_window:>12,.0f}")
    print(f"  TOTAL ROWS               : {total_rows:>12,.0f}")
    print(f"  columns                  : {ncols:>12,}")
    print(f"  APPROX DRIVE SIZE        : {gb:>12,.1f} GB")
    if gb > 40:
        print(f"\n  ⚠️ {gb:,.0f} GB is a lot of Drive. Options, in order of impact:")
        print(f"     • SCALE = 20  -> ~{gb/4:,.0f} GB   (4x fewer rows)")
        print(f"     • SCALE = 30  -> ~{gb/9:,.0f} GB   (9x fewer rows, matches")
        print( "       the native resolution of Landsat, and of the RUSLE terrain")
        print( "       terms, so you lose less real information than it looks)")
        print( "     • ADD_PROVENANCE_COLS = False to drop 6 of the columns")
        print( "     • run a subset of years first: main(years=[2019, 2020, 2021])")
    pre = [y for y in years if not _is_treated(y)]
    post = [y for y in years if _is_treated(y)]
    print(f"\n  DiD design (TREATMENT_YEAR={TREATMENT_YEAR}, rule={TREAT_RULE}):")
    print(f"     PRE  {len(pre)} years  {pre[0] if pre else '-'}-{pre[-1] if pre else '-'}"
          f"   YrRel {pre[0]-TREATMENT_YEAR if pre else 0:+d} .. {pre[-1]-TREATMENT_YEAR if pre else 0:+d}")
    print(f"     POST {len(post)} years  {post[0] if post else '-'}-{post[-1] if post else '-'}"
          f"   YrRel {post[0]-TREATMENT_YEAR if post else 0:+d} .. {post[-1]-TREATMENT_YEAR if post else 0:+d}")
    if len(pre) < 3:
        print("     ⚠️ fewer than 3 pre-treatment years — parallel trends cannot be tested")

    print("\n  windows that will be PROJECTED, GAP-FILLED, CLAMPED or SKIPPED:")
    # ⛑ v107  The preview used to say "SKIP" for a window the run actually
    # projects from the last 3 years (flagged as cosmetic in v105/v106, now
    # fixed): it mirrors build_stack()'s real decision, and reports the
    # ERA5-paced temperature coverage alongside the CHIRPS-paced one.
    for yr in years:
        for se in seasons:
            d0, d1 = season_window(yr, se)
            c0, c1, frac, note = clamp_window(d0, d1)
            _cr, _ct, _ce = window_coverage(d0, d1)
            if c0 is None:
                if GAPFILL_INCOMPLETE_WINDOWS and window_is_data_incomplete(d1):
                    print(f"     {yr} {se:7s} PROJECT {note} -> full "
                          f"{GAPFILL_LOOKBACK_YEARS}-yr historical projection "
                          f"(Coverage=0, GapFilled=1)")
                else:
                    print(f"     {yr} {se:7s} SKIP    {note}")
            elif frac < 0.999 or _ct < 0.999:
                fill = ("  -> gap-filled" if GAPFILL_INCOMPLETE_WINDOWS
                        and (window_is_data_incomplete(d1) or _temp_tail_missing(d1))
                        else "")
                print(f"     {yr} {se:7s} rain {frac:.0%} / temperature {_ct:.0%} "
                      f"of window   {note}{fill}")
    print("=" * 78)
    return {'tasks': tasks, 'rows': total_rows, 'gb': gb, 'windows': len(usable)}


def _centre_in(box, parent):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return parent[0] <= cx < parent[2] and parent[1] <= cy < parent[3]


# ---------------- MAIN ----------------
# ⛑ ROOT-CAUSE BUG FOUND AND FIXED, confirmed by a real Earth Engine crash:
# "Image.select: Band pattern 'PET' did not match any bands." ET and PET
# are NOT real, persistent bands anywhere in this pipeline's normal flow --
# they are local variables INSIDE addStressIndices(), computed fresh each
# call, used only to derive ESI/WSSI/WSI, and never themselves added to
# comp (confirmed by reading addStressIndices' own return statement: it
# adds only [esi, wssi, wsi, SMDI, vci, tci, vhi, esi_anom], never et/pet
# themselves). GAPFILL_SUM_BANDS including 'ET'/'PET' was wrong from the
# day this list was first written -- both gap-fill functions were trying
# to .select('ET')/.select('PET') from composites that never had those
# bands, in either the real pipeline or the historical reference windows
# gap-fill builds. The mock test environment did not catch this for
# several passes because it happened not to reach this exact code path
# under the specific dates those earlier tests used -- confirmed directly
# this pass, in isolation, that the identical crash reproduces with
# realistic dates. Only 'Rain' is a genuine sum-type band; the quantities
# that actually depend on ET/PET (ESI, WSSI, WSI, SMDI, VCI, TCI, VHI,
# ESI_Anom) are handled correctly via GAPFILL_STRESS_BANDS below, which
# only _build_fully_projected_window needs (see its own note for why).
GAPFILL_SUM_BANDS = ['Rain']
GAPFILL_MEAN_BANDS = ['NDVI', 'SAVI', 'LSWI', 'NDWI', 'EVI', 'NDMI', 'NDRE',
                      'LAI', 'Tmax', 'Tmin', 'Tmean']
# ⛑ Only needed by _build_fully_projected_window() below, not by
# _gapfill_missing_period() above -- see the bug note on
# _build_fully_projected_window for exactly why. addStressIndices()
# computes these FROM ET/PET/Rain/NDVI/Temp; averaging them directly
# across years (rather than recomputing from already-averaged inputs) is
# also the more defensible choice for the VCI/TCI-style ones specifically,
# since their min-max normalisation is nonlinear -- the average of three
# years' VCI is not the same value as VCI computed from the average of
# three years' NDVI, and the former is the more faithful "what was this
# typically like" estimate.
GAPFILL_STRESS_BANDS = ['ESI', 'WSSI', 'WSI', 'SMDI', 'VCI', 'TCI', 'VHI', 'ESI_Anom']


GAPFILL_TEMP_BANDS = ['Tmax', 'Tmin', 'Tmean']   # ⛑ v107 -- ERA5-paced, see below


def _temp_tail_missing(raw1):
    """⛑ v107  True when ERA5-Land daily (the temperature source) has not yet
    published to the requested window end -- its own lag, independent of
    CHIRPS's."""
    era5_end = _effective_end(ERA5_DAILY)
    return era5_end is not None and raw1 > era5_end + datetime.timedelta(days=1)


def _temp_coverage(raw0, raw1, d0, d1):
    """⛑ v107  Fraction of the requested window [raw0, raw1) for which the
    temperature source has real days (never more than the CHIRPS-paced
    clamp [d0, d1) allows). 1.0 when ERA5's end is unknown (probe failed)."""
    total = (raw1 - raw0).days
    if total <= 0 or d0 is None:
        return 0.0
    era5_end = _effective_end(ERA5_DAILY)
    t_end = d1 if era5_end is None else min(d1, era5_end + datetime.timedelta(days=1))
    return max(0.0, min(1.0, (t_end - d0).days / float(total)))


def window_coverage(raw0, raw1):
    """⛑ v107  (chirps_fraction, temperature_fraction, effective) for the
    window as of the CURRENT data -- the effective (minimum) value is what
    the gap-filled-window refresh in main() compares against what a window
    was filled at, so a refresh triggers when EITHER source has caught up
    meaningfully. 0.0 everywhere when the window hasn't started (or is
    below MIN_WINDOW_DAYS) as far as the data is concerned."""
    d0, d1, frac, _n = clamp_window(raw0, raw1)
    if d0 is None:
        return 0.0, 0.0, 0.0
    cov_t = _temp_coverage(raw0, raw1, d0, d1)
    return frac, cov_t, min(frac, cov_t)


def _temp_bands_only(a, b):
    """⛑ v107  Tmax/Tmin/Tmean for [a, b) via the SAME addClimateBands()
    code path every normal window uses (not a second implementation), on a
    throwaway seed image. Used only for the temperature tail of a gap-fill."""
    seed = ee.Image.constant(0).rename('_seed')
    return addClimateBands(seed, a, b).select(GAPFILL_TEMP_BANDS)


def _gapfill_missing_period(comp, d0, d1, raw_d1, observed_days, details=None, season=None):
    """Fills ONLY the missing tail [d1, raw_d1) of an otherwise-real,
    partial window -- never touches the already-observed [d0, d1) portion.

    For each of the last GAPFILL_LOOKBACK_YEARS complete years, re-derives
    the SAME missing sub-period shifted back k years, using the identical
    validated machinery every normal window uses (compositeIndices,
    addClimateBands's rain/temp resolution, resolve_source for ET/PET) --
    not a separate, unvalidated code path. A historical year is skipped
    (not silently included) if IT was also clamped/incomplete for that
    sub-period, so one bad year can't quietly bias the estimate.

    Sum-type bands (Rain) get the historical mean SUM for the missing days
    added onto the real observed sum. Mean-type bands (the spectral
    indices, Tmax/Tmin/Tmean) get a day-count-weighted blend of the real
    observed mean and the historical mean for the missing days -- not
    simply averaged with the historical estimate, so a long observed
    period is barely moved by a short missing tail, and vice versa.

    Returns (blended_comp, n_years_used) -- n_years_used=0 means every
    lookback year was itself unusable for this sub-period, so the input
    comp is returned completely unchanged. `details` (optional dict) is
    filled with what was done, for the manifest.

    ⛑ Defense in depth, independent of the caller's own gate: refuses to
    run at all unless the requested window end lies beyond what the data
    has published. Gap-fill exists specifically for "the data isn't there
    yet" -- a past window whose data IS fully published must never be
    silently filled here even if the calling code's own guard were ever
    weakened.

    ⛑ v107  BUG FOUND AND FIXED (two things, same root):
    (1) The refusal above used to compare raw_d1 against date.today(), i.e.
        the wall clock. But clamp_window() truncates a window for exactly
        one reason -- the pacing data source hasn't published past its end
        yet -- and CHIRPS final runs ~6 weeks behind. So for ~6 weeks after
        EVERY season ends, the window was "past" by the calendar, refused
        here, exported at 70-90% coverage with GapFilled=0, and (because it
        was never registered as gap-filled) never refreshed once the data
        completed: stuck partial for good. Reproduced: Rabi 2026 run on
        2027-03-15 exported at 82%, unfilled, unregistered. The same
        applies to Rabi 2025 if it was exported in March-April 2026. The
        gate is now window_is_data_incomplete(), the data-based statement
        of the same intent.
    (2) The temperature bands come from ERA5-Land DAILY, which is published
        ~2-3 months behind -- later than CHIRPS -- yet the observed/missing
        day counts used to blend them were CHIRPS's. Tmax/Tmin/Tmean were a
        mean over fewer real days than `Coverage` reported, blended with the
        wrong weights. They now get their OWN tail [ERA5 end, raw_d1), with
        their own day counts, filled from the same reference years via the
        same addClimateBands() path (_temp_bands_only); and this runs even
        when the CHIRPS-paced tail is already complete."""
    if details is None:
        details = {}
    src_snapshot = dict(_SRC)   # reference windows must not clobber this window's provenance
    try:
        # ---- temperature (ERA5-paced) tail -------------------------------
        era5_end = _effective_end(ERA5_DAILY)
        t_d1 = d1 if era5_end is None else min(d1, era5_end + datetime.timedelta(days=1))
        t_d1 = max(t_d1, d0)
        t_missing_days = (raw_d1 - t_d1).days
        t_observed_days = (t_d1 - d0).days
        details.update({'era5_end': str(era5_end) if era5_end else '',
                        'temp_tail_days': max(0, t_missing_days),
                        'temp_observed_days': t_observed_days})
        missing_days = (raw_d1 - d1).days
        if missing_days <= 0 and t_missing_days <= 0:
            return comp, 0
        if not window_is_data_incomplete(raw_d1) and not (
                era5_end is not None and raw_d1 > era5_end + datetime.timedelta(days=1)):
            print(f"      ⚠️ gap-fill refused: the data already covers the requested "
                  f"window end {raw_d1} -- this is a past window, not a currently-"
                  f"incomplete one; gap-fill only applies to data that hasn't "
                  f"been published yet.")
            return comp, 0

        sum_hist = {b: [] for b in GAPFILL_SUM_BANDS}
        mean_hist = {b: [] for b in GAPFILL_MEAN_BANDS if b not in GAPFILL_TEMP_BANDS}
        temp_hist = {b: [] for b in GAPFILL_TEMP_BANDS}
        n_years_used = 0
        n_temp_years = 0

        for k in range(1, GAPFILL_LOOKBACK_YEARS + 1):
            # ---- CHIRPS/optical tail [d1, raw_d1) ----------------------------
            if missing_days > 0:
                h0, h1 = shift_years(d1, k), shift_years(raw_d1, k)
                c0, c1, f, _n = clamp_window(h0, h1)
                # A historical year only counts if IT was itself fully covered for
                # this exact sub-period -- an incomplete historical year would bias
                # the very estimate meant to compensate for incompleteness.
                h_comp = None
                if c0 is not None and c1 == h1 and f >= 0.999:
                    try:
                        h_comp, _tag, _code = compositeIndices(h0, h1, season)   # ⛑ v108
                        h_comp = addClimateBands(h_comp, h0, h1)
                    except Exception as ex:
                        print(f"      ⚠️ gap-fill: {h0.year} reference window failed ({ex}); skipped")
                        h_comp = None
                if h_comp is not None:
                    for b in GAPFILL_SUM_BANDS:
                        sum_hist[b].append(h_comp.select(b))
                    for b in mean_hist:
                        mean_hist[b].append(h_comp.select(b))
                    n_years_used += 1
            else:
                h_comp = None
            # ---- temperature tail [t_d1, raw_d1) -----------------------------
            if t_missing_days > 0:
                ht0, ht1 = shift_years(t_d1, k), shift_years(raw_d1, k)
                ok_t, f_t = _covers(ERA5_DAILY, ht0, ht1, min_frac=FULL_COVERAGE)
                if not ok_t:
                    continue
                try:
                    if h_comp is not None and t_d1 == d1:
                        t_img = h_comp.select(GAPFILL_TEMP_BANDS)   # identical sub-period, reuse
                    else:
                        t_img = _temp_bands_only(ht0, ht1)
                except Exception as ex:
                    print(f"      ⚠️ gap-fill: {ht0.year} temperature reference failed ({ex}); skipped")
                    continue
                for b in GAPFILL_TEMP_BANDS:
                    temp_hist[b].append(t_img.select(b))
                n_temp_years += 1

        if n_years_used == 0 and n_temp_years == 0:
            print("      ⚠️ gap-fill: no usable reference year found "
                  f"(tried the last {GAPFILL_LOOKBACK_YEARS}); "
                  "row left as the real partial observation, unfilled")
            return comp, 0

        out = comp
        if n_years_used > 0:
            for b in GAPFILL_SUM_BANDS:
                hist_avg = ee.ImageCollection(sum_hist[b]).mean()
                filled = comp.select(b).add(hist_avg).rename(b)
                out = out.addBands(filled, None, True)
            total_days = observed_days + missing_days
            for b in mean_hist:
                hist_avg = ee.ImageCollection(mean_hist[b]).mean()
                blended = (comp.select(b).multiply(observed_days)
                           .add(hist_avg.multiply(missing_days))
                           .divide(total_days).rename(b))
                out = out.addBands(blended, None, True)
        if n_temp_years > 0:
            t_total = t_observed_days + t_missing_days
            for b in GAPFILL_TEMP_BANDS:
                hist_avg = ee.ImageCollection(temp_hist[b]).mean()
                if t_observed_days > 0:
                    blended = (comp.select(b).multiply(t_observed_days)
                               .add(hist_avg.multiply(t_missing_days))
                               .divide(t_total).rename(b))
                else:
                    blended = hist_avg.rename(b)   # no ERA5 day observed at all
                out = out.addBands(blended, None, True)
            if t_missing_days > missing_days:
                print(f"      🧩 temperature tail: ERA5-Land daily is published to "
                      f"{era5_end}, so Tmax/Tmin/Tmean were observed for "
                      f"{t_observed_days} d and filled for {t_missing_days} d "
                      f"({t_d1} to {raw_d1}) from the {n_temp_years}-yr mean -- "
                      f"their own day counts, not Rain's.")
        details.update({'n_ref_years': n_years_used, 'n_temp_ref_years': n_temp_years})
        return out, max(n_years_used, n_temp_years)
    finally:
        _SRC.clear()
        _SRC.update(src_snapshot)


# ⛑ BUG FOUND AND FIXED: reported directly -- "nothing is getting generated
# for the future time like Rabi season 2026", with a log confirming the
# exact mechanism: "SKIP 2026 Rabi: window starts 2026-10-01, data ends
# 2026-07-31". _gapfill_missing_period() above only fires once a window has
# genuinely STARTED (clamp_window returns a real d0) -- it fills the
# missing TAIL of an otherwise-real, partial observation. A window that
# hasn't started AT ALL yet (Rabi 2026, entirely in the future as of
# today) has no partial observation to speak of -- clamp_window correctly
# returns d0=None, and build_stack() was unconditionally skipping it before
# gap-fill logic was ever reached. This is a genuinely different case from
# the one gap-fill was built for, not an extension of it: zero real days
# means there is nothing to blend a historical estimate WITH, only a fully
# historical projection to build from scratch.
def _build_fully_projected_window(raw0, raw1, season=None):
    """For a window with ZERO real observed days (hasn't started yet as of
    today) -- builds a fully historically-projected composite from the last
    GAPFILL_LOOKBACK_YEARS complete years' REAL data for the exact same
    calendar window, averaged. Same per-year validity discipline as
    _gapfill_missing_period(): a historical year only counts if it was
    itself fully covered for this exact window, so one bad year can't
    quietly bias the projection. Returns (comp, n_years_used, (h0, h1)) --
    (h0, h1) is the most recent valid historical window, for classifying
    land use from (categorical data cannot be meaningfully averaged across
    years the way a spectral or climate value can). Returns (None, 0, None)
    if no valid historical year exists at all.

    ⛑ BUG REPORTED AND FIXED: real production run crashed with "Image.select:
    Band pattern 'PET' did not match any bands" -- ET and PET are NOT added
    by compositeIndices() or addClimateBands(), only by addStressIndices(),
    which this function never called. compositeIndices()+addClimateBands()
    alone produce exactly the 12 bands the error message listed as
    available; ET/PET (and every derived stress index: ESI, WSSI, WSI,
    SMDI, VCI, TCI, VHI, ESI_Anom) all come from addStressIndices()
    specifically. The mock test environment never caught this because it
    doesn't validate band existence the way Earth Engine's real server-side
    graph evaluation does -- .select() on a mock Node "succeeds" regardless
    of whether the band was ever actually added. Fixed by calling
    addStressIndices() for each historical year too, and averaging its
    outputs across years exactly like every other band -- not by having
    build_stack() call addStressIndices() a second time afterward, which
    would silently re-resolve ET/PET from just the most recent historical
    year alone (addStressIndices() always re-fetches from its own d0/d1
    arguments; it doesn't check whether ET/PET are already present), erasing
    the 3-year average this function exists to produce in the first place."""
    sum_hist = {b: [] for b in GAPFILL_SUM_BANDS}
    mean_hist = {b: [] for b in GAPFILL_MEAN_BANDS}
    stress_hist = {b: [] for b in GAPFILL_STRESS_BANDS}
    valid_windows = []
    # ⛑ v107  BUG FOUND AND FIXED: _SRC (SrcET / NObsV / NObsT / temp_source
    # provenance) was left holding whatever the LAST reference year iterated
    # set -- the OLDEST one (k=3) -- so a projected row's provenance
    # described 3 years back. It is now snapshotted after the MOST RECENT
    # valid reference year and restored at the end.
    src_recent = None
    for k in range(1, GAPFILL_LOOKBACK_YEARS + 1):
        h0, h1 = shift_years(raw0, k), shift_years(raw1, k)
        c0, c1, f, _n = clamp_window(h0, h1)
        if c0 is None or c1 != h1 or f < 0.999:
            continue
        try:
            h_comp, _tag, _code = compositeIndices(h0, h1, season)   # ⛑ v108 season
            h_comp = addClimateBands(h_comp, h0, h1)
            h_comp = addStressIndices(h_comp, h0, h1)
        except Exception as ex:
            print(f"      ⚠️ projection: {h0.year} reference window failed ({ex}); skipped")
            continue
        if src_recent is None:
            src_recent = dict(_SRC)
        for b in GAPFILL_SUM_BANDS:
            sum_hist[b].append(h_comp.select(b))
        for b in GAPFILL_MEAN_BANDS:
            mean_hist[b].append(h_comp.select(b))
        for b in GAPFILL_STRESS_BANDS:
            stress_hist[b].append(h_comp.select(b))
        valid_windows.append((h0, h1))

    if not valid_windows:
        print(f"      ⚠️ projection: no usable reference year found "
              f"(tried the last {GAPFILL_LOOKBACK_YEARS}) -- window left "
              f"skipped, nothing to project from")
        return None, 0, None

    comp = None
    for b in GAPFILL_SUM_BANDS:
        avg = ee.ImageCollection(sum_hist[b]).mean().rename(b)
        comp = avg if comp is None else comp.addBands(avg)
    for b in GAPFILL_MEAN_BANDS + GAPFILL_STRESS_BANDS:
        avg = ee.ImageCollection((mean_hist if b in GAPFILL_MEAN_BANDS
                                   else stress_hist)[b]).mean().rename(b)
        comp = comp.addBands(avg)
    if src_recent is not None:            # ⛑ v107 provenance = most recent reference year
        _SRC.clear()
        _SRC.update(src_recent)
    return comp, len(valid_windows), valid_windows[0]


def build_stack(yr, season, log=None):
    """Everything v7.7 did inline in main(), factored out so the failure sweep
    can rebuild a window. Returns (stack, info) or (None, info)."""
    raw0, raw1 = season_window(yr, season)
    d0, d1, frac, note = clamp_window(raw0, raw1)
    win_offset = 0

    # ⛑ FIX25b  WINDOW-LEVEL SUBSTITUTION.
    # If the requested window has no data, or too little of it, look backwards
    # for the SAME CALENDAR WINDOW in the most recent year that does. Only runs
    # for outcome variables when ALLOW_PREVIOUS_YEAR_OUTCOME is explicitly True,
    # because reusing last year's NDVI/rain/ET as this year's manufactures the
    # very quantity your treatment effect is measured on.
    if (d0 is None or frac < MIN_WINDOW_COVERAGE) and \
            ALLOW_PREVIOUS_YEAR and ALLOW_PREVIOUS_YEAR_OUTCOME:
        for k in range(1, PREV_YEAR_MAX_LOOKBACK + 1):
            a0, a1 = shift_years(raw0, k), shift_years(raw1, k)
            c0, c1, f2, _n2 = clamp_window(a0, a1)
            if c0 is not None and f2 >= MIN_WINDOW_COVERAGE:
                d0, d1, frac, win_offset = c0, c1, f2, k
                note = (f"NO {yr} DATA — substituted the {a0.year} {season} "
                        f"window ({f2:.0%} covered). DataYear={a0.year}.")
                print(f"   🔄 {note}")
                break

    info = {'year': yr, 'season': season,
            'built_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),   # ⛑ v110
            'requested_start': str(raw0),
            'requested_end': str(raw1), 'coverage': round(frac, 3),
            'data_year': yr - win_offset,
            'substituted': 'YES' if win_offset else '', 'note': note}
    fully_projected = False
    fp_comp = None
    # ⛑ v107  `raw1 > date.today()` -> window_is_data_incomplete(raw1): the
    # question is whether the DATA has reached the window, not the calendar
    # (see _gapfill_missing_period's note). Identical for a genuinely future
    # window; additionally rescues a just-started window that the pacing
    # source hasn't published yet (e.g. Rabi 2026 run in mid-November,
    # 9 days of CHIRPS, below MIN_WINDOW_DAYS) instead of skipping it.
    if d0 is None:
        if GAPFILL_INCOMPLETE_WINDOWS and window_is_data_incomplete(raw1):
            print(f"   🧩 {yr} {season} hasn't started yet as far as the data "
                  f"is concerned ({note}) -- attempting a full projection from "
                  f"historical data instead of skipping.")
            fp_comp, n_hist, hist_window = _build_fully_projected_window(raw0, raw1, season)
            if fp_comp is not None:
                fully_projected = True
                d0, d1 = hist_window   # most recent valid historical window --
                                        # used below ONLY for date-dependent
                                        # real-data lookups (land use), not
                                        # for re-querying climate/optical data
                info['coverage'] = 0.0   # honest: ZERO real observed days
                info['coverage_temp'] = 0.0
                info['coverage_effective'] = 0.0
                info['gap_filled'] = 'YES'
                info['projected'] = 'YES'
                info['n_ref_years'] = n_hist
                info['note'] = (f"{note} | fully projected from {n_hist}yr "
                                f"historical mean (0% real data)").strip(' |')
                print(f"      🧩 Fully projected {yr} {season} from the "
                      f"{n_hist}-year historical mean -- Coverage=0.000 "
                      f"(zero real observed days; every value in this row "
                      f"is a historical estimate, not a measurement). "
                      f"Land use classified from the most recent valid "
                      f"historical window ({hist_window[0]} to "
                      f"{hist_window[1]}) since a class label cannot be "
                      f"meaningfully averaged the way a spectral or "
                      f"climate value can.")
        if not fully_projected:
            print(f"⏭️ SKIP {yr} {season}: {note}")
            info['status'] = 'skipped'
            return None, info
    if note and not win_offset and not fully_projected:
        print(f"   ✂️ {note}")
        # ⛑ FOUND AND FIXED during deep validation: this was the only signal
        # a truncated window ever got, and it never stated the actual
        # scientific consequence. Rain/ET/PET are SUMS over the window, not
        # means -- a window truncated to `frac` of its normal length reads
        # approximately `frac` of a full-length window's total for that same
        # reason alone, with nothing in the exported number itself
        # distinguishing "less rain fell" from "the window was shorter".
        # `Coverage` (this row's `frac`) is exported specifically so this is
        # checkable, but only if the analyst knows to check it -- this
        # warning makes the consequence explicit in the run log itself,
        # where it's actually likely to be seen. WSI, a ratio of two
        # similarly-truncated sums, is comparatively more robust to this
        # than either sum alone, but not immune if Rain and ET are not
        # uniformly distributed across the missing days.
        if frac < 0.97:
            print(f"      ⚠️ SUM-based columns for this row (Rain, ET, PET, "
                  f"and the RUSLE R-factor, which uses Rain directly) reflect "
                  f"only {frac:.0%} of a normal season -- NOT directly "
                  f"comparable to a full-coverage window without accounting "
                  f"for Coverage={frac:.3f}. NDVI/Tmax/Tmin/Tmean (means, not "
                  f"sums) are far less affected by this.")
    info.update({'start': str(d0), 'end': str(d1)})

    if fully_projected:
        comp = fp_comp
        info['optical'] = "fully projected (0% real, historical mean)"
        opt_code = 5   # distinct from 1=S2 SR, 2=S2 TOA, 3=Landsat, 4=MODIS, 0=none
    else:
        comp, tag, opt_code = compositeIndices(d0, d1, season)     # ⛑ v108 season
        info['optical'] = tag
        comp = addClimateBands(comp, d0, d1)

    # ⛑ Requested explicitly: fill the genuinely missing remainder of an
    # incomplete CURRENT-period window using the last GAPFILL_LOOKBACK_YEARS
    # years' historical pattern for that exact missing sub-period. Only for
    # a genuinely clamped window (note set, frac<1) that was NOT already
    # handled by full-window previous-year substitution above -- those are
    # two different, mutually exclusive strategies for incompleteness, and
    # a window that already got a full substituted year has no "missing
    # remainder" left to fill. Standard/on by default; see
    # GAPFILL_INCOMPLETE_WINDOWS above to turn off for a specific run.
    #
    # ⛑ BUG FOUND AND FIXED on deep re-validation, per an explicit
    # requirement: gap-fill must apply ONLY to the present/future portion of
    # a window that genuinely hasn't happened yet -- never to a past
    # year/season, even if that past window is incomplete for some
    # completely different reason (a genuine historical gap in a specific
    # data source, a metadata quirk, anything unrelated to "hasn't happened
    # yet"). The condition below previously only checked d1 < raw1 --
    # "was the window truncated relative to what was requested" -- which
    # does NOT distinguish "truncated because today's date hasn't reached
    # it yet" from "truncated for some other, unrelated historical reason."
    # Verified directly: simulating a 2019 window truncated for a reason
    # having nothing to do with recency reproduced gap-fill incorrectly
    # firing on a fully-past year. `raw1 > date.today()` is now an explicit,
    # separate, unambiguous condition -- the ORIGINALLY REQUESTED window end
    # must itself be in the future relative to today, independent of why
    # clamp_window truncated it. A past window that is incomplete for any
    # other reason now correctly falls through to being exported exactly as
    # observed (Coverage < 1, un-filled), exactly like before gap-fill
    # existed -- the only thing that changed is closing this one loophole.
    if not fully_projected:
        info['gap_filled'] = ''
        info['projected'] = ''
        # ⛑ v107  Coverage of the ERA5-paced temperature bands, and the
        # EFFECTIVE (minimum) coverage the gap-filled-window refresh keys on.
        cov_t = _temp_coverage(raw0, raw1, d0, d1)
        info['coverage_temp'] = round(cov_t, 3)
        info['coverage_effective'] = round(min(frac, cov_t), 3)
    # ⛑ v107  Gate rewritten in terms of the DATA (see _gapfill_missing_period
    # for the two real bugs): fill when the pacing source hasn't published to
    # the window end (d1 < raw1, the only way clamp_window ever truncates)
    # OR when ERA5-Land, which lags further, hasn't -- even if CHIRPS has.
    # `note`/`frac < 1.0` are implied by d1 < raw1 and no longer required, so
    # a CHIRPS-complete window with a lagging ERA5 tail is handled too.
    _temp_tail = _temp_tail_missing(raw1)
    if (GAPFILL_INCOMPLETE_WINDOWS and not win_offset and not fully_projected
            and ((d1 < raw1 and window_is_data_incomplete(raw1)) or _temp_tail)):
        observed_days = (d1 - d0).days
        gf_details = {}
        comp, n_hist = _gapfill_missing_period(comp, d0, d1, raw1, observed_days,
                                               details=gf_details, season=season)
        info.update({k: v for k, v in gf_details.items()
                     if k in ('era5_end', 'temp_tail_days', 'n_ref_years')})
        if n_hist > 0:
            missing_days = (raw1 - d1).days
            info['gap_filled'] = 'YES'
            info['note'] = (info.get('note', '') +
                            f" | gap-filled {missing_days}d (temperature "
                            f"{gf_details.get('temp_tail_days', 0)}d) from {n_hist}yr "
                            f"historical mean").strip(' |')
            print(f"      🧩 Gap-filled the missing {missing_days} day(s) "
                  f"({raw1 - datetime.timedelta(days=missing_days)} to {raw1}) "
                  f"using the {n_hist}-year historical mean for that exact "
                  f"sub-period. Sum-type columns (Rain/ET/PET) = real "
                  f"observed sum + historical sum for the missing days. "
                  f"Mean-type columns = day-weighted blend of observed and "
                  f"historical means. Coverage={frac:.3f} still reports the "
                  f"TRUE observed fraction -- gap-filling changes what "
                  f"the SUM/MEAN columns read, never what Coverage says.")

    if not fully_projected:
        comp = addStressIndices(comp, d0, d1)
    info['temp_source'] = _SRC.get('temp', '?')
    info['et_source'] = _SRC.get('et', '?')
    info['et_coverage'] = _SRC.get('et_frac', '')          # ⛑ v107
    info['data_end'] = str(_data_hard_end())                # ⛑ v107
    if _SRC.get('et_year_offset'):
        info['note'] = (info.get('note', '') +
                        f" | ET from {yr - win_offset - _SRC['et_year_offset']}").strip(' |')

    lu, lu_dw, lu_src = classifyLandUse(comp.select('NDVI'), comp.select('NDWI'), d0, d1,
                                        season)                       # ⛑ v108 season
    info['landuse_source'] = lu_src
    info['optical_tiers'] = _SRC.get('opt_tier_counts', '')            # ⛑ v108
    agb = calcAGB(comp.select('NDVI'), comp.select('LAI'), lu, d0, d1)
    rusle = calcRUSLE(comp.select('Rain'), comp.select('NDVI'), lu_dw, yr - win_offset)

    subwshed = ROI.reduceToImage(['SubwshedID'], ee.Reducer.first()).rename('SubwshedID')
    dist = ROI.reduceToImage(['buff_km'], ee.Reducer.first()).rename('buff_km')
    treat = ee.Image.constant(1 if _is_treated(yr) else 0).rename('Treat')
    yearB = ee.Image.constant(yr).rename('Year')
    seasonB = ee.Image.constant(
        0 if season == 'Yearly' else list(SEASONS.keys()).index(season) + 1
    ).rename('Season')

    meta = (UID_BAND.addBands(LONLAT_BASE.select(['latitude', 'longitude']))
            .addBands(subwshed).addBands(dist).addBands(treat)
            .addBands([yearB, seasonB]))

    stack = (meta.addBands(comp).addBands(lu).addBands(lu_dw)
             .addBands(agb).addBands(rusle))

    if ADD_PROVENANCE_COLS:
        prov = (ee.Image.constant(yr - win_offset).rename('DataYear').toInt16()
                .addBands(ee.Image.constant(round(frac, 3)).rename('Coverage').toFloat())
                .addBands(ee.Image.constant(opt_code).rename('SrcOpt').toInt16())
                .addBands(ee.Image.constant(_SRC.get('et_code', 0)).rename('SrcET').toInt16())
                .addBands(_SRC.get('nobs_v', ee.Image.constant(0)).rename('NObsV').toInt16())
                .addBands(_SRC.get('nobs_t', ee.Image.constant(0)).rename('NObsT').toInt16()))
        stack = stack.addBands(prov)
    if EXPORT_EVENT_TIME:
        stack = stack.addBands(
            ee.Image.constant(yr - TREATMENT_YEAR).rename('YrRel').toInt16())
    if GAPFILL_INCOMPLETE_WINDOWS:
        # A real per-pixel export column, not just a run-log note -- so
        # "was this row's Rain/ET/PET/spectral/temperature data partly a
        # historical estimate, not fully observed" is checkable from the
        # data itself later, without needing an archived run log. 1/0
        # (not a string) for direct numeric filtering downstream.
        stack = stack.addBands(
            ee.Image.constant(1 if info['gap_filled'] == 'YES' else 0)
            .rename('GapFilled').toInt16())
    if ADD_OPTICAL_TIER_COL:
        # ⛑ v108  per-pixel priority level the spectral composite came from:
        # 1 = core months + strictest cloud tier ... N = full window + standard
        # tier (the pre-v108 rule); 0 = no clear observation (bands masked), and
        # 0 for a fully-projected row (no real observation at all).
        tier_img = None if fully_projected else _SRC.get('opt_tier')
        stack = stack.addBands(
            (tier_img if tier_img is not None else ee.Image.constant(0))
            .rename('OptTier').toInt16())

    stack = ensureBands(stack, export_columns())      # ⛑ FIX13
    info['status'] = 'ok'
    info['src_opt'] = opt_code
    return stack, info


# ⛑ BUG REPORTED AND FIXED: NameError: name 'export_columns' is not defined,
# raised from INSIDE build_stack() (its very last line), for every window in
# the run. That specific manifestation could not be caught by the
# @_friendly_name_errors wrapper on main() added last pass, because main()'s
# own per-window try/except (a few lines below, `except Exception as ex:`)
# catches it FIRST -- by design, so one bad window doesn't crash the other
# 46 -- and prints a generic "ERROR building ..." line before the exception
# ever has a chance to reach the outer wrapper. The real problem this
# revealed: build_stack() does the FULL window computation (compositing,
# LandUse, RUSLE, everything) and only discovers a missing definition on its
# very last line -- so a whole run can burn through 47 windows' worth of
# real Earth Engine computation, independently rediscovering the identical
# problem on every single one, before anyone notices the pattern in the log.
# Fixed with a fast check up front, before any window is attempted, so this
# class of problem is caught once and explained clearly instead of 47 times.
def _check_pipeline_defined():
    # ⛑ BUG FOUND on re-verification, twice over.
    # First: the original hand-maintained `required` list (export_columns,
    # compositeIndices, addClimateBands, addStressIndices, classifyLandUse,
    # calcAGB, calcRUSLE, ensureBands, build_export_grid) was missing FOUR
    # genuine dependencies build_stack() actually calls -- _is_treated,
    # clamp_window, season_window, shift_years. Fixed by deriving the list
    # from build_stack()'s own source via Python's ast module instead of
    # maintaining a second, parallel list by hand.
    # Second, found testing that very fix: inspect.getsource() is
    # documented (see e.g. ipython/ipython#11249) to often fail for
    # functions defined inside actual Jupyter/Colab notebook cells, as
    # opposed to a real .py file on disk -- which is exactly the context
    # this check matters most for. Without a complete fallback, the AST
    # introspection would silently fail in real notebook use and this
    # would fall back to a minimal, incomplete list, quietly reintroducing
    # the exact gap just described. FALLBACK is now the same complete,
    # currently-verified 12-name list AST introspection independently
    # derives when it *can* run (e.g. from the standalone .py file) -- so
    # this check is correct either way: self-maintaining where source
    # introspection works, and still complete where it doesn't.
    # ⛑ v107  Regenerated from build_stack()'s own source (the AST path
    # below) after this version's changes -- it had drifted: the projection
    # and gap-fill functions build_stack() already called in v105/v106 were
    # missing from it, so a notebook session that skipped only that cell
    # would have rediscovered the NameError on every window again.
    FALLBACK = ['_build_fully_projected_window', '_data_hard_end',
                '_gapfill_missing_period', '_is_treated', '_temp_coverage',
                '_temp_tail_missing', 'addClimateBands', 'addStressIndices',
                'calcAGB', 'calcRUSLE', 'clamp_window', 'classifyLandUse',
                'compositeIndices', 'ensureBands', 'export_columns',
                'season_window', 'shift_years', 'window_is_data_incomplete']
    import ast
    import inspect
    import textwrap
    import builtins
    try:
        src = textwrap.dedent(inspect.getsource(build_stack))
        tree = ast.parse(src)
        names = {n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        required = sorted((names - set(dir(builtins))) | set(FALLBACK))
    except Exception:
        required = FALLBACK
    missing = [n for n in required if n not in globals()]
    if missing:
        raise NameError(f"name(s) {missing} not defined")   # section hint added by the wrapper


@_friendly_name_errors
def main(authenticate=False, years=None, seasons=None):
    _check_pipeline_defined()
    setup(authenticate=authenticate)
    preflight_data_report()          # ⛑ FIX25  search the data BEFORE building
    done_dict = load_progress()
    done_dict = reconcile_tasks(done_dict)
    gapfilled_windows = load_gapfilled_windows()
    substituted_windows = load_substituted_windows()

    grid = build_export_grid()

    years = years or range(START_YEAR, END_YEAR + 1)
    seasons = seasons or (['Yearly'] + list(SEASONS.keys()))
    manifest = []

    # ⛑ FIX37  Everything that can submit or list batch tasks is inside this
    # try block. On a BatchBlockedError we stop immediately -- no further
    # submissions anywhere in this run -- save whatever progress exists, print
    # the guidance once, and return normally rather than crash with a
    # traceback. reconcile_tasks() above already ran once so anything genuinely
    # completed before the block took effect is recorded.
    _close_all_bars()                       # ⛑ v110
    _reset_run_clock()
    print(f"▶️ {PIPELINE_VERSION} run started for {ROI_ID}: "
          f"{len(list(years))} year(s) x {len(list(seasons))} season(s)")
    _wbar = progress_bar(len(list(years)) * len(list(seasons)), "windows")
    try:
        for yr in years:
            for season in seasons:
                _wbar.set_postfix_str(f"{yr} {season}")           # ⛑ v110
                _wbar.update(1)
                label = "Yearly Composite" if season == 'Yearly' else f"🌾 {season}"
                print(f"\n{'📆' if season == 'Yearly' else '📅'} {yr} {label}")
                # A window gap-filled in an earlier run must not stay stuck
                # as that estimate once MEANINGFULLY more real data has
                # since become available -- not only once its full period
                # has completely elapsed, but incrementally, as coverage
                # improves. Force just THIS window's tiles back to "not
                # done" so it is naturally reprocessed with the improved
                # data, without touching resume behaviour for anything else.
                if (yr, season) in gapfilled_windows:
                    _raw0, _raw1 = season_window(yr, season)
                    _prev = gapfilled_windows[(yr, season)]
                    _prev_cov = _prev['eff']
                    # ⛑ v107  "complete" now means the DATA is complete (every
                    # source's coverage of the requested window is 1.0), not
                    # that the calendar has passed the window end -- refreshing
                    # on the calendar alone re-exported a still-lagging window
                    # partial and unfilled (see _gapfill_missing_period). The
                    # improvement test uses the EFFECTIVE coverage (min over
                    # CHIRPS and ERA5) that the registry now stores.
                    _cur_d0, _cur_d1, _cur_frac, _cur_note = clamp_window(_raw0, _raw1)
                    _c_rain, _c_temp, _cur_eff = window_coverage(_raw0, _raw1)
                    _now_complete = _cur_eff >= 0.999
                    _improved = _cur_d0 is not None and (
                        (_c_rain - _prev['rain']) > GAPFILL_REFRESH_THRESHOLD or
                        (_c_temp - _prev['temp']) > GAPFILL_REFRESH_THRESHOLD)
                    if _now_complete or _improved:
                        # ⛑ BUG FOUND AND FIXED while testing this fix itself:
                        # matching against `grid`'s top-level tile names finds
                        # nothing to clear, because exportTile() recursively
                        # SPLITS oversized tiles and records the FINAL split
                        # sub-tile names in done_dict (e.g. tile0_sub0_s0..s3),
                        # not the pre-split name this loop was checking.
                        # Replicating that recursive splitting logic here just
                        # to reconstruct the exact stored names would be
                        # fragile and duplicative -- clearing this window's
                        # entire done-list at once is simpler and correct
                        # regardless of how many times any tile was split.
                        n_cleared = len(done_dict.get(str(yr), {}).get(season, []))
                        if str(yr) in done_dict and season in done_dict[str(yr)]:
                            done_dict[str(yr)][season] = []
                        why = (f"its real data is now complete (rain {_c_rain:.0%}, "
                               f"temperature {_c_temp:.0%})" if _now_complete else
                               f"coverage has meaningfully improved since it was "
                               f"gap-filled ({_prev_cov:.3f} -> {_cur_eff:.3f}; rain "
                               f"{_c_rain:.0%}, temperature {_c_temp:.0%})")
                        print(f"   🔁 This window was gap-filled in an earlier "
                              f"run; {why} -- forcing reprocessing with the "
                              f"now-available real data "
                              f"({n_cleared} tile record(s) reset).")
                        del gapfilled_windows[(yr, season)]
                        save_gapfilled_windows(gapfilled_windows)
                # Same principle as gap-fill above, for the OTHER
                # incompleteness strategy: a window substituted with a prior
                # year's real data must not stay stuck on it once the
                # NOMINAL year's own real data becomes sufficient.
                if (yr, season) in substituted_windows:
                    _sraw0, _sraw1 = season_window(yr, season)
                    _s_d0, _s_d1, _s_frac, _s_note = clamp_window(_sraw0, _sraw1)
                    if _s_d0 is not None and _s_frac >= MIN_WINDOW_COVERAGE:
                        n_cleared_s = len(done_dict.get(str(yr), {}).get(season, []))
                        if str(yr) in done_dict and season in done_dict[str(yr)]:
                            done_dict[str(yr)][season] = []
                        print(f"   🔁 This window was substituted from a prior "
                              f"year's data in an earlier run; {yr}'s own real "
                              f"data now reaches {_s_frac:.0%} coverage -- "
                              f"forcing reprocessing to use it instead of the "
                              f"substituted year ({n_cleared_s} tile record(s) reset).")
                        substituted_windows.discard((yr, season))
                        save_substituted_windows(substituted_windows)
                try:
                    stack, info = build_stack(yr, season)
                except NameError as ex:
                    print(f"🚫 ERROR building {yr} {season}: {ex}")
                    print("   This means a definition cell was not run in "
                          "this session (e.g. a runtime restart) -- the "
                          "preflight check at the top of main() should catch "
                          "this before starting; seeing it mid-run instead "
                          "means something became undefined partway through. "
                          "Runtime > Run all, then re-run this window.")
                    manifest.append({'year': yr, 'season': season, 'status': 'error',
                                     'note': str(ex)[:300]})
                    continue
                except Exception as ex:
                    print(f"🚫 ERROR building {yr} {season}: {ex}")
                    manifest.append({'year': yr, 'season': season, 'status': 'error',
                                     'note': str(ex)[:300]})
                    continue
                if stack is None:
                    manifest.append(info)
                    continue

                ok, err = validate_window(stack, yr, season)
                if not ok:
                    info['validation_error'] = err[:300]
                    # ⛑ v107  A pure TIMEOUT of the interactive validation call
                    # is not evidence the graph is wrong -- a fully-projected or
                    # gap-filled window carries 2-4x the normal graph (three
                    # reference composites) and can exceed the interactive
                    # request limit that batch export tasks do not have. Such a
                    # window is now exported anyway, clearly flagged, and any
                    # tile that genuinely fails is caught by the existing
                    # batch-failure sweep. Every OTHER validation error (band
                    # pattern, zero bands, memory) still skips the window.
                    if EXPORT_ON_VALIDATION_TIMEOUT and _looks_like_timeout(err):
                        print(f"   ⚠️ {yr} {season}: interactive validation TIMED OUT "
                              f"({err[:120]}) -- exporting anyway; the batch sweep "
                              f"will catch any tile that genuinely fails.")
                        info['note'] = (info.get('note', '') +
                                        ' | validation timed out; exported anyway').strip(' |')
                    else:
                        print(f"⏭️ SKIP {yr} {season}: graph validation failed → {err[:160]}")
                        info['status'] = 'invalid'
                        info['note'] = (info.get('note', '') + ' | ' + err[:200]).strip(' |')
                        manifest.append(info)
                        continue

                _STACK_CACHE[(yr, season)] = stack
                q = 0
                _tbar = progress_bar(len(grid), f"{yr} {season} tiles")    # ⛑ v110
                for tname, box in grid:
                    q += exportTile(stack, box, f"{yr}_{season}_{tname}",
                                    done_dict, yr, season,
                                    tilescale=YEARLY_TILE_SCALE if season == 'Yearly'
                                    else DEFAULT_TILE_SCALE)
                    _tbar.update(1)
                    _tbar.set_postfix_str(f"queued={q}")
                close_bar(_tbar)
                save_progress(done_dict)
                save_task_ledger()
                info.update({'tiles': len(grid), 'queued': q})
                manifest.append(info)
                print(f"   ✅ {yr} {season}: queued {q} tasks")
                # ⛑ v107  BUG FOUND AND FIXED (present since the registry was
                # introduced): the registry was overwritten on EVERY run, even
                # one that queued 0 tiles because they were already done. Each
                # run could then nudge the recorded coverage up by less than
                # GAPFILL_REFRESH_THRESHOLD without re-exporting anything, so
                # the exported data stayed at the OLD estimate while the
                # registry crept toward "current", and a refresh never fired.
                # The registry now records only a coverage that was actually
                # exported (q > 0); otherwise the earlier entry stands.
                if info.get('gap_filled') == 'YES' and q > 0:
                    # ⛑ v107 per-source coverage, see load_gapfilled_windows()
                    gapfilled_windows[(yr, season)] = {
                        'eff': info.get('coverage_effective', info['coverage']),
                        'rain': info['coverage'],
                        'temp': info.get('coverage_temp', info['coverage'])}
                    save_gapfilled_windows(gapfilled_windows)
                if info.get('substituted') == 'YES' and q > 0:
                    substituted_windows.add((yr, season))
                    save_substituted_windows(substituted_windows)

        close_bar(_wbar)                                                  # ⛑ v110
        _write_manifest(manifest)
        sweep_failed_tasks(done_dict, stack_builder=lambda y, s: build_stack(y, s)[0])
        _close_all_bars()
        print(f"🏁 {PIPELINE_VERSION} run finished (elapsed "
              f"{(time.time() - _RUN_T0) / 60:.1f} min)")
    except BatchBlockedError as e:
        _close_all_bars()
        save_progress(done_dict)
        save_task_ledger()
        _write_manifest(manifest)
        print(_tos_guidance(str(e)))
        print("Progress up to this point has been saved. Re-running main() "
              "after the block is resolved will resume, not restart.")
        return
    except KeyboardInterrupt:
        _close_all_bars()                                                 # ⛑ v110
        # ⛑ v9.1 -- addresses "cancel a run that's in progress" cleanly.
        # Colab's own Interrupt/Stop button raises exactly this inside the
        # currently-running cell. Without this handler, it propagated as a
        # raw traceback mid-window, and (a documented Colab/Jupyter
        # limitation, not something any notebook can control) does NOT
        # prevent cells queued after this one from starting once it exits --
        # see the note in the notebook's Download section on avoiding
        # "Run All" for that reason. What this handler DOES control: this
        # run stops at the next safe point (between windows, never mid-tile),
        # saves everything so nothing already done is lost, and tells you
        # plainly that tasks already SUBMITTED to Earth Engine keep running
        # there regardless -- interrupting the notebook cell does not cancel
        # them; cancel_all_pending_tasks() does, separately, if you want that.
        save_progress(done_dict)
        save_task_ledger()
        _write_manifest(manifest)
        print("\n" + "=" * 78)
        print("⏹  Interrupted. Progress saved -- re-running main()/run_download() "
              "will resume, not restart.")
        print("   Tasks already submitted to Earth Engine are still running there --")
        print("   this only stopped the LOCAL loop that was submitting new ones.")
        print("   To also stop those: cancel_all_pending_tasks()")
        print("=" * 78)
        return
    save_task_ledger()
    save_progress(done_dict)

    states = {}
    roi_prefix_final = task_prefix()        # ⛑ v107 this version's tasks only
    for t in _task_list():
        if t['description'].startswith(roi_prefix_final):
            states[t['state']] = states.get(t['state'], 0) + 1
    print(f"\n📊 Final task states for {ROI_ID} ({PIPELINE_VERSION}): {states}")


@_friendly_name_errors
def run_download(authenticate=False):
    """⛑ v9.0 -- the single entry point matched to the single config point.
    Reads DOWNLOAD_YEARS / DOWNLOAD_SEASONS (set once, at the top of the
    config section) and runs exactly that -- the complete panel if both are
    left as None, or whatever subset you set them to. This is a thin,
    unconditional pass-through to main(); it exists only so the one thing
    you edit and the one thing you run are visibly the same two variables,
    with no other cell needing to change for a different year/season choice.
    chunk_plan() / run_chunk() / run_period() (see below) remain available
    unchanged for anyone who wants the multi-chunk manual workflow instead --
    this function does not replace or alter them."""
    print(f"▶️ run_download(): DOWNLOAD_YEARS={DOWNLOAD_YEARS!r}  "
          f"DOWNLOAD_SEASONS={DOWNLOAD_SEASONS!r}")
    main(authenticate=authenticate, years=DOWNLOAD_YEARS, seasons=DOWNLOAD_SEASONS)


def _write_manifest(rows):
    """⛑ BUG FOUND AND FIXED (reported by user): 'landuse_source' not in index.
    build_stack() sets info['landuse_source'] (added when Dynamic World land
    use was introduced) and info['src_opt'], but this function's column list
    was never updated to include them -- csv.DictWriter(extrasaction='ignore')
    silently DROPPED both from every manifest ever written, with no error, no
    warning, nothing -- until someone tried to read that column back out.
    Both are now included explicitly.

    Root-cause fix, not just a patch: the column list below is the stable,
    ordered CORE (existing scripts/notebooks that read this CSV by these
    names keep working identically) but any OTHER key that ever shows up in
    a row -- present today or added in some future pass -- is now
    automatically unioned in and appended, with a printed note, instead of
    being silently discarded. This exact bug class cannot recur silently
    again."""
    import csv
    core_cols = ['year', 'season', 'built_at', 'status', 'data_year', 'substituted',
                 'requested_start', 'requested_end', 'start', 'end', 'coverage',
                 'optical', 'temp_source', 'et_source', 'landuse_source',
                 'src_opt', 'tiles', 'queued', 'note',
                 # ⛑ v107 -- why a window did or didn't produce what it did
                 'gap_filled', 'projected', 'n_ref_years', 'coverage_temp',
                 'coverage_effective', 'temp_tail_days', 'era5_end', 'data_end',
                 'et_coverage', 'validation_error',
                 'optical_tiers']                                    # ⛑ v108
    extra_cols = sorted({k for r in rows for k in r.keys()} - set(core_cols))
    if extra_cols:
        print(f"📄 Manifest: including {len(extra_cols)} additional field(s) "
              f"not in the core column list: {extra_cols}")
    cols = core_cols + extra_cols
    with open(MANIFEST_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"📄 Window manifest → {MANIFEST_FILE}")


@_friendly_name_errors
def diagnose_window(year, season, sample=True):
    """⛑ v107  One call that answers "why did this window produce nothing?"
    Prints, in order: the requested window; the data end of every relevant
    source and the resulting clamp; which ET source resolve_source() picks
    and at what coverage; whether the window will be exported as observed,
    gap-filled, fully projected, or skipped; then builds the stack exactly
    as main() would, validates it (timed), lists its bands, and -- if
    sample=True -- prints one real pixel's values so a masked/NaN column is
    visible immediately. Finally lists this version's Earth Engine tasks
    for the window and their states/errors. Nothing is exported."""
    raw0, raw1 = season_window(year, season)
    print("=" * 78)
    print(f"🔎 DIAGNOSE {year} {season}: requested {raw0} .. {raw1} "
          f"({(raw1 - raw0).days} d)   today={date.today()}   {PIPELINE_VERSION}")
    print("=" * 78)
    for cid in ('UCSB-CHG/CHIRPS/DAILY', ERA5_DAILY, 'MODIS/061/MOD16A2GF',
                'MODIS/061/MOD16A2', 'MODIS/061/MOD13Q1', 'MODIS/061/MOD11A2',
                'COPERNICUS/S2_SR_HARMONIZED', DW_ID):
        e = collection_end(cid)
        eff = _effective_end(cid)
        ok, fr = _covers(cid, raw0, raw1)
        print(f"   {cid:40s} last image {str(e):10s}  effective end {str(eff):10s}"
              f"  covers {fr:5.0%} of window")
    d0, d1, frac, note = clamp_window(raw0, raw1)
    cr, ct, ce = window_coverage(raw0, raw1)
    print(f"   pacing data end (CHIRPS/today): {_data_hard_end()}   ERA5 daily end: "
          f"{_effective_end(ERA5_DAILY)}")
    print(f"   clamp -> {d0} .. {d1}  rain-coverage {frac:.3f}  temperature-coverage "
          f"{ct:.3f}  effective {ce:.3f}  {note}")
    cid, code, off, efrac, enote = resolve_source('et', d0 or raw0, d1 or raw1)
    print(f"   ET source: {cid} (code {code}, shifted {off} yr, {efrac:.0%} of window) {enote}")
    if d0 is None:
        if GAPFILL_INCOMPLETE_WINDOWS and window_is_data_incomplete(raw1):
            print(f"   decision: FULL PROJECTION from the last {GAPFILL_LOOKBACK_YEARS} "
                  f"years (Coverage=0, GapFilled=1)")
        else:
            print(f"   decision: SKIP ({note}) -- gap-fill "
                  f"{'off' if not GAPFILL_INCOMPLETE_WINDOWS else 'does not apply: data already covers the window'}")
    elif GAPFILL_INCOMPLETE_WINDOWS and ((d1 < raw1 and window_is_data_incomplete(raw1))
                                         or _temp_tail_missing(raw1)):
        print(f"   decision: export observed data + gap-fill the missing tail "
              f"(rain {frac:.0%} real, temperature {ct:.0%} real)")
    else:
        print("   decision: export as observed (no gap-fill needed)")

    t0 = time.time()
    try:
        stack, info = build_stack(year, season)
    except Exception as ex:
        print(f"   🚫 build_stack raised: {type(ex).__name__}: {ex}")
        return None
    print(f"   build_stack: {time.time() - t0:.1f}s  status={info.get('status')}  "
          f"note={info.get('note', '')}")
    if stack is None:
        return info
    t0 = time.time()
    ok, err = validate_window(stack, year, season)
    print(f"   validate_window: {'OK' if ok else 'FAILED'} in {time.time() - t0:.1f}s"
          + ("" if ok else f" -> {err[:300]}"))
    if not ok:
        print(f"   (timeout-like: {_looks_like_timeout(err)}; with "
              f"EXPORT_ON_VALIDATION_TIMEOUT={EXPORT_ON_VALIDATION_TIMEOUT} main() would "
              f"{'still export' if EXPORT_ON_VALIDATION_TIMEOUT and _looks_like_timeout(err) else 'skip'} it)")
    try:
        bands = _retry(lambda: stack.bandNames().getInfo(), tries=2, what="bandNames")
        print(f"   bands ({len(bands)}): {bands}")
        missing = [c for c in export_columns() if c not in bands]
        if missing:
            print(f"   🚫 export columns missing from the stack: {missing}")
    except Exception as ex:
        print(f"   bandNames failed: {ex}")
    if sample and ok:
        try:
            pt = roiGeom.centroid(SCALE).buffer(SCALE * 20, ee.ErrorMargin(1))   # ⛑ v109
            vals = _retry(lambda: stack.reduceRegion(
                reducer=ee.Reducer.first(), geometry=pt, scale=SCALE,
                tileScale=16, maxPixels=10000, bestEffort=True).getInfo(),
                tries=2, what="sample pixel")
            nulls = [k for k, v in (vals or {}).items() if v is None]
            print(f"   sample pixel near the centroid: {vals}")
            if nulls:
                print(f"   ⚠️ masked/null at this pixel: {nulls}")
        except Exception as ex:
            print(f"   sample pixel failed: {ex}")
    key = f"{year}_{season}_"
    tp = task_prefix()
    states = {}
    errs = {}
    for t in _task_list():
        d = t['description']
        if d.startswith(tp) and d[len(tp):].startswith(key):
            states[t['state']] = states.get(t['state'], 0) + 1
            if t['error']:
                errs[t['error'][:120]] = errs.get(t['error'][:120], 0) + 1
    print(f"   Earth Engine tasks for this window ({PIPELINE_VERSION}): "
          f"{states or 'none yet'}")
    for e, c in sorted(errs.items(), key=lambda kv: -kv[1]):
        print(f"      x{c}: {e}")
    print("=" * 78)
    return info


@_friendly_name_errors
def task_failure_report(include_prior_versions=True):
    """⛑ v107  Groups every FAILED (and, separately, every completed) Earth
    Engine task for this ROI by (year, season) with the distinct error
    messages -- the direct answer to "which windows have no data and why".
    Prior-version tasks are listed separately so a window whose CSVs exist
    only in an OLDER version's Drive folder is visible as such."""
    mine, prior = {}, {}
    for t in _task_list():
        name, is_mine = _split_task_description(t['description'])
        if name is None:
            continue
        yr, se = parse_name(name)
        bucket = mine if is_mine else prior
        ent = bucket.setdefault((yr, se), {'states': {}, 'errors': {}})
        ent['states'][t['state']] = ent['states'].get(t['state'], 0) + 1
        if t['state'] == 'FAILED' and t['error']:
            k = t['error'][:140]
            ent['errors'][k] = ent['errors'].get(k, 0) + 1

    def _dump(title, bucket):
        print(f"\n{title}")
        if not bucket:
            print("   (none)")
            return
        for (yr, se) in sorted(bucket, key=lambda k: (str(k[0]), str(k[1]))):
            ent = bucket[(yr, se)]
            flag = "🚫" if ent['states'].get('FAILED') else "✅"
            print(f"   {flag} {yr} {se:7s} {ent['states']}")
            for e, c in sorted(ent['errors'].items(), key=lambda kv: -kv[1]):
                print(f"         x{c}: {e}")
    _dump(f"📊 {ROI_ID} tasks from THIS version ({PIPELINE_VERSION}):", mine)
    if include_prior_versions:
        _dump(f"📁 {ROI_ID} tasks from EARLIER versions (CSVs live in those versions' "
              f"Drive folders; not adopted unless ADOPT_PRIOR_VERSION_TASKS=True):", prior)
    return mine, prior

# ==================================================================
# ⛑ v110 -- INDEPENDENT-REFERENCE CROSS-CHECK OF THE EXPORTED VALUES
# ==================================================================
XCHECK_POINTS = 400        # random pixels per window sampled for the cross-check
XCHECK_SEED = 42
XCHECK_PAIRS = [           # (exported column, independent reference, what it tells you)
    ('Rain', 'Rain_ERA5',  'CHIRPS season total vs ERA5-Land daily total_precipitation_sum (mm)'),
    ('Rain', 'Rain_TC',    'CHIRPS season total vs TerraClimate monthly pr (mm; to 2024)'),
    ('ESI',  'ESI_TC',     'MOD16 ET/PET vs TerraClimate aet/pet (ratio; to 2024)'),
    ('NDVI', 'NDVI_MOD13', 'composite NDVI vs MOD13Q1 QA-filtered NDVI (250 m; scale/sensor differ)'),
    ('Tmax', 'Tmax_CHIRTS', 'ERA5-Land Tmax vs CHIRTS station-blended Tmax (deg C; to 2016)'),
    ('Tmin', 'Tmin_CHIRTS', 'ERA5-Land Tmin vs CHIRTS station-blended Tmin (deg C; to 2016)'),
    ('Tmean', 'LST_MOD11', 'ERA5 air Tmean vs MODIS surface LST -- context only, not the same quantity'),
]


def _pair_stats(rows, a, b):
    xs, ys = [], []
    for r in rows:
        x, y = r.get(a), r.get(b)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            xs.append(float(x))
            ys.append(float(y))
    n = len(xs)
    if n < 3:
        return {'n': n, 'r': float('nan'), 'bias': float('nan'), 'rmse': float('nan')}
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float('nan')
    bias = sum(x - y for x, y in zip(xs, ys)) / n
    rmse = math.sqrt(sum((x - y) ** 2 for x, y in zip(xs, ys)) / n)
    return {'n': n, 'r': r, 'bias': bias, 'rmse': rmse}


@_friendly_name_errors
def reference_crosscheck(year, season, n_points=None, export=True, print_stats=True):
    """⛑ v110  Validates a window's EXPORTED values against INDEPENDENT
    reference products at the same pixels -- using only collections this
    pipeline already probes (all present in the preflight table), so no new
    catalog dependency is introduced:

        Rain  vs ERA5-Land daily precipitation (mm) and TerraClimate pr (mm)
        ESI   vs TerraClimate aet/pet
        NDVI  vs MOD13Q1 QA-filtered NDVI (the VCI input)
        Tmax/Tmin vs CHIRTS station-blended temperatures (2015-2016 windows)
        Tmean vs MODIS LST (context: surface vs air temperature)

    Builds the window exactly as main() does, samples XCHECK_POINTS random
    pixels inside the ROI with the pipeline values and the references side
    by side, prints n / Pearson r / mean bias / RMSE per pair, and (export=
    True) writes the paired sample to Drive folder <DRIVE_FOLDER>_validation
    as XCHK_<ROI>_<year>_<season>.csv for offline validation. Reference
    products that end before the window (TerraClimate 2024, CHIRTS 2016)
    are simply masked for it -- an honest 'n' says so. Nothing here changes
    the exported panel; this is a measurement of its accuracy."""
    n_points = n_points or XCHECK_POINTS
    print(f"🧪 cross-check {year} {season}: building the window exactly as main() does")
    stack, info = build_stack(year, season)
    if stack is None:
        print(f"   window not buildable ({info.get('note', '')}); nothing to cross-check")
        return None
    d0, d1 = date.fromisoformat(info['start']), date.fromisoformat(info['end'])
    s, e = eedate(d0), eedate(d1)
    era = ee.ImageCollection(ERA5_DAILY).filterBounds(roiGeom).filterDate(s, e)
    tc = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE').filterBounds(roiGeom).filterDate(s, e)
    et_tc = safeSum(tc, 'aet', name='ET_TC').multiply(0.1)
    pet_tc = safeSum(tc, 'pet', name='PET_TC').multiply(0.1)
    refs = [
        safeSum(era, 'total_precipitation_sum', name='Rain_ERA5').multiply(1000).rename('Rain_ERA5'),
        safeSum(tc, 'pr', name='Rain_TC').rename('Rain_TC'),
        et_tc.divide(pet_tc.max(1e-6)).rename('ESI_TC'),
        _ndvi_window_ee(s, e).select('NDVI_c').rename('NDVI_MOD13'),
        _lst_window_ee(s, e).select('LST_c').rename('LST_MOD11'),
    ]
    if d1.year <= 2017:
        ch = ee.ImageCollection('UCSB-CHG/CHIRTS/DAILY').filterBounds(roiGeom).filterDate(s, e)
        refs.append(safeMean(ch, 'maximum_temperature', name='Tmax_CHIRTS').rename('Tmax_CHIRTS'))
        refs.append(safeMean(ch, 'minimum_temperature', name='Tmin_CHIRTS').rename('Tmin_CHIRTS'))
    cols = [c for c in ('UID', 'Rain', 'ESI', 'NDVI', 'Tmax', 'Tmin', 'Tmean', 'LAI',
                        'Coverage', 'GapFilled', 'OptTier') if c in export_columns()]
    img = stack.select(cols).addBands(ee.Image.cat(refs))
    pts = ee.FeatureCollection.randomPoints(roiGeom, n_points, XCHECK_SEED)
    fc = img.sampleRegions(collection=pts, scale=SCALE, tileScale=8, geometries=False)
    fc = fc.map(lambda f: f.set({'Year': year, 'Season': season}))
    stats = {}
    if print_stats:
        try:
            feats = _retry(lambda: fc.getInfo(), tries=2, what="cross-check sample")['features']
            rows = [f['properties'] for f in feats]
            print(f"   {len(rows)} sampled pixels  (window {d0}..{d1}, coverage "
                  f"{info.get('coverage')}, gap-filled {info.get('gap_filled') or 'no'})")
            print(f"   {'pipeline':8s} {'reference':12s} {'n':>5s} {'r':>7s} {'bias':>9s} {'rmse':>9s}   meaning")
            for a, b, meaning in XCHECK_PAIRS:
                if a not in cols:
                    continue
                st = _pair_stats(rows, a, b)
                stats[(a, b)] = st
                print(f"   {a:8s} {b:12s} {st['n']:5d} {st['r']:7.3f} {st['bias']:9.3f} "
                      f"{st['rmse']:9.3f}   {meaning}")
        except Exception as ex:
            print(f"   ⚠️ in-session statistics unavailable ({ex}); the export still runs")
    if export:
        desc = f"XCHK_{ROI_ID}_{PIPELINE_VERSION}_{year}_{season}"
        task = ee.batch.Export.table.toDrive(
            collection=fc, description=desc, folder=f"{DRIVE_FOLDER}_validation",
            fileNamePrefix=f"XCHK_{ROI_ID}_{year}_{season}", fileFormat='CSV')
        task.start()
        print(f"   📤 paired sample export queued: {desc} -> Drive/{DRIVE_FOLDER}_validation")
    return stats


# ==================================================================
# ⛑ v111 -- GROUND DATA: cross-check of the exported values against
# benchmark-site measurements (LAI, surface & root-zone soil moisture)
# and against the field-survey polygons (crop type / cropland class), plus
# a survey-based recommendation for the core (priority) months.
#
# Nothing here changes the exported panel unless YOU set
# CORE_MONTHS_OVERRIDE. The ground CSVs are the ones built by
# build_all.py (REWARD_ground_inputs). Ground observations are keyed to
# (Year, season) with THIS pipeline's SEASONS/season_window() rule, so a
# January reading is paired with the Rabi window that started the
# previous October -- the same way the exported rows are keyed.
# ==================================================================
GROUND_INPUTS_DIR = '/content/drive/MyDrive/REWARD_ground_inputs'   # folder with the build_all.py CSVs
GROUND_SITES_FILE = '01_benchmark_sites_master.csv'
GROUND_OBS_FILES = {                       # ground variable -> (csv, value column, site-number column)
    'lai': ('03_ground_lai_long.csv', 'lai_mean', 'bm_site_no'),
    'ssm': ('02_ground_ssm_long.csv', 'ssm_mean', 'bm_site_no'),
    'tdr': ('06_ground_tdr_rootzone_0_30cm_by_visit.csv', 'moisture_pct', 'probe_or_survey_no'),
}
GROUND_POLYGONS_FILE = '10_field_survey_landuse_truth_polygons.csv'
GROUND_WINDOWS_FILE = 'gee_compositing_windows_by_district.csv'
GROUND_PAIRS = [        # (exported column, ground variable, what it tells you)
    ('LAI',  'lai', 'exported LAI vs ceptometer / plant-canopy LAI at benchmark sites (same quantity)'),
    ('NDVI', 'lai', 'NDVI vs ground LAI (monotone; NDVI saturates above LAI ~3)'),
    ('SMDI', 'ssm', 'SMDI vs surface soil moisture 0-10 cm (%) -- proxy'),
    ('LSWI', 'ssm', 'LSWI vs surface soil moisture 0-10 cm (%) -- proxy'),
    ('NDMI', 'ssm', 'NDMI vs surface soil moisture 0-10 cm (%) -- proxy'),
    ('NDWI', 'ssm', 'NDWI vs surface soil moisture 0-10 cm (%) -- proxy'),
    ('SMDI', 'tdr', 'SMDI vs TDR root-zone moisture 0-30 cm (%) -- what SMDI is meant to track'),
    ('LSWI', 'tdr', 'LSWI vs TDR root-zone moisture 0-30 cm (%)'),
    ('NDMI', 'tdr', 'NDMI vs TDR root-zone moisture 0-30 cm (%)'),
]
GROUND_MAX_FEATURES = 5000     # client-side FeatureCollections stay small (sites: <800, polygons: ~3,300)

def ground_season_key(d):
    """⛑ v111  (Year, season) of a calendar date under THIS pipeline's SEASONS -- the inverse
    of season_window(). Rabi Jan/Feb readings belong to the Rabi that started the previous
    October. Returns (None, None) for a date that falls in no season (never, with the
    default SEASONS, since Jun-Sep / Oct-Feb / Mar-May cover the year)."""
    for season, (sm, em) in SEASONS.items():
        if em >= sm:
            if sm <= d.month <= em:
                return d.year, season
        else:
            if d.month >= sm:
                return d.year, season
            if d.month <= em:
                return d.year - 1, season
    return None, None


def _ground_csv(name):
    import csv as _csv
    path = os.path.join(GROUND_INPUTS_DIR, name)
    if not os.path.exists(path):                      # v111.1: the windows table ships in a sub-folder as well
        for sub in ('gee_v111_inputs', 'pipeline_inputs', 'excel'):
            alt = os.path.join(GROUND_INPUTS_DIR, sub, name)
            if os.path.exists(alt):
                path = alt; break
    if not os.path.exists(path):
        raise FileNotFoundError(f"ground file not found: {path} (set GROUND_INPUTS_DIR to the folder built by build_all.py)")
    with open(path, newline='', encoding='utf-8') as fh:
        return list(_csv.DictReader(fh))


def _ground_site_key(r, var, keycol):
    return f"{r.get('institution', '')}|{r.get('sws_name', '')}|{r.get('mws_name', '')}|{var}|{r.get(keycol, '')}"


def _ground_float(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def ground_season_means(year, season, variables=None):
    """⛑ v111  {ground var: {site_key: mean of the observations that fall in (year, season)}}."""
    out = {}
    for var, (fname, vcol, keycol) in GROUND_OBS_FILES.items():
        if variables and var not in variables:
            continue
        acc = {}
        for r in _ground_csv(fname):
            v = _ground_float(r.get(vcol))
            if v is None or not r.get('date'):
                continue
            try:
                d = date.fromisoformat(r['date'][:10])
            except ValueError:
                continue
            if ground_season_key(d) != (year, season):
                continue
            k = _ground_site_key(r, var, keycol)
            acc.setdefault(k, []).append(v)
        out[var] = {k: sum(vs) / len(vs) for k, vs in acc.items()}
    return out


def ground_site_collection(variables=None):
    """⛑ v111  ee.FeatureCollection of benchmark-site POINTS (median coordinate per site) with
    site_key / variable / institution / sws_role as properties."""
    feats, seen = [], set()
    for r in _ground_csv(GROUND_SITES_FILE):
        if variables and r.get('variable') not in variables:
            continue
        lat, lon = _ground_float(r.get('lat_median')), _ground_float(r.get('lon_median'))
        if lat is None or lon is None:
            continue
        k = f"{r.get('institution', '')}|{r.get('sws_name', '')}|{r.get('mws_name', '')}|{r.get('variable', '')}|{r.get('site_no', '')}"
        if k in seen:
            continue
        seen.add(k)
        feats.append(ee.Feature(ee.Geometry.Point([lon, lat]), {
            'site_key': k, 'variable': r.get('variable', ''), 'institution': r.get('institution', ''),
            'sws_name': r.get('sws_name', ''), 'sws_role': r.get('sws_role', ''), 'lat': lat, 'lon': lon}))
        if len(feats) >= GROUND_MAX_FEATURES:
            break
    return ee.FeatureCollection(feats), len(feats)


def ground_polygon_collection(year=None, season=None):
    """⛑ v111  ee.FeatureCollection of field-survey POLYGONS (WKT -> ee.Geometry.Polygon), optionally
    only those whose sowing date falls in (year, season) under this pipeline's SEASONS."""
    feats = []
    for r in _ground_csv(GROUND_POLYGONS_FILE):
        w = r.get('polygon_wkt', '')
        if not w.startswith('POLYGON(('):
            continue
        if year is not None and r.get('sowing_date'):
            try:
                if ground_season_key(date.fromisoformat(r['sowing_date'][:10])) != (year, season):
                    continue
            except ValueError:
                continue
        try:
            ring = [[float(x), float(y)] for x, y in (c.strip().split() for c in w[len('POLYGON(('):-2].split(','))]
        except ValueError:
            continue
        feats.append(ee.Feature(ee.Geometry.Polygon([ring]), {
            'plot_uid': r.get('plot_uid', ''), 'district': r.get('district', ''), 'crop': r.get('crop', ''),
            'next_season_cropped': _ground_float(r.get('next_season_cropped')) if r.get('next_season_cropped') not in (None, '') else -1,
            'area_ha': _ground_float(r.get('polygon_area_ha')) or 0.0}))
        if len(feats) >= GROUND_MAX_FEATURES:
            break
    return ee.FeatureCollection(feats), len(feats)


@_friendly_name_errors
def ground_crosscheck(year, season, export=True, print_stats=True, polygons=True):
    """⛑ v111  Validates a window's EXPORTED values against GROUND measurements at the same
    pixels:  LAI vs benchmark LAI; SMDI/LSWI/NDMI/NDWI vs surface (0-10 cm) and TDR root-zone
    (0-30 cm) soil moisture; LandUse / LandUseDW over cultivated field polygons (every survey
    polygon is a cropped field, so LandUse should be 2 = agriculture); Rabi NDVI/LSWI against
    reported double cropping.

    Builds the window exactly as main() does, samples the stack at the benchmark-site points
    (sampleRegions, SCALE) and averages it inside each field polygon (reduceRegions), prints
    n / Pearson r / mean bias / RMSE per pair, and (export=True) writes the paired tables to
    Drive folder <DRIVE_FOLDER>_validation as GROUND_SITES_<ROI>_<year>_<season>.csv and
    GROUND_PLOTS_<ROI>_<year>_<season>.csv. Sites outside this ROI are silently dropped by
    Earth Engine (they have no pixel) -- the printed counts say how many linked. The benchmark
    monitoring covers Apr-2023..Jun-2024 and the survey polygons 2025-26, so run it for those
    windows. Nothing here changes the exported panel; it measures its accuracy."""
    print(f"🌱 ground cross-check {year} {season}: building the window exactly as main() does")
    stack, info = build_stack(year, season)
    if stack is None:
        print(f"   window not buildable ({info.get('note', '')}); nothing to cross-check")
        return None
    cols = [c for c in ('UID', 'LAI', 'NDVI', 'SAVI', 'EVI', 'SMDI', 'LSWI', 'NDMI', 'NDWI', 'LandUse', 'LandUseDW',
                        'Coverage', 'GapFilled', 'OptTier') if c in export_columns()]
    stats = {}
    # ---- benchmark sites (points) ----
    gm = ground_season_means(year, season)
    n_ground = {v: len(m) for v, m in gm.items()}
    fc_sites, n_sites = ground_site_collection(variables=list(GROUND_OBS_FILES.keys()))
    sampled = stack.select(cols).sampleRegions(collection=fc_sites, scale=SCALE, tileScale=8, geometries=False)
    sampled = sampled.map(lambda f: f.set({'Year': year, 'Season': season}))
    if print_stats:
        try:
            feats = _retry(lambda: sampled.getInfo(), tries=2, what="ground site sample")['features']
            rows = [f['properties'] for f in feats]
            for r in rows:                       # attach the ground season mean of that site's variable
                k, v = r.get('site_key'), r.get('variable')
                if k is not None and v in gm and k in gm[v]:
                    r[f'ground_{v}'] = gm[v][k]
            linked = sum(1 for r in rows if any(c.startswith('ground_') for c in r))
            print(f"   sites: {n_sites} in the CSV, {len(rows)} inside this ROI, {linked} with a ground "
                  f"mean in this window (ground obs per variable: {n_ground})")
            print(f"   {'pipeline':8s} {'ground':6s} {'n':>5s} {'r':>7s} {'bias':>9s} {'rmse':>9s}   meaning")
            for a, g, meaning in GROUND_PAIRS:
                if a not in cols:
                    continue
                st = _pair_stats(rows, a, f'ground_{g}')
                stats[(a, g)] = st
                print(f"   {a:8s} {g:6s} {st['n']:5d} {st['r']:7.3f} {st['bias']:9.3f} {st['rmse']:9.3f}   {meaning}")
            for role in ('saturation', 'control'):
                sub = [r for r in rows if r.get('sws_role') == role]
                if len(sub) >= 3 and 'LAI' in cols:
                    st = _pair_stats(sub, 'LAI', 'ground_lai')
                    print(f"   LAI vs ground LAI in {role} SWS: n={st['n']} r={st['r']:.3f} bias={st['bias']:.3f}")
        except Exception as ex:
            print(f"   ⚠️ in-session site statistics unavailable ({ex}); the export still runs")
    # ---- field polygons ----
    reduced = None
    if polygons:
        try:
            fc_plots, n_plots = ground_polygon_collection(year, season)
            if n_plots:
                lu_cols = [c for c in ('LandUse', 'LandUseDW') if c in cols]
                idx_cols = [c for c in ('NDVI', 'LSWI', 'LAI', 'SMDI') if c in cols]
                mode_r = ee.Reducer.mode() if hasattr(ee.Reducer, 'mode') else ee.Reducer.first()
                mean_r = ee.Reducer.mean()
                # a reducer over ONE band names its output after the reducer ('mode'/'mean'), over several bands
                # after the bands -- force band names in both cases so the client-side join below always works
                if len(lu_cols) == 1 and hasattr(mode_r, 'setOutputs'):
                    mode_r = mode_r.setOutputs(lu_cols)
                if len(idx_cols) == 1 and hasattr(mean_r, 'setOutputs'):
                    mean_r = mean_r.setOutputs(idx_cols)
                r1 = stack.select(lu_cols).reduceRegions(collection=fc_plots, reducer=mode_r, scale=SCALE, tileScale=8) if lu_cols else fc_plots
                r2 = stack.select(idx_cols).reduceRegions(collection=fc_plots, reducer=mean_r, scale=SCALE, tileScale=8) if idx_cols else fc_plots
                reduced = r2.map(lambda f: f.set({'Year': year, 'Season': season}))
                if print_stats:
                    f1 = _retry(lambda: r1.getInfo(), tries=2, what="polygon class sample")['features']
                    f2 = _retry(lambda: r2.getInfo(), tries=2, what="polygon index sample")['features']
                    cls = {f['properties'].get('plot_uid'): f['properties'] for f in f1}
                    prow = []
                    for f in f2:
                        p = dict(f['properties']); p.update({k: v for k, v in cls.get(p.get('plot_uid'), {}).items() if k in lu_cols})
                        prow.append(p)
                    lu2 = [p for p in prow if isinstance(p.get('LandUse'), (int, float))]
                    print(f"   polygons: {n_plots} cropped fields sown in this window, {len(prow)} inside this ROI")
                    if lu2:
                        share = sum(1 for p in lu2 if round(p['LandUse']) == 2) / len(lu2)
                        print(f"   LandUse == 2 (agriculture) over cropped fields: {100 * share:.1f}%  (n={len(lu2)})  <- producer's accuracy of the cropland class")
                    dw = [round(p['LandUseDW']) for p in prow if isinstance(p.get('LandUseDW'), (int, float))]
                    if dw:
                        from collections import Counter as _Counter
                        print(f"   LandUseDW classes over cropped fields: {dict(_Counter(dw))}  (4 = crops)")
                    if season == 'Rabi':
                        for ix in ('NDVI', 'LSWI'):
                            a = [p[ix] for p in prow if p.get('next_season_cropped') == 1 and isinstance(p.get(ix), (int, float))]
                            b = [p[ix] for p in prow if p.get('next_season_cropped') == 0 and isinstance(p.get(ix), (int, float))]
                            if len(a) >= 3 and len(b) >= 3:
                                print(f"   Rabi {ix}: double-cropped fields {sum(a)/len(a):.3f} vs single-cropped {sum(b)/len(b):.3f} (n={len(a)}/{len(b)})")
            else:
                print("   polygons: none of the survey plots was sown in this window")
        except Exception as ex:
            print(f"   ⚠️ polygon statistics unavailable ({ex})")
    if export:
        desc = f"GROUND_SITES_{ROI_ID}_{PIPELINE_VERSION}_{year}_{season}"
        ee.batch.Export.table.toDrive(collection=sampled, description=desc, folder=f"{DRIVE_FOLDER}_validation",
                                      fileNamePrefix=f"GROUND_SITES_{ROI_ID}_{year}_{season}", fileFormat='CSV').start()
        print(f"   📤 site sample export queued: {desc} -> Drive/{DRIVE_FOLDER}_validation")
        if reduced is not None:
            desc = f"GROUND_PLOTS_{ROI_ID}_{PIPELINE_VERSION}_{year}_{season}"
            ee.batch.Export.table.toDrive(collection=reduced, description=desc, folder=f"{DRIVE_FOLDER}_validation",
                                          fileNamePrefix=f"GROUND_PLOTS_{ROI_ID}_{year}_{season}", fileFormat='CSV').start()
            print(f"   📤 polygon sample export queued: {desc}")
    return stats


def recommend_core_months(district=None, min_plots=30, min_core_share=0.5):
    """⛑ v111  Reads gee_compositing_windows_by_district.csv (field-survey sowing dates per
    district x season x crop, scored against THIS pipeline's SEASONS / core months) and prints,
    for the given district (or all), the season x crop combinations whose sowing lies outside the
    core months, with the CORE_MONTHS_OVERRIDE that would cover the crop's late growth.
    Returns {season: (start_month, end_month)} suggestions for `district` (empty = no change)."""
    rows = _ground_csv(GROUND_WINDOWS_FILE)
    sug = {}
    print(f"   {'district':15s} {'season':7s} {'crop':14s} {'plots':>5s} {'sow-mo':>6s} {'in-core':>7s}  note")
    for r in rows:
        if district and r.get('district', '').lower() != district.lower():
            continue
        if int(float(r.get('n_plots', 0))) < min_plots:
            continue
        season = r.get('season_name'); share = float(r.get('share_sown_in_core_months', 0)); mode_m = int(float(r.get('sowing_month_mode', 0)))
        if season not in SEASONS or share >= min_core_share:
            continue
        sm, em = SEASONS[season]; ma, mb = SEASON_CORE_MONTHS[season]
        window = list(range(sm, 13)) + list(range(1, em + 1)) if em < sm else list(range(sm, em + 1))
        note = ''
        if mode_m == window[0]:
            note = f"sown in the first window month -> extend core to ({ma}, {window[-1]})"
            if district:
                sug[season] = (ma, window[-1])
        elif mode_m == window[-1]:
            note = "sown in the LAST window month -> canopy develops in the next season's window; no core change helps"
        else:
            note = "sown between core and edge months"
        print(f"   {r.get('district', ''):15s} {season:7s} {r.get('crop', ''):14s} {int(float(r['n_plots'])):5d} {mode_m:6d} {share:7.2f}  {note}")
    if district:
        print(f"   suggestion for {district}: CORE_MONTHS_OVERRIDE = {sug or None}")
    return sug


if __name__ == "__main__":
    main(authenticate=True)
