# Stage 0.7b — Valid-side SMT scaling

## Conclusion

**The limits must change to 60 seconds for the solver and 90 seconds for the
process.** The original 5/30-second limits were based on a SAT/Counterexample
grid dominated by startup. On the Valid/UNSAT side, F3 at `n=64,k=4` remained
Valid but took a 42.241-second median, and `n=128,k=1` took 85.631 seconds.
`n=128,k=2` hit the 120-second hard ceiling in all three runs. Therefore the
tool proves the generated families through the chosen n=64 operating envelope,
but not every syntactically valid contract: the Python validator imposes no
size/depth ceiling. A result of `Indeterminate` or `Timeout` means “not
concluded”, never “invalid”.

The measured host should run at most two simultaneous jobs with a 2 GiB limit
per job. Four heavy jobs did complete, but peaked at 6,371,660 KiB on a host
with only 6,997,668 KiB available, leaving no safe operating margin.

## Method and coverage

`generate_valid_contracts.py` deterministically generates five Valid families
and one matched Counterexample control. Every n=1..3, k=1..2, nested/non-nested
combination passed the existing Python validator; F1–F5 returned `Valid`, C1
returned `Counterexample`, and duplicate generations had identical SHA-256.

The committed table contains 375 rows: the startup row; the complete requested
grid through n=64 (360 configurations, 1,080 measured runs); and 14 n=128
extension configurations. Every configuration has three runs. F1 and F2 were
extended fully at n=128; F3 produced one Valid row and one all-Timeout row.
The extension was stopped there rather than spend another 120 seconds × 3 on
each remaining F3 branch shape. Thus the required n≤64 grid is complete and the
n=128 extension is intentionally partial. Status cells contain only `Valid`,
`Counterexample`, or `Timeout` (the allowed `Indeterminate` state was forced in
a separate diagnostic).

The `"close"` startup median over ten runs was 0.105645 seconds. The CSV records
both wall time and wall time minus this baseline. `run_valid_bench.py` invokes
the driver directly so it can preserve the driver's status and samples the
entire process group every 50 ms. It sums the Haskell driver and its separate
Z3 child rather than reporting either process alone.

## Scaling and breakpoints

For a consistent comparison, the fit below uses the k=4, nested series from
n=8 through n=64 and regresses log(median wall time) on log(n). The exponent is
a power-law description over this measured interval, not an asymptotic proof.

| Family | n=8 → n=64 median | fitted exponent | R² | first >1 s | first >5 s | first >30 s | first 120 s |
|---|---:|---:|---:|---|---|---|---|
| F1 Choice | 0.157 → 0.260 s | 0.29 | 0.875 | none | none | none | none |
| F2 balanced Deposit/Pay | 0.209 → 0.415 s | 0.35 | 0.873 | none | none | none | none |
| F3 symbolic arithmetic | 0.730 → 24.294 s | 1.70 | 0.971 | n=12,k=4,if; 96 cases | n=48,k=1,if; 96 cases | n=64,k=4; 512 cases | n=128,k=2; 512 cases |
| F4 bounded Assert | 0.313 → 6.900 s | 1.46 | 0.955 | n=32,k=2,if; 64 cases | n=64,k=4; 256 cases | none | none |
| F5 expanded milestone | 0.316 → 2.091 s | 0.92 | 0.996 | n=32,k=4,if; 1,280 cases | none | none | none |
| C1 deepest overpay | 0.158 → 1.041 s | 0.89 | 0.995 | n=64,k=4,if; 512 cases | none | none | none |

F3 is the limiting family. Its n=64,k=4 non-nested point took
37.260/44.534/42.241 seconds (median 42.241) and peaked at 1,671,660 KiB total
RSS. At n=128,k=1 it still returned Valid in 87.571/85.146/85.631 seconds and
peaked at 2,741,304 KiB. At n=128,k=2 all three runs were killed at
120.120–120.169 seconds, with the largest sampled tree RSS 3,540,908 KiB.

F2 versus its same-shape C1 control does not support the assumption that SAT is
always faster. For k=4,nested, the Valid/Counterexample median ratios at
n=1,8,20,32,48,64 were 0.99, 1.32, 0.71, 0.45, 0.44, and 0.40. The single C1
fault is deliberately deepest, so reaching it can cost more than proving the
balanced F2 structure. The important correction remains that the old generator
measured only one, non-representative SAT shape.

## Real agent contracts

The six completed audit contracts all returned Valid in three fresh runs.
Their canonical contracts contain 2–9 cases, are 743–3,279 bytes, and had
0.158–0.168-second medians. The largest, `vi-milestone-L4-003-full.json`, had
9 cases, 3,279 bytes, and a 0.158-second median. The first 5-second F3 knee is
5.924 seconds at n=48,k=1,nested (96 cases, 81,061 bytes): 37.5× the largest
audit's measured time, 10.7× its case count, and 24.7× its byte size. There is
no validator-enforced maximum contract length, so there is no finite
“largest validator-accepted contract” to place on the curve.

