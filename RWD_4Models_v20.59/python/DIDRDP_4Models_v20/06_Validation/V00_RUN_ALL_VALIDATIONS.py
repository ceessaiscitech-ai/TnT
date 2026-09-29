import os
"""COMPREHENSIVE VALIDATION HARNESS -- loops until every check passes."""
import sys, os, json, glob, numpy as np, pandas as pd, traceback, io, contextlib
D=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # v20.29: the engine folder, wherever the bundle lives
sys.path.insert(0,D)
import _prep_common as P, _common as C
RESULTS={}
class Skip(Exception):
    """raised by a test whose input exists only on another machine / in an earlier session"""
def check(name, fn):
    try:
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf): fn()
        RESULTS[name]="PASS"
    except Skip as e:
        RESULTS[name]=f"SKIP: {e}"
    except Exception as e:
        RESULTS[name]=f"FAIL: {type(e).__name__}: {str(e)[:120]}"

# ====================================================================
# A. DiD COLUMN CONSTRUCTION -- the explicit rules you specified
# ====================================================================
def test_did_columns():
    rng=np.random.default_rng(0); rows=[]
    for u in range(60):
        b=int(rng.choice([0,1,2,3,4,5]))
        for yr in range(2015,2027):
            for sc in [1,2,3]:
                rows.append({"pixel_id":f"P{u}","Year":yr,"Season":sc,"buff_km":float(b),
                             "season_sort_rank":{1:0,2:1,3:2}[sc],"NDVI":rng.uniform()})
    df=pd.DataFrame(rows)
    for builder,tag in [(C.build_treatment_columns,"model"),(P.build_treatment_columns,"prep")]:
        o=builder(df, control_zones=(1,2,3,4,5))
        # YOUR SPEC 1: treatment = 1 iff buff_km == 0
        assert (o.treatment==(o.buff_km==0).astype(int)).all(), f"[{tag}] treatment rule"
        # YOUR SPEC 2: control = 1 iff buff_km in {1..5}
        assert (o.control==o.buff_km.isin([1,2,3,4,5]).astype(int)).all(), f"[{tag}] control rule"
        assert ((o.treatment+o.control)<=1).all(), f"[{tag}] a row is both treatment and control"
        # YOUR SPEC 3 (v20.27): post = 1 iff Year >= 2022 ; pre = 1 iff Year < 2022 ; complementary
        assert (o.post==(o.Year>=2022).astype(int)).all(), f"[{tag}] post rule"
        assert (o.pre==(o.Year<2022).astype(int)).all(),  f"[{tag}] pre rule"
        assert ((o.pre+o.post)==1).all(), f"[{tag}] pre/post must be complementary"
        assert (o[o.Year==2022].post==1).all(), f"[{tag}] 2022 must be POST per your spec (treatment start year)"
        # YOUR SPEC 4: DiD interaction
        assert (o.did_term==o.treatment*o.post).all(), f"[{tag}] did_term != treatment*post"
        assert (o[o.did_term==1].treatment==1).all() and (o[o.did_term==1].post==1).all()
        # aliases used by the 45 models must be identical
        for a,b_ in [("treat_core","treatment"),("control_zone_selected","control"),("pre_period","pre"),("post_period","post")]:
            assert (o[a]==o[b_]).all(), f"[{tag}] alias {a}!={b_}"
        assert (o.in_analysis_sample==((o.treatment==1)|(o.control==1)).astype(int)).all()
        assert (o.event_time==o.Year-2022).all()
        pi=o[["Year","season_sort_rank","period_index"]].drop_duplicates().sort_values(["Year","season_sort_rank"])
        assert pi.period_index.is_monotonic_increasing
    # control subset
    o2=C.build_treatment_columns(df, control_zones=(5,))
    assert (o2.control==(o2.buff_km==5).astype(int)).all()
    # optional old design still available
    o3=C.build_treatment_columns(df, exclude_transition_year=True)
    assert (o3[o3.Year==2022].pre==0).all() and (o3[o3.Year==2022].post==0).all()
    # prep and model builders agree column-for-column
    a=C.build_treatment_columns(df); b=P.build_treatment_columns(df)
    for c in ["treatment","control","pre","post","did_term","in_analysis_sample","event_time","period_index"]:
        assert (a[c].values==b[c].values).all(), f"prep vs model disagree on {c}"
check("A1 DiD columns: YOUR spec (treatment/control/pre<2022/post>=2022/did_term)", test_did_columns)

def test_2x2_identity_on_built_columns():
    """The did_term built by build_treatment_columns must reproduce the textbook 2x2."""
    rng=np.random.default_rng(1); rows=[]
    for u in range(200):
        b=0 if u<100 else 5; fe=rng.normal(0,1)
        for yr in [2020,2021,2023,2024]:
            for sc in [1,2,3]:
                eff=0.5 if (b==0 and yr>=2023) else 0.0
                rows.append({"pixel_id":f"P{u}","Year":yr,"Season":sc,"buff_km":float(b),
                             "season_sort_rank":{1:0,2:1,3:2}[sc],"time_fe_yearseason":f"{yr}_{sc}",
                             "subwshed_id":f"S{u%5}","y":fe+0.1*(yr-2020)+eff+rng.normal(0,.05)})
    d=C.build_treatment_columns(pd.DataFrame(rows))
    d=d[d.in_analysis_sample==1]
    m=d.groupby(["treat_core","post"]).y.mean()
    closed=(m[(1,1)]-m[(1,0)])-(m[(0,1)]-m[(0,0)])
    b,_=C.estimate_twfe_did(d,"y","did_term","pixel_id","time_fe_yearseason","subwshed_id")
    assert abs(b-0.5)<0.03, f"TWFE on built columns={b}, true 0.5"
    assert abs(closed-0.5)<0.03
check("A2 built did_term recovers a known 0.5 effect", test_2x2_identity_on_built_columns)


