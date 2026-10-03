"""
build_panel.py -- build the DID-ready panel from a folder of exports: from the command line, or step by step from a notebook
(01_Panel_Preparation/P00b_Build_Panel_From_Path.ipynb) with every step's result kept in a named attribute you can print.

    python build_panel.py --input D:\LKT\RWD_Artal\data                      # output -> <input>\output (the P00 layout)
    python build_panel.py --input D:\exports\Jantapur --output D:\panels\Jantapur [--workers 60] [--force] [--fund PATH] [--crosswalk PATH]
    python build_panel.py --input ... --no-readiness                          # the panel and its reports only

    from build_panel import PanelBuild                                        # in Python / a notebook
    B = PanelBuild(r"D:\LKT\RWD_Artal\data")                                  # the parent folder of the exports; output = <input>\output
    B.run_all()                                                               # or one step at a time: B.audit(); B.pass_a(); B.dose(); B.pass_b();
    B.summary(); B.validity["VERDICT"]; B.precision_report; B.stats          #   B.integrity(); B.precision(); B.design_defaults(); B.readiness()

Steps (P00's cells, in order): paths -> machine autotune -> input audit (Treat 1 / 0, buff_km 0 / 1-5 on every file) -> PASS A (ingest,
harmonise, pixel ids, per-file dedup; every core) -> the fund timing and dose tables -> PASS B (ordered panel, cross-file dedup, the
design columns from the exports' flag, the dose merge) -> integrity, validity verdict, duplicates confirmed, readiness report -> the
precision report and the outcome identities -> the season report, the default scenario saved for the models -> the per-variable estimator
files, the baseline means, the outcome screen and the model-readiness table. An existing valid panel is kept unless force. Nothing of the
DESIGN is set here -- every model sets its own in its CELL 1. The R twin: Rscript build_panel.R input=... [output=...].
"""
import os, sys, json, argparse, traceback, time
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)


