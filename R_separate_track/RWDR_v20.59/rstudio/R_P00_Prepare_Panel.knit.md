
<!-- rnb-text-begin -->

---
title: "R_P00 -- Prepare the panel (data preparation, R)"
output: html_notebook
---

Reads every export under ROOT (default D:/LKT/RWDR/data; the old D:/LKT/TST_ArtalR until MIGRATE_DATA.bat has moved the data), builds the pixel panel with the SAME rules as the Python P00, averages the benchmark (BM) sites of each sub-watershed, codes every row for the fragment rule and reads your fund workbook. v20.57: it sets NO design -- each model notebook sets and applies its own (the options set to "data" are chosen FROM THE DATA, never from the effect).


<!-- rnb-text-end -->


<!-- rnb-chunk-begin -->


<!-- rnb-source-begin eyJkYXRhIjpbIiMgdGhlIGJ1bmRsZSdzIFIgZm9sZGVyICh3b3JrcyBmcm9tIHJzdHVkaW8vLCBqdXB5dGVyLyBvciB0aGUgcHJvamVjdCByb290KSIsIlJfSE9NRV9ESVIgPC0gbm9ybWFsaXplUGF0aChpZiAoZmlsZS5leGlzdHMoXCJsaWIvcmV3YXJkX3BhdGhzLlJcIikpIFwiLlwiIGVsc2UgXCIuLlwiLCB3aW5zbGFzaCA9IFwiL1wiKSIsImZvciAoZiBpbiBjKFwicmV3YXJkX3BhdGhzLlJcIiwgXCJyZXdhcmRfZGVzaWduLlJcIiwgXCJyZXdhcmRfcHJlcC5SXCIsIFwicmV3YXJkX21vZGVsc19jb3JlLlJcIikpIHNvdXJjZShmaWxlLnBhdGgoUl9IT01FX0RJUiwgXCJsaWJcIiwgZiksIGxvY2FsID0gZW52aXJvbm1lbnQoKSkiXX0= -->

```r
# the bundle's R folder (works from rstudio/, jupyter/ or the project root)
R_HOME_DIR <- normalizePath(if (file.exists("lib/reward_paths.R")) "." else "..", winslash = "/")
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f), local = environment())
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIHVzaW5nIHRoZSB3aG9sZSBtYWNoaW5lOiA0IGNvcmVzLCBhbGwgUkFNIChubyBzcGxpdCwgbm8gY2FwKVxuIn0= -->

```
[INFO]    using the whole machine: 4 cores, all RAM (no split, no cap)
```



<!-- rnb-output-end -->

<!-- rnb-source-begin eyJkYXRhIjoiY2F0KFwiZGF0YSByb290OlwiLCBST09ULCBcInwgb3V0cHV0OlwiLCBPVVRQVVRfRElSLCBcIlxcblwiKSJ9 -->

```r
cat("data root:", ROOT, "| output:", OUTPUT_DIR, "\n")
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiZGF0YSByb290OiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMgfCBvdXRwdXQ6IC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQgXG4ifQ== -->

```
data root: /tmp/RtmpO0K6MW/reward_all_tests/E_options | output: /tmp/RtmpO0K6MW/reward_all_tests/E_options/output 
```



<!-- rnb-output-end -->

<!-- rnb-source-begin eyJkYXRhIjoiaW52aXNpYmxlKGNvbmZpcm1fcGFja2FnZXMoKSkgICAjIHYyMC41NTogYXJlIEFMTCBSIHBhY2thZ2VzIGluc3RhbGxlZD8gKHByZS1idWlsdCBmaXJzdDsgYSBtaXNzaW5nIG9uZSBpcyBpbnN0YWxsZWQgbm93IHdoZW4gQVVUT19JTlNUQUxMX1BBQ0tBR0VTKSJ9 -->

```r
invisible(confirm_packages())   # v20.55: are ALL R packages installed? (pre-built first; a missing one is installed now when AUTO_INSTALL_PACKAGES)
```



<!-- rnb-source-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZzogQ2FuJ3QgZmluZCBnZW5lcmljIGBmaWx0ZXJfb3V0YCBpbiBwYWNrYWdlIGRwbHlyIHRvIHJlZ2lzdGVyIFMzIG1ldGhvZC5cbmkgVGhpcyBtZXNzYWdlIGlzIG9ubHkgc2hvd24gdG8gZGV2ZWxvcGVycyB1c2luZyBkZXZ0b29scy5cbmkgRG8geW91IG5lZWQgdG8gdXBkYXRlIGRwbHlyIHRvIHRoZSBsYXRlc3QgdmVyc2lvbj9cbkNhbid0IGZpbmQgZ2VuZXJpYyBgZmlsdGVyX291dGAgaW4gcGFja2FnZSBkcGx5ciB0byByZWdpc3RlciBTMyBtZXRob2QuXG5pIFRoaXMgbWVzc2FnZSBpcyBvbmx5IHNob3duIHRvIGRldmVsb3BlcnMgdXNpbmcgZGV2dG9vbHMuXG5pIERvIHlvdSBuZWVkIHRvIHVwZGF0ZSBkcGx5ciB0byB0aGUgbGF0ZXN0IHZlcnNpb24/XG5DYW4ndCBmaW5kIGdlbmVyaWMgYGZpbHRlcl9vdXRgIGluIHBhY2thZ2UgZHBseXIgdG8gcmVnaXN0ZXIgUzMgbWV0aG9kLlxuaSBUaGlzIG1lc3NhZ2UgaXMgb25seSBzaG93biB0byBkZXZlbG9wZXJzIHVzaW5nIGRldnRvb2xzLlxuaSBEbyB5b3UgbmVlZCB0byB1cGRhdGUgZHBseXIgdG8gdGhlIGxhdGVzdCB2ZXJzaW9uP1xuQ2FuJ3QgZmluZCBnZW5lcmljIGBmaWx0ZXJfb3V0YCBpbiBwYWNrYWdlIGRwbHlyIHRvIHJlZ2lzdGVyIFMzIG1ldGhvZC5cbmkgVGhpcyBtZXNzYWdlIGlzIG9ubHkgc2hvd24gdG8gZGV2ZWxvcGVycyB1c2luZyBkZXZ0b29scy5cbmkgRG8geW91IG5lZWQgdG8gdXBkYXRlIGRwbHlyIHRvIHRoZSBsYXRlc3QgdmVyc2lvbj9cbiJ9 -->

```
Warning: Can't find generic `filter_out` in package dplyr to register S3 method.
i This message is only shown to developers using devtools.
i Do you need to update dplyr to the latest version?
Can't find generic `filter_out` in package dplyr to register S3 method.
i This message is only shown to developers using devtools.
i Do you need to update dplyr to the latest version?
Can't find generic `filter_out` in package dplyr to register S3 method.
i This message is only shown to developers using devtools.
i Do you need to update dplyr to the latest version?
Can't find generic `filter_out` in package dplyr to register S3 method.
i This message is only shown to developers using devtools.
i Do you need to update dplyr to the latest version?
```



<!-- rnb-warning-end -->

<!-- rnb-message-begin eyJkYXRhIjoiUmVnaXN0ZXJlZCBTMyBtZXRob2Qgb3ZlcndyaXR0ZW4gYnkgJ0dHYWxseSc6XG4gIG1ldGhvZCBmcm9tICAgXG4gICsuZ2cgICBnZ3Bsb3QyXG4ifQ== -->

```
Registered S3 method overwritten by 'GGally':
  method from   
  +.gg   ggplot2
```



<!-- rnb-message-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIGluc3RhbGxpbmcgJ3BvbGFycyc6IHItdW5pdmVyc2UgKGh0dHBzOi8vcnBvbGFycy5yLXVuaXZlcnNlLmRldiksIHByZS1idWlsdCAuLi5cbiJ9 -->

```
[INFO]    installing 'polars': r-universe (https://rpolars.r-universe.dev), pre-built ...
```



<!-- rnb-output-end -->

<!-- rnb-message-begin eyJkYXRhIjoiSW5zdGFsbGluZyBwYWNrYWdlIGludG8gJy91c3IvbG9jYWwvbGliL1Ivc2l0ZS1saWJyYXJ5J1xuKGFzICdsaWInIGlzIHVuc3BlY2lmaWVkKVxuIn0= -->

```
Installing package into '/usr/local/lib/R/site-library'
(as 'lib' is unspecified)
```



<!-- rnb-message-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIGluc3RhbGxpbmcgJ3BvbGFycyc6IENSQU4gKHRoZSByZXBvc2l0b3J5J3MgYnVpbGQgZm9yIHRoaXMgcGxhdGZvcm0pIC4uLlxuIn0= -->

```
[INFO]    installing 'polars': CRAN (the repository's build for this platform) ...
```



<!-- rnb-output-end -->

<!-- rnb-message-begin eyJkYXRhIjoiSW5zdGFsbGluZyBwYWNrYWdlIGludG8gJy91c3IvbG9jYWwvbGliL1Ivc2l0ZS1saWJyYXJ5J1xuKGFzICdsaWInIGlzIHVuc3BlY2lmaWVkKVxuIn0= -->

```
Installing package into '/usr/local/lib/R/site-library'
(as 'lib' is unspecified)
```



<!-- rnb-message-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZzogdW5hYmxlIHRvIGFjY2VzcyBpbmRleCBmb3IgcmVwb3NpdG9yeSBodHRwczovL3BhY2thZ2VtYW5hZ2VyLnBvc2l0LmNvL2NyYW4vX19saW51eF9fL25vYmxlL2xhdGVzdC9zcmMvY29udHJpYjpcbiAgY2Fubm90IG9wZW4gVVJMICdodHRwczovL3BhY2thZ2VtYW5hZ2VyLnBvc2l0LmNvL2NyYW4vX19saW51eF9fL25vYmxlL2xhdGVzdC9zcmMvY29udHJpYi9QQUNLQUdFUydcbiJ9 -->