def test_case_insensitive_harmonizer():
    variants=["Season","SEASON","season","Seasons","SEASONS","buff_km","Buff_km","BUFF_KM","Buff_Km",
              "LATITUDE","Latitude","YEAR","ndvi","Ndvi","TREAT","SUBWSHEDID","LANDUSE","land_use","TMEAN","GAPFILLED"]
    exp=["Season"]*5+["buff_km"]*4+["latitude","latitude","Year","NDVI","NDVI","Treat","SubwshedID","LandUse","LandUse","Tmean","GapFilled"]
    log=[]; mp=P.harmonize_columns(variants,unresolved_log=log)
    for v,e in zip(variants,exp): assert mp[v]==e, f"{v}->{mp[v]} expected {e}"
    assert not log
    # values: 0/1/2/3 season codes survive untouched
    d=pd.DataFrame({"SEASON":[0,1,2,3]}); d=d.rename(columns=P.harmonize_columns(list(d.columns)))
    assert list(d.Season)==[0,1,2,3] and d.Season.map(P.SEASON_LABEL).tolist()==["Yearly","Kharif","Rabi","Zaid"]
check("A3 case-insensitive column matching (Season/SEASON/Seasons, buff_km/Buff_km/BUFF_KM ...)", test_case_insensitive_harmonizer)

def test_deterministic_uid():
    rng=np.random.default_rng(5); lat=rng.uniform(16,17,5000); lon=rng.uniform(75,76,5000)
    a=P.assign_pixel_ids(lat,lon); b=P.assign_pixel_ids(lat,lon)
    assert (a==b).all(), "same coords must give same id"
    perm=rng.permutation(5000); c=P.assign_pixel_ids(lat[perm],lon[perm])
    assert set(a)==set(c), "order-independent"
    # Rounding has boundaries: a point sitting within 1e-7 of a 1e-5 boundary WILL flip. That is
    # inherent to any grid snap (only NN matching avoids it, which you asked me to drop). The
    # affected share must be tiny: expected ~ noise/cell = 1e-7/1e-5 = 1%.
    flipped=float((P.assign_pixel_ids(lat+1e-7,lon+1e-7)!=a).mean())
    assert flipped<0.03, f"{flipped:.1%} of ids changed under 1e-7 noise -- expected ~1%"
    assert len(set(a))==5000, "distinct real pixels must get distinct ids"
    assert np.asarray(a).dtype==np.int64 and all(15 <= len(str(int(x))) <= 18 for x in a[:50]), "int64 numeric id (v20)"
    assert int(max(a)) < 2**63, "18-digit id must fit int64 (compact_dtypes stores it as int64)"
    # cross-'file' stability: the SAME location in two files -> one pixel_id -> dedup can see it
    # exact same exported coordinates in two files -> identical id (the case dedup relies on)
    f1=pd.DataFrame({"latitude":lat[:100],"longitude":lon[:100]}); f2=f1.copy()
    assert (P.assign_pixel_ids(f1.latitude,f1.longitude)==P.assign_pixel_ids(f2.latitude,f2.longitude)).all()
check("A4 deterministic pixel UID from lat/lon (same location -> same id, every file, every year)", test_deterministic_uid)

def test_column_retention():
    import tempfile, os as _o
    d=pd.DataFrame({"latitude":[16.7]*3,"longitude":[75.3]*3,"Year":[2025]*3,"Season":[2]*3,"buff_km":[0,1,5],
                    "NDVI":[.4,.5,.6],"SubwshedID":[1,1,1],"Treat":[1,0,0],"GapFilled":[0,0,0],
                    "SomeBrandNewColumn":[9,9,9],"AnotherUnknown":["a","b","c"]})
    with tempfile.TemporaryDirectory() as td:
        f=_o.path.join(td,"CSV_Artal_2025_Rabi_tile0_sub0.csv"); d.to_csv(f,index=False)
        log=[]; out=P.load_and_harmonize(f,unresolved_log=log,parse_errors_log=[])
    assert "SomeBrandNewColumn" not in out.columns and "AnotherUnknown" not in out.columns, "extras must be DROPPED"
    assert "GapFilled" in out.columns and "NDVI" in out.columns and "buff_km" in out.columns, "canonical must be KEPT"
    assert any("DROPPED:SomeBrandNewColumn" in x[1] for x in log), "drop must be LOGGED"
check("A5 retain all canonical variables + DiD keys; DROP unmatched extras (logged)", test_column_retention)

def test_panel_validity_verdict():
    rng=np.random.default_rng(9); rows=[]
    for u in range(80):
        b=0 if u<30 else int(rng.choice([1,2,3,4,5])); la=16.7+u*1e-4
        for yr in range(2018,2026):
            for sc in [1,2,3]:
                rows.append({"pixel_id":f"P{u}","subwshed_id":f"S{u%7}","Year":yr,"Season":sc,"buff_km":float(b),
                             "latitude":la,"longitude":75.3,"season_sort_rank":sc-1})
    good=P.build_treatment_columns(pd.DataFrame(rows)); V=P.panel_validity_check(good)
    assert V["VERDICT"].startswith("VALID"), V
    assert V["cells_treat_x_post"]["treat=1,post=1"]>0
    # a panel with NO post period must be NOT VALID
    bad=P.build_treatment_columns(pd.DataFrame(rows).query("Year<2022")); V2=P.panel_validity_check(bad)
    assert V2["VERDICT"].startswith("NOT VALID") and any("EMPTY 2x2" in f for f in V2["failures"])
    # a panel with no control must be NOT VALID
    bad2=P.build_treatment_columns(pd.DataFrame(rows).query("buff_km==0")); V3=P.panel_validity_check(bad2)
    assert V3["VERDICT"].startswith("NOT VALID")
check("A6 panel_validity_check: VALID on a good panel, NOT VALID when a 2x2 cell or control is missing", test_panel_validity_verdict)