class PanelBuild:
    """The panel-preparation pipeline as steps. Every step stores what it produced on the object (see `summary()`), so a notebook can
    print any of it between the steps; `run_all()` runs them in sequence. Files are written exactly as P00 / the command line write them."""
    STEPS = ("audit", "pass_a", "dose", "pass_b", "integrity", "precision", "design_defaults", "readiness")

    def __init__(self, input_dir, output_dir=None, workers=None, force=False, fund=None, crosswalk=None, readiness=True, outcomes=None, verbose=True):
        self.input_dir_arg, self.output_dir_arg = input_dir, output_dir
        self.workers, self.force, self.fund_arg, self.crosswalk_arg, self.do_readiness, self.verbose = workers, bool(force), fund, crosswalk, bool(readiness), verbose
        self.outcomes = [x.strip() for x in outcomes.split(",")] if isinstance(outcomes, str) else (list(outcomes) if outcomes else None)
        self.results, self.timings, self.done = {}, {}, []
        self.t0 = time.time()
        self.paths()

    # ---- bookkeeping ---------------------------------------------------------------------------------------------------------------
    def _keep(self, name, value, what):
        """Store a step's result under `name` (an attribute you can print) and describe it in `results`."""
        setattr(self, name, value); self.results[name] = what; return value

    def _timed(self, step, fn):
        t = time.time(); out = fn(); self.timings[step] = round(time.time() - t, 1); self.done.append(step); return out

    # ---- 0 paths -------------------------------------------------------------------------------------------------------------------
    def paths(self):
        import _prep_common as P, _common as C
        self.P, self.C = P, C
        P.require_engine("20.44")
        self._keep("paths_info", P.set_paths(input_dir=self.input_dir_arg, output_dir=self.output_dir_arg, fund_release=self.fund_arg, crosswalk=self.crosswalk_arg, verbose=self.verbose),
                   "the folders in force (input, output, temp, panel, results)")
        C.start_cell_log("build_panel")
        P.validate_output_dir(); P.autotune_prep()
        self.input_dir, self.output_dir, self.panel_path, self.temp_dir = P.INPUT_DIR, P.OUTPUT_DIR, P.FINAL_PANEL, P.TEMP_DIR
        P.step(1, f"inputs: {P.INPUT_DIR} -> output: {P.OUTPUT_DIR}")
        P.info(f"missing-value policy: NaN and {'|value| <= ' + str(P.PRECISION_TOLERANCE) if getattr(P, 'USE_PRECISION_TOLERANCE', False) else 'exact 0'} = no-data in {len(P.ZERO_RULE_VARS)} variables; "
               f"rows with no usable outcome leave after the cross-file dedup; negative covariates {'allowed' if getattr(P, 'ALLOW_NEGATIVE_COVARIATES', False) else 'floored at 0'}")
        return self.paths_info

    # ---- 2 the input audit ---------------------------------------------------------------------------------------------------------
    def audit(self):
        """Every export file: its Treat flag (1 = post / 0 = pre), its buff_km codes (0 = treatment, 1-5 = control), its sub-watershed tag."""
        P = self.P
        def _run():
            try: P.audit_site_tags(P.INPUT_DIR, P.OUTPUT_DIR, n_workers=self.workers)
            except Exception as e: P.warn(f"sub-watershed tagging audit not run ({type(e).__name__}: {e})")
            import pandas as pd
            for name, fn, what in (("input_audit", "input_design_audit.csv", "per export file: Treat 1 / 0 rows, buff_km 0 / 1-5 rows, flag-vs-year disagreements (written by PASS A; read back here when present)"),
                                   ("site_tagging", "site_tagging_by_file.csv", "per export file: the sub-watershed its rows fall in, confirmed / corrected / assigned")):
                f = os.path.join(P.OUTPUT_DIR, fn)
                self._keep(name, pd.read_csv(f) if os.path.exists(f) else None, what)
            self._keep("files", sorted(P.discover_input_files(P.INPUT_DIR, P.OUTPUT_DIR, P.TEMP_DIR, verbose=False)[0]), "the export files PASS A will read (the pipeline's own products excluded)")
            return self.files
        return self._timed("audit", _run)

    # ---- 3 PASS A ------------------------------------------------------------------------------------------------------------------
    def pass_a(self):
        """Ingest, harmonise, stable pixel ids, QC, per-file dedup -- every core. Kept: registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths."""
        P = self.P
        def _run():
            if not self.force and P.final_panel_is_valid():
                P.ok(f"a valid panel is already there: {P.FINAL_PANEL} (force=True rebuilds it)")
                self._keep("panel_kept", True, "True = the panel on disk was valid and kept (PASS A / B skipped)"); self._keep("shard_paths", None, "PASS A shards (none: the panel was kept)")
                return None
            self._keep("panel_kept", False, "False = the panel was (re)built in this run")
            P.step(3, "PASS A -- ingest, harmonise, stable pixel ids, QC, per-file dedup")
            try: P.KNOWN_SUBWSHED_NAMES = P.load_subwshed_crosswalk(P.SUBWSHED_CROSSWALK_PATH)["Sub Watershed Name"].tolist()
            except Exception as e: P.warn(f"crosswalk unavailable ({e}) -- site_name will be unresolved")
            P.IN_MEMORY_BLOCKS = True
            try:
                import _hardware as _H; print("[INFO]   ", _H.memory_report())
            except Exception: pass
            registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths = P.run_pass_a(P.INPUT_DIR, P.TEMP_DIR, P.OUTPUT_DIR, n_workers=self.workers)
            self._keep("registry", registry, "PASS A's pixel registry (registry.uids = the set of pixel ids)")
            self._keep("n_pixels_pass_a", len(registry.uids), "unique pixels after PASS A")
            self._keep("unresolved_cols", unresolved_cols, "column names PASS A could not map (per file)")
            self._keep("parse_errors", parse_errors, "files or columns PASS A could not read (per file)")
            self._keep("dedup_conflicts", dedup_conflicts, "within-file duplicate conflicts PASS A resolved")
            self._keep("shard_paths", shard_paths, "the (Year, Season) blocks PASS A wrote (in RAM or shard files) for PASS B")
            P.ok(f"PASS A COMPLETE: {len(registry.uids):,} unique pixels, {len(shard_paths)} shards")
            import pandas as pd
            f = os.path.join(P.OUTPUT_DIR, "input_design_audit.csv")
            if os.path.exists(f): self._keep("input_audit", pd.read_csv(f), "per export file: Treat 1 / 0 rows, buff_km 0 / 1-5 rows, flag-vs-year disagreements")
            return shard_paths
        return self._timed("pass_a", _run)

    # ---- 4 the fund timing and the dose --------------------------------------------------------------------------------------------
    def dose(self):
        """The fund-release workbook -> the dose per district x season, divided over the sub-watersheds (dose_table); the fund timing tables."""
        P = self.P
        def _run():
            self._keep("dose_table", None, "dose per district x agricultural year x season (None when the fund file is unavailable)"); self._keep("crosswalk", None, "the sub-watershed crosswalk")
            if getattr(self, "panel_kept", False): P.info("fund / dose: the panel was kept -- its dose columns stand"); return None
            P.step(4, "fund-release timing and dose table")
            try:
                fund = P.load_fund_progress(P.FUND_RELEASE_PATH); dose = P.build_district_season_dose(fund)
                xw = P.load_subwshed_crosswalk(P.SUBWSHED_CROSSWALK_PATH); dose_table = P.apply_subwshed_division(dose, xw, threshold_pct=50.0)
                dose_table.to_csv(os.path.join(P.OUTPUT_DIR, "dose_table.csv"), index=False); P.ok(f"dose table: {len(dose_table)} rows")
                self._keep("fund", fund, "the fund-release workbook as read"); self._keep("dose_table", dose_table, "dose per district x agricultural year x season"); self._keep("crosswalk", xw, "the sub-watershed crosswalk")
            except Exception as e: P.warn(f"fund / dose unavailable ({e}) -- the panel carries NaN dose columns")
            try:
                import _fund as F; self._keep("fund_tables", F.build_fund_tables(P.FUND_RELEASE_PATH, list(range(2010, 2036)), out_dir=os.path.join(P.OUTPUT_DIR, "results", "FUND")), "the fund timing / dose tables per sub-watershed (results/FUND)")
            except Exception as e: P.warn(f"fund timing / dose tables not written ({type(e).__name__}: {e})")
            return self.dose_table
        return self._timed("dose", _run)

    # ---- 5 PASS B ------------------------------------------------------------------------------------------------------------------
    def pass_b(self):
        """One ordered panel: cross-file dedup, the design columns from the exports' flag, the dose merge. Kept: final_path, manifest."""
        P = self.P
        def _run():
            if getattr(self, "panel_kept", False):
                self._keep("final_path", P.FINAL_PANEL, "the panel file"); return P.FINAL_PANEL
            P.step(5, "PASS B -- ordered panel, cross-file dedup, the design columns, the dose merge")
            final_path = P.run_pass_b(self.shard_paths, P.OUTPUT_DIR, dose_table=self.dose_table, crosswalk=self.crosswalk)
            P.ok(f"panel written -> {final_path}")
            self._keep("final_path", final_path, "the panel file")
            man = P.build_manifest(final_path); self._keep("manifest", man, "the panel's manifest (rows, columns, blocks, settings)")
            print(json.dumps({k: v for k, v in man.items() if k != "row_order_check"}, indent=2, default=str))
            return final_path
        return self._timed("pass_b", _run)

    # ---- 6 integrity, validity, readiness ------------------------------------------------------------------------------------------
    def integrity(self):
        """Streamed statistics of the panel, the validity verdict, duplicates confirmed. Kept: stats, validity, readiness_report."""
        P = self.P
        def _run():
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
            rp = os.path.join(P.OUTPUT_DIR, "readiness_report.json"); json.dump({"stats": st, "validity": V}, open(rp, "w"), indent=2, default=str)
            self._keep("stats", st, "streamed panel statistics (rows, pixels, cells, unique key values, duplicates)")
            self._keep("validity", V, "the validity verdict with its failures and warnings (validity['VERDICT'])")
            self._keep("readiness_report", rp, "readiness_report.json (stats + validity)")
            self._keep("duplicates", P.confirm_panel_duplicates(P.FINAL_PANEL), "the duplicate check on the written panel")
            return V
        return self._timed("integrity", _run)

    # ---- 7 precision and identities ------------------------------------------------------------------------------------------------
    def precision(self):
        """The precision the panel holds per variable (the smallest difference present, whether float32 would have lost it); the outcome identities."""
        P, C = self.P, self.C
        def _run():
            P.step(7, "precision report and outcome identities")
            self._keep("precision_report", P.panel_precision_report(P.FINAL_PANEL, P.OUTPUT_DIR), "per variable: stored dtype, distinct values, smallest difference, decimals needed, float32 flags (panel_precision_report.csv)")
            C.PREPARED_PANEL = P.FINAL_PANEL
            self._keep("identities", C.outcome_identities(verbose=True), "outcomes that are exact linear functions of another (their estimates follow)")
            return self.precision_report
        return self._timed("precision", _run)

    # ---- 8 the season report and the default scenario ------------------------------------------------------------------------------
    def design_defaults(self):
        """The season report and the default scenario the models adopt for an option their CELL 1 leaves unset (every optional customisation OFF)."""
        P, C = self.P, self.C
        def _run():
            P.step(8, "the season report and the default scenario (every optional customisation OFF; a model's CELL 1 decides for itself)")
            try:
                self._keep("season_report", C.season_choice_report(path=P.FINAL_PANEL, save_as=os.path.join(P.OUTPUT_DIR, "season_choice_report.csv")), "rows per season x year: which seasons carry data (season_choice_report.csv)")
                C.set_scenario(verbose=False); C.resolve_design(verbose=True, force=True)
                self._keep("design", dict(C._RESOLVED) if isinstance(C._RESOLVED, dict) else C._RESOLVED, "DESIGN IN EFFECT of the defaults (choices, notes)")
                self._keep("fragments", C.fragment_table(verbose=True), "rows per fragment code (own sub-watershed / another's / outside)")
                tt = C.timing_table(save_as=os.path.join(C.RESULTS_ROOT, "sws_timing.csv")); print(tt.to_string(index=False))
                self._keep("timing_table", tt, "treatment timing per sub-watershed (fund / registry / fixed) -> results/sws_timing.csv")
                C.save_scenario(verbose=True); self._keep("scenario", dict(C.ACTIVE), "the default scenario saved for the models")
            except Exception as e: P.warn(f"the design report / default scenario not written ({type(e).__name__}: {e})")
            return getattr(self, "timing_table", None)
        return self._timed("design_defaults", _run)

    # ---- 9 estimator files, baselines, screen, readiness ---------------------------------------------------------------------------
    def readiness(self):
        """Per-variable estimator files, the baseline means, the outcome screen and the model-readiness table (skipped when readiness=False)."""
        P, C = self.P, self.C
        def _run():
            if not self.do_readiness: P.info("readiness steps skipped (readiness=False)"); return None
            P.step(9, "per-variable estimator files, baseline means, the outcome screen, the model-readiness table")
            try:
                outs = self.outcomes
                C.autotune(); C.build_estimator_files(outcomes=outs, overwrite=self.force)
                self._keep("baselines", C.baseline_and_counts_all(outcomes=outs), "baseline means and pixel counts per outcome")
                self._keep("screen", C.screen_all_outcomes(outcomes=outs), "the outcome screen per outcome (fill year-seasons, collapsed coverage)")
                import _readiness as R; C.load_scenario(verbose=False)
                self._keep("readiness_table", R.model_readiness(C=C, outcomes=outs or (C.SELECTED_OUTCOMES if getattr(C, "SELECTED_OUTCOMES", None) else ["NDVI"]), compare="auto"),
                           "which of the 45 models this panel completes / limits / needs data for (MODEL_READINESS)")
            except Exception as e: P.warn(f"readiness steps not completed ({type(e).__name__}: {e})"); traceback.print_exc()
            return getattr(self, "readiness_table", None)
        return self._timed("readiness", _run)

    # ---- all, and what is there ----------------------------------------------------------------------------------------------------
    def run_all(self):
        for s in self.STEPS: getattr(self, s)()
        self.P.ok(f"panel: {self.panel_path} ({time.time() - self.t0:.0f} s). Next: any model notebook (its CELL 1 sets the design), or orchestrator.py --config config/analysis_config.yaml")
        return self

    def summary(self):
        """What every step left on this object: name, what it is, its type and size -- print any of them (B.<name>)."""
        import pandas as pd
        rows = []
        for k, what in self.results.items():
            v = getattr(self, k, None)
            size = (f"{len(v):,} rows x {v.shape[1]} cols" if isinstance(v, pd.DataFrame) else f"{len(v):,} items" if isinstance(v, (list, tuple, set, dict)) and not isinstance(v, str)
                    else f"{len(v.uids):,} pixels" if hasattr(v, "uids") else "")
            rows.append({"attribute": f"B.{k}", "what": what, "type": type(v).__name__, "size": size})
        tab = pd.DataFrame(rows)
        print(f"steps done: {', '.join(self.done) or 'none'} | seconds per step: {self.timings}")
        with pd.option_context("display.max_colwidth", 120, "display.width", 220): print(tab.to_string(index=False))
        return tab


