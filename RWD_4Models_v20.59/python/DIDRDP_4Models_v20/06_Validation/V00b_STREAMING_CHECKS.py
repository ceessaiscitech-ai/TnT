"""Exercise the v15 streaming paths -- v20.49: with the REAL pyarrow when it is installed (real multi-row-group parquet
files), else with the pyarrow shim below (the sandbox that wrote v15 had no pyarrow).
The shim implements exactly the API surface the code uses: ParquetFile(.num_row_groups,
.metadata.num_rows, .schema_arrow.names, .read_row_group), Table(.num_rows, .filter, .to_pandas,
__getitem__), pc.not_equal/is_in/and_, pa.array."""
import sys, types, numpy as np, pandas as pd, os, json
# ---------------- pyarrow shim backed by a list of DataFrames (row-groups) ----------------
class _Col:
    def __init__(s,v): s.v=np.asarray(v)
class _Table:
    def __init__(s,df): s.df=df.reset_index(drop=True); s.num_rows=len(df)
    def __getitem__(s,c): return _Col(s.df[c].values)
    def filter(s,mask): return _Table(s.df[np.asarray(mask.v,bool)])
    def to_pandas(s): return s.df.copy()
class _PF:
    def __init__(s,path):
        s.groups=_STORE[path]; s.num_row_groups=len(s.groups)
        s.metadata=types.SimpleNamespace(num_rows=sum(len(g) for g in s.groups))
        s.schema_arrow=types.SimpleNamespace(names=list(s.groups[0].columns))
    def read_row_group(s,i,columns=None):
        g=s.groups[i]; return _Table(g[columns] if columns else g)
_STORE={}
pq=types.ModuleType("pyarrow.parquet"); pq.ParquetFile=_PF
pa=types.ModuleType("pyarrow"); pa.array=lambda x: np.asarray(list(x)); pa.parquet=pq
pc=types.ModuleType("pyarrow.compute")
pc.not_equal=lambda col,v: _Col(col.v!=v); pc.is_in=lambda col,value_set=None: _Col(np.isin(col.v,value_set))
pc.and_=lambda a,b: _Col(a.v & b.v)
ENGINE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import pyarrow as _rpa, pyarrow.parquet as _rpq; REAL=True
except Exception:
    REAL=False
if not REAL:
    sys.modules["pyarrow"]=pa; sys.modules["pyarrow.parquet"]=pq; sys.modules["pyarrow.compute"]=pc
sys.path.insert(0,ENGINE_DIR); import _common as C, _prep_common as P
print(f"pyarrow: {'REAL ' + _rpa.__version__ if REAL else 'shim (not installed)'}")
if not REAL: os.path.exists=(lambda _o: (lambda p: p in _STORE or _o(p)))(os.path.exists)
def _store(path, frames):
    """Register a multi-row-group panel: a REAL parquet file (one row group per frame) or the shim's store."""
    if REAL:
        w=None
        for g in frames:
            t=_rpa.Table.from_pandas(g, preserve_index=False)
            if w is None: w=_rpq.ParquetWriter(path, t.schema)
            w.write_table(t.cast(w.schema), row_group_size=len(g))
        w.close()
    else:
        _STORE[path]=frames

# ---------------- build a "1B-row-shaped" panel as 6 row-groups ----------------
rng=np.random.default_rng(7); groups=[]
for gi in range(6):
    rows=[]
    for u in range(gi*300,(gi+1)*300):
        b=0 if u%4==0 else int(rng.choice([1,2,3,4,5])); sw=f"SW{u%5}"
        for yr in range(2019,2026):
            for sc in [0,1,2,3]:
                rows.append({"pixel_id":f"PX{u:06d}","subwshed_id":sw,"Year":yr,"Season":sc,"buff_km":float(b),
                             "season_sort_rank":{0:3,1:0,2:1,3:2}[sc],"time_fe_yearseason":f"{yr}_{sc}",
                             "NDVI":rng.uniform(0,.8),"SAVI":rng.uniform(),"AGB":rng.uniform(10,40),
                             "Rain":rng.uniform(0,300),"Tmean":rng.uniform(20,32),"Tmax":rng.uniform(30,38),"Tmin":rng.uniform(14,22),   # v20.49: the four weather covariates
                             "site_id":1+u%5,"LandUse":int(rng.choice([1,2,3])),
                             "first_treat_agri_year":2022.0,"dose_per_subwshed":rng.uniform(0,90)})
    g=pd.DataFrame(rows); g=P.build_treatment_columns(g); groups.append(g)
import tempfile; _TD=tempfile.mkdtemp(); FAKE=os.path.join(_TD,"did_panel_full.parquet"); _store(FAKE, groups)
total=sum(len(g) for g in groups); print(f"fake panel: {total:,} rows in {len(groups)} row-groups, {groups[0].shape[1]} cols")

R={}
def chk(n,f):
    try: f(); R[n]="PASS"
    except Exception as e: R[n]=f"FAIL {type(e).__name__}: {str(e)[:110]}"

# 1. column projection + Season!=0 filter, streamed
def t1():
    d=C.load_panel(columns=C.columns_for("NDVI"),path=FAKE)
    assert "SAVI" not in d.columns and "AGB" not in d.columns, "must NOT load other outcomes"
    assert (d.Season==0).any(), "v20.24/v20.29: the ANNUAL composite (Season 0) is used with the seasons -- it must be kept"
    assert len(d)==total
chk("S1 streaming load: column projection per row-group; annual + seasonal rows kept (your rule since v20.29)",t1)
# 2. subwshed filter (predicate pushdown per row-group)
def t2():
    d=C.load_panel(columns=C.columns_for("NDVI"),path=FAKE,subwshed_filter=["SW0","SW1"])
    assert set(d.subwshed_id)=={"SW0","SW1"}