def test_memory_column_projection():
    """load ONLY the columns a model needs; release() frees them."""
    cols=C.columns_for("NDVI")
    assert "NDVI" in cols and "SAVI" not in cols and "AGB" not in cols, "other outcomes must NOT be loaded"
    assert set(C.ID_FE_COLS)<=set(cols) and set(c for c in C.DEFAULT_COVARIATES if c!="NDVI")<=set(cols)
    assert len(cols)<=22, f"NDVI model loads {len(cols)} columns -- should be ~18 (ids+FE+site+covariates+outcome), not the ~57-column panel"
    # the firm design rule: weather is a COVARIATE only -- asking for it as an outcome is refused
    try:
        C.columns_for("Rain"); raise AssertionError("Rain was accepted as an OUTCOME -- weather must stay a covariate")
    except C.InsufficientDataError:
        pass
    import io,contextlib
    with contextlib.redirect_stdout(io.StringIO()): C.release(pd.DataFrame({"a":[1]}),pd.DataFrame({"b":[2]}))
check("A7 memory: each model loads ONLY its columns (NDVI model excludes SAVI/AGB/...); release() works", test_memory_column_projection)

def test_ndvi_range_sanity():
    """DiD on NDVI: the harmonized value column must be numeric and plausible."""
    d=pd.DataFrame({"NDVI":["0.4","0.5","abc",None],"Year":[2020]*4,"Season":[1]*4,"buff_km":[0,1,2,3],
                    "latitude":[16.7]*4,"longitude":[75.3]*4,"SubwshedID":[1]*4,"Treat":[1,0,0,0]})
    import tempfile,os as _o
    with tempfile.TemporaryDirectory() as td:
        f=_o.path.join(td,"CSV_2020_Kharif_tile0.csv"); d.to_csv(f,index=False)
        out=P.load_and_harmonize(f,unresolved_log=[],parse_errors_log=[])
    assert pd.api.types.is_numeric_dtype(out["NDVI"]), "outcome must be coerced to numeric"
    assert out["NDVI"].isna().sum()==2, "non-numeric -> NaN, not a crash"
check("A8 outcome columns coerced to numeric; junk -> NaN not crash", test_ndvi_range_sanity)

# ====================================================================
# B. ANALYTICAL IDENTITIES (V01) -- machine-precision, not simulation
# ====================================================================
def test_twfe_equals_closed_form():
    rng=np.random.default_rng(99); n=37; data=[]; means={}
    for tr in [0,1]:
        for po in [0,1]:
            v=rng.normal(10+2*tr+3*po+5*tr*po,2,n); means[(tr,po)]=v.mean()
            data+=[{"y":x,"treat":tr,"post":po} for x in v]
    d=pd.DataFrame(data); d["did_term"]=d.treat*d.post
    beta,_=C.estimate_twfe_did(d,"y","did_term","treat","post","treat")
    closed=(means[(1,1)]-means[(1,0)])-(means[(0,1)]-means[(0,0)])
    assert abs(beta-closed)<1e-9, f"diff={abs(beta-closed):.2e}"
check("B1 TWFE == closed-form 2x2 (<1e-9)", test_twfe_equals_closed_form)

def test_cluster_se_cr1():
    X=np.array([[1.],[2.],[3.],[1.5],[2.5],[3.5]]); r=np.array([.5,-.3,.2,-.1,.4,-.6])
    cl=np.array(["A","A","A","B","B","B"]); v=C.cluster_robust_se(X,r,cl)
    n,k,G=6,1,2; dfc=(G/(G-1))*((n-1)/(n-k)); XtXi=np.linalg.inv(X.T@X); meat=np.zeros((1,1))
    for c in ["A","B"]:
        s=X[cl==c].T@r[cl==c]; meat+=np.outer(s,s)
    assert np.allclose(v,dfc*XtXi@meat@XtXi), "CR1 mismatch (Cameron-Gelbach-Miller 2011)"
check("B2 cluster SE == CGM2011 CR1", test_cluster_se_cr1)

def test_cs_collapses_to_2x2():
    rng=np.random.default_rng(7); n=50; rows=[]; mm={}
    for tr in [0,1]:
        for t in [2021,2022]:
            v=rng.normal(5+2*tr+(t==2022)+3*tr*(t==2022),1.5,n); mm[(tr,t)]=v.mean()
            rows+=[{"unit":f"{tr}_{i}","time":t,"y":x,"first_treat":2022 if tr else np.inf} for i,x in enumerate(v)]
    tbl,_=C.callaway_santanna_att(pd.DataFrame(rows),"y","unit","time","first_treat")
    cf=(mm[(1,2022)]-mm[(1,2021)])-(mm[(0,2022)]-mm[(0,2021)])
    assert abs(tbl["ATT_gt"].iloc[0]-cf)<1e-9
check("B3 Callaway-Sant'Anna collapses EXACTLY to 2x2", test_cs_collapses_to_2x2)

def test_season_fe():
    rng=np.random.default_rng(4242); SE={"K":.55,"R":.35,"Z":.12}; TRUE=.06; rows=[]
    for u in range(300):
        tr=1 if u<150 else 0; fe=rng.normal(0,.05)
        for yr in range(2018,2026):
            for s in SE:
                if rng.uniform()>(0.65 if (tr and s=="Z") else 0.95): continue
                po=1 if yr>=2022 else 0
                rows.append({"pixel_id":u,"Year":yr,"tfe":f"{yr}_{s}","did_term":tr*po,
                             "y":fe+SE[s]+.004*(yr-2018)+TRUE*tr*po+rng.normal(0,.02)})
    d=pd.DataFrame(rows)
    b1,_=C.estimate_twfe_did(d,"y","did_term","pixel_id","Year","pixel_id")
    b2,_=C.estimate_twfe_did(d,"y","did_term","pixel_id","tfe","pixel_id")
    assert abs(b2-TRUE)<abs(b1-TRUE), "year x season FE must beat year-only"
check("B4 season FE absorption (guards the 3.4x bias bug)", test_season_fe)

