"""
build_panel.py -- build the DID-ready panel from a folder of exports, from the command line (the same engine and rules as P00; nothing of the
design is set here -- every model sets its own in its CELL 1 / R_Mxx).

    python build_panel.py --input D:\LKT\RWD_Artal\data                      # output -> <input>\output (the P00 layout)
    python build_panel.py --input D:\exports\Jantapur --output D:\panels\Jantapur [--workers 60] [--force] [--fund PATH] [--crosswalk PATH]
    python build_panel.py --input ... --no-ground --no-readiness               # the panel and its reports only

Steps (P00's cells, in order): paths -> machine autotune -> input audit (Treat 1 / 0, buff_km 0 / 1-5 on every file) -> PASS A (ingest,
harmonise, pixel ids, per-file dedup; every core) -> the fund timing and dose tables -> PASS B (ordered panel, cross-file dedup, the
design columns from the exports' flag, the dose merge) -> integrity, validity verdict, duplicates confirmed, readiness report -> the season
report, the default scenario saved for the models -> the per-variable estimator files, the baseline means and the outcome screen -> the
model-readiness table. An existing valid panel is kept unless --force. The R twin: Rscript build_panel.R input=... [output=...].
"""
import os, sys, json, argparse, traceback, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)

def main(argv=None):
    ap = argparse.ArgumentParser(description="REWARD DiD -- build the DID-ready panel from a folder of exports")
    ap.add_argument("--input", required=True, help="the folder holding the export CSVs (any depth)")
    ap.add_argument("--output", default=None, help="where the panel and its reports go (default: <input>/output)")
    ap.add_argument("--workers", type=int, default=None, help="PASS A worker processes (default: every core the platform allows)")
    ap.add_argument("--force", action="store_true", help="rebuild even when a valid panel is already there")
    ap.add_argument("--fund", default=None, help="the fund-release workbook (default: _paths.py / P00_Settings)")
    ap.add_argument("--crosswalk", default=None, help="the sub-watershed crosswalk workbook (default: _paths.py)")
    ap.add_argument("--no-ground", action="store_true", help="skip the ground-site linkage steps (P08)")
    ap.add_argument("--no-readiness", action="store_true", help="skip the estimator files, baseline means, screen and readiness table (P09 / P10)")
    ap.add_argument("--outcomes", default=None, help="comma-separated outcomes for the estimator files / screen (default: every outcome the panel has)")
    a = ap.parse_args(argv); t0 = time.time()
    import _prep_common as P, _common as C
    P.require_engine("20.44")
    paths = P.set_paths(input_dir=a.input, output_dir=a.output, fund_release=a.fund, crosswalk=a.crosswalk, verbose=True)
    C.start_cell_log("build_panel")
    P.validate_output_dir(); P.autotune_prep()
    P.step(1, f"inputs: {P.INPUT_DIR} -> output: {P.OUTPUT_DIR}")
    P.info(f"missing-value policy: NaN and {'|value| <= ' + str(P.PRECISION_TOLERANCE) if getattr(P, 'USE_PRECISION_TOLERANCE', False) else 'exact 0'} = no-data in {len(P.ZERO_RULE_VARS)} variables; rows with no usable outcome are dropped")
    try: P.audit_site_tags(P.INPUT_DIR, P.OUTPUT_DIR, n_workers=a.workers)
    except Exception as e: P.warn(f"sub-watershed tagging audit not run ({type(e).__name__}: {e})")
    if not a.force and P.final_panel_is_valid():
        P.ok(f"a valid panel is already there: {P.FINAL_PANEL} (--force rebuilds it)"); shard_paths = None
    else:
        P.step(3, "PASS A -- ingest, harmonise, stable pixel ids, QC, per-file dedup")
        try: P.KNOWN_SUBWSHED_NAMES = P.load_subwshed_crosswalk(P.SUBWSHED_CROSSWALK_PATH)["Sub Watershed Name"].tolist()
        except Exception as e: P.warn(f"crosswalk unavailable ({e}) -- site_name will be unresolved")
        P.IN_MEMORY_BLOCKS = True
        try:
            import _hardware as _H; print("[INFO]   ", _H.memory_report())
        except Exception: pass
        registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths = P.run_pass_a(P.INPUT_DIR, P.TEMP_DIR, P.OUTPUT_DIR, n_workers=a.workers)
        P.ok(f"PASS A COMPLETE: {len(registry.uids):,} unique pixels, {len(shard_paths)} shards")
        P.step(4, "fund-release timing and dose table")
        dose_table = None; xw = None
        try:
            fund = P.load_fund_progress(P.FUND_RELEASE_PATH); dose = P.build_district_season_dose(fund)
            xw = P.load_subwshed_crosswalk(P.SUBWSHED_CROSSWALK_PATH); dose_table = P.apply_subwshed_division(dose, xw, threshold_pct=50.0)
            dose_table.to_csv(os.path.join(P.OUTPUT_DIR, "dose_table.csv"), index=False); P.ok(f"dose table: {len(dose_table)} rows")
        except Exception as e: P.warn(f"fund / dose unavailable ({e}) -- the panel carries NaN dose columns")
        try:
            import _fund as F; F.build_fund_tables(P.FUND_RELEASE_PATH, list(range(2010, 2036)), out_dir=os.path.join(P.OUTPUT_DIR, "results", "FUND"))
        except Exception as e: P.warn(f"fund timing / dose tables not written ({type(e).__name__}: {e})")
        P.step(5, "PASS B -- ordered panel, cross-file dedup, the design columns, the dose merge")
        final_path = P.run_pass_b(shard_paths, P.OUTPUT_DIR, dose_table=dose_table, crosswalk=xw)
        P.ok(f"panel written -> {final_path}")
        man = P.build_manifest(final_path); print(json.dumps({k: v for k, v in man.items() if k != "row_order_check"}, indent=2, default=str))
    # the integrity, validity and readiness report (P00 step 6) -- streamed
    P.step(6, "panel integrity, validity verdict and readiness -- streamed")
    import pyarrow.parquet as pq
    KEY = ["buff_km", "Season", "Year", "treatment", "control", "pre", "post", "did_term", "subwshed_id", "site_name", "District", "LandUse", "first_treat_agri_year"]
    OUT = ["NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE", "Rain", "Tmax", "Tmean", "Tmin", "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI"]
    have = set(pq.ParquetFile(P.FINAL_PANEL).schema_arrow.names)
    st = P.streaming_panel_stats(P.FINAL_PANEL, key_cols=[k for k in KEY if k in have], outcome_cols=[o for o in OUT if o in have], pixel_sample_mod=100)
    print(f"rows {st['n_rows']:,} | est. treated pixels {st['n_treated_pixels_est']:,} | est. control pixels {st['n_control_pixels_est']:,} | treatment x post cells: {st['cells_treat_x_post']}")
    (P.ok if st["duplicates_total"] == 0 else P.fail)(f"duplicate pixel-Year-Season rows: {st['duplicates_total']} (must be 0)")
    ncl = len(st["unique_key_values"].get("subwshed_id", {})) or None; npre = sum(1 for y in st["unique_key_values"].get("Year", {}) if int(y) < P.POST_CUTOFF)
    V = P.panel_validity_from_stats(st, n_clusters=ncl, n_pre_years=npre)
    for f in V["failures"]: P.fail(f)
    for w in V["warnings"]: P.warn(w)
    (P.ok if V["VERDICT"].startswith("VALID") else P.fail)(f"VERDICT: {V['VERDICT']}")
    json.dump({"stats": st, "validity": V}, open(os.path.join(P.OUTPUT_DIR, "readiness_report.json"), "w"), indent=2, default=str)
    P.confirm_panel_duplicates(P.FINAL_PANEL)
    P.panel_precision_report(P.FINAL_PANEL, P.OUTPUT_DIR)       # 2 Oct: the precision the panel holds, per variable
    C.PREPARED_PANEL = P.FINAL_PANEL; C.outcome_identities(verbose=True)
    # the season report and the default scenario the models adopt for an option their CELL 1 leaves unset (P00 step 8, the engine defaults)
    P.step(8, "the season report and the default scenario (every optional customisation OFF; a model's CELL 1 decides for itself)")
    try:
        C.season_choice_report(path=P.FINAL_PANEL, save_as=os.path.join(P.OUTPUT_DIR, "season_choice_report.csv"))
        C.set_scenario(verbose=False); C.resolve_design(verbose=True, force=True); C.fragment_table(verbose=True)
        tt = C.timing_table(save_as=os.path.join(C.RESULTS_ROOT, "sws_timing.csv")); print(tt.to_string(index=False)); C.save_scenario(verbose=True)
    except Exception as e: P.warn(f"the design report / default scenario not written ({type(e).__name__}: {e})")
    if not a.no_readiness:
        P.step(9, "per-variable estimator files, baseline means, the outcome screen, the model-readiness table")
        try:
            outs = [x.strip() for x in a.outcomes.split(",")] if a.outcomes else None
            C.autotune(); C.build_estimator_files(outcomes=outs, overwrite=a.force); C.baseline_and_counts_all(outcomes=outs); C.screen_all_outcomes(outcomes=outs)
            import _readiness as R; C.load_scenario(verbose=False); R.model_readiness(C=C, outcomes=outs or (C.SELECTED_OUTCOMES if getattr(C, "SELECTED_OUTCOMES", None) else ["NDVI"]), compare="auto")
        except Exception as e: P.warn(f"readiness steps not completed ({type(e).__name__}: {e})"); traceback.print_exc()
    P.ok(f"panel: {P.FINAL_PANEL} ({time.time() - t0:.0f} s). Next: any model notebook (its CELL 1 sets the design), or orchestrator.py --config config/analysis_config.yaml")
    return 0

if __name__ == "__main__":
    sys.exit(main())