def main(argv=None):
    ap = argparse.ArgumentParser(description="REWARD DiD -- build the DID-ready panel from a folder of exports")
    ap.add_argument("--input", required=True, help="the folder holding the export CSVs (any depth)")
    ap.add_argument("--output", default=None, help="where the panel and its reports go (default: <input>/output)")
    ap.add_argument("--workers", type=int, default=None, help="PASS A worker processes (default: every core the platform allows)")
    ap.add_argument("--force", action="store_true", help="rebuild even when a valid panel is already there")
    ap.add_argument("--fund", default=None, help="the fund-release workbook (default: _paths.py / P00_Settings)")
    ap.add_argument("--crosswalk", default=None, help="the sub-watershed crosswalk workbook (default: _paths.py)")
    ap.add_argument("--no-ground", action="store_true", help="(kept for compatibility: the ground-site linkage runs in P00 only)")
    ap.add_argument("--no-readiness", action="store_true", help="skip the estimator files, baseline means, screen and readiness table (P09 / P10)")
    ap.add_argument("--outcomes", default=None, help="comma-separated outcomes for the estimator files / screen (default: every outcome the panel has)")
    a = ap.parse_args(argv)
    PanelBuild(a.input, output_dir=a.output, workers=a.workers, force=a.force, fund=a.fund, crosswalk=a.crosswalk, readiness=not a.no_readiness, outcomes=a.outcomes).run_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