def test_counterfactual():
    rng=np.random.default_rng(201); TRUE=2.5; rows=[]; y0={}
    for u in range(60):
        tr=1 if u<30 else 0; ufe=rng.normal(0,1.5)
        for t in range(2018,2026):
            base=ufe+rng.normal(0,.8)+rng.normal(0,.3); d=1 if (tr and t>=2022) else 0
            y0[(u,t)]=base; rows.append({"unit":u,"time":t,"treat_core":tr,"post":int(t>=2022),"y":base+TRUE*d})
    d=pd.DataFrame(rows); d["did_term"]=d.treat_core*d.post
    beta,_=C.estimate_twfe_did(d,"y","did_term","unit","time","unit")
    d["effect_applied"]=d.did_term*beta; cf=C.construct_counterfactual(d,"y","effect_applied")
    cf["t"]=cf.apply(lambda r:y0[(r.unit,r.time)],axis=1)
    tp=cf[(cf.treat_core==1)&(cf.post==1)]; err=(tp.Y_counterfactual-tp.t).abs()
    assert np.allclose(err.values,abs(beta-TRUE),atol=1e-9)
check("B5 counterfactual adds zero distortion", test_counterfactual)

# ====================================================================
# C. ALL ESTIMATORS vs KNOWN TRUTH (validate_all + validate_ml)
# ====================================================================
def test_validate_all():
    r=C.validate_all(verbose=False); bad={k:v for k,v in r.items() if v!="PASS"}
    assert not bad, f"{bad}"
check("C1 9 classical estimators (validate_all)", test_validate_all)
def test_validate_ml():
    r=C.validate_ml(verbose=False); bad={k:v for k,v in r.items() if v!="PASS"}
    assert not bad, f"{bad}"
check("C2 8 ML/AI causal methods (validate_ml)", test_validate_ml)

def test_bjs_beats_twfe():
    rng=np.random.default_rng(801); rows=[]; taus=[]
    coh={i:(2021 if i<30 else 2024 if i<60 else np.inf) for i in range(90)}
    ufe={i:rng.normal(0,2) for i in coh}; tfe={t:rng.normal(0,1) for t in range(2018,2027)}
    for i,g in coh.items():
        for t in range(2018,2027):
            tr=1 if (g!=np.inf and t>=g) else 0
            e=(0.5*(t-g+1) if g==2021 else 2.0) if tr else 0.0
            if tr: taus.append(e)
            rows.append({"pixel":i,"time":t,"y":ufe[i]+tfe[t]+e+rng.normal(0,.3),"treated":tr,"event_time":(t-g) if g!=np.inf else np.nan})
    df=pd.DataFrame(rows); true=np.mean(taus)
    n,_=C.estimate_twfe_did(df,"y","treated","pixel","time","pixel")
    b=C.bjs_imputation_did(df,"y","pixel","time","treated","event_time")["overall_ATT"]
    assert abs(b-true)<abs(n-true) and abs(b-true)<0.25
check("C3 BJS imputation beats naive TWFE under heterogeneity", test_bjs_beats_twfe)

def test_wild_bootstrap_calibration():
    rej_c=rej_w=0; N=25
    for sim in range(N):
        rng=np.random.default_rng(sim); rows=[]
        for c in range(6):
            sh=rng.normal(0,1.5); tr=1 if c<3 else 0
            for i in range(30):
                for t in [0,1]:
                    rows.append({"unit":f"{c}_{i}","time":t,"cluster":c,"d":tr*t,"y":sh+rng.normal(0,.5)})
        df=pd.DataFrame(rows)
        b,se=C.estimate_twfe_did(df,"y","d","unit","time","cluster")
        if se>0 and abs(b/se)>1.96: rej_c+=1
        r=C.wild_cluster_bootstrap_pvalue(df,"y","d","unit","time","cluster",n_boot=99,seed=sim)
        if r["p_value_wild_bootstrap"]<0.05: rej_w+=1
    assert rej_w<=rej_c+1, f"wild {rej_w}/{N} vs CRVE {rej_c}/{N}"
check("C4 wild bootstrap not worse than CRVE with 6 clusters", test_wild_bootstrap_calibration)

# ====================================================================
# D. DATA PIPELINE vs YOUR REAL FILES
# ====================================================================
def test_filename_parser():
    for f,exp in [("CSV_Artal_2025_Rabi_tile11_sub1.csv",(2025,2,"11","1","Artal")),
                  ("CSV_2015_Kharif_tile12.csv",(2015,1,"12",None,None)),
                  ("CSV_2015_yearly_tile15_sub0.csv",(2015,0,"15","0",None))]:
        m=P.parse_filename(f); assert m, f
        assert (m["Year"],m["Season"],m["tile_raw"],m["sub_raw"],m["site_from_name"])==exp, (f,m)
    for junk in ["FileList.csv","file_inventory.csv","notes.txt","CSV_summary.csv"]:
        assert P.parse_filename(junk) is None, junk
check("D1 filename parser (both vintages + rejects junk)", test_filename_parser)

def test_real_crosswalk():
    if not os.path.exists("/mnt/user-data/uploads/RWD_Sub_watershed_final_list.xlsx"): raise Skip("crosswalk workbook from an earlier session not present here")
    xw=P.load_subwshed_crosswalk("/mnt/user-data/uploads/RWD_Sub_watershed_final_list.xlsx")
    assert len(xw)==20 and "Artal" in xw["Sub Watershed Name"].values
    assert xw[xw["Sub Watershed Name"]=="Artal"].District.iloc[0]=="Belagavi"
check("D2 real crosswalk: 20 pairs, Artal->Belagavi", test_real_crosswalk)