```
Warning: unable to access index for repository https://packagemanager.posit.co/cran/__linux__/noble/latest/src/contrib:
  cannot open URL 'https://packagemanager.posit.co/cran/__linux__/noble/latest/src/contrib/PACKAGES'
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIGluc3RhbGxpbmcgJ3BvbGFycyc6IENSQU4gc291cmNlIChwdXJlIFIsIG5vIGNvbXBpbGF0aW9uIG5lZWRlZCkgLi4uXG4ifQ== -->

```
[INFO]    installing 'polars': CRAN source (pure R, no compilation needed) ...
```



<!-- rnb-output-end -->

<!-- rnb-message-begin eyJkYXRhIjoiSW5zdGFsbGluZyBwYWNrYWdlIGludG8gJy91c3IvbG9jYWwvbGliL1Ivc2l0ZS1saWJyYXJ5J1xuKGFzICdsaWInIGlzIHVuc3BlY2lmaWVkKVxuIn0= -->

```
Installing package into '/usr/local/lib/R/site-library'
(as 'lib' is unspecified)
```



<!-- rnb-message-end -->

<!-- rnb-message-begin eyJkYXRhIjoiW1dBUk5JTkddICdwb2xhcnMnIGNvdWxkIG5vdCBiZSBpbnN0YWxsZWQgZnJvbSBhbnkgcm91dGUgKENSQU4gYmluYXJ5LCBzb3VyY2UsIHItdW5pdmVyc2UsIEdpdEh1YiwgYXJjaGl2ZSwgbWlycm9yKVxuIn0= -->

```
[WARNING] 'polars' could not be installed from any route (CRAN binary, source, r-universe, GitHub, archive, mirror)
```



<!-- rnb-message-end -->

<!-- rnb-message-begin eyJkYXRhIjoiW1dBUk5JTkddIFIgcGFja2FnZXM6IDM5IG9mIDQwIGluc3RhbGxlZCAtLSBNSVNTSU5HOiBwb2xhcnMgKE0xMyAoRElEbXVsdGlwbGVndERZTikpXG4ifQ== -->

```
[WARNING] R packages: 39 of 40 installed -- MISSING: polars (M13 (DIDmultiplegtDYN))
```



<!-- rnb-message-end -->

<!-- rnb-message-begin eyJkYXRhIjoiW1dBUk5JTkddIHRoZSBtb2RlbHMgdGhlc2UgcGFja2FnZXMgc2VydmUgZmFsbCBiYWNrIHRvIHRoZSBlbmdpbmUgb3Igc3RvcCB3aXRoIHRoZSBpbnN0YWxsIGNvbW1hbmQ7IHJ1biAwMF9TRVRVUC5SIChuZWVkcyBpbnRlcm5ldCksIG9yIHNldCBBVVRPX0lOU1RBTExfUEFDS0FHRVMgPC0gVFJVRSBpbiBsaWIvcmV3YXJkX3BhdGhzLlI7IGJ1aWxkIHRvb2xzOiBmb3VuZCAobmVlZGVkIG9ubHkgd2hlbiBubyBwcmUtYnVpbHQgYmluYXJ5IGV4aXN0cylcbiJ9 -->

```
[WARNING] the models these packages serve fall back to the engine or stop with the install command; run 00_SETUP.R (needs internet), or set AUTO_INSTALL_PACKAGES <- TRUE in lib/reward_paths.R; build tools: found (needed only when no pre-built binary exists)
```



<!-- rnb-message-end -->

<!-- rnb-chunk-end -->


<!-- rnb-text-begin -->


**The design is NOT set here (v20.57).** R_P00 builds the panel ONCE with every row -- all rings, years and seasons, every sub-watershed and every fragment of another sub-watershed, each row coded (`fragment`) -- and never has to be re-run for a design choice. The timing (your fund workbook by default), the dose, the control rings, the years, the seasons, OVERLAP_ROWS, FRAGMENT_RULE and POOLED_FE are set in the settings cell of EACH MODEL notebook (R_M01 ... R_M45, R_RUN_ALL_MODELS, R_D01) and applied when that model runs. The defaults live in `lib/reward_paths.R`. Change `ROOT` there if your exports are elsewhere.


<!-- rnb-text-end -->


<!-- rnb-chunk-begin -->


<!-- rnb-source-begin eyJkYXRhIjpbIiMgdjIwLjU3OiBub3RoaW5nIHRvIHNldCBoZXJlIGZvciB0aGUgZGVzaWduIC0tIGl0IGlzIHNldCBpbiBlYWNoIE1PREVMIG5vdGVib29rIChkZWZhdWx0czogbGliL3Jld2FyZF9wYXRocy5SKS4iLCIjIHYyMC41OSAoWU9VUiBSVUxFKTogUEVSSU9EX1JVTEUgKGxpYi9yZXdhcmRfcGF0aHMuUikgc2V0cyB0aGUgcGFuZWwncyBwb3N0IC8gcHJlIC0tIFwidHJlYXRcIiA9IHRoZSBleHBvcnRzJyBUcmVhdCBjb2x1bW4gKDEgPSBwb3N0LCAwID0gcHJlKSwiLCIjIFwieWVhclwiID0gWWVhciA+PSBUUkVBVE1FTlRfWUVBUiwgXCJib3RoXCIgPSB0aGUgdHdvIG11c3QgYWdyZWUgKGEgZGlzYWdyZWVpbmcgcm93IGxlYXZlcykuIGJ1ZmZfa20gMCA9IHRoZSB0cmVhdG1lbnQgYXJlYSwgMS01ID0gdGhlIGNvbnRyb2wiLCIjIHJpbmdzLiBSX1AwMCBjb25maXJtcyBib3RoIG9uIGV2ZXJ5IGlucHV0IGZpbGUgLT4gaW5wdXRfZGVzaWduX2F1ZGl0X1IuY3N2LiIsIiMgVGhlIHBhbmVsLWJ1aWxkaW5nIHJ1bGVzIChwaXhlbCBsaW5rYWdlLCBkdXBsaWNhdGVzLCBtYXNrZWQgemVyb3MsIG5lZ2F0aXZlIGNvdmFyaWF0ZXMpIHN0YXkgaW4gbGliL3Jld2FyZF9wYXRocy5SIC8gcmV3YXJkX3ByZXAuUi4iLCIjIHYyMC41OSAtLSBFVkVSWSBjdXN0b21pc2F0aW9uIGF0IHRoZSBwYW5lbCBsZXZlbCB0b28gKGFzIFB5dGhvbidzIFAwMF9TZXR0aW5ncyk6IHRoZXNlIGFyZSB0aGUgREVGQVVMVFMgdGhlIGRlc2lnbiByZXBvcnQsIHRoZSBzY3JlZW4gdGFibGUiLCIjIGFuZCBhIG1vZGVsIHRoYXQgbGVhdmVzIGFuIG9wdGlvbiB1bnNldCB1c2U7IGVhY2ggbW9kZWwgbm90ZWJvb2sgc2V0cyBJVFMgT1dOIHZhbHVlcyBpbiBpdHMgZmlyc3QgY2h1bmsgYW5kIHRoZXkgd2luIGZvciB0aGF0IG1vZGVsLiIsIiMgVGhlIHBhbmVsIGl0c2VsZiBpcyBidWlsdCBvbmNlIHdpdGggZXZlcnkgcm93IGFuZCBuZXZlciBoYXMgdG8gYmUgcmUtcnVuIGZvciBhIGRlc2lnbiBjaG9pY2UgKGxpYi9yZXdhcmRfcGF0aHMuUiBoYXMgdGhlIHNhbWUgZGVmYXVsdHMpLiIsIkRFU0lHTl9NT0RFICAgICAgIDwtIFwicmVjb21tZW5kZWRcIiAgICMgXCJyZWNvbW1lbmRlZFwiOiBhbiBvcHRpb24gc2V0IHRvIFwiZGF0YVwiIGlzIGNob3NlbiBGUk9NIFRIRSBEQVRBIChERVNJR05fUkVDT01NRU5EQVRJT04ubWQpIHwgXCJtYW51YWxcIiIsIlRSRUFUTUVOVF9USU1JTkcgIDwtIFwiZnVuZFwiICAgICAgICAgICMgXCJmdW5kXCIgKHRoZSBmdW5kIHdvcmtib29rOiBlYWNoIHN1Yi13YXRlcnNoZWQncyBmaXJzdCB0cmVhdGVkIHNlYXNvbikgfCBcInJlZ2lzdHJ5XCIgKHNpdGVzLmNzdikgfCBcImZpeGVkXCIiLCJUUkVBVE1FTlRfWUVBUiAgICA8LSAyMDIyICAgICAgICAgICAgIyBcImZpeGVkXCIgdGltaW5nLCBhbmQgdGhlIGZhbGwtYmFjayBmb3IgYSBzdWItd2F0ZXJzaGVkIHRoZSBmdW5kIGZpbGUgLyByZWdpc3RyeSBkb2VzIG5vdCBkYXRlIiwiRlVORF9TVEFSVF9SVUxFICAgPC0gXCJiYWNrY2FzdFwiICAgICAgIyBcImJhY2tjYXN0XCIgfCBcInNoYXJlXCIgfCBcImZpbGVfc3RhcnRcIiIsIkRPU0VfVkFSSUFCTEUgICAgIDwtIFwiZG9zZV9pbnRlbnNpdHlfcGVyX2hhXCIgICAjIHwgXCJkb3NlX2Ftb3VudF9zd3NcIiB8IFwiZG9zZV9zaGFyZV9vZl90YXJnZXRcIiIsIkNPTlRST0xfUklOR1MgICAgIDwtIFwiZGF0YVwiICAgICAgICAgICMgXCJkYXRhXCIgfCAxOjUgfCAxOjMgfCBjKDIsIDQpICAgKHRoZSBUUkVBVE1FTlQgQVJFQSBpcyBidWZmX2ttIDApIiwiUFJFX1lFQVJTICAgICAgICAgPC0gXCJkYXRhXCIgICAgICAgICAgIyBcImRhdGFcIiB8IE5BIChldmVyeSB5ZWFyIGJlZm9yZSB0aGUgc3RhcnQpIHwgYSBudW1iZXIgb2YgeWVhcnMgfCAyMDE1IChhIGNhbGVuZGFyIHllYXIgPSB0aGUgRklSU1QgcHJlIHllYXIpIiwiUE9TVF9ZRUFSUyAgICAgICAgPC0gXCJkYXRhXCIgICAgICAgICAgIyBcImRhdGFcIiB8IE5BIChldmVyeSB5ZWFyIGZyb20gdGhlIHN0YXJ0KSB8IGEgbnVtYmVyIG9mIHllYXJzIHwgMjAyNSAoYSBjYWxlbmRhciB5ZWFyID0gdGhlIExBU1QgcG9zdCB5ZWFyKSIsIlNFQVNPTlMgICAgICAgICAgIDwtIFwiYWxsXCIgICAgICAgICAgICMgXCJhbGxcIiB8IFwic2Vhc29uYWxcIiB8IFwieWVhcmx5XCIgfCBcIlJhYmlcIiB8IFwiS2hhcmlmK1JhYmlcIiIsIkVYQ0xVREVfVFJBTlNJVElPTl9ZRUFSIDwtIEZBTFNFICAgICAjIFRSVUUgPSB0aGUgZmlyc3QgdHJlYXRlZCB5ZWFyIG9mIGVhY2ggc2VyaWVzIGxlYXZlcyB0aGUgc2FtcGxlIiwiVU5JVF9GRSAgICAgICAgICAgPC0gXCJwaXhlbF9zZWFzb25cIiAgIyB8IFwicGl4ZWxcIiIsIkNPSE9SVF9PRkZTRVQgICAgIDwtIDBMIiwiUE9PTEVEX0ZFICAgICAgICAgPC0gXCJzaXRlX3BlcmlvZFwiICAgIyBzZXZlcmFsIHN1Yi13YXRlcnNoZWRzOiBzdWItd2F0ZXJzaGVkIHggeWVhciB4IHNlYXNvbiBlZmZlY3RzIHwgXCJwZXJpb2RcIiIsIk9WRVJMQVBfUk9XUyAgICAgIDwtIFwiZHJvcFwiICAgICAgICAgICMgfCBcImtlZXBcIiIsIkZSQUdNRU5UX1JVTEUgICAgIDwtIFwiZHJvcFwiICAgICAgICAgICMgfCBcImtlZXBcIiAgKGZyYWdtZW50cyBvZiBvdGhlciBzdWItd2F0ZXJzaGVkcyBpbnNpZGUgdGhlIGV4cG9ydHMsIG1pbm9yIHN1Yi13YXRlcnNoZWRzIG9mIHRoZSBwYW5lbCkiLCJDT1ZBUklBVEVTICAgICAgICA8LSBjKFwiUmFpblwiLCBcIlRtYXhcIiwgXCJUbWVhblwiLCBcIlRtaW5cIikiLCIjIHYyMC41OSAtLSBZT1VSIFJVTEU6IHRoZSBzdWItd2F0ZXJzaGVkIG9mIGV2ZXJ5IHJvdyBpcyB3aGVyZSBpdHMgbGF0aXR1ZGUgLyBsb25naXR1ZGUgZmFsbHMgaW4gdGhlIHNoYXBlZmlsZSAodGhlIGNvcmUgb3IgYSBjb250cm9sIHJpbmcpOyIsIiMgICB0aGUgZmlsZSdzIGlkIG9ubHkgbGFiZWxzLiBPTkUgc3ViLXdhdGVyc2hlZCBwcm9jZXNzZWQgPSB0aGUgb25lIGhvbGRpbmcgdGhlIG1ham9yaXR5IG9mIHRoZSByb3dzIChTVUJfV0FURVJTSEVEUyA9IFwiZGF0YVwiOiBldmVyeSIsIiMgICBzdWItd2F0ZXJzaGVkIHdpdGggPj0gRlJBR01FTlRfTUlOX1NIQVJFIG9mIHRoZSBsYXJnZXN0IG9uZSdzIG93biByb3dzOyB0aGUgcmVzdCBhcmUgZnJhZ21lbnRzKTsgU0VWRVJBTCA9IGV2ZXJ5IHJvdyBpbiBpdHMgb3duIHN1Yi13YXRlcnNoZWQuIiwiU1VCX1dBVEVSU0hFRFMgICAgICA8LSBcImRhdGFcIiAgICAgICAgIyBcImRhdGFcIiB8IFwiYWxsXCIgfCAxMSB8IGMoNywgMTEpIiwiU0lURV9HRU9NRVRSWV9DSEVDSyA8LSBUUlVFICAgICAgICAgICMgZXZlcnkgcm93IGxvY2F0ZWQgaW4gdGhlIHNoYXBlZmlsZTogY29uZmlybWVkIC8gY29ycmVjdGVkIC8gYXNzaWduZWQgfCBGQUxTRSA9IHRydXN0IHRoZSBpZCBpbiB0aGUgZmlsZSIsIkJVRkZfRlJPTV9HRU9NRVRSWSAgPC0gRkFMU0UgICAgICAgICAjIFRSVUUgPSBidWZmX2ttIGFsd2F5cyBmcm9tIHRoZSBwb2x5Z29uIHJpbmcgfCBGQUxTRSA9IG9ubHkgd2hlcmUgdGhlIHN1Yi13YXRlcnNoZWQgd2FzIGNvcnJlY3RlZCAvIGFzc2lnbmVkIiwiUElYRUxfT05FX1NJVEUgICAgICA8LSBUUlVFICAgICAgICAgICMgdjIwLjU5IC0tIFlPVVIgUlVMRTogb25lIHN1Yi13YXRlcnNoZWQgYW5kIG9uZSByaW5nIHBlciBwaXhlbCBpbiB0aGUgd2hvbGUgcGFuZWwgKHRoZSBwb2x5Z29uIHRoYXQgaG9sZHMgdGhlIHBvaW50IGRlY2lkZXM7IiwiICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgICBjb25maXJtZWQ6IHBhbmVsX3BpeGVsX2NvbnNpc3RlbmN5X1IuY3N2KSB8IEZBTFNFID0gdGhlIHYyMC41OCBydWxlIChhIHBvaW50IGluIHR3byB6b25lcyBrZXB0IG9uY2UgcGVyIHN1Yi13YXRlcnNoZWQpIiwiIyB2MjAuNTkgLS0gWU9VUiBSVUxFOiB0aGUgcGFuZWwgS0VFUFMgZXZlcnkgcm93IGFuZCBldmVyeSB2YWx1ZS4gRmlsbCB2YWx1ZXMgKGEgeWVhci1zZWFzb24gd2l0aCBPTkUgdmFsdWUgZm9yIGV2ZXJ5IHBpeGVsKSBhbmQgZ2FwLWZpbGxlZCIsIiMgcm93cyAoR2FwRmlsbGVkID0gMSAvIENvdmVyYWdlIDApIHN0YXkgSU4gdGhlIHBhbmVsOyB3aGV0aGVyIGEgTU9ERUwgZXN0aW1hdGVzIG9uIHRoZW0gaXMgZGVjaWRlZCBieSB0aGUgdHdvIG9wdGlvbnMgYmVsb3cgLS0gdGhlIERFRkFVTFRTIiwiIyBoZXJlICh0aGUgZGVzaWduIHJlcG9ydCBhbmQgdGhlIHNjcmVlbiB0YWJsZSBvZiB0aGlzIG5vdGVib29rIHVzZSB0aGVtKSBhbmQsIGZvciBlYWNoIG1vZGVsLCBJVFMgT1dOIHNldHRpbmcgaW4gaXRzIG5vdGVib29rIChhcyBQeXRob24ncyIsIiMgUDAwX1NldHRpbmdzIGFuZCBldmVyeSBtb2RlbCdzIENFTEwgMSkuIEtlZXBpbmcgYSBmaWxsIHllYXItc2Vhc29uIGlzIG5vdCBuZXV0cmFsOiBpbiBpdCB0aGUgdHJlYXRlZC1jb250cm9sIGRpZmZlcmVuY2UgaXMgZXhhY3RseSAwLCIsIiMgd2hpY2ggZGlsdXRlcyB0aGUgcHJlIChvciBwb3N0KSBnYXAgdGhlIERpRCBjb21wYXJlcyAtLSB0aGUgc2NyZWVuJ3MgcmVwb3J0IHNheXMgc28gd2hlbiBcImtlZXBcIiBpcyBpbiBmb3JjZS4iLCJPVVRDT01FX1NDUkVFTiAgICA8LSBcImRyb3BcIiAgICMgXCJkcm9wXCIgPSBhIHllYXItc2Vhc29uIGNvbnN0YW50IGFjcm9zcyBwaXhlbHMgKGEgZmlsbCB2YWx1ZSkgb3Igd2l0aCBjb2xsYXBzZWQgY292ZXJhZ2UgbGVhdmVzIHRoZSBtb2RlbCAoZXZpZGVuY2U6IiwiICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyAgIE9VVENPTUVfU0NSRUVOXzxvdXRjb21lPi5jc3YpIHwgXCJrZWVwXCIgPSByZXBvcnRlZCBhbmQgS0VQVCAocmVzdWx0cyB0YWdnZWQgX3NjcmVlbktlcHQpIHwgXCJvZmZcIiA9IG5vIHNjcmVlbiIsIkVYQ0xVREVfR0FQRklMTEVEIDwtIFRSVUUgICAgICMgVFJVRSA9IHJvd3MgdGhlIGV4cG9ydGVyIGZpbGxlZCBmcm9tIGhpc3RvcnkgKEdhcEZpbGxlZCA9IDEgLyBDb3ZlcmFnZSAwKSBhcmUgbm90IG9ic2VydmF0aW9ucyB8IEZBTFNFIGtlZXBzIHRoZW0iLCJERVNJR05fU09VUkNFICAgICA8LSBcInBhbmVsXCIgICMgdjIwLjU5IC0tIFlPVVIgUlVMRTogdGhlIFBBTkVMJ3MgdHJlYXQgLyBjb250cm9sIC8gcHJlIC8gcG9zdCAvIGRpZCAodGhlIGV4cG9ydHMnIFRyZWF0IGZsYWcsIFBFUklPRF9SVUxFKSBhcmUgd2hhdCBldmVyeSIsIiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgICBtb2RlbCBlc3RpbWF0ZXMgb24gYnkgZGVmYXVsdCAocmVzdWx0cyB0YWdnZWQgX3BhbmVsRGVzaWduOyBhIG5vdGVib29rJ3MgQ0VMTCAxIG92ZXJyaWRlcyBpdCkgfCBcIm1vZGVsXCIgPSBkZXNpZ24tYmFzZWQiLCIjID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09IiwiIyBPUFRJT05BTCBDVVNUT01JU0FUSU9OUyAoMSBPY3QsIHlvdXIgcnVsZSkgLS0gZXZlcnkgb25lIGhhcyBhIFVTRV8gc3dpdGNoLiBGQUxTRSA9IE5PVCBhcHBsaWVkIGF0IGFsbCwgd2hhdGV2ZXIgdGhlIHZhbHVlIGJlc2lkZSBpdCIsIiMgc2F5cyAodGhlIHN0YW5kYXJkIGRlc2lnbiBhYm92ZSBydW5zIGFzIGl0IGlzKTsgVFJVRSA9IGFwcGxpZWQgZXhhY3RseSBhcyBzZXQuIEFsbCBhcmUgRkFMU0UgYnkgZGVmYXVsdC4gREVTSUdOIElOIEVGRkVDVCBzaG93cyBlYWNoIiwiIyBvbmUgYXMgXCJub3QgdXNlZFwiIG9yIHdpdGggdGhlIHZhbHVlIGluIGZvcmNlOyBhIHJ1bGUgaW4gZm9yY2UgYWxzbyB0YWdzIHRoZSByZXN1bHRzIGZvbGRlciAodGhlIHRhZyBpcyBuYW1lZCBiZXNpZGUgZWFjaCBvcHRpb24pLiIsIiMgSEVSRTogdGhlIHBhbmVsLWxldmVsIERFRkFVTFRTIG9mIHRoZXNlIHN3aXRjaGVzIGFuZCB2YWx1ZXMgKGEgbW9kZWwgbm90ZWJvb2sncyBvd24gU0VDVElPTiBCIC8gQyB3aW5zIGZvciB0aGF0IG1vZGVsKS4iLCIjIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tIiwiIyBTRUNUSU9OIEIgLS0gVEhFIENPTlRST0wgR1JPVVAgQ0hPU0VOIE9OIFRIRSBQUkUgUEVSSU9EICh5b3VyIHJlcXVlc3Qgb2YgMzAgU2VwKTogd2hpY2ggYnVmZmVycyAvIGNsdXN0ZXJzIGFyZSB0aGUgY29udHJvbHMgZm9yIFRISVMiLCIjIG91dGNvbWUsIGRlY2lkZWQgb24gdGhlIHByZSBwZXJpb2Qgb25seSBhbmQgdGhlbiBGSVhFRCBhY3Jvc3MgdGhlIHdob2xlIHBhbmVsICh0aGUgc2FtZSBjb250cm9sIHBpeGVscyBpbiBldmVyeSB5ZWFyIGFuZCBzZWFzb24pIiwiIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLSIsIlVTRV9DT05UUk9MX1NFTEVDVElPTiA8LSBGQUxTRSAgICAjIEZBTFNFID0gZXZlcnkgcmluZyBvZiBDT05UUk9MX1JJTkdTIGlzIHRoZSBjb250cm9sIGdyb3VwIChhcyBhYm92ZSkgfCBUUlVFID0gQ09OVFJPTF9TRUxFQ1RJT04gYmVsb3cgY2hvb3NlcyBpdCIsIkNPTlRST0xfU0VMRUNUSU9OIDwtIFwicHJlX3JpbmdzXCIgICMgICBcInByZV9yaW5nc1wiOiB0aGUgQ09OVFJPTF9TRUxFQ1RfSyAoMSBvciAyKSBidWZmZXJzIHdob3NlIFBSRS1wZXJpb2Qgc2VyaWVzIGlzIGNsb3Nlc3QgdG8gdGhlIHRyZWF0bWVudCBhcmVhJ3MgLS0geW91ciIsIiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjICAgXCJtb3N0IGNsb3NlIDEgb3IgMiBidWZmZXJzXCIgfCBcInByZV9ibG9ja3NcIjogY29udHJvbCBDTFVTVEVSUyAofjEga20gYmxvY2tzIG9mIHBpeGVscykgZnJvbSBBTlkgcGFydCBvZiB0aGUgYnVmZmVycywgdGhlIiwiICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgICBjbG9zZXN0IGZpcnN0LCB1bnRpbCBDT05UUk9MX1NFTEVDVF9SQVRJTyB4IHRoZSB0cmVhdGVkIHBpeGVscyAtLSB5b3VyIFwiY2x1c3RlcnMgZnJvbSBhbnkgcGFydCBvZiB0aGUgYnVmZmVyc1wiLiIsIiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjICAgUGVyIG91dGNvbWU7IHRoZSBkZWNpc2lvbiB1c2VzIHRoZSBQUkUgcGVyaW9kIG9ubHkgKGEgcG9zdC0gb3Igb3V0Y29tZS1iYXNlZCBydWxlIGlzIHJlZnVzZWQpOyBtYWRlIG9uY2UgYW5kIGFwcGxpZWQiLCIgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyAgIHRvIGV2ZXJ5IHllYXIgYW5kIHNlYXNvbi4gRXZpZGVuY2U6IENPTlRST0xfU0VMRUNUSU9OXzxvdXRjb21lPl9SLmNzdiBiZXNpZGUgdGhlIHJlc3VsdHMuIFRhZyBfY3RybFByZTJyIC8gX2N0cmxQcmVCbGszeCIsIkNPTlRST0xfU0VMRUNUX0sgIDwtIDJMICAgICAgICAgICAjICAgcHJlX3JpbmdzOiBob3cgbWFueSBidWZmZXJzIC0tIDEgb3IgMiAodXAgdG8gNSkiLCJDT05UUk9MX1NFTEVDVF9SQVRJTyA8LSAzICAgICAgICAgIyAgIHByZV9ibG9ja3M6IGNvbnRyb2wgcGl4ZWxzID49IHRoaXMgeCB0aGUgdHJlYXRlZCBwaXhlbHMiLCJDT05UUk9MX1NFTEVDVF9PTiA8LSBcInRyZW5kXCIgICAgICAjICAgd2hhdCBcImNsb3Nlc3RcIiBtZWFuczogXCJ0cmVuZFwiID0gdGhlIGRlbWVhbmVkIHByZSBzZXJpZXMnIGRpc3RhbmNlICh3aGF0IHRoZSBwYXJhbGxlbC10cmVuZHMgYXNzdW1wdGlvbiBhc2tzOyByZWNvbW1lbmRlZCkiLCIgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyAgIHwgXCJsZXZlbFwiID0gdGhlIG5lYXJlc3QgcHJlLXBlcmlvZCBNRUFOICh5b3VyIFwibWVhbiBvZiB0aGUgdHJlYXRtZW50IGFyZWEgdnMgdGhlIGJ1ZmZlcidzIG1lYW5cIikgfCBcInJtc2VcIiA9IHRoZSBSTVNFIG9mIHRoZSIsIiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjICAgY2VsbC13aXNlIHByZSBkaWZmZXJlbmNlcyB8IFwiYm90aFwiID0gdHJlbmQgKyBsZXZlbC4gIFRhZyBzdWZmaXg6IG5vbmUgLyBMIC8gUiAvIEIiLCJVU0VfU0FNRV9QSVhFTFMgICA8LSBGQUxTRSAgICAgICAgIyBGQUxTRSA9IGEgcGl4ZWwgbWF5IGNvbnRyaWJ1dGUgdG8gb25lIHNpZGUgb25seSAodGhlIHYyMC41OCBzYW1wbGUpIHwgVFJVRSA9IHRoZSB0cmVhdGVkIGFuZCBjb250cm9sIGdyb3VwcyBhcmUgdGhlIFNBTUUiLCJTQU1FX1BJWEVMUyAgICAgICA8LSBcInByZV9wb3N0XCIgICAjICAgcGl4ZWxzIGFjcm9zcyB0aGUgcGFuZWw6IFwicHJlX3Bvc3RcIiA9IGV2ZXJ5IHBpeGVsIG9ic2VydmVkIGluIHByZSBBTkQgcG9zdCwgZWxzZSBpdCBsZWF2ZXMgKHRhZyBfcGl4UFApIHwgXCJhbGxcIiA9IGluIiwiICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgICBldmVyeSB5ZWFyLXNlYXNvbiBvZiB0aGUgc2FtcGxlIChhIGJhbGFuY2VkIHBpeGVsIHNldDsgdGFnIF9waXhBbGwpLiBUaGUgc2FtcGxlLWludGVncml0eSBsaW5lIGNvbmZpcm1zIGl0IGF0IGV2ZXJ5IHJ1biIsIiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0iLCIjIFNFQ1RJT04gQyAtLSBQQU5FTC1QUkVQQVJBVElPTiBFTkhBTkNFTUVOVFMgKHRoZSB0aHJlZSBzcGVjaWZpY2F0aW9ucyBvZiAzMCBTZXApOyBlYWNoIHdpdGggaXRzIG93biBzd2l0Y2giLCIjIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tIiwiVVNFX0RPTlVUICAgICAgICAgPC0gRkFMU0UgICAgICAgICMgRkFMU0UgPSByaW5nIDEgaXMgYSBjb250cm9sIGxpa2UgdGhlIG90aGVycyB8IFRSVUUgPSBET05VVF9SSU5HUyBsZWF2ZSB0aGUgY29udHJvbCBwb29sIC0tIHRoZSBzcGlsbG92ZXIgYnVmZmVyIG5leHQgdG8gdGhlIGNvcmUiLCJET05VVF9SSU5HUyAgICAgICA8LSAxTCAgICAgICAgICAgIyAgIHRoZSByaW5nKHMpIGxlZnQgb3V0LCBlLmcuIDFMIG9yIGMoMUwsIDJMKTsgYXBwbGllZCBiZWZvcmUgYW55IGNvbnRyb2wgY2hvaWNlLiBUYWcgX2RvbnV0MSIsIlVTRV9MQU5EVVNFX01BU0sgIDwtIEZBTFNFICAgICAgICAjIEZBTFNFID0gZXZlcnkgbGFuZC11c2UgY2xhc3MgfCBUUlVFID0gb25seSBwaXhlbHMgd2hvc2UgUFJFLXBlcmlvZCAoYmFzZWxpbmUpIExhbmRVc2UgY2xhc3MgaXMgaW4gTEFORFVTRV9LRUVQIHN0YXkuIFRhZyBfbHUyIiwiTEFORFVTRV9LRUVQICAgICAgPC0gMkwgICAgICAgICAgICMgICB5b3VyIGV4cG9ydGVyJ3MgY2xhc3MgY29kZShzKSBmb3IgYWdyaWN1bHR1cmUgKGEgcGl4ZWwncyBjbGFzcyBpcyByZWFkIG9uIHRoZSBwcmUgcGVyaW9kLCBzbyB0aGUgd29ya3MgY2Fubm90IG1vdmUgaXQpIiwiVVNFX0JBU0VMSU5FX05EVklfTUFTSyA8LSBGQUxTRSAgICMgRkFMU0UgPSBubyBtYXNrIHwgVFJVRSA9IG9ubHkgcGl4ZWxzIHdob3NlIFBSRS1wZXJpb2QgbWVhbiBORFZJIGV4Y2VlZHMgQkFTRUxJTkVfTkRWSV9NSU4gc3RheSAoYW4gYWdyaWN1bHR1cmFsIG1hc2spLiBUYWcgX25kdmlQcmUwLjI1IiwiQkFTRUxJTkVfTkRWSV9NSU4gPC0gMC4yNSAgICAgICAgICMgICB0aGUgdGhyZXNob2xkIChhbiBORFZJIHZhbHVlKSIsIlVTRV9DT1ZFUkFHRV9USFJFU0hPTEQgPC0gRkFMU0UgICAjIEZBTFNFID0gdGhlIHN0YW5kYXJkIHNjcmVlbiAoYSB5ZWFyLXNlYXNvbiBiZWxvdyA1ICUgb2YgdGhlIHR5cGljYWwgY292ZXJhZ2UgbGVhdmVzKSB8IFRSVUUgPSBiZWxvdyBNSU5fUElYRUxfQ09WRVJBR0VfUENULiBUYWcgX2NvdjcwIiwiTUlOX1BJWEVMX0NPVkVSQUdFX1BDVCA8LSAwLjcwICAgICMgICB0aGUgc2hhcmUgb2YgdGhlIHR5cGljYWwgdHJlYXRlZCAvIGNvbnRyb2wgY292ZXJhZ2UgYSB5ZWFyLXNlYXNvbiBtdXN0IHJlYWNoICh5b3VyIGxvZzogMjAyMyBaYWlkLCAyMDI1IEtoYXJpZiAvIFphaWQgY29sbGFwc2VkKSIsIlVTRV9EUk9QX1NJTkdMRVRPTlMgPC0gRkFMU0UgICAgICAjIEZBTFNFID0gc2VyaWVzIHNlZW4gb25jZSBzdGF5IHwgVFJVRSA9IHRoZXkgbGVhdmUgYmVmb3JlIHRoZSBkZW1lYW5pbmcgKHRoZSBwcmUtZmxpZ2h0KS4gVGFnIF9ub1NpbmdsZSIsIlVTRV9QUkVDSVNJT05fVE9MRVJBTkNFIDwtIEZBTFNFICAjIEZBTFNFID0gdGhlIG5vLWRhdGEgemVybyBpcyBhbiBFWEFDVCAwICh0aGUgdjIwLjU4IHJ1bGUpIHwgVFJVRSA9IHx2YWx1ZXwgPD0gUFJFQ0lTSU9OX1RPTEVSQU5DRSBpcyB0aGUgbm8tZGF0YSB6ZXJvIGFuZCBhIiwiUFJFQ0lTSU9OX1RPTEVSQU5DRSA8LSAxZS02ICAgICAgICMgICB5ZWFyLXNlYXNvbiBpcyBcImNvbnN0YW50IGFjcm9zcyBwaXhlbHNcIiB3aXRoaW4gaXQgLS0gaW5kaWNlcyBpbiBbLTEsIDFdIGFyZSBuZXZlciBjb21wYXJlZCB3aXRoIGV4YWN0IGVxdWFsaXR5IiwiIyBUaGUgUmFiaS1vbmx5IHJ1biBvZiB0aGUgc3BlY2lmaWNhdGlvbnMgaXMgU0VBU09OUyA8LSBcIlJhYmlcIiBhYm92ZTsgdGhlIH4xIGttIGJsb2NrIGNsdXN0ZXJzIGFyZSBDTFVTVEVSIDwtIFwiYmxvY2tcIiBhYm92ZS4iLCIjID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09IiwiQ0xVU1RFUiAgICAgICAgICAgPC0gXCJhdXRvXCIgICAjIFwiYXV0b1wiICh0aGUgc3ViLXdhdGVyc2hlZHM7IGZld2VyIHRoYW4gNiAtPiB0aGUgeWVhcnMpIHwgXCJibG9ja1wiICh+MSBrbSBzcGF0aWFsIGJsb2NrczogbWFueSBjbHVzdGVycywgc3BhdGlhbCBjb3JyZWxhdGlvbiBhYnNvcmJlZCkiLCJjYXQoXCJkZXNpZ24gZGVmYXVsdHMgKGEgbW9kZWwgbm90ZWJvb2sgb3ZlcnJpZGVzIGVhY2gpOlwiLCBERVNJR05fTU9ERSwgXCJ8IHRpbWluZ1wiLCBUUkVBVE1FTlRfVElNSU5HLCBcInwgcGVyaW9kIHJ1bGUgKFJfUDAwKVwiLCBQRVJJT0RfUlVMRSwgXCJ8IG91dGNvbWUgc2NyZWVuXCIsIE9VVENPTUVfU0NSRUVOLCBcInwgZGVzaWduIHNvdXJjZVwiLCBERVNJR05fU09VUkNFLCBcInwgY29udHJvbCBzZWxlY3Rpb25cIiwgQ09OVFJPTF9TRUxFQ1RJT04sIFwifCBzYW1lIHBpeGVsc1wiLCBTQU1FX1BJWEVMUywgXCJ8IGRvbnV0XCIsIHBhc3RlKERPTlVUX1JJTkdTLCBjb2xsYXBzZSA9IFwiLFwiKSwgXCJ8IGxhbmQgdXNlXCIsIHBhc3RlKExBTkRVU0VfS0VFUCwgY29sbGFwc2UgPSBcIixcIiksIFwifCBjbHVzdGVyXCIsIENMVVNURVIsIFwifCBnYXAtZmlsbGVkIHJvd3NcIiwgaWYgKGlzVFJVRShFWENMVURFX0dBUEZJTExFRCkpIFwibGVmdCBvdXRcIiBlbHNlIFwia2VwdFwiLCBcInwgcmluZ3NcIiwgcGFzdGUoQ09OVFJPTF9SSU5HUywgY29sbGFwc2UgPSBcIixcIiksXG4gICAgXCJ8IHNlYXNvbnNcIiwgcGFzdGUoU0VBU09OUywgY29sbGFwc2UgPSBcIixcIiksIFwifCBmcmFnbWVudHNcIiwgRlJBR01FTlRfUlVMRSwgXCJ8IG92ZXJsYXBcIiwgT1ZFUkxBUF9ST1dTLCBcInwgcG9vbGVkIEZFXCIsIFBPT0xFRF9GRSwgXCJcXG5cIikiXX0= -->

```r
# v20.57: nothing to set here for the design -- it is set in each MODEL notebook (defaults: lib/reward_paths.R).
# v20.59 (YOUR RULE): PERIOD_RULE (lib/reward_paths.R) sets the panel's post / pre -- "treat" = the exports' Treat column (1 = post, 0 = pre),
# "year" = Year >= TREATMENT_YEAR, "both" = the two must agree (a disagreeing row leaves). buff_km 0 = the treatment area, 1-5 = the control
# rings. R_P00 confirms both on every input file -> input_design_audit_R.csv.
# The panel-building rules (pixel linkage, duplicates, masked zeros, negative covariates) stay in lib/reward_paths.R / reward_prep.R.
# v20.59 -- EVERY customisation at the panel level too (as Python's P00_Settings): these are the DEFAULTS the design report, the screen table
# and a model that leaves an option unset use; each model notebook sets ITS OWN values in its first chunk and they win for that model.
# The panel itself is built once with every row and never has to be re-run for a design choice (lib/reward_paths.R has the same defaults).
DESIGN_MODE       <- "recommended"   # "recommended": an option set to "data" is chosen FROM THE DATA (DESIGN_RECOMMENDATION.md) | "manual"
TREATMENT_TIMING  <- "fund"          # "fund" (the fund workbook: each sub-watershed's first treated season) | "registry" (sites.csv) | "fixed"
TREATMENT_YEAR    <- 2022            # "fixed" timing, and the fall-back for a sub-watershed the fund file / registry does not date
FUND_START_RULE   <- "backcast"      # "backcast" | "share" | "file_start"
DOSE_VARIABLE     <- "dose_intensity_per_ha"   # | "dose_amount_sws" | "dose_share_of_target"
CONTROL_RINGS     <- "data"          # "data" | 1:5 | 1:3 | c(2, 4)   (the TREATMENT AREA is buff_km 0)
PRE_YEARS         <- "data"          # "data" | NA (every year before the start) | a number of years | 2015 (a calendar year = the FIRST pre year)
POST_YEARS        <- "data"          # "data" | NA (every year from the start) | a number of years | 2025 (a calendar year = the LAST post year)
SEASONS           <- "all"           # "all" | "seasonal" | "yearly" | "Rabi" | "Kharif+Rabi"
EXCLUDE_TRANSITION_YEAR <- FALSE     # TRUE = the first treated year of each series leaves the sample
UNIT_FE           <- "pixel_season"  # | "pixel"
COHORT_OFFSET     <- 0L
POOLED_FE         <- "site_period"   # several sub-watersheds: sub-watershed x year x season effects | "period"
OVERLAP_ROWS      <- "drop"          # | "keep"
FRAGMENT_RULE     <- "drop"          # | "keep"  (fragments of other sub-watersheds inside the exports, minor sub-watersheds of the panel)
COVARIATES        <- c("Rain", "Tmax", "Tmean", "Tmin")
# v20.59 -- YOUR RULE: the sub-watershed of every row is where its latitude / longitude falls in the shapefile (the core or a control ring);
#   the file's id only labels. ONE sub-watershed processed = the one holding the majority of the rows (SUB_WATERSHEDS = "data": every
#   sub-watershed with >= FRAGMENT_MIN_SHARE of the largest one's own rows; the rest are fragments); SEVERAL = every row in its own sub-watershed.
SUB_WATERSHEDS      <- "data"        # "data" | "all" | 11 | c(7, 11)
SITE_GEOMETRY_CHECK <- TRUE          # every row located in the shapefile: confirmed / corrected / assigned | FALSE = trust the id in the file
BUFF_FROM_GEOMETRY  <- FALSE         # TRUE = buff_km always from the polygon ring | FALSE = only where the sub-watershed was corrected / assigned
PIXEL_ONE_SITE      <- TRUE          # v20.59 -- YOUR RULE: one sub-watershed and one ring per pixel in the whole panel (the polygon that holds the point decides;
                                     #   confirmed: panel_pixel_consistency_R.csv) | FALSE = the v20.58 rule (a point in two zones kept once per sub-watershed)