## Memory, concurrency, and process states

On F3 n=32,k=1, GNU `time -v` reported 116,328 KiB maximum RSS for the driver.
The 50 ms tree sampler measured 203,740–205,676 KiB total and 116,580–116,732
KiB driver RSS in the three grid runs. Driver RSS agrees within 0.4%, while the
whole tree is about 76% higher because Z3 is a separate child process. The
sampling method can miss very short-lived peaks, so values are sizing evidence,
not a formal upper bound.

The parallel target was F3 n=64,k=4, the heaviest configuration whose original
three-run median was below 60 seconds:

| Jobs | batch median job times | peak group RSS range | slowdown vs N=1 median |
|---:|---|---:|---:|
| 1 | 62.792, 52.876, 48.754 s | 1,671,804–1,671,988 KiB | 1.00× |
| 2 | 56.793, 50.033, 49.989 s | 3,338,760–3,343,124 KiB | 0.946× |
| 4 | 62.804, 63.752, 64.564 s | 6,235,080–6,371,660 KiB | 1.206× |

All parallel jobs returned Valid. N=4 consumed 91% of reported WSL memory at
peak, so the operational recommendation is N=2 despite 16 logical CPUs.

The same heavy Valid contract with a 1,000 ms solver limit returned the exact
solver result `Unknown.\n  Reason: timeout` and status `Indeterminate`. The
Python wrapper with a 0.1-second deadline returned `Timeout`, exit 124; neither
was converted to Valid.

## Operating recommendation

- Solver timeout: **60,000 ms**. It covers the complete n≤64 grid, including
  the 42.241-second limiting median, while refusing the 85.631-second n=128
  case rather than allowing unbounded work.
- Hard process timeout: **90 seconds**, leaving 30 seconds beyond the solver
  ceiling for parsing, translation, process startup, and teardown.
- Concurrency: **2 jobs** on this 7-GiB host. Re-measure on a larger host before
  raising it.
- Memory: **2 GiB per job** for the n≤64 envelope. The n=128 Valid point needs
  more and is intentionally outside this operating envelope.
- Node 3 policy: fail closed, do not automatically retry an unchanged contract
  more than once, and ask the agent to reduce branching/arithmetic or escalate
  for manual analysis. Never label an inconclusive result as a bad contract.

## Acceptance criteria

- (a) Pass: deterministic generator, validator acceptance, expected small-grid
  statuses, SHA equality, and automated test.
- (b) Pass: complete through n=64 plus documented partial n=128 extension; all
  CSV statuses are in the allowed set.
- (c) Pass: ten-run startup baseline and net-time columns.
- (d) Pass: matched F2/C1 comparison at every requested size.
- (e) Pass: summed process-group RSS and GNU-time cross-check.
- (f) Pass: N=1,2,4, three batches each on a 16-logical-core host.
- (g) Pass: forced Indeterminate and Timeout on the heavy Valid input; Timeout
  was never Valid.
- (h) Pass: defaults changed to 60/90 seconds; N=2 and 2 GiB/job justified
  above.
- (i) Pass: 12 tests passed; upstream verification reported the pinned SHA and
  `no patches` after all changes.
- (j) Pass: 15 files across every family, 2,092,954 bytes including manifest;
  SHA and byte regeneration pass, small representatives rerun correctly, and
  every family retains its smallest and heaviest measured expected-status
  representative. The 389,079-byte first-timeout file was omitted to remain
  below 2 MiB; its SHA and measurements remain in the summary CSV.

## Environment and limits of evidence

Measurements used WSL2 kernel 6.18.33.2, AMD Ryzen 7 8845H, 16 logical CPUs,
6,997,668 KiB reported RAM, GHC 9.6.7, cabal-install 3.10.3.0, Z3 4.13.3, and
upstream commit `7b5b1e900ec53a8eb18747992bec73470704dfcb`.

Verified: the five generated Valid families, the C1 control, six completed
audits, process-tree RSS, concurrency on this host, forced process states, the
corpus manifest, and upstream integrity. Not verified: other machines or Z3
versions, arbitrary contract shapes outside F1–F5, a validator size ceiling
(none exists), address/native-token-heavy stress, another SlotLength (the
engine has no such parameter), production Node 3 integration, and full n=128
coverage. The corpus is representative, not the complete generated grid.

Primary evidence: [`stress-valid-summary.csv`](../../tools/marlowe_smt/bench/stress-valid-summary.csv),
[`parallel-valid-summary.csv`](../../tools/marlowe_smt/bench/parallel-valid-summary.csv),
and [`valid-corpus/MANIFEST.csv`](../../tools/marlowe_smt/bench/valid-corpus/MANIFEST.csv).