def test_real_fund_file():
    if not glob.glob('/mnt/user-data/uploads/Districtwise_Month_wise_Progress*'): raise Skip('fund-release workbook from an earlier session not present here')
    f=P.load_fund_progress("/mnt/user-data/uploads/Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS__1_.xlsx")
    assert len(f)==440 and f.District.nunique()==20 and f.Date.nunique()==22
    chk=f.dropna(subset=["Dose/Intensity","Progress","Target"])
    assert (chk["Dose/Intensity"]-chk["Progress"]/chk["Target"]*100).abs().max()<1e-8
    assert f.area_hectare.notna().all()
    xw=P.load_subwshed_crosswalk("/mnt/user-data/uploads/RWD_Sub_watershed_final_list.xlsx")
    m=f[["District","SWS"]].drop_duplicates().merge(xw,on="District",how="outer",indicator=True)
    assert ((m._merge=="both")&(m.SWS==m["Sub Watershed Name"])).all(), "embedded vs standalone crosswalk mismatch"
    dose=P.build_district_season_dose(f)
    assert dose.is_complete_origin_season.dtype==bool
    fd=P.apply_subwshed_division(dose,xw,threshold_pct=50.0)
    assert "dose_per_subwshed" in fd.columns and fd.dose_per_subwshed.notna().any()
check("D3 real fund file: 440 rows, dose==Progress/Target*100, area, crosswalk match", test_real_fund_file)

def test_next_season_rule():
    for date,exp in [("2024-06-15",(2024,2)),("2024-10-31",(2025,3)),("2024-11-01",(2025,3)),
                     ("2025-03-31",(2025,1)),("2025-04-01",(2025,1)),("2025-05-31",(2025,1)),("2025-01-15",(2025,3))]:   # v20.29: export calendar
        got=P.next_season_after(pd.Timestamp(date)); assert got==exp,(date,got,exp)
check("D4 next-nearest-season rule: 7 boundary cases", test_next_season_rule)

def test_cross_file_dedup():
    rows=[]
    for src,mt,v in [("CSV_2025_Rabi_tile0.csv",1000.,0.40),("CSV_Artal_2025_Rabi_tile0_sub0.csv",2000.,0.55)]:
        for px in range(200):
            rows.append({"pixel_id":f"PX{px}","Year":2025,"Season":2,"NDVI":v,"SAVI":v,"EVI":v,"LAI":1.,
                         "LSWI":.1,"NDWI":.2,"NDMI":.1,"NDRE":.2,"AGB":25.,"RUSLE":1.,
                         "src_file":src,"file_mtime":mt,"schema_vintage":"x"})
    s=pd.DataFrame(rows); assert s.duplicated(subset=["pixel_id","Year","Season"]).sum()==200
    out,log=P.resolve_duplicates(s,group_keys=("pixel_id","Year","Season"),conflict_log=[])
    assert out.duplicated(subset=["pixel_id","Year","Season"]).sum()==0
    assert set(out.src_file)=={"CSV_Artal_2025_Rabi_tile0_sub0.csv"} and len([x for x in log if not (isinstance(x, dict) and x.get("summary"))])==200
    import inspect   # PASS B de-duplicates inside prepare_pass_b_block (the function every PASS B worker runs)
    assert "resolve_duplicates" in inspect.getsource(P.prepare_pass_b_block) and "prepare_pass_b_block" in inspect.getsource(P._pb_worker), "cross-file dedup must be wired into PASS B"
check("D5 cross-file dedup (your 61,330-row bug) + wired into PASS B", test_cross_file_dedup)

def test_extract_site():
    known=["Artal","Chittharagi"]
    assert P.extract_site_name(r"D:\LKT\TST_Artal\CSV_Artal_2025_Rabi_tile1_sub0.csv",known)==("Artal","site_embedded_in_filename")
    assert P.extract_site_name(r"D:\LKT\REWARD_Artal_Exports_final\CSV_2015_Kharif_tile0.csv",known)==("Artal","reward_exports_final_pattern")
    assert P.extract_site_name(r"D:\x\CSV_2019_Zaid_tile2.csv",known)==(None,None)
check("D6 extract_site_name: filename-first, never guesses", test_extract_site)

def test_paths():
    # v20.54: the data root is THIS project's folder in _paths.py (D:\LKT\RWD_Artal\data since v20.50) -- or the old folder
    # until MIGRATE_DATA.bat has moved the data. v20.50-v20.53 still expected ...\TST_Artal\output here, so on Windows D7
    # failed on every run (it was skipped everywhere else). It now runs on every system.
    import _paths as _PP
    d=_PP.derive(); nc=lambda x: os.path.normcase(os.path.abspath(x))
    assert nc(P.INPUT_DIR)==nc(d["INPUT_DIR"]) and nc(P.OUTPUT_DIR)==nc(d["OUTPUT_DIR"]), "the preparation engine does not follow _paths.py"
    assert nc(C.PREPARED_PANEL)==nc(d["FINAL_PANEL"]) and nc(C.RESULTS_ROOT)==nc(d["RESULTS_ROOT"]), "the model engine does not follow _paths.py"
    if not os.environ.get("REWARD_INPUT_DIR"):
        allowed={nc(_PP._portable(x)) for x in (_PP.INPUT_DIR, getattr(_PP, "LEGACY_INPUT_DIR", None)) if x}
        assert nc(P.INPUT_DIR) in allowed, f"data root {P.INPUT_DIR} is neither INPUT_DIR nor the old folder in _paths.py"
    if not _PP.OUTPUT_DIR: assert nc(P.OUTPUT_DIR)==nc(os.path.join(P.INPUT_DIR, getattr(_PP, "OUTPUT_SUBDIR", "output"))), "output is not inside the data folder"
    import re as _re                                       # the DEFAULT written in _paths.py (REWARD_INPUT_DIR, a test hook, may override it)
    _lit = _re.search(r'^INPUT_DIR = .*?r"([^"]+)"', open(_PP.__file__, encoding="utf-8").read(), _re.M).group(1)
    assert _lit.upper().startswith("D:\\LKT\\") and str(_PP.SUBWSHED_CROSSWALK_PATH).startswith("D:\\LKT") and str(_PP.FUND_RELEASE_PATH).startswith("D:\\LKT"), "your D:\\LKT paths changed"
    if os.name == "nt": assert P.SUBWSHED_CROSSWALK_PATH.startswith(r"D:\LKT") and P.FUND_RELEASE_PATH.startswith(r"D:\LKT")
    assert os.path.basename(C.PREPARED_PANEL)=="did_panel_full.parquet"
    assert "assign_pixel_ids" in open(f"{D}/_prep_common.py").read() and "PixelRegistry(tol_m" not in open(f"{D}/_prep_common.py").read().split("def run_pass_a")[1].split("def ")[0]
    assert "GapFilled" in P.CANONICAL