# v20.59 -- YOUR RULE: the panel KEEPS every row and every value. Fill values (a year-season with ONE value for every pixel) and gap-filled
# rows (GapFilled = 1 / Coverage 0) stay IN the panel; whether a MODEL estimates on them is decided by the two options below -- the DEFAULTS
# here (the design report and the screen table of this notebook use them) and, for each model, ITS OWN setting in its notebook (as Python's
# P00_Settings and every model's CELL 1). Keeping a fill year-season is not neutral: in it the treated-control difference is exactly 0,
# which dilutes the pre (or post) gap the DiD compares -- the screen's report says so when "keep" is in force.
OUTCOME_SCREEN    <- "drop"   # "drop" = a year-season constant across pixels (a fill value) or with collapsed coverage leaves the model (evidence:
                              #   OUTCOME_SCREEN_<outcome>.csv) | "keep" = reported and KEPT (results tagged _screenKept) | "off" = no screen
EXCLUDE_GAPFILLED <- TRUE     # TRUE = rows the exporter filled from history (GapFilled = 1 / Coverage 0) are not observations | FALSE keeps them
DESIGN_SOURCE     <- "panel"  # v20.59 -- YOUR RULE: the PANEL's treat / control / pre / post / did (the exports' Treat flag, PERIOD_RULE) are what every
                              #   model estimates on by default (results tagged _panelDesign; a notebook's CELL 1 overrides it) | "model" = design-based
