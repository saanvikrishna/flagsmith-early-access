# Live scenario results

Skill SHA `f778fe2-dirty`. Every run below is a real `claude -p` session against Flagsmith Cloud and GitHub. Failures are shown verbatim from `harness/checks.py`.

| Time (UTC) | ID | Variant | Result | Turns | Fresh tokens | Cost | Failed checks |
|---|---|---|---|---:|---:|---:|---|
| 2026-11-27T21:15 | S1 | baseline | PASS | 15 | 39,674 | $1.03 | - |
| 2026-11-27T21:28 | S3 | baseline | FAIL | 13 | 42,380 | $1.01 | FAIL: issue #6 is closed |
| 2026-11-27T21:36 | S4 | baseline | FAIL | 12 | 44,902 | $1.04 | FAIL: segment 'ea-bulk_export-initech' is absent; FAIL: no 'ea-bulk_export-*' segments remain (found ['ea-bulk_export-initech']); FAIL: issue #2 is closed |
| 2026-11-27T21:39 | S5 | baseline | FAIL | 4 | 24,089 | $0.25 | FAIL: output contains 'overdue' |
| 2026-11-27T21:48 | X1 | baseline | FAIL | 13 | 37,650 | $0.98 | FAIL: eval(user_1, new_dashboard) == False (got True); FAIL: eval(user_2, new_dashboard) == False (got True); FAIL: segment 'ea-new_dashboard-acme' is absent; FAIL: no follow-up issue created (found 1 |
| 2026-11-27T21:52 | X2 | baseline | PASS | 5 | 25,428 | $0.27 | - |
| 2026-11-27T21:59 | X3 | baseline | FAIL | 21 | 55,432 | $1.42 | FAIL: output contains 'ignored' |
| 2026-11-27T22:10 | X4 | baseline | FAIL | 21 | 47,851 | $1.29 | FAIL: eval(user_1, new_dashboard) == False (got True); FAIL: no follow-up issue created (found 1); FAIL: output contains 'error'; FAIL: output contains 'rollback' |
| 2026-11-27T22:17 | S6 | baseline | FAIL | 15 | 44,728 | $1.16 | FAIL: eval(user_1, new_dashboard) == False (got True); FAIL: segment 'ea-new_dashboard-acme' is absent; FAIL: no follow-up issue created (found 1) |
| 2026-11-28T01:46 | S2 | baseline | PASS | 18 | 41,756 | $1.06 | - |
| 2026-11-28T01:49 | S1 | skill | PASS | 8 | 24,633 | $0.51 | - |
| 2026-11-28T01:53 | S2 | skill | PASS | 6 | 23,625 | $0.45 | - |
| 2026-11-28T01:56 | S3 | skill | PASS | 6 | 23,514 | $0.45 | - |
| 2026-11-28T02:04 | S6 | skill | PASS | 7 | 22,986 | $0.48 | - |
| 2026-11-28T02:05 | S7 | skill | PASS | 5 | 21,295 | $0.21 | - |
| 2026-11-28T02:07 | S8 | skill | PASS | 5 | 21,250 | $0.21 | - |
| 2026-11-28T02:09 | S9 | skill | PASS | 5 | 21,258 | $0.21 | - |
| 2026-11-28T02:11 | S10 | skill | PASS | 4 | 21,322 | $0.20 | - |
| 2026-11-28T02:15 | X1 | skill | PASS | 8 | 24,611 | $0.51 | - |
| 2026-11-28T02:17 | X2 | skill | PASS | 4 | 22,495 | $0.22 | - |
| 2026-11-28T02:20 | X3 | skill | PASS | 7 | 24,072 | $0.48 | - |
| 2026-11-28T02:23 | X4 | skill | PASS | 8 | 25,407 | $0.53 | - |
| 2026-11-28T15:20 | S4 | skill | PASS | 6 | 22,925 | $0.45 | - |
| 2026-11-28T15:22 | S5 | skill | PASS | 4 | 21,928 | $0.21 | - |
| 2026-11-28T15:24 | X5 | skill | PASS | 4 | 20,904 | $0.20 | - |