check("D7 paths: the data root from _paths.py (your D:\\LKT folder, or the old one until migrated), output inside it; GapFilled canonical", test_paths)

# ====================================================================
# E. NO UNDEFINED NAMES in either engine (the _re bug class)
# ====================================================================
def test_no_undefined_names():
    import ast, builtins
    for path in [f"{D}/_prep_common.py"]:
        tree=ast.parse(open(path).read()); top=set(dir(builtins))|{'__file__','__name__','__doc__','__spec__'}
        for n in ast.walk(tree):
            if isinstance(n,(ast.FunctionDef,ast.ClassDef)): top.add(n.name)
            elif isinstance(n,ast.Assign):
                for t in n.targets:
                    for x in ast.walk(t):
                        if isinstance(x,ast.Name): top.add(x.id)
            elif isinstance(n,(ast.Import,ast.ImportFrom)):
                for a in n.names: top.add((a.asname or a.name).split(".")[0])
            elif isinstance(n,ast.For):
                for x in ast.walk(n.target):
                    if isinstance(x,ast.Name): top.add(x.id)
        parents={}
        for node in ast.walk(tree):
            for ch in ast.iter_child_nodes(node): parents[ch]=node
        def _enclosing_names(fn):
            names=set(); p=parents.get(fn)
            while p is not None:
                if isinstance(p,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    names|={a.arg for a in p.args.args+p.args.kwonlyargs}
                    if p.args.vararg: names.add(p.args.vararg.arg)
                    if p.args.kwarg: names.add(p.args.kwarg.arg)
                    for n in ast.walk(p):
                        if isinstance(n,ast.Assign):
                            for t in n.targets:
                                for x in ast.walk(t):
                                    if isinstance(x,ast.Name): names.add(x.id)
                        elif isinstance(n,(ast.For,ast.comprehension)):
                            for x in ast.walk(n.target):
                                if isinstance(x,ast.Name): names.add(x.id)
                p=parents.get(p)
            return names
        for fn in [x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef)]:
            loc=set(top)|{a.arg for a in fn.args.args+fn.args.kwonlyargs}|_enclosing_names(fn)
            if fn.args.vararg: loc.add(fn.args.vararg.arg)
            if fn.args.kwarg: loc.add(fn.args.kwarg.arg)
            for n in ast.walk(fn):
                if isinstance(n,ast.Assign):
                    for t in n.targets:
                        for x in ast.walk(t):
                            if isinstance(x,ast.Name): loc.add(x.id)
                elif isinstance(n,(ast.For,ast.comprehension)):
                    for x in ast.walk(n.target):
                        if isinstance(x,ast.Name): loc.add(x.id)
                elif isinstance(n,ast.withitem) and n.optional_vars is not None:
                    for x in ast.walk(n.optional_vars):
                        if isinstance(x,ast.Name): loc.add(x.id)
                elif isinstance(n,(ast.Import,ast.ImportFrom)):
                    for a in n.names: loc.add((a.asname or a.name).split(".")[0])
                elif isinstance(n,ast.ExceptHandler) and n.name: loc.add(n.name)
                elif isinstance(n,(ast.FunctionDef,ast.Lambda)):
                    if hasattr(n,"name"): loc.add(n.name)
                    for a in n.args.args: loc.add(a.arg)
            for n in ast.walk(fn):
                if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id not in loc:
                    raise AssertionError(f"{path}:{n.lineno} undefined '{n.id}' in {fn.name}")
check("E1 no undefined names in _prep_common.py", test_no_undefined_names)

def test_all_notebooks_compile():
    import glob
    for p in glob.glob(f"{D}/**/*.ipynb",recursive=True):
        nb=json.load(open(p))
        if nb["metadata"]["kernelspec"]["name"]=="ir": continue
        compile("\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"]=="code"),p,"exec")
check("E2 all Python notebooks compile", test_all_notebooks_compile)

# ====================================================================
# F. YOUR THREE FINAL CHECKS
# ====================================================================
def test_pre_rule_everywhere():
    """pre = Year < 2022 in BOTH Python engines AND the R engine -- one analysis sample (v20.27/29)."""
    d=pd.DataFrame({"buff_km":[0,1,0,3,0,5],"Year":[2019,2021,2022,2023,2024,2026],"season_sort_rank":0})
    for B,tag in [(C.build_treatment_columns,"model"),(P.build_treatment_columns,"prep")]:
        o=B(d); assert list(o.pre)==[1,1,0,0,0,0], f"[{tag}] pre must be Year<2022"; assert list(o.post)==[0,0,1,1,1,1]
        assert (o.pre+o.post==1).all()
    r=open(os.path.join(os.path.dirname(C.r_bridge_script()), "reward_design.R"), encoding="utf-8").read()   # v20.57: the R MODEL stage
    assert "post := as.integer(Year >= cohort_row)" in r, "R pipeline must use post = Year >= the row's implementation (cohort) year"
    assert "treat := as.integer(buff_km == 0L)" in r and "cohort_row" in r
    assert 'paste(pixel_id, Season, sep = "_")' in r, "R pipeline must build the same pixel x season unit as Python"
    assert C.POST_CUTOFF==2022 and P.POST_CUTOFF==2022
check("F1 pre period = Year < 2022 -- Python (both engines) AND R agree", test_pre_rule_everywhere)