# ================================================================================================================================
# OPTIONAL CUSTOMISATIONS (1 Oct, your rule) -- every one has a USE_ switch. FALSE = NOT applied at all, whatever the value beside it
# says (the standard design above runs as it is); TRUE = applied exactly as set. All are FALSE by default. DESIGN IN EFFECT shows each
# one as "not used" or with the value in force; a rule in force also tags the results folder (the tag is named beside each option).
# HERE: the panel-level DEFAULTS of these switches and values (a model notebook's own SECTION B / C wins for that model).
# --------------------------------------------------------------------------------------------------------------------------------
# SECTION B -- THE CONTROL GROUP CHOSEN ON THE PRE PERIOD (your request of 30 Sep): which buffers / clusters are the controls for THIS
# outcome, decided on the pre period only and then FIXED across the whole panel (the same control pixels in every year and season)
# --------------------------------------------------------------------------------------------------------------------------------
USE_CONTROL_SELECTION <- FALSE    # FALSE = every ring of CONTROL_RINGS is the control group (as above) | TRUE = CONTROL_SELECTION below chooses it
CONTROL_SELECTION <- "pre_rings"  #   "pre_rings": the CONTROL_SELECT_K (1 or 2) buffers whose PRE-period series is closest to the treatment area's -- your
                                  #   "most close 1 or 2 buffers" | "pre_blocks": control CLUSTERS (~1 km blocks of pixels) from ANY part of the buffers, the
                                  #   closest first, until CONTROL_SELECT_RATIO x the treated pixels -- your "clusters from any part of the buffers".
                                  #   Per outcome; the decision uses the PRE period only (a post- or outcome-based rule is refused); made once and applied
                                  #   to every year and season. Evidence: CONTROL_SELECTION_<outcome>_R.csv beside the results. Tag _ctrlPre2r / _ctrlPreBlk3x
CONTROL_SELECT_K  <- 2L           #   pre_rings: how many buffers -- 1 or 2 (up to 5)
CONTROL_SELECT_RATIO <- 3         #   pre_blocks: control pixels >= this x the treated pixels
CONTROL_SELECT_ON <- "trend"      #   what "closest" means: "trend" = the demeaned pre series' distance (what the parallel-trends assumption asks; recommended)
                                  #   | "level" = the nearest pre-period MEAN (your "mean of the treatment area vs the buffer's mean") | "rmse" = the RMSE of the
                                  #   cell-wise pre differences | "both" = trend + level.  Tag suffix: none / L / R / B
USE_SAME_PIXELS   <- FALSE        # FALSE = a pixel may contribute to one side only (the v20.58 sample) | TRUE = the treated and control groups are the SAME
SAME_PIXELS       <- "pre_post"   #   pixels across the panel: "pre_post" = every pixel observed in pre AND post, else it leaves (tag _pixPP) | "all" = in
                                  #   every year-season of the sample (a balanced pixel set; tag _pixAll). The sample-integrity line confirms it at every run
# --------------------------------------------------------------------------------------------------------------------------------
# SECTION C -- PANEL-PREPARATION ENHANCEMENTS (the three specifications of 30 Sep); each with its own switch
# --------------------------------------------------------------------------------------------------------------------------------
USE_DONUT         <- FALSE        # FALSE = ring 1 is a control like the others | TRUE = DONUT_RINGS leave the control pool -- the spillover buffer next to the core
DONUT_RINGS       <- 1L           #   the ring(s) left out, e.g. 1L or c(1L, 2L); applied before any control choice. Tag _donut1
USE_LANDUSE_MASK  <- FALSE        # FALSE = every land-use class | TRUE = only pixels whose PRE-period (baseline) LandUse class is in LANDUSE_KEEP stay. Tag _lu2
LANDUSE_KEEP      <- 2L           #   your exporter's class code(s) for agriculture (a pixel's class is read on the pre period, so the works cannot move it)
USE_BASELINE_NDVI_MASK <- FALSE   # FALSE = no mask | TRUE = only pixels whose PRE-period mean NDVI exceeds BASELINE_NDVI_MIN stay (an agricultural mask). Tag _ndviPre0.25
BASELINE_NDVI_MIN <- 0.25         #   the threshold (an NDVI value)
USE_COVERAGE_THRESHOLD <- FALSE   # FALSE = the standard screen (a year-season below 5 % of the typical coverage leaves) | TRUE = below MIN_PIXEL_COVERAGE_PCT. Tag _cov70
MIN_PIXEL_COVERAGE_PCT <- 0.70    #   the share of the typical treated / control coverage a year-season must reach (your log: 2023 Zaid, 2025 Kharif / Zaid collapsed)
USE_DROP_SINGLETONS <- FALSE      # FALSE = series seen once stay | TRUE = they leave before the demeaning (the pre-flight). Tag _noSingle
USE_PRECISION_TOLERANCE <- FALSE  # FALSE = the no-data zero is an EXACT 0 (the v20.58 rule) | TRUE = |value| <= PRECISION_TOLERANCE is the no-data zero and a
PRECISION_TOLERANCE <- 1e-6       #   year-season is "constant across pixels" within it -- indices in [-1, 1] are never compared with exact equality
# The Rabi-only run of the specifications is SEASONS <- "Rabi" above; the ~1 km block clusters are CLUSTER <- "block" above.
# ================================================================================================================================
CLUSTER           <- "auto"   # "auto" (the sub-watersheds; fewer than 6 -> the years) | "block" (~1 km spatial blocks: many clusters, spatial correlation absorbed)
cat("design defaults (a model notebook overrides each):", DESIGN_MODE, "| timing", TREATMENT_TIMING, "| period rule (R_P00)", PERIOD_RULE, "| outcome screen", OUTCOME_SCREEN, "| design source", DESIGN_SOURCE, "| control selection", CONTROL_SELECTION, "| same pixels", SAME_PIXELS, "| donut", paste(DONUT_RINGS, collapse = ","), "| land use", paste(LANDUSE_KEEP, collapse = ","), "| cluster", CLUSTER, "| gap-filled rows", if (isTRUE(EXCLUDE_GAPFILLED)) "left out" else "kept", "| rings", paste(CONTROL_RINGS, collapse = ","),
    "| seasons", paste(SEASONS, collapse = ","), "| fragments", FRAGMENT_RULE, "| overlap", OVERLAP_ROWS, "| pooled FE", POOLED_FE, "\n")
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiZGVzaWduIGRlZmF1bHRzIChhIG1vZGVsIG5vdGVib29rIG92ZXJyaWRlcyBlYWNoKTogcmVjb21tZW5kZWQgfCB0aW1pbmcgZnVuZCB8IHBlcmlvZCBydWxlIChSX1AwMCkgdHJlYXQgfCBvdXRjb21lIHNjcmVlbiBkcm9wIHwgZGVzaWduIHNvdXJjZSBwYW5lbCB8IGNvbnRyb2wgc2VsZWN0aW9uIHByZV9yaW5ncyB8IHNhbWUgcGl4ZWxzIHByZV9wb3N0IHwgZG9udXQgMSB8IGxhbmQgdXNlIDIgfCBjbHVzdGVyIGF1dG8gfCBnYXAtZmlsbGVkIHJvd3MgbGVmdCBvdXQgfCByaW5ncyBkYXRhIHwgc2Vhc29ucyBhbGwgfCBmcmFnbWVudHMgZHJvcCB8IG92ZXJsYXAgZHJvcCB8IHBvb2xlZCBGRSBzaXRlX3BlcmlvZCBcbiJ9 -->

```
design defaults (a model notebook overrides each): recommended | timing fund | period rule (R_P00) treat | outcome screen drop | design source panel | control selection pre_rings | same pixels pre_post | donut 1 | land use 2 | cluster auto | gap-filled rows left out | rings data | seasons all | fragments drop | overlap drop | pooled FE site_period 
```



<!-- rnb-output-end -->

<!-- rnb-chunk-end -->


<!-- rnb-text-begin -->