chk("S2 streaming load: subwshed_filter",t2)
# 3. sample_fraction + max_rows (early stop)
def t3():
    d=C.load_panel(columns=C.columns_for("NDVI"),path=FAKE,sample_fraction=0.1)
    assert abs(len(d)/total-0.1)<0.02
    d2=C.load_panel(columns=C.columns_for("NDVI"),path=FAKE,max_rows=5000)
    assert len(d2)==5000
chk("S3 streaming load: sample_fraction + max_rows early-stop",t3)
# 4. streaming stats == exact stats on the concatenated panel
def t4():
    full=pd.concat(groups,ignore_index=True)
    st=P.streaming_panel_stats(FAKE,
        key_cols=["buff_km","Season","treatment","control","pre","post","did_term","Year"],
        outcome_cols=["NDVI","AGB"],pixel_sample_mod=1)   # mod=1 -> ALL pixels, so numbers must be exact
    assert st["n_rows"]==len(full)
    assert st["unique_key_values"]["buff_km"]==full.buff_km.value_counts().to_dict()
    assert st["cells_treat_x_post"]["treat=1,post=1"]==int(((full.treatment==1)&(full.post==1)).sum())
    assert abs(st["outcome_ranges"]["NDVI"]["mean"]-full.NDVI.mean())<1e-9
    assert st["duplicates_total"]==0
    assert st["pct_pixels_multi_year"]==100.0 and st["n_treated_pixels_est"]==full.loc[full.treatment==1,"pixel_id"].nunique()
    v=P.panel_validity_from_stats(st,n_clusters=5,n_pre_years=4)
    assert v["VERDICT"].startswith("VALID"), v
chk("S4 streaming stats EXACTLY match the full-panel computation; verdict VALID",t4)
# 5. streaming stats DETECT duplicates injected into one partition
def t5():
    bad=[g.copy() for g in groups]; bad[2]=pd.concat([bad[2],bad[2].head(50)],ignore_index=True)
    _store(os.path.join(_TD,"bad.parquet"), bad)
    st=P.streaming_panel_stats(os.path.join(_TD,"bad.parquet"),key_cols=["buff_km"],outcome_cols=["NDVI"],pixel_sample_mod=1)
    assert st["duplicates_total"]==50, st["duplicates_total"]
    assert P.panel_validity_from_stats(st)["VERDICT"].startswith("NOT VALID")
chk("S5 streaming duplicate check catches 50 injected duplicates -> NOT VALID",t5)
# 6. PASS B per-shard: materialized DiD columns + dose merge + hard uniqueness (using resolve+build directly)
def t6():
    shard=pd.concat([groups[0].head(400),groups[0].head(400).assign(file_mtime=2000.0, NDVI=lambda d: d.NDVI+0.1)],ignore_index=True)
    shard["src_file"]="a.csv"; shard.loc[400:,"src_file"]="b_newer.csv"; shard["file_mtime"]=shard["file_mtime"].fillna(1000.0)
    shard["schema_vintage"]="x"
    out,log=P.resolve_duplicates(shard,group_keys=("pixel_id","Year","Season"),conflict_log=[])
    assert out.duplicated(subset=["pixel_id","Year","Season"]).sum()==0 and set(out.src_file)=={"b_newer.csv"}
    out=P.build_treatment_columns(out)
    for c in ["treatment","control","pre","post","did_term"]: assert c in out.columns and out[c].dtype==np.int8
    import inspect; src=inspect.getsource(P.run_pass_b)+inspect.getsource(P.prepare_pass_b_block)   # v20.6: the block work moved
    assert "raise RuntimeError" in src and "build_treatment_columns(" in src and "dose_table" in src
chk("S6 PASS B: newer file wins, DiD cols materialized as int8, hard uniqueness guard, per-shard dose merge wired",t6)
# 7. same pixel same id across every year/season of the panel
def t7():
    full=pd.concat(groups,ignore_index=True)
    lat=16.7+(full.pixel_id.str[2:].astype(int)%200)*8.98e-5; lon=75.3+(full.pixel_id.str[2:].astype(int)//200)*9.35e-5
    ids=P.assign_pixel_ids(lat.values,lon.values)
    per=pd.Series(ids).groupby(full.pixel_id.values).nunique()
    assert (per==1).all(), "a pixel must map to exactly ONE id across all its years/seasons"
    assert pd.Series(ids).nunique()==full.pixel_id.nunique(), "distinct 10 m pixels -> distinct ids"
chk("S7 same pixel -> same id across all years/seasons; distinct pixels -> distinct ids",t7)

def t8():
    m=P.build_manifest(FAKE,pixel_sample_mod=1)
    full=pd.concat(groups,ignore_index=True)
    assert m["n_rows"]==len(full) and m["n_unique_pixels_est"]==full.pixel_id.nunique()
    assert m["pct_pixels_in_gt1_year"]==100.0 and m["n_subwatersheds"]==5 and m["years"]==list(range(2019,2026))
    import re,inspect
    src=open(os.path.join(ENGINE_DIR,"_prep_common.py"),encoding="utf-8").read()
    bad=[l for l in src.split("\n") if re.search(r'read_table\(final_path\)|read_parquet\(final_path\)',l) and not l.strip().startswith("#") and '"""' not in l]
    assert not bad, f"prep engine still loads the whole panel: {bad}"
chk("S8 build_manifest streams (exact vs full computation) and NOTHING in prep loads the full panel",t8)

for k,v in R.items(): print(f"  {'PASS' if v=='PASS' else 'FAIL'}  {k}"+("" if v=="PASS" else f"\n        {v}"))
n=sum(v=="PASS" for v in R.values()); print(f"{n}/{len(R)} streaming checks passed")