def test_time_fe_modes():
    """Year x Season (interacted, default) AND additive Year + Season both recover a known effect;
    with YEAR-SPECIFIC seasonal shocks the interacted spec must be the less biased one."""
    rng=np.random.default_rng(77); TRUE=0.05; rows=[]
    yr_season_shock={(y,s):rng.normal(0,0.15) for y in range(2018,2026) for s in ("Kharif","Rabi","Zaid")}
    for u in range(400):
        tr=1 if u<200 else 0; fe=rng.normal(0,.05)
        for y in range(2018,2026):
            for s in ("Kharif","Rabi","Zaid"):
                if rng.uniform()>(0.7 if (tr and s=="Zaid") else 0.95): continue
                po=1 if y>=2023 else 0
                rows.append({"pixel_id":u,"time_fe_year":str(y),"time_fe_season":s,"time_fe_yearseason":f"{y}_{s}",
                             "cl":f"c{u%8}","did_term":tr*po,"y":fe+{"Kharif":.55,"Rabi":.35,"Zaid":.12}[s]
                             +yr_season_shock[(y,s)]+.01*(y-2018)+TRUE*tr*po+rng.normal(0,.02)})
    d=pd.DataFrame(rows)
    b_int,_=C.estimate_twfe_did_multi(d,"y","did_term","pixel_id",C.time_fe_columns("yearseason"),"cl")
    b_add,_=C.estimate_twfe_did_multi(d,"y","did_term","pixel_id",C.time_fe_columns("additive"),"cl")
    b_old,_=C.estimate_twfe_did(d,"y","did_term","pixel_id","time_fe_yearseason","cl")
    assert abs(b_int-b_old)<1e-9, "multi-way demeaner must reproduce the 2-way result exactly for the same FE"
    assert abs(b_int-TRUE)<0.01, f"interacted spec err {abs(b_int-TRUE):.4f}"
    assert abs(b_int-TRUE)<=abs(b_add-TRUE)+1e-6, "with year-specific seasonal shocks, Year x Season must not be worse than additive"
    # the multi-way demeaner equals dummy-variable OLS on a small case (exact identity)
    sm=d.sample(600,random_state=1)
    Xd=pd.get_dummies(sm[["pixel_id","time_fe_year","time_fe_season"]].astype(str),drop_first=True).astype(float)
    Xd["did"]=sm.did_term.values; Xd["c"]=1.0
    beta_ols=np.linalg.lstsq(Xd.values,sm.y.values,rcond=None)[0][list(Xd.columns).index("did")]
    b_chk,_=C.estimate_twfe_did_multi(sm,"y","did_term","pixel_id",["time_fe_year","time_fe_season"],"cl")
    assert abs(beta_ols-b_chk)<1e-6, f"additive demeaner {b_chk} != dummy OLS {beta_ols}"
check("F2 year & season FE: interacted (default) and additive both correct; multi-way == dummy-variable OLS", test_time_fe_modes)

def test_uid_uniqueness_and_persistence_end_to_end():
    """(a) a pixel id never repeats within one Year/Season after PASS-B dedup;
       (b) the SAME physical pixel keeps ONE id across ALL years and seasons, across files."""
    dlat,dlon=10/111320.0,10/(111320.0*np.cos(np.radians(16.7)))
    grid=[(16.7+i*dlat,75.3+j*dlon) for i in range(30) for j in range(30)]   # 900 real 10 m pixels
    rng=np.random.default_rng(3); final=[]
    for yr in range(2019,2026):
        for se in (1,2,3):
            files=[]
            for k,src in enumerate(["CSV_%d_%s_tile0.csv"%(yr,{1:"Kharif",2:"Rabi",3:"Zaid"}[se]),
                                    "CSV_Artal_%d_%s_tile0_sub0.csv"%(yr,{1:"Kharif",2:"Rabi",3:"Zaid"}[se])]):
                lat=np.array([g[0] for g in grid])+rng.normal(0,1e-9,900); lon=np.array([g[1] for g in grid])+rng.normal(0,1e-9,900)
                f=pd.DataFrame({"latitude":lat,"longitude":lon,"Year":yr,"Season":se,"NDVI":rng.uniform(0,.8,900)+0.1*k,
                                "SAVI":.1,"EVI":.1,"LAI":1.,"LSWI":.1,"NDWI":.1,"NDMI":.1,"NDRE":.1,"AGB":20.,"RUSLE":1.,
                                "src_file":src,"file_mtime":1000.+k*1000,"schema_vintage":"x"})
                f["pixel_id"]=P.assign_pixel_ids(f.latitude.values,f.longitude.values)   # what PASS A does
                files.append(f)
            shard=pd.concat(files,ignore_index=True)                                       # two files -> one shard
            assert shard.duplicated(subset=["pixel_id","Year","Season"]).sum()==900        # duplicates present BEFORE dedup
            out,_=P.resolve_duplicates(shard,group_keys=("pixel_id","Year","Season"),conflict_log=[])  # what PASS B does
            assert out.duplicated(subset=["pixel_id","Year","Season"]).sum()==0, "(a) id repeats within a Year/Season"
            assert len(out)==900 and set(out.src_file)=={files[1].src_file.iloc[0]}, "newer file must win"
            final.append(out)
    panel=pd.concat(final,ignore_index=True)
    assert panel.duplicated(subset=["pixel_id","Year","Season"]).sum()==0, "(a) global"
    assert panel.pixel_id.nunique()==900, f"(b) 900 physical pixels must map to exactly 900 ids, got {panel.pixel_id.nunique()}"
    per_pixel=panel.groupby("pixel_id").size()
    assert (per_pixel==21).all(), "(b) every pixel must appear in all 7 years x 3 seasons = 21 periods with ONE id"
    yrs=panel.groupby("pixel_id").Year.nunique(); assert (yrs==7).all(), "(b) same id across all years"
check("F3 UID: never repeats within a Year/Season; same pixel keeps ONE id across all years & seasons & files", test_uid_uniqueness_and_persistence_end_to_end)

