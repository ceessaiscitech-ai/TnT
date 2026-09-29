"""
validate_preprocessing.py -- production gate for the PANEL PREPARATION path (v20.5)

The model gate (validate_all_models.py) starts from a ready panel, so it never executed PASS A -- which is how the
int64 `pixel_id` regression (`row_id` string concatenation -> UFuncTypeError) reached you. This script builds
synthetic Earth-Engine-style CSV exports in a temp folder and runs the REAL preparation functions over them:

    load_and_harmonize -> assign_pixel_ids -> resolve_duplicates -> data_qc -> build_fe_and_treatment
    -> run_pass_a (parallel AND sequential) -> assemble/PASS B -> the scenario columns models rely on

and checks the things that actually break: dtypes, the id being a pure function of the coordinate, duplicate
resolution, the FE keys, and that the same pixel keeps one id across files. Run it before trusting a rebuild:

    python validate_preprocessing.py
"""
import json, tempfile, os, sys, tempfile, json, glob, shutil, tempfile, traceback
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _prep_common as P

PROBLEMS = []
def bad(m): PROBLEMS.append(m); print(f"[FAILED]  {m}")
def ok(m): print(f"[OK]      {m}")


def write_synthetic_exports(root, n_files=6, n_pix=40, years=(2022, 2023, 2024), seasons=(0, 1, 2, 3)):   # v20.24: Season 0 = annual
    """GEE-style CSVs: one file per Year x Season block, the columns the exporter writes."""
    os.makedirs(root, exist_ok=True)
    rng = np.random.default_rng(3)
    lat0, lon0 = 16.4412, 75.1711
    pix = [(round(lat0 + i * 9e-5, 5), round(lon0 + (i % 7) * 9e-5, 5)) for i in range(n_pix)]
    made = []
    for y in years:
        for s in seasons:
            rows = []
            for k, (la, lo) in enumerate(pix):
                rows.append({"system:index": f"{y}_{s}_{k}", "UID": f"u{k}", "latitude": la, "longitude": lo,
                             "Year": y, "Season": s, "SubwshedID": 3, "Treat": 1 if y >= 2022 else 0,            # the exporter writes Treat as a PERIOD flag
                             "buff_km": 0 if k % 5 == 0 else (k % 5), "NDVI": 0.4 + rng.normal(0, .02),
                             "LAI": 1.2 + rng.normal(0, .05), "Rain": 600 + rng.normal(0, 40),
                             "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2, "Coverage": 1.0,
                             "SWSiD_All": 1 + (k % 2),                        # v20.22: two sites in one export
                             ".geo": "{}",
                             **{c: 0.3 + rng.normal(0, .02) for c in
                                ("SAVI", "EVI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE",
                                 "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI")}})
            d = pd.DataFrame(rows)
            # v20.17: the exports carry no-data cells the way real ones do -- exact zeros and NaN
            _r = np.random.default_rng(y * 10 + s)
            d.loc[_r.random(len(d)) < 0.10, "NDVI"] = 0.0
            d.loc[_r.random(len(d)) < 0.05, "Tmax"] = 0.0
            d.loc[_r.random(len(d)) < 0.05, "LAI"] = np.nan
            if s == seasons[0]:                              # two rows with NO usable outcome at all -> must be dropped
                d.loc[d.index[:2], [c for c in d.columns if c in ("NDVI", "LAI", "SAVI", "EVI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE", "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI")]] = 0.0
            if y == years[-1] and s == seasons[0]:          # a duplicated pixel row, as real exports contain
                d = pd.concat([d, d.iloc[[0]].assign(NDVI=d.NDVI.iloc[0] + 0.01)], ignore_index=True)
            f = os.path.join(root, f"Artal_{y}_{'Yearly' if s == 0 else 'S' + str(s)}.csv")
            d.to_csv(f, index=False); made.append(f)
    return made