**Build the panel** -- exports, harmonised columns, masked zeros as missing, the sub-watershed from the shapefile (confirmed or corrected), every row coded for the fragment rule per export file, shifted grids linked, repeated rows dropped whole (the newer export's row kept as it is -- v20.58; DEDUP_FILL_FROM_DUPLICATES in lib/reward_prep.R), the BM means; the fund workbook's timing and dose tables (results/FUND) for you to read -- the models apply them when they run.


<!-- rnb-text-end -->


<!-- rnb-chunk-begin -->


<!-- rnb-source-begin eyJkYXRhIjoicGFuZWwgPC0gcnVuX3ByZXAoKSJ9 -->

```r
panel <- run_prep()
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW09LXSAgICAgIDgwIGV4cG9ydCBmaWxlcyB1bmRlciAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMgKDgwIC5jc3YpXG5bSU5GT10gICAgcmVhZGluZyA4MCBmaWxlcyAoNCB0aHJlYWRzKVxuW09LXSAgICAgIGlucHV0IGZpbGVzIENPTkZJUk1FRCAoODAgZmlsZXMsIDcsNTYwIHJvd3MpOiBUcmVhdCBjb2x1bW4gMSA9IHBvc3Qgb24gMywwMjQgcm93cywgMCA9IHByZSBvbiA0LDUzNiByb3dzOyBidWZmX2ttIDAgPSB0aGUgdHJlYXRtZW50IGFyZWEgb24gMSw0ODAgcm93cywgMS01ID0gdGhlIGNvbnRyb2wgcmluZ3Mgb24gNiwwODAgcm93czsgUEVSSU9EX1JVTEUgPSAndHJlYXQnOiBwb3N0IC8gcHJlID0gdGhlIGV4cG9ydHMnIFRyZWF0IGNvbHVtbiAoMSA9IHBvc3QsIDAgPSBwcmUpIC0+IGlucHV0X2Rlc2lnbl9hdWRpdF9SLmNzdlxuW1dBUk5JTkddIDgwIGZpbGUocykgY2FycnkgTk8gVHJlYXQgY29sdW1uOiAxID0gcG9zdCAvIDAgPSBwcmUgd2FzIGRlcml2ZWQgZnJvbSB0aGUgcnVsZSBZZWFyID49IDIwMjIgZm9yIHRoZW0gKGlucHV0X2Rlc2lnbl9hdWRpdF9SLmNzdilcbltPS10gICAgICA3LDU2MCByb3dzIHJlYWQgZnJvbSA4MCBmaWxlc1xuW0lORk9dICAgIHN1Yi13YXRlcnNoZWQgbmFtZWQgYnkgdGhlIGV4cG9ydCBmaWxlcyAoPj0gODAgJSBydWxlKTogQXJ0YWwgNDAgZmlsZShzKSB8IENoaXR0aGFyYWdpIDQwIGZpbGUocylcbltJTkZPXSAgICBvdmVybGF5aW5nIDE4OSBwaXhlbCBsb2NhdGlvbnMgb24gdGhlIDIwIHN1Yi13YXRlcnNoZWRzIHggcmluZ3NcbltJTkZPXSAgICBvdmVybGF5OiBjb25maXJtZWQgMTgzIHwgY29ycmVjdGVkICAgNlxuW0lORk9dICAgIHdvcmtpbmcgc3ViLXdhdGVyc2hlZCBydWxlICh2MjAuNTkpOiBldmVyeSByb3cgYmVsb25ncyB0byB0aGUgc3ViLXdhdGVyc2hlZCBpdHMgbGF0aXR1ZGUgLyBsb25naXR1ZGUgZmFsbHMgaW4gKGNvcmUgb3IgY29udHJvbCByaW5nKTsgdGhlIGxhcmdlc3QgaGVyZSBpcyBBcnRhbCB3aXRoIDcsMjAwIHJvd3MgKDk1LjIgJSkgLS0gYSBzaW5nbGUtc3ViLXdhdGVyc2hlZCBydW4gcHJvY2Vzc2VzIGl0IGFuZCBjb2RlcyB0aGUgcmVzdCBhcyBmcmFnbWVudHMgKFNVQl9XQVRFUlNIRURTID0gXCJkYXRhXCIsIEZSQUdNRU5UX1JVTEUpOyBhIHBvb2xlZCBydW4ga2VlcHMgZXZlcnkgcm93IGluIGl0cyBvd24gc3ViLXdhdGVyc2hlZFxuW0lORk9dICAgIGZyYWdtZW50cyBvZiBvdGhlciBzdWItd2F0ZXJzaGVkcyBpbnNpZGUgdGhlIGV4cG9ydCBmaWxlczogMjQwIHJvd3MgaW4gNDAgZmlsZShzKSAoY29kZWQ7IEZSQUdNRU5UX1JVTEUgaW4gdGhlIG1vZGVscyBkcm9wcyB0aGVtKSAtPiBzaXRlX3RhZ2dpbmdfYnlfZmlsZS5jc3ZcbltPS10gICAgICBuZWFyLWR1cGxpY2F0ZSBwaXhlbHM6IDE4OSBwaXhlbHMsIG5vIHBhaXIgb3ZlcmxhcHMgPj0gNjUgJVxuW0lORk9dICAgIGR1cGxpY2F0ZXMgY2hlY2tlZCBvbiB0aGUgcmVzdWx0ICgwIHMpXG5bT0tdICAgICAgcGl4ZWwgY29uc2lzdGVuY3kgQ09ORklSTUVEOiAxODkgcGl4ZWxzLCBlYWNoIHdpdGggT05FIHN1Yi13YXRlcnNoZWQgYW5kIE9ORSByaW5nIGluIGV2ZXJ5IHllYXIgYW5kIHNlYXNvbiwgZXZlcnkgKHBpeGVsLCB5ZWFyLCBzZWFzb24pIG9uY2VcbltJTkZPXSAgICBwaXhlbCBjb25zaXN0ZW5jeSBjaGVja2VkICgwIHMpXG5bT0tdICAgICAgbmVhci1kdXBsaWNhdGUgcGl4ZWxzIENPTkZJUk1FRDogMCBwaXhlbChzKSByZW1haW4gd2hvc2UgZm9vdHByaW50cyBvdmVybGFwID49IDY1ICUgYW1vbmcgMTg5IHBpeGVsc1xuW0lORk9dICAgIG5lYXItZHVwbGljYXRlIHBpeGVscyBjaGVja2VkIG9uIHRoZSByZXN1bHQgKDAgcylcbltPS10gICAgICBkdXBsaWNhdGVzIENPTkZJUk1FRCByZW1vdmVkOiA3LDU2MCByb3dzLCBldmVyeSAoc3ViLXdhdGVyc2hlZCwgcGl4ZWwsIHllYXIsIHNlYXNvbikgZXhhY3RseSBvbmNlXG5bT0tdICAgICAgRGlEIGRlc2lnbiBjb2x1bW5zIGluIHRoZSBwYW5lbDogdHJlYXQgKGJ1ZmZlciAwID0gdGhlIHRyZWF0bWVudCBhcmVhKSAvIGNvbnRyb2wgKHJpbmdzIDEtNSk7IHBvc3QgPSB0aGUgZXhwb3J0cycgVHJlYXQgY29sdW1uICgxID0gcG9zdCwgMCA9IHByZTsgUEVSSU9EX1JVTEUgPSAndHJlYXQnKSBvbiA3LDU2MCByb3dzOyBwcmUgPSAxIC0gcG9zdDsgZGlkID0gdHJlYXQgeCBwb3N0IC0+IHBhbmVsX2Rlc2lnbl9jaGVja19SLmNzdlxuW0lORk9dICAgIHJvd3MgcGVyIGdyb3VwIHggcGVyaW9kOiB0cmVhdG1lbnQgKGJ1ZmZlciAwKSBwcmUgICA4ODggfCBjb250cm9sIChidWZmZXIgMS01KSBwcmUgMyw2NDggfCB0cmVhdG1lbnQgKGJ1ZmZlciAwKSBwb3N0ICAgNTkyIHwgY29udHJvbCAoYnVmZmVyIDEtNSkgcG9zdCAyLDQzMlxuW0lORk9dICAgIGRlc2lnbiBjb2x1bW5zIGFkZGVkICgwIHMpXG4ifQ== -->

```
[OK]      80 export files under /tmp/RtmpO0K6MW/reward_all_tests/E_options (80 .csv)
[INFO]    reading 80 files (4 threads)
[OK]      input files CONFIRMED (80 files, 7,560 rows): Treat column 1 = post on 3,024 rows, 0 = pre on 4,536 rows; buff_km 0 = the treatment area on 1,480 rows, 1-5 = the control rings on 6,080 rows; PERIOD_RULE = 'treat': post / pre = the exports' Treat column (1 = post, 0 = pre) -> input_design_audit_R.csv
[WARNING] 80 file(s) carry NO Treat column: 1 = post / 0 = pre was derived from the rule Year >= 2022 for them (input_design_audit_R.csv)
[OK]      7,560 rows read from 80 files
[INFO]    sub-watershed named by the export files (>= 80 % rule): Artal 40 file(s) | Chittharagi 40 file(s)
[INFO]    overlaying 189 pixel locations on the 20 sub-watersheds x rings
[INFO]    overlay: confirmed 183 | corrected   6
[INFO]    working sub-watershed rule (v20.59): every row belongs to the sub-watershed its latitude / longitude falls in (core or control ring); the largest here is Artal with 7,200 rows (95.2 %) -- a single-sub-watershed run processes it and codes the rest as fragments (SUB_WATERSHEDS = "data", FRAGMENT_RULE); a pooled run keeps every row in its own sub-watershed
[INFO]    fragments of other sub-watersheds inside the export files: 240 rows in 40 file(s) (coded; FRAGMENT_RULE in the models drops them) -> site_tagging_by_file.csv
[OK]      near-duplicate pixels: 189 pixels, no pair overlaps >= 65 %
[INFO]    duplicates checked on the result (0 s)
[OK]      pixel consistency CONFIRMED: 189 pixels, each with ONE sub-watershed and ONE ring in every year and season, every (pixel, year, season) once
[INFO]    pixel consistency checked (0 s)
[OK]      near-duplicate pixels CONFIRMED: 0 pixel(s) remain whose footprints overlap >= 65 % among 189 pixels
[INFO]    near-duplicate pixels checked on the result (0 s)
[OK]      duplicates CONFIRMED removed: 7,560 rows, every (sub-watershed, pixel, year, season) exactly once
[OK]      DiD design columns in the panel: treat (buffer 0 = the treatment area) / control (rings 1-5); post = the exports' Treat column (1 = post, 0 = pre; PERIOD_RULE = 'treat') on 7,560 rows; pre = 1 - post; did = treat x post -> panel_design_check_R.csv
[INFO]    rows per group x period: treatment (buffer 0) pre   888 | control (buffer 1-5) pre 3,648 | treatment (buffer 0) post   592 | control (buffer 1-5) post 2,432
[INFO]    design columns added (0 s)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiJ9 -->

```
Warning in min(z): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoeik6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4ifQ== -->

```
Warning in max(z): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW09LXSAgICAgIHBpeGVsIHZhcmlhdGlvbiBDT05GSVJNRUQgaW4gZXZlcnkgb3V0Y29tZSB4IHllYXItc2Vhc29uIGNlbGwgKDQwIGNlbGxzLCBubyBmaWxsIHZhbHVlKSAtPiBwYW5lbF92YXJpYXRpb25fYnlfYmxvY2suY3N2XG5bSU5GT10gICAgcGl4ZWwtdmFyaWF0aW9uIHJlcG9ydCB3cml0dGVuICgwIHMpXG5bT0tdICAgICAgdGhlIHBhbmVsIEtFRVBTIGV2ZXJ5IHJvdyBhbmQgdmFsdWU6IDAgb3V0Y29tZSB4IHllYXItc2Vhc29uIGZpbGwgY2VsbChzKSBhbmQgNDUgZ2FwLWZpbGxlZCByb3cocykgKEdhcEZpbGxlZCA9IDEpIGFyZSBJTiB0aGUgcGFuZWwgLS0gZWFjaCBtb2RlbCBkZWNpZGVzIHdpdGggT1VUQ09NRV9TQ1JFRU4gKFwiZHJvcFwiIHwgXCJrZWVwXCIgfCBcIm9mZlwiKSBhbmQgRVhDTFVERV9HQVBGSUxMRUQgKFRSVUUgfCBGQUxTRSkgaW4gaXRzIG93biBub3RlYm9vazsgdGhlIGRlZmF1bHRzIG9mIHRoaXMgcnVuOiBPVVRDT01FX1NDUkVFTiBcImRyb3BcIiwgRVhDTFVERV9HQVBGSUxMRUQgVFJVRVxuW0lORk9dICAgIDIgc3ViLXdhdGVyc2hlZChzKSBpbiB0aGUgcGFuZWwgYWZ0ZXIgdGhlIGZyYWdtZW50IHJ1bGUgKHRoZSBwb29sZWQgZGVzaWduLCBQT09MRURfRkUgYW5kIHRoZSBjbHVzdGVycyBhcmUgc2V0IGJ5IGVhY2ggbW9kZWwpXG5bT0tdICAgICAgZnVuZCBmaWxlIChmbGF0IHRhYmxlKTogMSBzdWItd2F0ZXJzaGVkcyBtYXRjaGVkIGJ5IHRoZSA4MCAlIG5hbWUgcnVsZSwgMjIgbW9udGhzIDIwMjQtMTAgLT4gMjAyNi0wN1xuW09LXSAgICAgIGZ1bmQgdGltaW5nIGFuZCBkb3NlIC0+IEZVTkRfVElNSU5HLmNzdiwgRlVORF9TRUFTT05fRE9TRS5jc3YgaW4gL3RtcC9SdG1wTzBLNk1XL3Jld2FyZF9hbGxfdGVzdHMvRV9vcHRpb25zL291dHB1dC9yZXN1bHRzL0ZVTkQgKHN0YXJ0IHJ1bGUgYmFja2Nhc3QpXG4gICBzaXRlX2lkIHN3c19uYW1lICBhcmVhX2hhIGZpcnN0X21vbnRoIGFtb3VudF9maXJzdF9tb250aCBiYWNrY2FzdF9zdGFydFxuICAgICA8aW50PiAgIDxjaGFyPiAgICA8bnVtPiAgICAgIDxjaGFyPiAgICAgICAgICAgICAgPG51bT4gICAgICAgICA8Y2hhcj5cbjE6ICAgICAgIDEgICAgQXJ0YWwgNDYzMi4zMzggICAgIDIwMjQtMTAgICAgICAgICAgICAgICAgIDQwICAgICAgICAyMDI0LTA3XG4gICBmaXJzdF90cmVhdGVkX2xhYmVsIGNvaG9ydF9hbm51YWxcbiAgICAgICAgICAgICAgICA8Y2hhcj4gICAgICAgICA8aW50PlxuMTogICAgICAgICAgIFJhYmkgMjAyNCAgICAgICAgICAyMDI1XG5bT0tdICAgICAgQk0gc3ViLXdhdGVyc2hlZCBtZWFucyAodGhlIG1lYW4gb2YgZWFjaCBzdWItd2F0ZXJzaGVkJ3Mgc2l0ZXMpOiAxOSBwcm9ncmFtbWUgKyAxMyBjb250cm9sIHN1Yi13YXRlcnNoZWRzLCB2YXJpYWJsZXMgZ3dfZGVwdGhfbSwgbGFpLCBzb2lsX3RlbXBfYywgc3NtX3BjdCwgdGRyX3Jvb3R6b25lX2VjX2RzX20sIHRkcl9yb290em9uZV9wY3QgLS0gL2hvbWUvdXNlci9UblQvUldEUl92MjAuNTkvZGF0YS9ncm91bmQvYm1fc3dzX3NlYXNvbl9tZWFucy5jc3ZcbltPS10gICAgICBwYW5lbDogNyw1NjAgcm93cywgMTg5IHBpeGVscywgMyBzdWItd2F0ZXJzaGVkKHMpLCA0MCB5ZWFyLXNlYXNvbnMgKHBpeGVscyBwZXIgeWVhci1zZWFzb24gMTg5LTE4OTogYW4gdW5iYWxhbmNlZCBwYW5lbCBpcyBrZXB0IGFzIGl0IGlzOyBhIG1pc3NpbmcgcGl4ZWwtcGVyaW9kIGxlYXZlcyBvbmx5IHRoZSBlc3RpbWF0aW9ucyB0aGF0IG5lZWQgaXQpIC0+IC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvZGlkX3BhbmVsX2Z1bGwucGFycXVldCAoMC4wIG1pbilcbiJ9 -->

```
[OK]      pixel variation CONFIRMED in every outcome x year-season cell (40 cells, no fill value) -> panel_variation_by_block.csv
[INFO]    pixel-variation report written (0 s)
[OK]      the panel KEEPS every row and value: 0 outcome x year-season fill cell(s) and 45 gap-filled row(s) (GapFilled = 1) are IN the panel -- each model decides with OUTCOME_SCREEN ("drop" | "keep" | "off") and EXCLUDE_GAPFILLED (TRUE | FALSE) in its own notebook; the defaults of this run: OUTCOME_SCREEN "drop", EXCLUDE_GAPFILLED TRUE
[INFO]    2 sub-watershed(s) in the panel after the fragment rule (the pooled design, POOLED_FE and the clusters are set by each model)
[OK]      fund file (flat table): 1 sub-watersheds matched by the 80 % name rule, 22 months 2024-10 -> 2026-07
[OK]      fund timing and dose -> FUND_TIMING.csv, FUND_SEASON_DOSE.csv in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/FUND (start rule backcast)
   site_id sws_name  area_ha first_month amount_first_month backcast_start
     <int>   <char>    <num>      <char>              <num>         <char>
1:       1    Artal 4632.338     2024-10                 40        2024-07
   first_treated_label cohort_annual
                <char>         <int>
1:           Rabi 2024          2025
[OK]      BM sub-watershed means (the mean of each sub-watershed's sites): 19 programme + 13 control sub-watersheds, variables gw_depth_m, lai, soil_temp_c, ssm_pct, tdr_rootzone_ec_ds_m, tdr_rootzone_pct -- /home/user/TnT/RWDR_v20.59/data/ground/bm_sws_season_means.csv
[OK]      panel: 7,560 rows, 189 pixels, 3 sub-watershed(s), 40 year-seasons (pixels per year-season 189-189: an unbalanced panel is kept as it is; a missing pixel-period leaves only the estimations that need it) -> /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/did_panel_full.parquet (0.0 min)
```



<!-- rnb-output-end -->

<!-- rnb-chunk-end -->


<!-- rnb-text-begin -->


**The design the DEFAULTS give** (export breaks, fill years, spillover into inner rings; the fund timing per sub-watershed) -- what a model uses when its settings are left as in lib/reward_paths.R. Each model applies its own settings when it runs.


<!-- rnb-text-end -->


<!-- rnb-chunk-begin -->


<!-- rnb-source-begin eyJkYXRhIjoiZGVzaWduIDwtIHByZXBhcmVfZGVzaWduKCk7IHN0cihkZXNpZ25bc2V0ZGlmZihuYW1lcyhkZXNpZ24pLCBjKFwiY2hvaWNlc1wiLCBcIm5vdGVzXCIpKV0pIn0= -->

```r
design <- prepare_design(); str(design[setdiff(names(design), c("choices", "notes"))])
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIGxvY2F0aW9uIHRhYmxlIG9mIHRoaXMgcGFuZWwgKG9uY2U7IDAgcyk6IDAgcm93cyBvdXRzaWRlIGV2ZXJ5IHBvbHlnb24sIDAgcGl4ZWwocykgd2hvc2UgcmluZyBkaWZmZXJzIGJldHdlZW4gcm93cywgMCBuZWFyLWR1cGxpY2F0ZSBwaXhlbCBwYWlyKHMpID49IDY1ICUgb2YgMTg5IHBpeGVsc1xuW09LXSAgICAgIGZ1bmQgZmlsZSAoZmxhdCB0YWJsZSk6IDEgc3ViLXdhdGVyc2hlZHMgbWF0Y2hlZCBieSB0aGUgODAgJSBuYW1lIHJ1bGUsIDIyIG1vbnRocyAyMDI0LTEwIC0+IDIwMjYtMDdcbltJTkZPXSAgICBkZXNpZ24gZnJvbSB0aGUgZGF0YTogcHJlIDIwMTYsMjAxNywyMDE4LDIwMTksMjAyMCwyMDIxLDIwMjIsMjAyMywgcG9zdCAyMDI0LDIwMjUsIGNvbnRyb2wgcmluZ3MgMSwyLDMsNCw1LCBzZWFzb25zIGFsbFxuW0lORk9dICAgIERFU0lHTiBJTiBFRkZFQ1QgKHYyMC41OTogZXZlcnkgb3B0aW9uIGlzIGFwcGxpZWQgaGVyZSwgYXQgdGhlIG1vZGVsIHN0YWdlIC0tIHRoZSBwYW5lbCBpcyBub3QgcmVidWlsdCk6XG4gIERFU0lHTl9NT0RFICAgICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IHJlY29tbWVuZGVkICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IHJlY29tbWVuZGVkICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nXG4gIFRSRUFUTUVOVF9USU1JTkcgICAgICAgICAgICB5b3VyIHNldHRpbmc6IGZ1bmQgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IGZ1bmQ6IGZpcnN0IHRyZWF0ZWQgc2Vhc29uIHBlciBzdWItd2F0ZXJzaGVkICAgICAgPC0gdGhlIGZ1bmQgd29ya2Jvb2sgL3RtcC9SdG1wTzBLNk1XL3Jld2FyZF9hbGxfdGVzdHMvRV9mdW5kLnhsc3hcbiAgVFJFQVRNRU5UX1lFQVIgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogMjAyMiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogMjAyNCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB0aGUgZWFybGllc3QgZmlyc3QgdHJlYXRlZCB5ZWFyIG9mIHRoZSAxIHN1Yi13YXRlcnNoZWQocykgKHRoZSBiYXNlIG9mIFBSRV9ZRUFSUyAvIFBPU1RfWUVcbiAgICBzdGFydCBvZiBzdWItd2F0ZXJzaGVkIDEgIHlvdXIgc2V0dGluZzogKGZyb20gVFJFQVRNRU5UX1RJTUlORyA9IGZ1bmQpICAgICAgVVNFRDogUmFiaSAyMDI0ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSBmdW5kIGZpbGU6IHN0YXJ0IDIwMjQtMDcgKGJhY2tjYXN0OyBiYWNrLWNhc3QgYXQgMTAgcGVyIG1vbnRoIG92ZXIgdGhlIGZpbGUncyBmaXJzdCAxMiBtb25cbiAgQ09OVFJPTF9SSU5HUyAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogZGF0YSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogMSwyLDMsNCw1ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB0aGUgZGF0YSAoREVTSUdOX1JFQ09NTUVOREFUSU9OLm1kLCBORFZJLCBpbXBsZW1lbnRhdGlvbiB5ZWFyIDIwMjQpXG4gIFBSRV9ZRUFSUyAgICAgICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IGRhdGEgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IGZyb20gMjAxNiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gdGhlIGRhdGEgKERFU0lHTl9SRUNPTU1FTkRBVElPTi5tZCwgTkRWSSwgaW1wbGVtZW50YXRpb24geWVhciAyMDI0KVxuICBQT1NUX1lFQVJTICAgICAgICAgICAgICAgICAgeW91ciBzZXR0aW5nOiBkYXRhICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBVU0VEOiB0byAyMDI1ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIDwtIHRoZSBkYXRhIChERVNJR05fUkVDT01NRU5EQVRJT04ubWQsIE5EVkksIGltcGxlbWVudGF0aW9uIHllYXIgMjAyNClcbiAgU0VBU09OUyAgICAgICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogYWxsICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogYWxsICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmdcbiAgRVhDTFVERV9UUkFOU0lUSU9OX1lFQVIgICAgIHlvdXIgc2V0dGluZzogRkFMU0UgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogRkFMU0UgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmdcbiAgVU5JVF9GRSAgICAgICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogcGl4ZWxfc2Vhc29uICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogcGl4ZWxfc2Vhc29uICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmdcbiAgQ09IT1JUX09GRlNFVCAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogMCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogMCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmdcbiAgU1VCX1dBVEVSU0hFRFMgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogZGF0YSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogMSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSBkYXRhOiBldmVyeSBzdWItd2F0ZXJzaGVkIHdpdGggPj0gNSAlIG9mIHRoZSBsYXJnZXN0IG9uZSdzIG93biByb3dzIC0+IEFydGFsICgxKTsgbm90IHByb2NcbiAgRlJBR01FTlRfUlVMRSAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogZHJvcCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogZHJvcCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmc6IHJvd3Mgb2Ygc3ViLXdhdGVyc2hlZHMgTk9UIHByb2Nlc3NlZCAzNjAsIHJvd3Mgb3V0c2lkZSBldmVyeSBwb2x5Z29uIDAgLS0gbGVcbiAgT1ZFUkxBUF9ST1dTICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogZHJvcCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogZHJvcCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmc6IDAgcGl4ZWwocykgd2hvc2UgcmluZyBkaWZmZXJzIGJldHdlZW4gcm93cywgMCBuZWFyLWR1cGxpY2F0ZSBwYWlyKHMpLCBwaXhlbHNcbiAgUE9PTEVEX0ZFICAgICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogc2l0ZV9wZXJpb2QgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogc2l0ZV9wZXJpb2QgKG9uZSBzdWItd2F0ZXJzaGVkOiB0aGUgc2FtZSBhcyAncGVyICA8LSB5b3VyIHNldHRpbmdcbiAgRE9TRV9WQVJJQUJMRSAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogZG9zZV9pbnRlbnNpdHlfcGVyX2hhICAgICAgICAgICAgICAgVVNFRDogZG9zZV9pbnRlbnNpdHlfcGVyX2hhICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmcgKGZ1bmQgZmlsZTsgY29udHJvbHMgYW5kIHVudHJlYXRlZCBwZXJpb2RzIDApXG4gIEZVTkRfU1RBUlRfUlVMRSAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IGJhY2tjYXN0ICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IGJhY2tjYXN0ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nXG4gIEVYQ0xVREVfR0FQRklMTEVEICAgICAgICAgICB5b3VyIHNldHRpbmc6IFRSVUUgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IFRSVUUgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nXG4gIE9VVENPTUVfU0NSRUVOICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IGRyb3AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IGRyb3AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nIChhIHllYXItc2Vhc29uIGNvbnN0YW50IGFjcm9zcyBwaXhlbHMgLS0gYSBmaWxsIHZhbHVlIC0tIG9yIHdpdGggY29sbGFwc2VkIGNvXG4gIERFU0lHTl9TT1VSQ0UgICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IHBhbmVsICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IHBhbmVsICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nICh0aGUgUEFORUwncyB0cmVhdCAvIGNvbnRyb2wgLyBwcmUgLyBwb3N0IC8gZGlkIC0tIHRoZSBleHBvcnRzJyBUcmVhdCBmbGFnLCBQXG4gIENPTlRST0xfU0VMRUNUSU9OICAgICAgICAgICB5b3VyIHNldHRpbmc6IHByZV9yaW5ncyAtLSBzd2l0Y2ggT0ZGICAgICAgICAgICAgIFVTRUQ6IHJpbmdzICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gVVNFX0NPTlRST0xfU0VMRUNUSU9OID0gRkFMU0UgLT4gTk9UIGFwcGxpZWQ7IHlvdXIgc2V0dGluZyAoZXZlcnkgcmluZyBvZiBDT05UUk9MX1JJTkdTIGlzXG4gIERPTlVUX1JJTkdTICAgICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IDEgLS0gc3dpdGNoIE9GRiAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IG5vbmUgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gVVNFX0RPTlVUID0gRkFMU0UgLT4gTk9UIGFwcGxpZWQ7IHlvdXIgc2V0dGluZyAocmluZ3MgbGVmdCBvdXQgb2YgdGhlIGNvbnRyb2wgcG9vbCAtLSB0aGUgXG4gIExBTkRVU0VfS0VFUCAgICAgICAgICAgICAgICB5b3VyIHNldHRpbmc6IDIgLS0gc3dpdGNoIE9GRiAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IGFsbCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gVVNFX0xBTkRVU0VfTUFTSyA9IEZBTFNFIC0+IE5PVCBhcHBsaWVkOyB5b3VyIHNldHRpbmcgKGEgcGl4ZWwgaXMga2VwdCBieSBpdHMgUFJFLXBlcmlvZCBsXG4gIEJBU0VMSU5FX05EVklfTUlOICAgICAgICAgICB5b3VyIHNldHRpbmc6IDAuMjUgLS0gc3dpdGNoIE9GRiAgICAgICAgICAgICAgICAgIFVTRUQ6IE5BICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gVVNFX0JBU0VMSU5FX05EVklfTUFTSyA9IEZBTFNFIC0+IE5PVCBhcHBsaWVkOyB5b3VyIHNldHRpbmcgKGEgcGl4ZWwncyBwcmUtcGVyaW9kIG1lYW4gTkRWXG4gIE1JTl9QSVhFTF9DT1ZFUkFHRV9QQ1QgICAgICB5b3VyIHNldHRpbmc6IDAuNyAtLSBzd2l0Y2ggT0ZGICAgICAgICAgICAgICAgICAgIFVTRUQ6IDAuMDUgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0gVVNFX0NPVkVSQUdFX1RIUkVTSE9MRCA9IEZBTFNFIC0+IE5PVCBhcHBsaWVkOyB5b3VyIHNldHRpbmcgKGEgeWVhci1zZWFzb24gYmVsb3cgdGhpcyBzaGFyXG4gIFVTRV9EUk9QX1NJTkdMRVRPTlMgICAgICAgICB5b3VyIHNldHRpbmc6IEZBTFNFICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFVTRUQ6IEZBTFNFICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPC0geW91ciBzZXR0aW5nIChUUlVFID0gc2VyaWVzIHNlZW4gb25jZSBsZWF2ZSBiZWZvcmUgdGhlIGRlbWVhbmluZylcbiAgUFJFQ0lTSU9OX1RPTEVSQU5DRSAgICAgICAgIHlvdXIgc2V0dGluZzogMWUtMDYgLS0gc3dpdGNoIE9GRiAgICAgICAgICAgICAgICAgVVNFRDogMCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSBVU0VfUFJFQ0lTSU9OX1RPTEVSQU5DRSA9IEZBTFNFIC0+IE5PVCBhcHBsaWVkOyB5b3VyIHNldHRpbmcgKHx2YWx1ZXwgPD0gdG9sZXJhbmNlIGlzIHRoZSBcbiAgU0FNRV9QSVhFTFMgICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogcHJlX3Bvc3QgLS0gc3dpdGNoIE9GRiAgICAgICAgICAgICAgVVNFRDogb2ZmICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSBVU0VfU0FNRV9QSVhFTFMgPSBGQUxTRSAtPiBOT1QgYXBwbGllZDsgeW91ciBzZXR0aW5nIChhIHBpeGVsIG1heSBjb250cmlidXRlIHRvIG9uZSBzaWRlIG9cbiAgQ0xVU1RFUiAgICAgICAgICAgICAgICAgICAgIHlvdXIgc2V0dGluZzogYXV0byAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVVNFRDogYXV0byAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA8LSB5b3VyIHNldHRpbmcgKHRoZSBzdWItd2F0ZXJzaGVkOyBmZXdlciB0aGFuIDYgc3ViLXdhdGVyc2hlZHMgLT4gdGhlIHllYXJzKVxuICBDT1ZBUklBVEVTICAgICAgICAgICAgICAgICAgeW91ciBzZXR0aW5nOiBSYWluLFRtYXgsVG1lYW4sVG1pbiAgICAgICAgICAgICAgICBVU0VEOiBSYWluLFRtYXgsVG1lYW4sVG1pbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIDwtIHlvdXIgc2V0dGluZ1xuW09LXSAgICAgIGRlc2lnbiB3aXRoIHRoZSBkZWZhdWx0IHNldHRpbmdzIHNhdmVkIC0+IC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvUl9kZXNpZ24uanNvbiB8IGN0cmwxLTVfdHJlYXRGdW5kX2FsbF9wYW5lbERlc2lnbl9jb3ZBbGw0X3lyMjAxNi0yMDI1XG5bT0tdICAgICAgb3V0Y29tZSBpZGVudGl0aWVzOiBubyB0d28gb3V0Y29tZXMgYXJlIHRoZSBzYW1lIHZhcmlhYmxlIGluIHRoaXMgcGFuZWxcbiJ9 -->

```
[INFO]    location table of this panel (once; 0 s): 0 rows outside every polygon, 0 pixel(s) whose ring differs between rows, 0 near-duplicate pixel pair(s) >= 65 % of 189 pixels
[OK]      fund file (flat table): 1 sub-watersheds matched by the 80 % name rule, 22 months 2024-10 -> 2026-07
[INFO]    design from the data: pre 2016,2017,2018,2019,2020,2021,2022,2023, post 2024,2025, control rings 1,2,3,4,5, seasons all
[INFO]    DESIGN IN EFFECT (v20.59: every option is applied here, at the model stage -- the panel is not rebuilt):
  DESIGN_MODE                 your setting: recommended                         USED: recommended                                       <- your setting
  TREATMENT_TIMING            your setting: fund                                USED: fund: first treated season per sub-watershed      <- the fund workbook /tmp/RtmpO0K6MW/reward_all_tests/E_fund.xlsx
  TREATMENT_YEAR              your setting: 2022                                USED: 2024                                              <- the earliest first treated year of the 1 sub-watershed(s) (the base of PRE_YEARS / POST_YE
    start of sub-watershed 1  your setting: (from TREATMENT_TIMING = fund)      USED: Rabi 2024                                         <- fund file: start 2024-07 (backcast; back-cast at 10 per month over the file's first 12 mon
  CONTROL_RINGS               your setting: data                                USED: 1,2,3,4,5                                         <- the data (DESIGN_RECOMMENDATION.md, NDVI, implementation year 2024)
  PRE_YEARS                   your setting: data                                USED: from 2016                                         <- the data (DESIGN_RECOMMENDATION.md, NDVI, implementation year 2024)
  POST_YEARS                  your setting: data                                USED: to 2025                                           <- the data (DESIGN_RECOMMENDATION.md, NDVI, implementation year 2024)
  SEASONS                     your setting: all                                 USED: all                                               <- your setting
  EXCLUDE_TRANSITION_YEAR     your setting: FALSE                               USED: FALSE                                             <- your setting
  UNIT_FE                     your setting: pixel_season                        USED: pixel_season                                      <- your setting
  COHORT_OFFSET               your setting: 0                                   USED: 0                                                 <- your setting
  SUB_WATERSHEDS              your setting: data                                USED: 1                                                 <- data: every sub-watershed with >= 5 % of the largest one's own rows -> Artal (1); not proc
  FRAGMENT_RULE               your setting: drop                                USED: drop                                              <- your setting: rows of sub-watersheds NOT processed 360, rows outside every polygon 0 -- le
  OVERLAP_ROWS                your setting: drop                                USED: drop                                              <- your setting: 0 pixel(s) whose ring differs between rows, 0 near-duplicate pair(s), pixels
  POOLED_FE                   your setting: site_period                         USED: site_period (one sub-watershed: the same as 'per  <- your setting
  DOSE_VARIABLE               your setting: dose_intensity_per_ha               USED: dose_intensity_per_ha                             <- your setting (fund file; controls and untreated periods 0)
  FUND_START_RULE             your setting: backcast                            USED: backcast                                          <- your setting
  EXCLUDE_GAPFILLED           your setting: TRUE                                USED: TRUE                                              <- your setting
  OUTCOME_SCREEN              your setting: drop                                USED: drop                                              <- your setting (a year-season constant across pixels -- a fill value -- or with collapsed co
  DESIGN_SOURCE               your setting: panel                               USED: panel                                             <- your setting (the PANEL's treat / control / pre / post / did -- the exports' Treat flag, P
  CONTROL_SELECTION           your setting: pre_rings -- switch OFF             USED: rings                                             <- USE_CONTROL_SELECTION = FALSE -> NOT applied; your setting (every ring of CONTROL_RINGS is
  DONUT_RINGS                 your setting: 1 -- switch OFF                     USED: none                                              <- USE_DONUT = FALSE -> NOT applied; your setting (rings left out of the control pool -- the 
  LANDUSE_KEEP                your setting: 2 -- switch OFF                     USED: all                                               <- USE_LANDUSE_MASK = FALSE -> NOT applied; your setting (a pixel is kept by its PRE-period l
  BASELINE_NDVI_MIN           your setting: 0.25 -- switch OFF                  USED: NA                                                <- USE_BASELINE_NDVI_MASK = FALSE -> NOT applied; your setting (a pixel's pre-period mean NDV
  MIN_PIXEL_COVERAGE_PCT      your setting: 0.7 -- switch OFF                   USED: 0.05                                              <- USE_COVERAGE_THRESHOLD = FALSE -> NOT applied; your setting (a year-season below this shar
  USE_DROP_SINGLETONS         your setting: FALSE                               USED: FALSE                                             <- your setting (TRUE = series seen once leave before the demeaning)
  PRECISION_TOLERANCE         your setting: 1e-06 -- switch OFF                 USED: 0                                                 <- USE_PRECISION_TOLERANCE = FALSE -> NOT applied; your setting (|value| <= tolerance is the 
  SAME_PIXELS                 your setting: pre_post -- switch OFF              USED: off                                               <- USE_SAME_PIXELS = FALSE -> NOT applied; your setting (a pixel may contribute to one side o
  CLUSTER                     your setting: auto                                USED: auto                                              <- your setting (the sub-watershed; fewer than 6 sub-watersheds -> the years)
  COVARIATES                  your setting: Rain,Tmax,Tmean,Tmin                USED: Rain,Tmax,Tmean,Tmin                              <- your setting
[OK]      design with the default settings saved -> /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/R_design.json | ctrl1-5_treatFund_all_panelDesign_covAll4_yr2016-2025
[OK]      outcome identities: no two outcomes are the same variable in this panel
```



<!-- rnb-output-end -->

<!-- rnb-output-begin eyJkYXRhIjoiTGlzdCBvZiA0N1xuICQgZGVzaWduX21vZGUgICAgICAgICAgICA6IGNociBcInJlY29tbWVuZGVkXCJcbiAkIHRpbWluZyAgICAgICAgICAgICAgICAgOiBjaHIgXCJmdW5kXCJcbiAkIHRyZWF0bWVudF95ZWFyICAgICAgICAgOiBpbnQgMjAyNFxuICQgdHJlYXRtZW50X3llYXJfc2V0dGluZyA6IGludCAyMDIyXG4gJCBzaXRlX3N0YXJ0ICAgICAgICAgICAgIDpDbGFzc2VzICdkYXRhLnRhYmxlJyBhbmQgJ2RhdGEuZnJhbWUnOlx0MSBvYnMuIG9mICAzIHZhcmlhYmxlczpcbiAgLi4kIHNpdGVfaWQ6IGludCAxXG4gIC4uJCB5ZWFyICAgOiBpbnQgMjAyNFxuICAuLiQgc2Vhc29uIDogaW50IDJcbiAgLi4tIGF0dHIoKiwgXCIuaW50ZXJuYWwuc2VsZnJlZlwiKT08ZXh0ZXJuYWxwdHI+IFxuICQgc2l0ZV95ZWFycyAgICAgICAgICAgICA6Q2xhc3NlcyAnZGF0YS50YWJsZScgYW5kICdkYXRhLmZyYW1lJzpcdDEgb2JzLiBvZiAgMiB2YXJpYWJsZXM6XG4gIC4uJCBzaXRlX2lkOiBpbnQgMVxuICAuLiQgeWVhciAgIDogaW50IDIwMjVcbiAgLi4tIGF0dHIoKiwgXCIuaW50ZXJuYWwuc2VsZnJlZlwiKT08ZXh0ZXJuYWxwdHI+IFxuICQgY29udHJvbF9yaW5ncyAgICAgICAgICA6IGludCBbMTo1XSAxIDIgMyA0IDVcbiAkIHllYXJfbWluICAgICAgICAgICAgICAgOiBpbnQgMjAxNlxuICQgeWVhcl9tYXggICAgICAgICAgICAgICA6IGludCAyMDI1XG4gJCBkcm9wX3llYXJzICAgICAgICAgICAgIDogaW50KDApIFxuICQgcHJlX3dpbmRvdyAgICAgICAgICAgICA6IGludCBbMTo4XSAyMDE2IDIwMTcgMjAxOCAyMDE5IDIwMjAgMjAyMSAyMDIyIDIwMjNcbiAkIHBvc3Rfd2luZG93ICAgICAgICAgICAgOiBpbnQgWzE6Ml0gMjAyNCAyMDI1XG4gJCBzZWFzb25zICAgICAgICAgICAgICAgIDogY2hyIFwiYWxsXCJcbiAkIHNlYXNvbnNfc2V0dGluZyAgICAgICAgOiBjaHIgXCJhbGxcIlxuICQgZXhjbHVkZV90cmFuc2l0aW9uX3llYXI6IGxvZ2kgRkFMU0VcbiAkIHVuaXRfZmUgICAgICAgICAgICAgICAgOiBjaHIgXCJwaXhlbF9zZWFzb25cIlxuICQgY29ob3J0X29mZnNldCAgICAgICAgICA6IGludCAwXG4gJCBvdmVybGFwX3Jvd3MgICAgICAgICAgIDogY2hyIFwiZHJvcFwiXG4gJCBmcmFnbWVudF9ydWxlICAgICAgICAgIDogY2hyIFwiZHJvcFwiXG4gJCBmcmFnbWVudF9taW5fc2hhcmUgICAgIDogbnVtIDAuMDVcbiAkIHBvb2xlZF9mZSAgICAgICAgICAgICAgOiBjaHIgXCJzaXRlX3BlcmlvZFwiXG4gJCBkb3NlX3ZhcmlhYmxlICAgICAgICAgIDogY2hyIFwiZG9zZV9pbnRlbnNpdHlfcGVyX2hhXCJcbiAkIGV4Y2x1ZGVfZ2FwZmlsbGVkICAgICAgOiBsb2dpIFRSVUVcbiAkIGNvdmFyaWF0ZXMgICAgICAgICAgICAgOiBjaHIgWzE6NF0gXCJSYWluXCIgXCJUbWF4XCIgXCJUbWVhblwiIFwiVG1pblwiXG4gJCBvdXRjb21lX3NjcmVlbiAgICAgICAgIDogY2hyIFwiZHJvcFwiXG4gJCBkZXNpZ25fc291cmNlICAgICAgICAgIDogY2hyIFwicGFuZWxcIlxuICQgY29udHJvbF9zZWxlY3Rpb24gICAgICA6IGNociBcInJpbmdzXCJcbiAkIGNvbnRyb2xfc2VsZWN0X2sgICAgICAgOiBpbnQgMlxuICQgY29udHJvbF9zZWxlY3RfcmF0aW8gICA6IG51bSAzXG4gJCBjb250cm9sX3NlbGVjdF9vbiAgICAgIDogY2hyIFwidHJlbmRcIlxuICQgY29udHJvbF9ibG9ja19kZWcgICAgICA6IG51bSAwLjAxXG4gJCBjbHVzdGVyICAgICAgICAgICAgICAgIDogY2hyIFwiYXV0b1wiXG4gJCBzYW1lX3BpeGVscyAgICAgICAgICAgIDogY2hyIFwib2ZmXCJcbiAkIGRvbnV0X3JpbmdzICAgICAgICAgICAgOiBpbnQoMCkgXG4gJCBsYW5kdXNlX2tlZXAgICAgICAgICAgIDogY2hyIFwiYWxsXCJcbiAkIGJhc2VsaW5lX25kdmlfbWluICAgICAgOiBudW0gTkFcbiAkIG1pbl9waXhlbF9jb3ZlcmFnZV9wY3QgOiBudW0gMC4wNVxuICQgZHJvcF9zaW5nbGV0b25zICAgICAgICA6IGxvZ2kgRkFMU0VcbiAkIHByZWNpc2lvbl90b2xlcmFuY2UgICAgOiBudW0gMFxuICQgZnVuZCAgICAgICAgICAgICAgICAgICA6TGlzdCBvZiA0XG4gIC4uJCBzdGFydF9ydWxlIDogY2hyIFwiYmFja2Nhc3RcIlxuICAuLiQgc3RhcnRfc2hhcmU6IG51bSAwLjFcbiAgLi4kIHJhdGVfbW9udGhzOiBpbnQgMTJcbiAgLi4kIGJlZm9yZV9maWxlOiBjaHIgXCJiYWNrY2FzdFwiXG4gJCBuX3NpdGVzICAgICAgICAgICAgICAgIDogaW50IDFcbiAkIHNpdGVzICAgICAgICAgICAgICAgICAgOiBpbnQgMVxuICQgbl9mdW5kX2RhdGVkICAgICAgICAgICA6IGludCAxXG4gJCBkYXRhX2tleXMgICAgICAgICAgICAgIDogY2hyIFsxOjNdIFwiY29udHJvbF9yaW5nc1wiIFwicHJlX3llYXJzXCIgXCJwb3N0X3llYXJzXCJcbiAkIHN1Yl93YXRlcnNoZWRzICAgICAgICAgOiBjaHIgXCJkYXRhXCJcbiAkIHByb2Nlc3NlZCAgICAgICAgICAgICAgOiBpbnQgMVxuICQgcHJvY2Vzc2VkX2hvdyAgICAgICAgICA6IGNociBcImRhdGE6IGV2ZXJ5IHN1Yi13YXRlcnNoZWQgd2l0aCA+PSA1ICUgb2YgdGhlIGxhcmdlc3Qgb25lJ3Mgb3duIHJvd3MgLT4gQXJ0YWwgKDEpOyBub3QgcHJvY2Vzc2VkOiBCZWd1cnUgKDI0MCByb1wifCBfX3RydW5jYXRlZF9fXG4ifQ== -->

```
List of 47
 $ design_mode            : chr "recommended"
 $ timing                 : chr "fund"
 $ treatment_year         : int 2024
 $ treatment_year_setting : int 2022
 $ site_start             :Classes 'data.table' and 'data.frame':	1 obs. of  3 variables:
  ..$ site_id: int 1
  ..$ year   : int 2024
  ..$ season : int 2
  ..- attr(*, ".internal.selfref")=<externalptr> 
 $ site_years             :Classes 'data.table' and 'data.frame':	1 obs. of  2 variables:
  ..$ site_id: int 1
  ..$ year   : int 2025
  ..- attr(*, ".internal.selfref")=<externalptr> 
 $ control_rings          : int [1:5] 1 2 3 4 5
 $ year_min               : int 2016
 $ year_max               : int 2025
 $ drop_years             : int(0) 
 $ pre_window             : int [1:8] 2016 2017 2018 2019 2020 2021 2022 2023
 $ post_window            : int [1:2] 2024 2025
 $ seasons                : chr "all"
 $ seasons_setting        : chr "all"
 $ exclude_transition_year: logi FALSE
 $ unit_fe                : chr "pixel_season"
 $ cohort_offset          : int 0
 $ overlap_rows           : chr "drop"
 $ fragment_rule          : chr "drop"
 $ fragment_min_share     : num 0.05
 $ pooled_fe              : chr "site_period"
 $ dose_variable          : chr "dose_intensity_per_ha"
 $ exclude_gapfilled      : logi TRUE
 $ covariates             : chr [1:4] "Rain" "Tmax" "Tmean" "Tmin"
 $ outcome_screen         : chr "drop"
 $ design_source          : chr "panel"
 $ control_selection      : chr "rings"
 $ control_select_k       : int 2
 $ control_select_ratio   : num 3
 $ control_select_on      : chr "trend"
 $ control_block_deg      : num 0.01
 $ cluster                : chr "auto"
 $ same_pixels            : chr "off"
 $ donut_rings            : int(0) 
 $ landuse_keep           : chr "all"
 $ baseline_ndvi_min      : num NA
 $ min_pixel_coverage_pct : num 0.05
 $ drop_singletons        : logi FALSE
 $ precision_tolerance    : num 0
 $ fund                   :List of 4
  ..$ start_rule : chr "backcast"
  ..$ start_share: num 0.1
  ..$ rate_months: int 12
  ..$ before_file: chr "backcast"
 $ n_sites                : int 1
 $ sites                  : int 1
 $ n_fund_dated           : int 1
 $ data_keys              : chr [1:3] "control_rings" "pre_years" "post_years"
 $ sub_watersheds         : chr "data"
 $ processed              : int 1
 $ processed_how          : chr "data: every sub-watershed with >= 5 % of the largest one's own rows -> Artal (1); not processed: Beguru (240 ro"| __truncated__
```



<!-- rnb-output-end -->

<!-- rnb-chunk-end -->


<!-- rnb-text-begin -->


**The outcome screen** -- which outcome-years are fill values (not data), per outcome.


<!-- rnb-text-end -->


<!-- rnb-chunk-begin -->


<!-- rnb-source-begin eyJkYXRhIjoic2NyIDwtIG91dGNvbWVfc2NyZWVuX1IoT1VUQ09NRVMsIGRlc2lnbikgICAjIHYyMC41ODogZXZlcnkgb3V0Y29tZSdzIHVzYWJsZSB5ZWFycyAtLSBhbGwgcm93cyBhdCBvbmNlLCBvciBvdXQgb2YgY29yZSBiZXlvbmQgOTggJSBvZiB0aGUgUkFNIn0= -->

```r
scr <- outcome_screen_R(OUTCOMES, design)   # v20.58: every outcome's usable years -- all rows at once, or out of core beyond 98 % of the RAM
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIE5EVkk6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgTkRWSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBERVNJR04gdnMgUEFORUw6IERFU0lHTl9TT1VSQ0UgPSBcInBhbmVsXCIgLS0gdGhpcyBtb2RlbCBlc3RpbWF0ZXMgb24gdGhlIFBBTkVMJ3MgcG9zdCAvIHByZSAvIGRpZCAodGhlIGV4cG9ydHMnIFRyZWF0IGZsYWcsIFBFUklPRF9SVUxFKTsgdGhlIGRlc2lnbiBpbiBlZmZlY3QgKGZ1bmQgdGltaW5nOiB0aGUgZmlyc3QgdHJlYXRlZCBzZWFzb24gcGVyIHN1Yi13YXRlcnNoZWQsIGJhc2UgeWVhciAyMDI0KSB3b3VsZCBkaWZmZXIgb24gMSw5ODAgb2YgNywxNTYgcm93cyAoMjcuNyAlKSAtLSBzZXQgREVTSUdOX1NPVVJDRSA8LSBcIm1vZGVsXCIgdG8gZXN0aW1hdGUgb24gaXQgKHlvdXIgc2V0dGluZ3M6IFRSRUFUTUVOVF9USU1JTkcgLyBUUkVBVE1FTlRfWUVBUiAvIEVYQ0xVREVfVFJBTlNJVElPTl9ZRUFSKVxuW09LXSAgICAgIHJhbmdlIHNhZmV0eSAoTkRWSSk6IDcsMTU2IGZpbml0ZSB2YWx1ZXMgaW4gWzAuMTYxNjU5LCAwLjU1MjkzNF0gYWdhaW5zdCB0aGUgYm91bmRzIFstMSwgMV07IDAgb3V0c2lkZSwgMCBuby1kYXRhIGNvZGVzLCAwIHdpdGhpbiAwIG9mIHplcm9cbltPS10gICAgICBzYW1wbGUgaW50ZWdyaXR5IChORFZJKTogNywxNTYgcm93cywgMTgwIHBpeGVscyB8IHN1Yi13YXRlcnNoZWQocykgMSB8IHJpbmdzIDAsMSwyLDMsNCw1IHwgeWVhcnMgMjAxNi0yMDI1IHwgc2Vhc29ucyBZZWFybHksS2hhcmlmLFJhYmksWmFpZCB8IENPTkZJUk1FRDogZXZlcnkgKHBpeGVsLCB5ZWFyLCBzZWFzb24pIG9uY2UsIG9uZSByaW5nIHBlciBwaXhlbCwgbm8gcGl4ZWwgYm90aCB0cmVhdGVkIGFuZCBhIGNvbnRyb2wsIG5vdGhpbmcgb3V0c2lkZSB0aGUgcHJvY2Vzc2VkIHN1Yi13YXRlcnNoZWQocylcbltJTkZPXSAgICBFVkk6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgRVZJOiA0NCByb3dzIGZpbGxlZCBmcm9tIGhpc3RvcnkgbGVmdCBvdXQgKDQ0IG9mIHRoZW0gaW4gdGhlIHBvc3QgeWVhcnMpXG5bSU5GT10gICAgYW5udWFsIHJvd3M6IDcsMjAwIGNvdmFyaWF0ZSB2YWx1ZXMgdGhlIGFubnVhbCBjb21wb3NpdGUgbGFja3Mgd2VyZSBmaWxsZWQgd2l0aCB0aGUgc2FtZSBwaXhlbC15ZWFyJ3Mgc2Vhc29uYWwgbWVhblxuW0lORk9dICAgIEVWSTogNywxNTYgb2YgNywxNTYgcm93cyBoYXZlIGEgbWlzc2luZyBvdXRjb21lIG9yIGNvdmFyaWF0ZSBhbmQgbGVhdmUgVEhJUyBlc3RpbWF0aW9uIG9ubHkgKGFuIHVuYmFsYW5jZWQgcGFuZWw6IHRoZSBwaXhlbCdzIG90aGVyIHBlcmlvZHMgYW5kIHRoZSBvdGhlciBvdXRjb21lcyBrZWVwIHRoZW0pXG4ifQ== -->

```
[INFO]    NDVI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    NDVI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    DESIGN vs PANEL: DESIGN_SOURCE = "panel" -- this model estimates on the PANEL's post / pre / did (the exports' Treat flag, PERIOD_RULE); the design in effect (fund timing: the first treated season per sub-watershed, base year 2024) would differ on 1,980 of 7,156 rows (27.7 %) -- set DESIGN_SOURCE <- "model" to estimate on it (your settings: TREATMENT_TIMING / TREATMENT_YEAR / EXCLUDE_TRANSITION_YEAR)
[OK]      range safety (NDVI): 7,156 finite values in [0.161659, 0.552934] against the bounds [-1, 1]; 0 outside, 0 no-data codes, 0 within 0 of zero
[OK]      sample integrity (NDVI): 7,156 rows, 180 pixels | sub-watershed(s) 1 | rings 0,1,2,3,4,5 | years 2016-2025 | seasons Yearly,Kharif,Rabi,Zaid | CONFIRMED: every (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s)
[INFO]    EVI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    EVI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    EVI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtaW4oZ2V0KG91dGNvbWUpKTogbm8gbm9uLW1pc3NpbmcgYXJndW1lbnRzIHRvIG1pbjsgcmV0dXJuaW5nIEluZlxuIn0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf
```



<!-- rnb-warning-end -->

<!-- rnb-warning-begin eyJkYXRhIjoiV2FybmluZyBpbiBtYXgoZ2V0KG91dGNvbWUpKTogbm8gbm9uLW1pc3NpbmcgYXJndW1lbnRzIHRvIG1heDsgcmV0dXJuaW5nIC1JbmZcbiJ9 -->

```
Warning in max(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFNBVkk6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgU0FWSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBTQVZJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    SAVI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    SAVI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    SAVI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIExBSTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBMQUk6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgTEFJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    LAI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    LAI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    LAI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIE5EUkU6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgTkRSRTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBORFJFOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    NDRE: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    NDRE: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    NDRE: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIE5ETUk6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgTkRNSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBORE1JOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    NDMI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    NDMI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    NDMI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIExTV0k6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgTFNXSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBMU1dJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    LSWI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    LSWI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    LSWI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIE5EV0k6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgTkRXSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBORFdJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    NDWI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    NDWI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    NDWI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFNNREk6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgU01ESTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBTTURJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    SMDI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    SMDI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    SMDI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFZDSTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBWQ0k6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgVkNJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    VCI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    VCI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    VCI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFRDSTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBUQ0k6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgVENJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    TCI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    TCI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    TCI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFZISTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBWSEk6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgVkhJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    VHI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    VHI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    VHI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIEVTSTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBFU0k6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgRVNJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    ESI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    ESI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    ESI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFdTSTogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBXU0k6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgV1NJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    WSI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    WSI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    WSI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFdTU0k6IDM2MCByb3dzIGxlZnQgb3V0IC0tIGFub3RoZXIgc3ViLXdhdGVyc2hlZCdzIGRhdGEgKG5vdCBwcm9jZXNzZWQgaW4gdGhpcyBydW4pICh0cmVhdGVkIHByZSAyMjQgLyBwb3N0IDU2LCBjb250cm9sIHByZSA2NCAvIHBvc3QgMTYpXG5bSU5GT10gICAgV1NTSTogNDQgcm93cyBmaWxsZWQgZnJvbSBoaXN0b3J5IGxlZnQgb3V0ICg0NCBvZiB0aGVtIGluIHRoZSBwb3N0IHllYXJzKVxuW0lORk9dICAgIGFubnVhbCByb3dzOiA3LDIwMCBjb3ZhcmlhdGUgdmFsdWVzIHRoZSBhbm51YWwgY29tcG9zaXRlIGxhY2tzIHdlcmUgZmlsbGVkIHdpdGggdGhlIHNhbWUgcGl4ZWwteWVhcidzIHNlYXNvbmFsIG1lYW5cbltJTkZPXSAgICBXU1NJOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    WSSI: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    WSSI: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    WSSI: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIFJVU0xFOiAzNjAgcm93cyBsZWZ0IG91dCAtLSBhbm90aGVyIHN1Yi13YXRlcnNoZWQncyBkYXRhIChub3QgcHJvY2Vzc2VkIGluIHRoaXMgcnVuKSAodHJlYXRlZCBwcmUgMjI0IC8gcG9zdCA1NiwgY29udHJvbCBwcmUgNjQgLyBwb3N0IDE2KVxuW0lORk9dICAgIFJVU0xFOiA0NCByb3dzIGZpbGxlZCBmcm9tIGhpc3RvcnkgbGVmdCBvdXQgKDQ0IG9mIHRoZW0gaW4gdGhlIHBvc3QgeWVhcnMpXG5bSU5GT10gICAgYW5udWFsIHJvd3M6IDcsMjAwIGNvdmFyaWF0ZSB2YWx1ZXMgdGhlIGFubnVhbCBjb21wb3NpdGUgbGFja3Mgd2VyZSBmaWxsZWQgd2l0aCB0aGUgc2FtZSBwaXhlbC15ZWFyJ3Mgc2Vhc29uYWwgbWVhblxuW0lORk9dICAgIFJVU0xFOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    RUSLE: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    RUSLE: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    RUSLE: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-output-begin eyJkYXRhIjoiW0lORk9dICAgIEFHQjogMzYwIHJvd3MgbGVmdCBvdXQgLS0gYW5vdGhlciBzdWItd2F0ZXJzaGVkJ3MgZGF0YSAobm90IHByb2Nlc3NlZCBpbiB0aGlzIHJ1bikgKHRyZWF0ZWQgcHJlIDIyNCAvIHBvc3QgNTYsIGNvbnRyb2wgcHJlIDY0IC8gcG9zdCAxNilcbltJTkZPXSAgICBBR0I6IDQ0IHJvd3MgZmlsbGVkIGZyb20gaGlzdG9yeSBsZWZ0IG91dCAoNDQgb2YgdGhlbSBpbiB0aGUgcG9zdCB5ZWFycylcbltJTkZPXSAgICBhbm51YWwgcm93czogNywyMDAgY292YXJpYXRlIHZhbHVlcyB0aGUgYW5udWFsIGNvbXBvc2l0ZSBsYWNrcyB3ZXJlIGZpbGxlZCB3aXRoIHRoZSBzYW1lIHBpeGVsLXllYXIncyBzZWFzb25hbCBtZWFuXG5bSU5GT10gICAgQUdCOiA3LDE1NiBvZiA3LDE1NiByb3dzIGhhdmUgYSBtaXNzaW5nIG91dGNvbWUgb3IgY292YXJpYXRlIGFuZCBsZWF2ZSBUSElTIGVzdGltYXRpb24gb25seSAoYW4gdW5iYWxhbmNlZCBwYW5lbDogdGhlIHBpeGVsJ3Mgb3RoZXIgcGVyaW9kcyBhbmQgdGhlIG90aGVyIG91dGNvbWVzIGtlZXAgdGhlbSlcbiJ9 -->

```
[INFO]    AGB: 360 rows left out -- another sub-watershed's data (not processed in this run) (treated pre 224 / post 56, control pre 64 / post 16)
[INFO]    AGB: 44 rows filled from history left out (44 of them in the post years)
[INFO]    annual rows: 7,200 covariate values the annual composite lacks were filled with the same pixel-year's seasonal mean
[INFO]    AGB: 7,156 of 7,156 rows have a missing outcome or covariate and leave THIS estimation only (an unbalanced panel: the pixel's other periods and the other outcomes keep them)
```



<!-- rnb-output-end -->

<!-- rnb-warning-begin eyJkYXRhIjpbIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtaW47IHJldHVybmluZyBJbmZcbiIsIldhcm5pbmcgaW4gbWluKGdldChvdXRjb21lKSk6IG5vIG5vbi1taXNzaW5nIGFyZ3VtZW50cyB0byBtYXg7IHJldHVybmluZyAtSW5mXG4iXX0= -->

```
Warning in min(get(outcome)): no non-missing arguments to min; returning Inf

Warning in min(get(outcome)): no non-missing arguments to max; returning -Inf
```



<!-- rnb-warning-end -->

<!-- rnb-source-begin eyJkYXRhIjoiZndyaXRlKHNjciwgZmlsZS5wYXRoKFJFU1VMVFNfRElSLCBcIk9VVENPTUVfU0NSRUVOX1IuY3N2XCIpKTsgcHJpbnQoc2NyKSJ9 -->

```r
fwrite(scr, file.path(RESULTS_DIR, "OUTCOME_SCREEN_R.csv")); print(scr)
```



<!-- rnb-source-end -->

<!-- rnb-output-begin eyJkYXRhIjoiICAgIG91dGNvbWUgICAgIHN0YXR1c1xuICAgICA8Y2hhcj4gICAgIDxjaGFyPlxuIDE6ICAgIE5EVkkgICAgIHVzYWJsZVxuIDI6ICAgICBFVkkgTk9UIHVzYWJsZVxuIDM6ICAgIFNBVkkgTk9UIHVzYWJsZVxuIDQ6ICAgICBMQUkgTk9UIHVzYWJsZVxuIDU6ICAgIE5EUkUgTk9UIHVzYWJsZVxuIDY6ICAgIE5ETUkgTk9UIHVzYWJsZVxuIDc6ICAgIExTV0kgTk9UIHVzYWJsZVxuIDg6ICAgIE5EV0kgTk9UIHVzYWJsZVxuIDk6ICAgIFNNREkgTk9UIHVzYWJsZVxuMTA6ICAgICBWQ0kgTk9UIHVzYWJsZVxuMTE6ICAgICBUQ0kgTk9UIHVzYWJsZVxuMTI6ICAgICBWSEkgTk9UIHVzYWJsZVxuMTM6ICAgICBFU0kgTk9UIHVzYWJsZVxuMTQ6ICAgICBXU0kgTk9UIHVzYWJsZVxuMTU6ICAgIFdTU0kgTk9UIHVzYWJsZVxuMTY6ICAgUlVTTEUgTk9UIHVzYWJsZVxuMTc6ICAgICBBR0IgTk9UIHVzYWJsZVxuICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgeWVhcnNcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPGNoYXI+XG4gMTogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgMjAxNiwyMDE3LDIwMTgsMjAxOSwyMDIwLDIwMjEsMjAyMiwyMDIzLDIwMjQsMjAyNVxuIDI6ICAgICAnRVZJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fRVZJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDM6ICAgJ1NBVkknIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9TQVZJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDQ6ICAgICAnTEFJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fTEFJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDU6ICAgJ05EUkUnIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9ORFJFLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDY6ICAgJ05ETUknIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9ORE1JLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDc6ICAgJ0xTV0knIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9MU1dJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDg6ICAgJ05EV0knIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9ORFdJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIDk6ICAgJ1NNREknIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9TTURJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTA6ICAgICAnVkNJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fVkNJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTE6ICAgICAnVENJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fVENJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTI6ICAgICAnVkhJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fVkhJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTM6ICAgICAnRVNJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fRVNJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTQ6ICAgICAnV1NJJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fV1NJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTU6ICAgJ1dTU0knIGlzIG5vdCB1c2FibGU6IGFmdGVyIHRoZSBzY3JlZW4gKDAgb2YgMCB5ZWFyLXNlYXNvbnMgbGVmdCBvdXQgYXMgZmlsbCB2YWx1ZXMgLyBjb2xsYXBzZWQgY292ZXJhZ2UpIGl0IGhhcyAwIHZhbGlkIHByZS1wZXJpb2QgeWVhcihzKSBbXSBhbmQgMCBwb3N0LXBlcmlvZCB5ZWFyKHMpIFtdIChuZWVkID49IDIgYW5kID49IDEpLiBUaGUgZXZpZGVuY2UgLS0gcm93cywgcGl4ZWxzLCBtZWFuLCBTRCwgbWluIGFuZCBtYXggcGVyIHllYXItc2Vhc29uIC0tIGlzIGluIC90bXAvUnRtcE8wSzZNVy9yZXdhcmRfYWxsX3Rlc3RzL0Vfb3B0aW9ucy9vdXRwdXQvcmVzdWx0cy9PVVRDT01FX1NDUkVFTl9XU1NJLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTY6ICdSVVNMRScgaXMgbm90IHVzYWJsZTogYWZ0ZXIgdGhlIHNjcmVlbiAoMCBvZiAwIHllYXItc2Vhc29ucyBsZWZ0IG91dCBhcyBmaWxsIHZhbHVlcyAvIGNvbGxhcHNlZCBjb3ZlcmFnZSkgaXQgaGFzIDAgdmFsaWQgcHJlLXBlcmlvZCB5ZWFyKHMpIFtdIGFuZCAwIHBvc3QtcGVyaW9kIHllYXIocykgW10gKG5lZWQgPj0gMiBhbmQgPj0gMSkuIFRoZSBldmlkZW5jZSAtLSByb3dzLCBwaXhlbHMsIG1lYW4sIFNELCBtaW4gYW5kIG1heCBwZXIgeWVhci1zZWFzb24gLS0gaXMgaW4gL3RtcC9SdG1wTzBLNk1XL3Jld2FyZF9hbGxfdGVzdHMvRV9vcHRpb25zL291dHB1dC9yZXN1bHRzL09VVENPTUVfU0NSRUVOX1JVU0xFLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuMTc6ICAgICAnQUdCJyBpcyBub3QgdXNhYmxlOiBhZnRlciB0aGUgc2NyZWVuICgwIG9mIDAgeWVhci1zZWFzb25zIGxlZnQgb3V0IGFzIGZpbGwgdmFsdWVzIC8gY29sbGFwc2VkIGNvdmVyYWdlKSBpdCBoYXMgMCB2YWxpZCBwcmUtcGVyaW9kIHllYXIocykgW10gYW5kIDAgcG9zdC1wZXJpb2QgeWVhcihzKSBbXSAobmVlZCA+PSAyIGFuZCA+PSAxKS4gVGhlIGV2aWRlbmNlIC0tIHJvd3MsIHBpeGVscywgbWVhbiwgU0QsIG1pbiBhbmQgbWF4IHBlciB5ZWFyLXNlYXNvbiAtLSBpcyBpbiAvdG1wL1J0bXBPMEs2TVcvcmV3YXJkX2FsbF90ZXN0cy9FX29wdGlvbnMvb3V0cHV0L3Jlc3VsdHMvT1VUQ09NRV9TQ1JFRU5fQUdCLmNzdi4gSWYgdGhvc2UgeWVhci1zZWFzb25zIEFSRSBwaXhlbCBkYXRhLCBzZXQgT1VUQ09NRV9TQ1JFRU4gPC0gXCJrZWVwXCIgaW4gdGhpcyBtb2RlbCdzIHNldHRpbmdzICh0aGUgbW9kZWwgdGhlbiBydW5zIG9uIGV2ZXJ5IHllYXItc2Vhc29uLCB0YWdnZWQgX3NjcmVlbktlcHQpIC0tIG9yIHJlLWV4cG9ydCB0aGUgdmFyaWFibGUgaWYgdGhleSBhcmUgbm90LlxuIn0= -->

```
    outcome     status
     <char>     <char>
 1:    NDVI     usable
 2:     EVI NOT usable
 3:    SAVI NOT usable
 4:     LAI NOT usable
 5:    NDRE NOT usable
 6:    NDMI NOT usable
 7:    LSWI NOT usable
 8:    NDWI NOT usable
 9:    SMDI NOT usable
10:     VCI NOT usable
11:     TCI NOT usable
12:     VHI NOT usable
13:     ESI NOT usable
14:     WSI NOT usable
15:    WSSI NOT usable
16:   RUSLE NOT usable
17:     AGB NOT usable
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           years
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          <char>
 1:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            2016,2017,2018,2019,2020,2021,2022,2023,2024,2025
 2:     'EVI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_EVI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 3:   'SAVI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_SAVI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 4:     'LAI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_LAI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 5:   'NDRE' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_NDRE.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 6:   'NDMI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_NDMI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 7:   'LSWI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_LSWI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 8:   'NDWI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_NDWI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
 9:   'SMDI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_SMDI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
10:     'VCI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_VCI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
11:     'TCI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_TCI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
12:     'VHI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_VHI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
13:     'ESI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_ESI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
14:     'WSI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_WSI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
15:   'WSSI' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_WSSI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
16: 'RUSLE' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_RUSLE.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
17:     'AGB' is not usable: after the screen (0 of 0 year-seasons left out as fill values / collapsed coverage) it has 0 valid pre-period year(s) [] and 0 post-period year(s) [] (need >= 2 and >= 1). The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in /tmp/RtmpO0K6MW/reward_all_tests/E_options/output/results/OUTCOME_SCREEN_AGB.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" in this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.
```



<!-- rnb-output-end -->

<!-- rnb-chunk-end -->