def test_final_schema_and_dtypes():
    """ONE schema (FINAL_PANEL_SCHEMA), compact dtypes, nothing DiD needs is lost; derivables are
    dropped from storage but re-created by build_treatment_columns at model time."""
    rng=np.random.default_rng(1); rows=[]
    for u in range(50):
        for yr in (2021,2024):
            for sc in (1,2):
                rows.append({"latitude":16.7+u*1e-4,"longitude":75.3,"Year":yr,"Season":sc,"buff_km":float(u%6),
                             "NDVI":rng.uniform(),"AGB":rng.uniform(10,40),"LandUse":2,"SubwshedID":1,"Treat":int(u%6==0),
                             "src_file":"a.csv","file_mtime":1.0,"schema_vintage":"x","UID":u,"DataYear":yr,"Coverage":1.0,
                             "subwshed_id":"S1","site_name":"Artal","season_sort_rank":sc-1,
                             "time_fe_year":str(yr),"time_fe_season":"K","time_fe_yearseason":f"{yr}_K",
                             "GapFilled":0,"any_outcome_flat_flag":0,"treat_period_mismatch_flag":0,"outcome_missing_flag":0})
    b=pd.DataFrame(rows); b["pixel_id"]=P.assign_pixel_ids(b.latitude.values,b.longitude.values)
    for extra in ["SrcOpt","SrcET","NObsV","NObsT","YrRel","LandUseDW","ESI_Anom","missing_source_cols","site_match_strategy",
                  "external_uid_final","row_id","treat_legacy","SAVI","EVI","LAI","LSWI","NDWI","NDMI","NDRE","RUSLE","Rain",
                  "Tmax","Tmin","Tmean","ESI","WSSI","WSI","SMDI","VCI","TCI","VHI"]:
        if extra not in b: b[extra]=0.5
    b=P.build_treatment_columns(b); n_before=b.shape[1]
    f=P.finalize_panel_block(b)
    assert list(f.columns)==P.FINAL_PANEL_COLUMNS and f.shape[1]==len(P.FINAL_PANEL_SCHEMA), f.shape
    assert not f.columns.duplicated().any()
    assert n_before>f.shape[1], "must actually drop the junk"
    for dropped in P.DROPPED_FROM_PANEL: assert dropped not in f.columns, dropped
    _left=set(P.panel_columns_left_out()) if hasattr(P,"panel_columns_left_out") else set()   # v20.58: the project's scope (_paths.PIPELINE_MODELS)
    for kept in ["pixel_id","buff_km","treatment","control","pre","post","did_term","time_fe_yearseason","NDVI","Rain","VHI","GapFilled","dose_per_subwshed","area_hectare","first_treat_agri_year"]:
        if kept in _left: assert kept not in f.columns, f"{kept}: only other models read it, yet it is in this project's panel"; continue
        assert kept in f.columns, kept
    # DiD information preserved exactly
    for c in ["treatment","control","pre","post","did_term"]: assert (f[c].values==b[c].values).all(), c
    assert (f.pixel_id.values==np.asarray(b.pixel_id, dtype=np.int64)).all() and f.pixel_id.dtype==np.int64
    assert str(f.NDVI.dtype)=="float32" and np.allclose(f.NDVI.values,b.NDVI.values,atol=1e-6)
    # derivables come back identically at model time
    r=C.build_treatment_columns(f.assign(Year=f.Year.astype(int),buff_km=f.buff_km.astype(float)))
    assert (r.event_time.values==b.event_time.values).all() and (r.period_index.values==b.period_index.values).all()
    # memory: substantially smaller
    ratio=b.memory_usage(deep=True).sum()/f.memory_usage(deep=True).sum()
    assert ratio>2.0, f"only {ratio:.1f}x smaller"
check(f"G1 ONE final schema ({len(P.FINAL_PANEL_SCHEMA)} cols, compact dtypes): DiD info exact, junk dropped, derivables restored, >2x smaller", test_final_schema_and_dtypes)

def test_gpu_dispatch_and_cpu_equivalence():
    """GPU path dispatches only when available; CPU path is the unchanged algorithm."""
    rng=np.random.default_rng(3); y=rng.normal(0,1,5000); f1=rng.integers(0,200,5000); f2=rng.integers(0,12,5000)
    a=C.demean_two_way(y,f1,f2); b=C._demean_cpu(y,(f1,f2),1e-10,100); c_=C.demean_multi_way(y,f1,f2)
    assert np.allclose(a,b,atol=1e-12) and np.allclose(a,c_,atol=1e-12)
    # exact FE property: within-group means of the residual are ~0 for every FE
    assert abs(pd.Series(a).groupby(f1).mean()).max()<1e-8 and abs(pd.Series(a).groupby(f2).mean()).max()<1e-8
    assert isinstance(C.gpu_status(),str) and hasattr(C,"gpu_selftest") and hasattr(C,"_demean_gpu")
    # the torch code must at least be syntactically valid python with the expected calls
    import inspect; src=inspect.getsource(C._demean_gpu)
    for api in ("index_add_","bincount","as_tensor","cuda.empty_cache","factorize"): assert api in src, api
check("G2 GPU dispatcher: CPU fallback identical to original algorithm; torch path present & well-formed", test_gpu_dispatch_and_cpu_equivalence)

# ====================================================================
print("="*74); print("COMPREHENSIVE VALIDATION"); print("="*74)
for k,v in RESULTS.items(): print(f"  {'PASS' if v=='PASS' else ('SKIP' if str(v).startswith('SKIP') else 'FAIL'):4s}  {k}" + ("" if v=="PASS" else f"\n        {v}"))
n=sum(1 for v in RESULTS.values() if v=="PASS")
_sk=sum(1 for v in RESULTS.values() if str(v).startswith("SKIP"))
print("="*74); print(f"{n}/{len(RESULTS)-_sk} PASSED" + (f"  ({_sk} skipped: input only on another machine / session)" if _sk else "")); print("="*74)
sys.exit(0 if n==len(RESULTS)-_sk else 1)