def main():
    tmp = tempfile.mkdtemp()
    inp = os.path.join(tmp, "input"); out = os.path.join(tmp, "output"); tempd = os.path.join(out, "TEMP")
    files = write_synthetic_exports(inp)
    os.makedirs(out, exist_ok=True)
    print(f"=== preprocessing gate: {len(files)} synthetic export files in {inp}")

    # ---- 1. one file, the exact chain a PASS A worker runs -------------------------------------------------
    try:
        unresolved, errs = [], []
        df = P.load_and_harmonize(files[0], unresolved_log=unresolved, parse_errors_log=errs)
        df["pixel_id"] = P.assign_pixel_ids(df["latitude"].values, df["longitude"].values)
        df, dups = P.resolve_duplicates(df, group_keys=("pixel_id", "Year", "Season"), conflict_log=[])
        df = P.data_qc(df)
        df = P.build_fe_and_treatment(df)
        ok(f"single-file chain: {len(df)} rows, {len(df.columns)} columns")
        if str(df["pixel_id"].dtype) != "int64": bad(f"pixel_id dtype is {df['pixel_id'].dtype}, expected int64")
        else: ok("pixel_id is int64 (8 bytes/row)")
        for c in ("row_id", "time_fe_yearseason", "time_fe_season", "season_sort_rank", "subwshed_id"):
            if c not in df.columns: bad(f"build_fe_and_treatment did not create {c}")
        if "row_id" in df:
            r = str(df["row_id"].iloc[0])
            if not r.split("_")[0].isdigit() or len(r.split("_")) != 3:
                bad(f"row_id is malformed: {r!r}")
            else: ok(f"row_id built from the int64 id: {r}")
        if df.duplicated(subset=["pixel_id", "Year", "Season"]).any():
            bad("duplicate (pixel_id, Year, Season) rows survived resolve_duplicates")
        else: ok("no duplicate keys after resolve_duplicates")
    except Exception as e:
        bad(f"single-file chain raised {type(e).__name__}: {e}"); traceback.print_exc(limit=3)

    # ---- 2. the id is a pure function of the coordinate (same pixel, different files) ----------------------
    try:
        a = P.load_and_harmonize(files[0]); b = P.load_and_harmonize(files[-1])
        ia = pd.Series(P.assign_pixel_ids(a["latitude"].values, a["longitude"].values), index=a.index)
        ib = pd.Series(P.assign_pixel_ids(b["latitude"].values, b["longitude"].values), index=b.index)
        ka = dict(zip(zip(a.latitude.round(5), a.longitude.round(5)), ia))
        kb = dict(zip(zip(b.latitude.round(5), b.longitude.round(5)), ib))
        shared = set(ka) & set(kb)
        if shared and all(ka[k] == kb[k] for k in shared):
            ok(f"the same coordinate gets the same pixel_id across files ({len(shared)} checked)")
        else: bad("pixel_id is not stable across files")
        s_id = P.assign_pixel_ids(a["latitude"].values[:3], a["longitude"].values[:3], as_int=False)
        i_id = P.assign_pixel_ids(a["latitude"].values[:3], a["longitude"].values[:3], as_int=True)
        if all(int(x) == int(y) for x, y in zip(s_id, i_id)): ok("int64 id equals the legacy 18-digit string id")
        else: bad("int64 id does not match the legacy string id")
    except Exception as e:
        bad(f"id-stability check raised {type(e).__name__}: {e}")

    # ---- 3. the real PASS A, parallel and sequential --------------------------------------------------------
    for workers, label in ((2, "parallel (2 workers)"), (1, "sequential")):
        try:
            shutil.rmtree(tempd, ignore_errors=True); os.makedirs(tempd, exist_ok=True)
            res = P.run_pass_a(inp, tempd, out, n_workers=workers)
            registry, unresolved, errors, dups, shards = res
            n = 0
            for sh in shards:
                try: n += len(pd.read_parquet(sh))
                except Exception: n = -1; break
            if errors: bad(f"PASS A {label}: {len(errors)} file error(s): {errors[:2]}")
            elif not shards: bad(f"PASS A {label}: no shards written")
            else: ok(f"PASS A {label}: {len(shards)} shard(s), "
                     f"{'rows not counted (no parquet reader here)' if n < 0 else format(n, ',') + ' rows'}, "
                     f"{len(errors)} errors, {len(dups)} duplicate group(s) resolved")
        except Exception as e:
            bad(f"PASS A {label} raised {type(e).__name__}: {e}"); traceback.print_exc(limit=3)

    # ---- 4. the columns every model depends on -------------------------------------------------------------
    try:
        shards = sorted(glob.glob(os.path.join(tempd, "*.parquet")))
        try:
            d = pd.concat([pd.read_parquet(s) for s in shards], ignore_index=True) if shards else None
        except Exception as _e:
            print(f"[INFO]    shards not readable here ({type(_e).__name__}); rebuilding the frame in memory for the scenario check")
            d = None
        if d is None:
            d = P.build_fe_and_treatment(P.data_qc(P.resolve_duplicates(
                P.load_and_harmonize(files[0]).assign(
                    pixel_id=lambda x: P.assign_pixel_ids(x["latitude"].values, x["longitude"].values)),
                group_keys=("pixel_id", "Year", "Season"), conflict_log=[])[0]))
        if d is not None:
            import _common as C
            ctrl_ok = post_ok = trans_ok = True
            for excl in (False, True):
                C.set_scenario(control_zones="1-3", treatment_year=2023, exclude_transition_year=excl, verbose=False)
                t = C.build_treatment_columns(d.copy())
                need = ["treatment", "control", "pre", "post", "did_term", "in_analysis_sample", "event_time"]
                miss = [c for c in need if c not in t.columns]
                if miss: bad(f"scenario columns missing after preparation: {miss}"); break
                ctrl_ok &= bool((t["control"].astype(int) == pd.to_numeric(t["buff_km"]).isin([1, 2, 3]).astype(int)).all())
                if excl:        # v20.26: the treatment year is a transition year -- out of the sample, post from +1
                    post_ok &= bool((t["post"].astype(int) == (t["Year"] >= 2024).astype(int)).all())
                    trans_ok &= bool((t.loc[t["Year"] == 2023, "in_analysis_sample"] == 0).all()) and bool((t.loc[t["Year"] < 2023, "pre"] == 1).all())
                else:
                    post_ok &= bool((t["post"].astype(int) == (t["Year"] >= 2023).astype(int)).all())
            (ok if ctrl_ok and post_ok and trans_ok else bad)(
                f"prepared panel + scenario: rings, post period and the transition-year rule computed correctly in both modes "
                f"(treated pixels {int(t.loc[t.treatment == 1, 'pixel_id'].nunique())}, control {int(t.loc[t.control == 1, 'pixel_id'].nunique())})")
    except Exception as e:
        bad(f"scenario check on the prepared shards raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 4b. SWSiD_All travels into the panel as site_id, and the SAME coordinate in TWO sites is NOT a duplicate --
    try:
        unresolved, errs = [], []
        d0 = P.load_and_harmonize(files[0], unresolved_log=unresolved, parse_errors_log=errs)
        d0["pixel_id"] = P.assign_pixel_ids(d0["latitude"].values, d0["longitude"].values)
        d0 = P.build_fe_and_treatment(d0)
        if "site_id" not in d0.columns or sorted(d0.site_id.unique()) != [1, 2]: bad(f"SWSiD_All did not become site_id: {d0.get('site_id', pd.Series()).unique()[:5]}")
        else: ok("SWSiD_All ingested as site_id (two sites in one export)")
        two = pd.concat([d0.iloc[[0]], d0.iloc[[0]].assign(site_id=np.int16(2))], ignore_index=True)   # one coordinate, two sites
        # v20.58: the site-aware key protects a pixel INSIDE the polygons (two sub-watersheds' overlapping rings); this test's coordinates
        # lie outside the shipped polygons (site_check 3), and there the copies are ONE pixel-year-season (its site id is only what the
        # file's name said) -- both cases checked
        if "site_check" in two.columns: two["site_check"] = 0
        r2, _ = P.resolve_duplicates(two.copy(), conflict_log=[])
        if len(r2) != 2: bad("the same coordinate in two sites was merged as a duplicate -- overlapping rings would be lost")
        else: ok("dedup key is site-aware: the same pixel in two sites' rings is kept in both")
        if "site_check" in two.columns:
            r3, _ = P.resolve_duplicates(two.assign(site_check=3).copy(), conflict_log=[])
            if len(r3) != 1: bad("a pixel outside every polygon, in a named export and an unnamed tile: its copies were kept as two pixel-year-seasons")
            else: ok("outside every polygon the copies of one coordinate are one pixel-year-season (the site id there is only the file's name)")
    except Exception as e:
        bad(f"site ingestion check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 5. PASS B: parallel and sequential must give the SAME panel ---------------------------------------
    try:
        shutil.rmtree(tempd, ignore_errors=True); os.makedirs(tempd, exist_ok=True)
        reg, unres, errs2, dups2, shards = P.run_pass_a(inp, tempd, out, n_workers=1)
        panels = {}
        for nw, label in ((1, "sequential"), (2, "parallel (2 workers)")):
            odir = os.path.join(out, f"passb_{nw}"); shutil.rmtree(odir, ignore_errors=True); os.makedirs(odir, exist_ok=True)
            P.run_pass_b(shards, odir, n_workers=nw)
            fp = os.path.join(odir, "did_panel_full.parquet")
            if not os.path.exists(fp): bad(f"PASS B {label}: no panel written"); continue
            d = P.pq.read_table(fp).to_pandas()
            panels[nw] = d
            ok(f"PASS B {label}: {len(d):,} rows, {len(d.columns)} columns")
        if len(panels) == 2:
            a_, b_ = panels[1], panels[2]
            same_shape = a_.shape == b_.shape
            key = ["pixel_id", "Year", "Season"]
            same_order = same_shape and a_[key].reset_index(drop=True).equals(b_[key].reset_index(drop=True))
            num = [c for c in a_.columns if pd.api.types.is_numeric_dtype(a_[c])]
            same_vals = same_shape and np.allclose(a_[num].fillna(-999).values, b_[num].fillna(-999).values, equal_nan=True)
            if same_shape and same_order and same_vals:
                ok("PASS B parallel output is IDENTICAL to sequential (shape, row order and every numeric column)")
            else:
                bad(f"PASS B parallel != sequential (shape {same_shape}, order {same_order}, values {same_vals})")
            need = ["treatment", "control", "pre", "post", "did_term"]          # DROPPED_FROM_PANEL excludes the aliases
            miss = [c for c in need if c not in a_.columns]
            if miss: bad(f"final panel is missing materialised columns: {miss}")
            else: ok("final panel carries the materialised DiD columns")
    except Exception as e:
        bad(f"PASS B check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=3)

    # ---- 6. an interrupted PASS B must never leave an unreadable panel -------------------------------------
    try:
        odir = os.path.join(out, "passb_1"); fp = os.path.join(odir, "did_panel_full.parquet")
        if os.path.exists(fp):
            good = open(fp, "rb").read()
            with open(fp, "wb") as fh: fh.write(good[: max(1, len(good) // 2)])      # simulate a killed run
            P.FINAL_PANEL = fp
            valid = P.final_panel_is_valid(fp)
            rep = P.panel_file_report(fp) if os.path.exists(fp) else {"exists": False}
            quarantined = sorted(glob.glob(fp + ".corrupt_*"))
            if valid: bad("a truncated panel was reported as VALID")
            elif not quarantined: bad("a truncated panel was not moved aside")
            else: ok(f"truncated panel detected and quarantined ({os.path.basename(quarantined[0])})")
            P.run_pass_b(shards, odir, n_workers=1)
            rep2 = P.panel_file_report(fp)
            if rep2.get("readable"): ok(f"rebuild produced a readable panel ({rep2['rows']:,} rows)")
            else: bad(f"rebuild did not produce a readable panel: {rep2}")
            if glob.glob(os.path.join(odir, "*.building")): bad(".building file left behind after a successful run")
            else: ok("no .building file left behind (atomic publish)")
    except Exception as e:
        bad(f"corrupt-panel check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 7. v20.58 (your rule "repeated rows are dropped"): by default the kept row is taken AS IT IS -- a value of a dropped (repeated)
    #      row never fills its gap, and the values not used are counted; DEDUP_FILL_FROM_DUPLICATES = True merges them (exports split by
    #      variable). Until v20.57 the merge was always on (the poison test found the leak: a cloud gap took the repeated tile's value)
    try:
        base = pd.DataFrame({"pixel_id": [11, 11, 22], "Year": [2023, 2023, 2023], "Season": [1, 1, 1],
                             "NDVI": [0.40, np.nan, 0.50], "LAI": [np.nan, 1.90, 2.10],
                             "src_file": ["a.csv", "b.csv", "a.csv"], "file_mtime": [100.0, 100.0, 100.0]})
        if P.DEDUP_FILL_FROM_DUPLICATES is not False: bad(f"DEDUP_FILL_FROM_DUPLICATES defaults to {P.DEDUP_FILL_FROM_DUPLICATES!r} (must be False)")
        kept, log = P.resolve_duplicates(base.copy(), conflict_log=[])
        row = kept[kept.pixel_id == 11].iloc[0]
        if len(kept) != 2 or row.NDVI != 0.40 or not pd.isna(row.LAI) or kept.attrs.get("values_filled_from_duplicates") != 0 \
                or kept.attrs.get("values_in_dropped_rows_not_used") != 1 or kept.attrs.get("values_not_used_by_variable") != {"LAI": 1} \
                or kept.attrs.get("duplicate_kinds") != {"complementary": 1} or log[0].get("values_in_dropped_rows_not_used") != 1:
            bad(f"a repeated row's value reached the kept row (default): NDVI={row.NDVI}, LAI={row.LAI}, attrs {kept.attrs}")
        else:
            ok("repeated rows dropped whole by default: the kept row keeps its gap (LAI missing), the 1 value not used is counted and logged")
        merged, log = P.resolve_duplicates(base.copy(), conflict_log=[], fill_from_duplicates=True)
        row = merged[merged.pixel_id == 11].iloc[0]
        if pd.isna(row.NDVI) or pd.isna(row.LAI) or merged.attrs.get("values_filled_from_duplicates") != 1:
            bad(f"DEDUP_FILL_FROM_DUPLICATES = True: complementary duplicate rows lost data: NDVI={row.NDVI}, LAI={row.LAI} (both must survive)")
        else:
            ok(f"DEDUP_FILL_FROM_DUPLICATES = True: complementary duplicates merged (NDVI={row.NDVI}, LAI={row.LAI}); "
               f"kinds={merged.attrs.get('duplicate_kinds')}, filled={merged.attrs.get('values_filled_from_duplicates')}")
        same = pd.DataFrame({"pixel_id": [7, 7], "Year": [2023, 2023], "Season": [1, 1], "NDVI": [0.4, 0.4],
                             "LAI": [1.0, 1.0], "src_file": ["a.csv", "b.csv"], "file_mtime": [1.0, 2.0]})
        m2, _ = P.resolve_duplicates(same.copy(), conflict_log=[])
        if len(m2) != 1 or m2.attrs.get("duplicate_kinds", {}).get("redundant") != 1:
            bad(f"identical duplicates mis-classified: {m2.attrs.get('duplicate_kinds')}")
        else:
            ok("identical duplicates collapse to one row and are reported as redundant")
        confl = pd.DataFrame({"pixel_id": [9, 9], "Year": [2023, 2023], "Season": [1, 1], "NDVI": [0.4, 0.9],
                              "LAI": [1.0, 2.0], "src_file": ["a.csv", "b.csv"], "file_mtime": [1.0, 9.0]})
        m3, _ = P.resolve_duplicates(confl.copy(), conflict_log=[])
        if m3.attrs.get("duplicate_kinds", {}).get("conflicting") != 1:
            bad(f"genuinely conflicting duplicates not flagged: {m3.attrs.get('duplicate_kinds')}")
        else:
            ok("conflicting duplicates are flagged (newer file wins, both values logged)")
    except Exception as e:
        bad(f"duplicate-merge check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 8. the balance report must be written and must notice an unbalanced block ------------------------
    try:
        bp = os.path.join(out, "passb_1", "panel_balance_by_block.csv")
        if not os.path.exists(bp): bad("panel_balance_by_block.csv was not written by PASS B")
        else:
            b = pd.read_csv(bp)
            ok(f"panel balance report written: {len(b)} blocks, "
               f"{b.unique_pixels.min():,}-{b.unique_pixels.max():,} pixels per block")
    except Exception as e:
        bad(f"balance report check raised {type(e).__name__}: {e}")

    # ---- 9. Windows-style publish failure must be recoverable without re-running PASS B --------------------
    try:
        odir = os.path.join(out, "passb_1"); fp = os.path.join(odir, "did_panel_full.parquet")
        bp = fp + ".building"
        # every metadata read must CLOSE its handle (this is what broke the rename on Windows)
        opened = {"n": 0, "closed": 0}
        real = P.pq.ParquetFile
        class _Tracked(real):
            def __init__(self, *a, **k): opened["n"] += 1; super().__init__(*a, **k)
            def close(self):
                opened["closed"] += 1
                try: super().close()
                except Exception: pass
        P.pq.ParquetFile = _Tracked
        try:
            P.final_panel_is_valid(fp); P.panel_file_report(fp); P.pq_is_readable(fp)
        finally:
            P.pq.ParquetFile = real
        if opened["n"] and opened["closed"] >= opened["n"]:
            ok(f"metadata reads close their handles ({opened['closed']}/{opened['n']}) -- rename cannot be blocked")
        else:
            bad(f"a metadata read leaked a file handle ({opened['closed']} closed of {opened['n']} opened) -- "
                f"Windows would refuse to publish the panel")
        # simulate the exact failure: a finished .building plus an unreadable file at the final name
        shutil.copyfile(fp, bp)
        with open(fp, "wb") as fh: fh.write(b"not a parquet file")
        res = P.finalize_pending_panel(odir, verbose=False)
        okfile = P.panel_file_report(res)
        if okfile.get("readable") and not os.path.exists(bp) and glob.glob(fp + ".corrupt_*"):
            ok(f"finalize_pending_panel() published the finished panel without re-running PASS B "
               f"({okfile['rows']:,} rows) and quarantined the bad file")
        else:
            bad(f"finalize_pending_panel did not recover cleanly: {okfile}, building_left={os.path.exists(bp)}")
    except Exception as e:
        bad(f"publish-recovery check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 10. build_manifest must run on the finished panel (v20.11 shipped a NameError here) -------------
    try:
        fp = os.path.join(out, "passb_1", "did_panel_full.parquet")
        if os.path.exists(fp):
            man = P.build_manifest(fp)
            if not isinstance(man, dict) or not man: bad("build_manifest returned nothing")
            else: ok(f"build_manifest streamed the panel ({man.get('n_rows', man.get('rows', '?'))} rows)")
    except Exception as e:
        bad(f"build_manifest raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)
    # ---- 11. dedup speed: 200k duplicate groups must resolve in seconds, not minutes -------------------------
    try:
        import time as _t
        n = 200_000; rng = np.random.default_rng(1)
        big = pd.DataFrame({"pixel_id": np.repeat(np.arange(n), 2), "Year": 2025, "Season": 0,
                            "NDVI": rng.random(2 * n), "LAI": np.where(rng.random(2 * n) < .5, np.nan, rng.random(2 * n)),
                            "src_file": np.tile(["a.csv", "b.csv"], n), "file_mtime": np.tile([1.0, 9.0], n)})
        t0 = _t.time(); r, lg = P.resolve_duplicates(big, conflict_log=[]); dt = _t.time() - t0
        if len(r) != n: bad(f"vectorised dedup kept {len(r):,} rows for {n:,} groups")
        elif dt > 60: bad(f"dedup took {dt:.0f}s for {n:,} groups -- the per-group loop is back")
        else: ok(f"dedup resolved {n:,} duplicate groups in {dt:.1f}s (kinds {r.attrs.get('duplicate_kinds')})")
    except Exception as e:
        bad(f"dedup speed check raised {type(e).__name__}: {e}")

    # ---- 12. ANY FORMAT, ANY NAME: csv / csv.gz / tsv / parquet / xlsx (+feather) with awkward names --------
    try:
        mix = os.path.join(tmp, "mixed"); os.makedirs(os.path.join(mix, "nested", "deeper"), exist_ok=True)
        rng = np.random.default_rng(9)
        def block(y, s, k0=0, n=25):
            return pd.DataFrame({"latitude": [round(16.5 + (k0 + i) * 9e-5, 5) for i in range(n)],
                                 "longitude": [round(75.2 + ((k0 + i) % 7) * 9e-5, 5) for i in range(n)],
                                 "SubwshedID": 3, **({"Treat": 1 if y >= 2022 else 0} if y is not None else {}),   # keyless blocks carry no Treat
                                 "buff_km": [0 if (k0 + i) % 5 == 0 else (k0 + i) % 5 for i in range(n)],
                                 "NDVI": 0.4 + rng.normal(0, .02, n), "LAI": 1.2 + rng.normal(0, .05, n),
                                 "Rain": 600.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2,
                                 **({"Year": y, "Season": s} if y is not None else {})})
        expected = {}
        def put(df, key, n): expected[key] = expected.get(key, 0) + n
        block(2022, 1).to_csv(os.path.join(mix, "CSV_2022_Kharif_tile1.csv"), index=False); put(None, (2022, 1), 25)
        with pd.ExcelWriter(os.path.join(mix, "Artal 2022 rabi export (final v3).xlsx")) as xw:
            block(None, None).to_excel(xw, sheet_name="data", index=False)
            block(None, None, k0=25).to_excel(xw, sheet_name="tile2", index=False)
            pd.DataFrame({"note": ["not data"], "value": [1]}).to_excel(xw, sheet_name="notes", index=False)
        put(None, (2022, 2), 50)
        P.pq.write_table(P.pa.Table.from_pandas(block(None, None), preserve_index=False), os.path.join(mix, "nested", "2022_zaid_v3.parquet")); put(None, (2022, 3), 25)
        block(2023, 1).to_csv(os.path.join(mix, "nested", "deeper", "export_no_key_in_name.csv"), index=False); put(None, (2023, 1), 25)
        block(None, None).to_csv(os.path.join(mix, "2023-Rabi tile 07 copy.csv.gz"), index=False, compression="gzip"); put(None, (2023, 2), 25)
        block(None, None).to_csv(os.path.join(mix, "zaid 2023.tsv"), index=False, sep="\t"); put(None, (2023, 3), 25)
        with pd.ExcelWriter(os.path.join(mix, "nested", "site export.xlsx")) as xw:       # key in the SHEET names
            block(None, None).to_excel(xw, sheet_name="2024_Rabi", index=False)
            block(None, None, k0=25).to_excel(xw, sheet_name="2024 zaid", index=False)
        put(None, (2024, 2), 25); put(None, (2024, 3), 25)
        P.pq.write_table(P.pa.Table.from_pandas(block(2024, 1), preserve_index=False), os.path.join(mix, "kharif-final.pq")); put(None, (2024, 1), 25)
        feather_ok = False
        try:
            import pyarrow.feather as _pf
            _pf.write_feather(P.pa.Table.from_pandas(block(None, None), preserve_index=False), os.path.join(mix, "2025-Kharif.feather"))
            put(None, (2025, 1), 25); feather_ok = True
        except Exception:
            pass
        open(os.path.join(mix, "README.txt"), "w").write("ignore me")
        open(os.path.join(mix, "~$Artal 2022 rabi export (final v3).xlsx"), "wb").write(b"lock")
        pd.DataFrame({"District": ["A"], "Sub Watershed Name": ["X"]}).to_excel(os.path.join(mix, "crosswalk_like.xlsx"), index=False)
        os.makedirs(os.path.join(mix, "output"), exist_ok=True)
        block(2022, 1).to_csv(os.path.join(mix, "output", "generated_should_be_ignored.csv"), index=False)
        files, nx, nseen = P.discover_input_files(mix, os.path.join(mix, "output"), os.path.join(mix, "output", "TEMP"), verbose=False)
        names = sorted(os.path.basename(f) for f in files)
        if any(n.startswith("~$") or n.endswith(".txt") for n in names): bad(f"discovery picked up a lock/readme file: {names}")
        if nx != 1: bad(f"discovery did not exclude the generated file under output/ (excluded {nx})")
        want = 8 + (1 if feather_ok else 0) + 1     # eight data files (+feather) + the crosswalk-like workbook (skipped later)
        if len(files) != want: bad(f"discovery found {len(files)} files, expected {want}: {names}")
        else: ok(f"discovery: {len(files)} readable files in 7 formats at 3 depths; lock/readme/output ignored")
        mtmp = os.path.join(mix, "output", "TEMP"); os.makedirs(mtmp, exist_ok=True)
        reg, unres, errs, dups, shards = P.run_pass_a(mix, mtmp, os.path.join(mix, "output"), n_workers=1)
        skipped = [e for e in errs if "crosswalk_like" in e]
        other_err = [e for e in errs if "crosswalk_like" not in e and "filled NaN" not in e]   # NaN-fill notes are not errors
        if other_err: bad(f"PASS A reported errors on data files: {other_err[:3]}")
        if not skipped: bad("the crosswalk-like workbook (no pixel columns) was not reported as skipped")
        got = {}
        for k, pth in shards.items():
            got[k] = P.pq.read_table(pth).to_pandas().shape[0]
        if got != expected: bad(f"rows per (Year, Season) block differ from what was written: got {got}, expected {expected}")
        else: ok(f"PASS A ingested every format under every name: {len(got)} blocks, rows per block exactly as written")
        P.run_pass_b(shards, os.path.join(mix, "output"), n_workers=1)
        rep = P.panel_file_report(os.path.join(mix, "output", "did_panel_full.parquet"))
        if rep.get("readable") and rep["rows"] == sum(expected.values()):
            ok(f"PASS B panel from the mixed folder: {rep['rows']} rows = every row of every file")
        else: bad(f"PASS B panel from the mixed folder is wrong: {rep} vs {sum(expected.values())}")
        # the pixel key is the same whichever format a row came from
        pan = P.pq.read_table(os.path.join(mix, "output", "did_panel_full.parquet")).to_pandas()
        per_block = pan.groupby(["Year", "Season"])["pixel_id"].nunique()
        if per_block.min() < 25: bad(f"pixel ids differ across formats: {per_block.to_dict()}")
        else: ok("the same coordinates got the same pixel_id in csv, gz, tsv, parquet and xlsx")
    except Exception as e:
        bad(f"mixed-format check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=3)

    # ---- 13a. the FINAL panel from exports with zeros/NaN: no zero survives, empty rows are gone, report exists --
    try:
        fp = os.path.join(out, "passb_1", "did_panel_full.parquet")
        pan = P.pq.read_table(fp).to_pandas()
        _floored = {k for k, r in P.NEGATIVE_COVARIATE_RULE.items() if r == "zero" and not P.ALLOW_NEGATIVE_COVARIATES}   # v20.30
        zero_cols = [c for c in P.ZERO_RULE_VARS if c in pan.columns and c not in P.ZERO_RULE_EXCEPT and c not in _floored]
        n_neg = int(sum((pd.to_numeric(pan[c], errors="coerce") < 0).sum() for c in _floored if c in pan.columns))
        if n_neg: bad(f"{n_neg} negative covariate cells survived into the final panel (the floor must set them to 0)")
        n_zero = int(sum((pd.to_numeric(pan[c], errors="coerce") == 0).sum() for c in zero_cols))
        ocols = [c for c in P.OUTCOME_VARS if c in pan.columns]
        n_empty = int((~np.isfinite(pan[ocols].apply(pd.to_numeric, errors="coerce").values.astype(np.float64)).any(axis=1)).sum())
        rep = os.path.join(out, "passb_1", "panel_missingness_report.csv")
        if n_zero: bad(f"{n_zero} exact-zero cells survived into the final panel")
        elif n_empty: bad(f"{n_empty} rows with no usable outcome survived into the final panel")
        elif not os.path.exists(rep): bad("panel_missingness_report.csv was not written")
        else:
            mr = pd.read_csv(rep)
            nd = mr[mr.variable == "NDVI"]
            ok(f"final panel: 0 exact zeros in {len(zero_cols)} policy variables, 0 rows without an outcome, "
               f"{len(pan)} rows; missingness report: NDVI missing {nd.missing.sum()} of {nd.rows.sum()} rows "
               f"({nd.missing.sum()/max(nd.rows.sum(),1):.1%} -- the injected zeros, minus rows the other file filled)")
        # the zeros must have been counted, not silently converted
        if os.path.exists(rep) and mr.zero_after_policy.sum() != 0: bad("report shows zeros after the policy")
        if os.path.exists(rep):
            need_cols = {"finite_core", "finite_rings", "share_missing_core", "share_missing_rings", "rows_core_in_export"}
            if not need_cols <= set(mr.columns): bad(f"missingness report lacks the group split: {sorted(need_cols - set(mr.columns))}")
            else: ok("missingness report splits every variable by treated core vs control rings")
    except Exception as e:
        bad(f"final-panel zero check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 13. zero cells are missing; rows with no outcome are dropped; a second file fills a zero -------------
    try:
        base = pd.DataFrame({"pixel_id": [1, 1, 2, 3], "Year": 2023, "Season": 1, "NDVI": [0.0, 0.41, 0.5, 0.0],
                             "LAI": [1.2, np.nan, np.nan, 0.0], "Rain": [0.0, 600.0, 590.0, 0.0],
                             "src_file": ["old.csv", "new.csv", "old.csv", "old.csv"], "file_mtime": [1.0, 2.0, 1.0, 1.0]})
        dz, stz = P.apply_missing_policy(base.copy())
        mz, _ = P.resolve_duplicates(dz.copy(), conflict_log=[])
        r1 = mz[mz.pixel_id == 1].iloc[0]
        mf, _ = P.resolve_duplicates(dz.copy(), conflict_log=[], fill_from_duplicates=True)     # v20.58: the fill is an option
        f1 = mf[mf.pixel_id == 1].iloc[0]
        if stz["zero_cells_set_missing"] != 5 or stz["rows_dropped_no_outcome"] != 1: bad(f"zero policy counts wrong: {stz}")
        elif r1.NDVI != 0.41 or r1.Rain != 600.0 or not pd.isna(r1.LAI): bad(f"the newer row is not kept as it is (default): {r1.to_dict()}")
        elif f1.NDVI != 0.41 or f1.Rain != 600.0 or f1.LAI != 1.2: bad(f"DEDUP_FILL_FROM_DUPLICATES = True: the gap was not filled from the other file: {f1.to_dict()}")
        else: ok("zero cells become missing before dedup; the newer row is kept as it is (its gap stays a gap; filled from the other file only "
                 "with DEDUP_FILL_FROM_DUPLICATES = True); empty rows are dropped")
    except Exception as e:
        bad(f"zero-policy check raised {type(e).__name__}: {e}")

    # ---- 13b. v20.25: two exports on grids 1.0 m / 0.6 m apart (overlap 0.85) are ONE set of pixels ----------
    try:
        lat0, lon0 = 16.44, 75.17; mlat = 1 / 110574.0; mlon = 1 / (111320.0 * np.cos(np.radians(lat0)))
        def _exp(path, years, eo, no, shift, mtime, lai_nan=False, n=10):
            rr = []
            for yy in years:
                for ss in (0, 1):
                    for kk in range(n * n):
                        e_ = (kk % n) * 10.0 + eo; n_ = (kk // n) * 10.0 + no
                        rr.append({"latitude": round(lat0 + n_ * mlat, 7), "longitude": round(lon0 + e_ * mlon, 7), "Year": yy, "Season": ss,
                                   "SubwshedID": 3, "Treat": 1 if yy >= 2022 else 0, "buff_km": 0 if kk % 5 == 0 else 1 + kk % 4,
                                   "NDVI": 0.40 + shift + 0.001 * kk, "LAI": np.nan if lai_nan else 1.2, "Rain": 600.0, "Tmax": 33.0,
                                   "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2})
            pd.DataFrame(rr).to_csv(path, index=False); os.utime(path, (mtime, mtime))
        res_ = {}
        for flag, fill_ in ((True, False), (False, False), (True, True)):      # v20.58: + the gap fill as the option it now is
            d_ = os.path.join(tmp, f"overlap_{flag}_{fill_}"); inp_ = os.path.join(d_, "in"); os.makedirs(inp_, exist_ok=True)
            _exp(os.path.join(inp_, "older_grid.csv"), [2022, 2023], 0.0, 0.0, 0.00, 1_700_000_000)
            _exp(os.path.join(inp_, "newer_grid.csv"), [2023, 2024], 1.0, 0.6, 0.05, 1_760_000_000, lai_nan=True)
            P.NEAR_DUPLICATE_PIXELS = flag; P.DEDUP_FILL_FROM_DUPLICATES = fill_
            try:
                o_ = os.path.join(d_, "out"); td_ = os.path.join(o_, "TEMP"); os.makedirs(td_, exist_ok=True)
                _r, _u, _e, _d, sh_ = P.run_pass_a(inp_, td_, o_, n_workers=1); P.run_pass_b(sh_, o_, n_workers=1)
            finally:
                P.DEDUP_FILL_FROM_DUPLICATES = False
            pan_ = P.pq.read_table(os.path.join(o_, "did_panel_full.parquet")).to_pandas()
            y23_ = pan_[(pan_.Year == 2023) & (pan_.Season == 1)]
            _bs_ = json.load(open(os.path.join(o_, "panel_build_settings.json"), encoding="utf-8"))
            res_[(flag, fill_)] = (pan_.pixel_id.nunique(), int((pan_.groupby("pixel_id").Year.nunique() == 3).sum()), len(y23_),
                                   round(float(y23_.NDVI.mean()), 4), int(y23_.LAI.notna().sum()), _bs_.get("dedup_fill_from_duplicates"),
                                   _bs_.get("dedup_values_not_used"), _bs_.get("dedup_values_filled"))
        P.NEAR_DUPLICATE_PIXELS = True
        on_, off_, fill_on_ = res_[(True, False)], res_[(False, False)], res_[(True, True)]
        # the two exports overlap in 2023, both seasons (annual + Kharif): 2 x 100 cells whose newer row lacks LAI -- 200 older LAI values
        # not used (v20.58: the check expected 100, one season's; the count is over every repeated cell -- found by the four-model gate)
        if on_[:3] == (100, 100, 100) and on_[4] == 0 and on_[5:] == (False, 200, 0) and off_[0] == 200 \
                and fill_on_[:5] == (100, 100, 100, on_[3], 100) and fill_on_[5:] == (True, 0, 200):
            ok(f"near-duplicate pixels: 200 ids -> 100 (every pixel continuous 2022-2024), one row per 2023 cell: the NEWER export's row "
               f"as it is (NDVI {on_[3]}; its missing LAI stays missing -- the older rows' {on_[6]} LAI values (2023, annual + Kharif) counted as "
               f"not used; filled only with DEDUP_FILL_FROM_DUPLICATES = True: {fill_on_[7]}); with merging off the old behaviour stays ({off_[0]} ids)")
        else:
            bad(f"near-duplicate merge wrong: on {on_}, off {off_}, fill on {fill_on_}")
    except Exception as e:
        bad(f"near-duplicate check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 13c. v20.27: messy buffer codes are recoded exactly; the export's Treat is checked as a PERIOD flag -----
    try:
        d_ = os.path.join(tmp, "design"); inp_ = os.path.join(d_, "in"); os.makedirs(inp_, exist_ok=True)
        codes = [0, "1 km", 2.0000001, "Buffer_3", "ring-4", 5, 7]          # 7 is not a valid ring
        rr = []
        for yy in (2020, 2021, 2022, 2023):
            for kk, bc in enumerate(codes):
                rr.append({"latitude": round(16.6 + kk * 1e-3, 6), "longitude": 75.3, "Year": yy, "Season": 0, "SubwshedID": 3,
                           "Treat": 1 if yy >= 2023 else 0,            # an export made with the WRONG year (2023): 2022 mis-flagged
                           "buff_km": bc, "NDVI": 0.4, "LAI": 1.2, "Rain": 600.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2})
        pd.DataFrame(rr).to_csv(os.path.join(inp_, "design_case.csv"), index=False)
        o_ = os.path.join(d_, "out"); td_ = os.path.join(o_, "TEMP"); os.makedirs(td_, exist_ok=True)
        _r, _u, _e, _d, sh_ = P.run_pass_a(inp_, td_, o_, n_workers=1); P.run_pass_b(sh_, o_, n_workers=1)
        pan_ = P.pq.read_table(os.path.join(o_, "did_panel_full.parquet")).to_pandas()
        dz = pd.read_csv(os.path.join(o_, "panel_design_check.csv"))
        g = pan_.groupby("buff_km")[["treatment", "control"]].max()
        okb = (g.loc[0, "treatment"] == 1 and g.loc[0, "control"] == 0 and all(g.loc[k, "control"] == 1 and g.loc[k, "treatment"] == 0 for k in (1, 2, 3, 4, 5))
               and -1 in g.index and g.loc[-1, "treatment"] == 0 and g.loc[-1, "control"] == 0)
        okp = bool((pan_.post == (pan_.Year >= 2022).astype(int)).all() and (pan_.pre == (pan_.Year < 2022).astype(int)).all()
                   and (pan_.did_term == pan_.treatment * pan_.post).all())
        n_mis = int(pan_.loc[pan_.Year == 2022, "treat_period_mismatch_flag"].sum())
        if okb and okp and n_mis == len(codes) and len(dz):
            ok(f"design: '1 km' / 2.0000001 / 'Buffer_3' / 'ring-4' recoded to rings 1-4 (control), 0 = treatment, 7 in neither group; "
               f"post = Year >= 2022, did = treatment x post; the mis-flagged 2022 export Treat detected on {n_mis} rows")
        else:
            bad(f"design case wrong: buffers {okb}, periods {okp}, Treat mismatches {n_mis} (expected {len(codes)})")
    except Exception as e:
        bad(f"design check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 13d. v20.28: pixels generated INSIDE the real shapefile polygons -> SWS confirmed / corrected / flagged -----
    try:
        import _sws_geometry as G_
        Lg = G_.SWSLocator.from_shapefile(); rg = np.random.default_rng(5)
        def _inside(site, buff, n):
            poly = [p for s_, b_, p in Lg.polys if s_ == site and b_ == buff][0]; bb = poly.bbox; got = []
            while sum(len(o) for o in got) < n:
                x = rg.uniform(bb[0], bb[2], 3000); y = rg.uniform(bb[1], bb[3], 3000); m = poly.contains(x, y)
                got.append(np.column_stack([x[m], y[m]]))
            xy = np.vstack(got)[:n]; return G_.tm_to_latlon(xy[:, 0], xy[:, 1])
        root_ = os.path.join(tmp, "SWSs20Final")
        def _exp(folder, site, id_col=None, wrong=0.0, outside=0):
            rr = []
            for b_ in range(6):
                la, lo = _inside(site, b_, 20)
                for k in range(len(la)):
                    for yy in (2021, 2022):
                        r = {"latitude": la[k], "longitude": lo[k], "Year": yy, "Season": 0, "SubwshedID": 1, "Treat": int(yy >= 2022),
                             "buff_km": b_, "NDVI": 0.4, "Rain": 600.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2}
                        if id_col: r[id_col] = site
                        rr.append(r)
            df_ = pd.DataFrame(rr)
            if wrong: w_ = rg.random(len(df_)) < wrong; df_.loc[w_, id_col] = site % 20 + 1
            if outside: o_ = df_.head(outside).copy(); o_["latitude"] += 0.5; df_ = pd.concat([df_, o_])
            os.makedirs(os.path.join(root_, folder), exist_ok=True); df_.to_csv(os.path.join(root_, folder, "x.csv"), index=False)
        _exp("Kodihalli/exports", 12, "SWSiD_All", wrong=0.25)
        _exp("Chhatrakodihalli/exports", 3, None, outside=6)
        P.INPUT_DIR = root_
        o_ = os.path.join(tmp, "sws_out"); td_ = os.path.join(o_, "TEMP"); os.makedirs(td_, exist_ok=True)
        _r, _u, _e, _d, sh_ = P.run_pass_a(root_, td_, o_, n_workers=1); P.run_pass_b(sh_, o_, n_workers=1)
        pan_ = P.pq.read_table(os.path.join(o_, "did_panel_full.parquet")).to_pandas()
        rep_ = pd.read_csv(os.path.join(o_, "site_tagging_report.csv"))
        px = pan_.groupby("site_id").pixel_id.nunique().to_dict()
        corrected = int(rep_["corrected"].sum()); outside = int(rep_["outside_all_polygons"].sum())
        good = (px.get(12) == 120 and px.get(3, 0) >= 120 and corrected > 0 and outside == 6
                and set(pan_.loc[pan_.site_id == 12, "buff_km"].unique()) == set(range(6))
                and set(pan_["sws_name"].astype(str).unique()) >= {"Kodihalli", "Chhatrakodihalli"})
        (ok if good else bad)(f"SWS from the shapefile: Kodihalli's {corrected} wrong-id rows corrected (120 pixels, rings 0-5 intact); "
                              f"Chhatrakodihalli found from its folder name (not Kodihalli); {outside} rows outside every polygon kept + flagged")
    except Exception as e:
        bad(f"SWS tagging check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 13e. v20.30: negative covariates floored at 0 at panel level; barrier switch; outcomes untouched --------
    try:
        def _neg_build(tag, **st):
            saved_ = (P.ALLOW_NEGATIVE_COVARIATES, dict(P.NEGATIVE_COVARIATE_RULE))
            for k_, v_ in st.items(): setattr(P, k_, v_)
            try:
                d_ = os.path.join(tmp, f"neg_{tag}"); inp_ = os.path.join(d_, "in"); os.makedirs(inp_, exist_ok=True); rr = []
                for kk in range(30):
                    for yy in (2021, 2022):
                        rr.append({"latitude": 16.6 + kk * 1e-3, "longitude": 75.3, "Year": yy, "Season": 1, "SubwshedID": 1, "Treat": int(yy >= 2022),
                                   "buff_km": 0 if kk % 5 == 0 else 1 + kk % 4, "NDVI": -0.05 if kk == 3 else 0.4,
                                   "Rain": {0: -0.4, 1: 0.0, 2: -12.0}.get(kk, 500.0), "Tmax": 33.0, "Tmean": 26.0,
                                   "Tmin": {5: -10.0, 6: -3.2}.get(kk, 19.0), "LandUse": 2})
                pd.DataFrame(rr).to_csv(os.path.join(inp_, "x.csv"), index=False)
                o_ = os.path.join(d_, "out"); td_ = os.path.join(o_, "TEMP"); os.makedirs(td_, exist_ok=True)
                _r, _u, _e, _d, sh_ = P.run_pass_a(inp_, td_, o_, n_workers=1); P.run_pass_b(sh_, o_, n_workers=1)
                pan_ = P.pq.read_table(os.path.join(o_, "did_panel_full.parquet")).to_pandas()
                at = lambda k, c_: pan_.loc[np.isclose(pan_.latitude, 16.6 + k * 1e-3), c_].iloc[0]
                return at(0, "Rain"), at(1, "Rain"), at(2, "Rain"), at(5, "Tmin"), at(6, "Tmin"), at(3, "NDVI")
            finally:
                P.ALLOW_NEGATIVE_COVARIATES, P.NEGATIVE_COVARIATE_RULE = saved_[0], saved_[1]
        f0 = _neg_build("floor"); f1 = _neg_build("keep", ALLOW_NEGATIVE_COVARIATES=True)
        f2 = _neg_build("missing", NEGATIVE_COVARIATE_RULE={"Rain": "missing", "Tmax": "missing", "Tmean": "missing", "Tmin": "missing"})
        good = (f0[0] == 0 and np.isnan(f0[1]) and f0[2] == 0 and np.isnan(f0[3]) and f0[4] == 0 and abs(f0[5] + 0.05) < 1e-6   # -10 C clamp -> missing
                and f1[0] < 0 and f1[2] < 0 and f1[4] < 0 and np.isnan(f1[3]) and np.isnan(f1[1])      # v20.54: barrier off keeps REAL negatives;
                and all(np.isnan(x) for x in (f2[0], f2[2], f2[3], f2[4])))                         # the -10 C clamp stays missing
        (ok if good else bad)(f"negative covariates: floored to 0 (Rain -0.4/-12, Tmin -3.2 -> 0; the -10 C clamp -> missing), an original masked 0 stays missing, "
                              f"NDVI -0.05 untouched; barrier removed keeps real negatives (the -10 C clamp stays missing); rule 'missing' blanks them" if good else f"negative floor wrong: {f0} / {f1} / {f2}")
    except Exception as e:
        bad(f"negative-floor check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 13f. v20.30: PASS A -> PASS B in RAM == shard files == RAM with a forced spill -------------------------
    try:
        import _hardware as H_
        src_ = os.path.join(tmp, "parity_in"); files_ = write_synthetic_exports(src_)
        KEYS = ["site_id", "pixel_id", "Year", "Season"]
        def _pb(in_memory, fits=None):
            o_ = tempfile.mkdtemp(); td_ = os.path.join(o_, "TEMP"); os.makedirs(td_); f_ = H_.fits
            if fits: H_.fits = fits
            try:
                _r, _u, _e, _d, sh_ = P.run_pass_a(src_, td_, o_, n_workers=1, in_memory=in_memory); P.run_pass_b(sh_, o_, n_workers=1)
            finally:
                H_.fits = f_
            kinds_ = {type(x).__name__ for x in sh_.values()}
            return P.pq.read_table(os.path.join(o_, "did_panel_full.parquet")).to_pandas().sort_values(KEYS, kind="mergesort").reset_index(drop=True), kinds_
        def _eq(x, y):
            return x.shape == y.shape and all(all((a == b) or (pd.isna(a) and pd.isna(b)) for a, b in zip(x[k].astype(object), y[k].astype(object))) for k in x.columns)
        A, ka = _pb(False); B, kb = _pb(True); cnt = {"n": 0}
        def _spill(nb, device="ram"): cnt["n"] += 1; return cnt["n"] <= 4
        Cc, kc = _pb(True, _spill)
        good = _eq(A, B) and _eq(A, Cc) and kb == {"MemBlock"} and ka == {"str"}
        (ok if good else bad)(f"memory first: PASS A -> PASS B in RAM ({kb}) and with a forced spill to shards give the IDENTICAL panel ({A.shape})")
    except Exception as e:
        bad(f"in-RAM parity check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 14. v20.24: P08 end to end with the SHIPPED ground inputs, resolved from the bundle layout ----------
    try:
        gi = C_ = None
        import _common as C_
        gi = C_.resolve_ground_inputs_dir()
        _p00_code = ["".join(c_["source"]) for c_ in json.load(open(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))[0], encoding="utf-8"))["cells"]
                     if c_["cell_type"] == "code"]
        if not any(c_.startswith("# ===== P08_Ground_Site_Linkage") for c_ in _p00_code):
            # v20.58: a project whose models use no ground data (RWD_4Models: M01 M02 M16 M34) has no P08 in its P00 -- said, not skipped silently
            print(f"[INFO]    P08 (ground linkage) is not part of this project's P00: its models ({' '.join(C_.pipeline_models()) if C_.PIPELINE_MODELS else 'all'}) "
                  f"use no ground data -- nothing to check")
        elif not os.path.exists(os.path.join(gi, "01_benchmark_sites_master.csv")):
            print("[INFO]    shipped REWARD_ground_inputs not found next to this engine -- P08 end-to-end check skipped")
        else:
            import re as _re
            if getattr(P.pa, "__version__", "0.0.0") == "0.0.0":            # sandbox stub: route pandas' to_parquet through it
                pd.DataFrame.to_parquet = lambda self, path, index=False, **k: P.pq.write_table(P.pa.Table.from_pandas(self, preserve_index=False), path)
            ms = pd.read_csv(os.path.join(gi, "01_benchmark_sites_master.csv"), dtype=str)
            pts = ms[["lat_median", "lon_median"]].dropna().astype(float).drop_duplicates()
            rows_ = []
            for k, (la, lo) in enumerate(pts.values):
                for y in (2022, 2023):
                    for s in (0, 1, 2, 3): rows_.append((50_000 + k, y, s, 0 if k % 5 == 0 else 1, "SW1", la, lo, 0.4, 2.0, 500.0, 33.0, 26.0, 19.0))
            gdf = pd.DataFrame(rows_, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "latitude", "longitude", "NDVI", "LAI", "Rain", "Tmax", "Tmean", "Tmin"])
            gdir = os.path.join(tmp, "p08"); os.makedirs(gdir, exist_ok=True)
            gpanel = os.path.join(gdir, "panel.parquet"); P.pq.write_table(P.pa.Table.from_pandas(gdf, preserve_index=False), gpanel)
            saved = (C_.PREPARED_PANEL, C_.RESULTS_ROOT, C_.GROUND_LINKS_PATH, C_.GROUND_TRUTH_OUTCOMES_PATH, C_.GROUND_INPUTS_DIR)
            C_.PREPARED_PANEL = gpanel; C_.RESULTS_ROOT = os.path.join(gdir, "results"); C_.GROUND_INPUTS_DIR = gi
            C_.GROUND_LINKS_PATH = os.path.join(C_.RESULTS_ROOT, "P08", "ground_links.parquet")
            C_.GROUND_TRUTH_OUTCOMES_PATH = os.path.join(C_.RESULTS_ROOT, "P08", "ground_truth_outcomes.csv")
            import validate_all_models as _V
            # v20.38: P08 lives inside P00 -- run exactly P00's P08 cells (the code you run), on the shipped inputs
            _p00 = json.load(open(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))[0], encoding="utf-8"))
            _p8 = [c_ for c_ in _p00["cells"] if c_["cell_type"] == "code" and "".join(c_["source"]).startswith("# ===== P08_Ground_Site_Linkage")]
            assert _p8, "P00 has no P08 cells"
            _cell = lambda t: {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [t]}
            _nbd = {"cells": [_cell("RUN_GROUND_LINKAGE = True\nimport os, numpy as np, pandas as pd")] + _p8,
                    "metadata": _p00["metadata"], "nbformat": 4, "nbformat_minor": 5}
            nb = os.path.join(tempfile.mkdtemp(), "P08_cells_of_P00.ipynb")
            json.dump(_nbd, open(nb, "w", encoding="utf-8"))
            st, err, log = _V.run_notebook(nb)
            okp = os.path.exists(C_.GROUND_LINKS_PATH) and os.path.exists(C_.GROUND_TRUTH_OUTCOMES_PATH) and "[FAILED]" not in log
            (ok if okp else bad)(f"P08 end to end on the shipped ground inputs: links {os.path.exists(C_.GROUND_LINKS_PATH)}, "
                                 f"M07 file {os.path.exists(C_.GROUND_TRUTH_OUTCOMES_PATH)}, failures {'none' if '[FAILED]' not in log else 'SEE LOG'}")
            C_.PREPARED_PANEL, C_.RESULTS_ROOT, C_.GROUND_LINKS_PATH, C_.GROUND_TRUTH_OUTCOMES_PATH, C_.GROUND_INPUTS_DIR = saved
    except Exception as e:
        bad(f"P08 end-to-end check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)

    # ---- 15. v20.24: the season report ranks annual vs seasonal coverage and names the rows used -------------------
    try:
        import _common as C2
        rep = C2.season_choice_report(path=os.path.join(out, "passb_1", "did_panel_full.parquet"), verbose=False)
        need = {"annual_share_finite", "seasonal_share_finite", "annual_core_share_finite", "rows_used_with_auto"}
        if not need <= set(rep.columns) or not len(rep): bad("season_choice_report is incomplete")
        else: ok(f"season_choice_report covers {len(rep)} outcomes and names the rows each one uses")
    except Exception as e:
        bad(f"season report raised {type(e).__name__}: {e}")

    # v20.50: PASS B with a process pool and blocks held in RAM -- the Windows failure ("OSError: [WinError 87]" when a
    # multi-GB block is pickled into a worker). Large in-RAM blocks now reach the workers as files; the panel must be
    # identical to the one the parent builds by itself (the sequential path).
    try:
        import tempfile as _tf, pandas as _pd
        _root = _tf.mkdtemp(prefix="vp_spill_in_"); write_synthetic_exports(_root, n_files=4, n_pix=30, years=(2020, 2021, 2022, 2023), seasons=(0, 1))
        _saved = P.PICKLE_SAFE_BYTES; _panels = {}
        for _lab, _safe, _w in (("files", 1, 2), ("sequential", 10**12, 1)):
            _o = _tf.mkdtemp(prefix=f"vp_spill_{_lab}_"); P.PICKLE_SAFE_BYTES = _safe
            _sh = P.run_pass_a(_root, os.path.join(_o, "_tmp"), _o, n_workers=1, in_memory=True)[-1]
            _fp = P.run_pass_b(_sh, _o, n_workers=_w); _fp = _fp if isinstance(_fp, str) else os.path.join(_o, "did_panel_full.parquet")
            _d = _pd.read_parquet(_fp); _k = [c for c in ("pixel_id", "site_id", "Year", "Season") if c in _d.columns]
            _panels[_lab] = _d.sort_values(_k).reset_index(drop=True).drop(columns=[c for c in ("src_file", "file_mtime") if c in _d.columns])
        P.PICKLE_SAFE_BYTES = _saved
        if _panels["files"].equals(_panels["sequential"]):
            ok(f"PASS B pool: in-RAM blocks handed to the worker processes as files == the sequential panel ({len(_panels['files']):,} rows)")
        else:
            bad("PASS B pool: the panel built from spilled blocks differs from the sequential one")
    except Exception as e:
        bad(f"PASS B spill check raised {type(e).__name__}: {e}")
    print("=" * 74)
    if PROBLEMS:
        print(f"{len(PROBLEMS)} PROBLEM(S):"); [print("  -", p) for p in PROBLEMS]; return 1
    print("CLEAN: the preparation path works end to end on synthetic exports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
