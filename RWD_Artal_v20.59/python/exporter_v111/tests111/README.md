# v107 offline test harness (no Earth Engine account or network needed)

`mockee/ee/__init__.py` is a band-tracking mock of the Earth Engine Python API:
selecting a band that does not exist raises like the real server; every collection
has a realistic publication lag relative to the run date (CHIRPS 42 d, ERA5-Land
daily 73 d, MOD16A2GF fixed at 2025-12-27, MOD16A2 13 d, everything else 6 d).
Edit `CATALOG` / `DATA_END` / `LAG_DAYS` there to model a different catalog state.

Paths inside the scripts point at /home/claude/...; change them to where you
unpack this (each script takes the exporter path and a scratch work directory).

    python3 run_mock.py <exporter.py> <workdir> rabi [YYYY-MM-DD]   # Rabi 2025+2026 (optionally frozen run date)
    python3 run_mock.py <exporter.py> <workdir> all                 # full 48-window panel
    python3 test_lifecycle.py <exporter.py> <workdir> 2027-03-15    # main() at a frozen date; run several dates in one workdir
    python3 test_reconcile2.py <exporter.py> <workdir> 0|1          # prior-version tasks on EE; 1 = ADOPT_PRIOR_VERSION_TASKS
    python3 test_diag.py / test_switches.py / test_notebook.py      # diagnostics, config switches, notebook cell-by-cell

v109: set `ee.ROI_KIND = 'collection'` (see test_roi.py) to model a multi-feature ROI such as
Gummlapalli; the mock then enforces Earth Engine's "MultiGeometry ... requires non-zero maxError"
rule, which v108 trips and v109 does not.
