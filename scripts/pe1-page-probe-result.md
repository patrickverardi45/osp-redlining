# PE.1 — Per-Page Parser Probe Results

**Run:** 2026-05-20T13:00:12
**Python:** 3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
**PDF source:** `C:\Nova\knowledge\TrueLine-Wiki\raw\trueline\engineering-plans\brenham`
**Worker:** `pe1_page_probe_worker.py`
**Page timeout budget:** 30 s
**Count timeout budget:** 60 s

## Aggregate

- PDFs processed: **3**
- Pages attempted: **127**
- Pages OK: **96**
- Pages TIMEOUT: **31**
- Pages ERROR: **0**
- OK rate: **75%**

## Pathological pages

| PDF | Page | Class | Wallclock (ms) |
|---|---:|---|---:|
| `Brenham - Phase 5_07-15-25.pdf` | 6 | timeout | 30011 |
| `Brenham - Phase 5_07-15-25.pdf` | 13 | timeout | 30017 |
| `Brenham - Phase 5_07-15-25.pdf` | 14 | timeout | 30015 |
| `Brenham - Phase 5_07-15-25.pdf` | 15 | timeout | 30013 |
| `Brenham - Phase 5_07-15-25.pdf` | 16 | timeout | 30011 |
| `Brenham - Phase 5_07-15-25.pdf` | 17 | timeout | 30018 |
| `Brenham - Phase 5_07-15-25.pdf` | 18 | timeout | 30019 |
| `Brenham - Phase 5_07-15-25.pdf` | 19 | timeout | 30008 |
| `Brenham - Phase 5_07-15-25.pdf` | 20 | timeout | 30019 |
| `Brenham - Phase 5_07-15-25.pdf` | 21 | timeout | 30009 |
| `Brenham - Phase 5_07-15-25.pdf` | 22 | timeout | 30016 |
| `Brenham - Phase 5_07-15-25.pdf` | 23 | timeout | 30011 |
| `Brenham - Phase 5_07-15-25.pdf` | 24 | timeout | 30014 |
| `Brenham - Phase 5_07-15-25.pdf` | 25 | timeout | 30020 |
| `Brenham - Phase 5_07-15-25.pdf` | 26 | timeout | 30010 |
| `Brenham - Phase 5_07-15-25.pdf` | 27 | timeout | 30013 |
| `Brenham - Phase 5_07-15-25.pdf` | 28 | timeout | 30006 |
| `Brenham - Phase 5_07-15-25.pdf` | 29 | timeout | 30011 |
| `Brenham - Phase 5_07-15-25.pdf` | 30 | timeout | 30009 |
| `Brenham - Phase 5_07-15-25.pdf` | 31 | timeout | 30012 |
| `Brenham - Phase 5_07-15-25.pdf` | 32 | timeout | 30005 |
| `Brenham - Phase 5_07-15-25.pdf` | 33 | timeout | 30006 |
| `Brenham - Phase 5_07-15-25.pdf` | 34 | timeout | 30013 |
| `Brenham - Phase 5_07-15-25.pdf` | 35 | timeout | 30011 |
| `Brenham - Phase 5_07-15-25.pdf` | 36 | timeout | 30007 |
| `Brenham - Phase 5_07-15-25.pdf` | 37 | timeout | 30009 |
| `Brenham - Phase 5_07-15-25.pdf` | 38 | timeout | 30013 |
| `Brenham - Phase 5_07-15-25.pdf` | 39 | timeout | 30007 |
| `Brenham - Phase 5_07-15-25.pdf` | 40 | timeout | 30015 |
| `Brenham - Phase 5_07-15-25.pdf` | 41 | timeout | 30009 |
| `Brenham - Phase 5_07-15-25.pdf` | 42 | timeout | 30013 |

## Per-PDF detail

### PDF_0: `Brenham - Phase 5_07-15-25.pdf`  (14008 KB)

| Page | Status | Text len | Worker ms | Peak KB | Total ms | Error |
|---:|---|---:|---:|---:|---:|---|
| 0 | ok | 156 | 7472 | 8696 | 7600 | — |
| 1 | ok | 365 | 10549 | 20834 | 10707 | — |
| 2 | ok | 462 | 11594 | 25964 | 11764 | — |
| 3 | ok | 16479 | 25625 | 93946 | 25940 | — |
| 4 | ok | 231 | 13700 | 34413 | 13892 | — |
| 5 | ok | 793 | 21021 | 64894 | 21286 | — |
| 6 | **timeout** | — | — | — | 30011 | (killed by orchestrator) |
| 7 | ok | 208 | 8761 | 14156 | 8904 | — |
| 8 | ok | 208 | 8784 | 14200 | 8928 | — |
| 9 | ok | 279 | 12859 | 32685 | 13043 | — |
| 10 | ok | 36 | 25916 | 87182 | 26250 | — |
| 11 | ok | 241 | 8773 | 14085 | 8917 | — |
| 12 | ok | 1793 | 11996 | 29840 | 12171 | — |
| 13 | **timeout** | — | — | — | 30017 | (killed by orchestrator) |
| 14 | **timeout** | — | — | — | 30015 | (killed by orchestrator) |
| 15 | **timeout** | — | — | — | 30013 | (killed by orchestrator) |
| 16 | **timeout** | — | — | — | 30011 | (killed by orchestrator) |
| 17 | **timeout** | — | — | — | 30018 | (killed by orchestrator) |
| 18 | **timeout** | — | — | — | 30019 | (killed by orchestrator) |
| 19 | **timeout** | — | — | — | 30008 | (killed by orchestrator) |
| 20 | **timeout** | — | — | — | 30019 | (killed by orchestrator) |
| 21 | **timeout** | — | — | — | 30009 | (killed by orchestrator) |
| 22 | **timeout** | — | — | — | 30016 | (killed by orchestrator) |
| 23 | **timeout** | — | — | — | 30011 | (killed by orchestrator) |
| 24 | **timeout** | — | — | — | 30014 | (killed by orchestrator) |
| 25 | **timeout** | — | — | — | 30020 | (killed by orchestrator) |
| 26 | **timeout** | — | — | — | 30010 | (killed by orchestrator) |
| 27 | **timeout** | — | — | — | 30013 | (killed by orchestrator) |
| 28 | **timeout** | — | — | — | 30006 | (killed by orchestrator) |
| 29 | **timeout** | — | — | — | 30011 | (killed by orchestrator) |
| 30 | **timeout** | — | — | — | 30009 | (killed by orchestrator) |
| 31 | **timeout** | — | — | — | 30012 | (killed by orchestrator) |
| 32 | **timeout** | — | — | — | 30005 | (killed by orchestrator) |
| 33 | **timeout** | — | — | — | 30006 | (killed by orchestrator) |
| 34 | **timeout** | — | — | — | 30013 | (killed by orchestrator) |
| 35 | **timeout** | — | — | — | 30011 | (killed by orchestrator) |
| 36 | **timeout** | — | — | — | 30007 | (killed by orchestrator) |
| 37 | **timeout** | — | — | — | 30009 | (killed by orchestrator) |
| 38 | **timeout** | — | — | — | 30013 | (killed by orchestrator) |
| 39 | **timeout** | — | — | — | 30007 | (killed by orchestrator) |
| 40 | **timeout** | — | — | — | 30015 | (killed by orchestrator) |
| 41 | **timeout** | — | — | — | 30009 | (killed by orchestrator) |
| 42 | **timeout** | — | — | — | 30013 | (killed by orchestrator) |

### PDF_1: `BRENHAM PH5 - 18-02-2026.pdf`  (1451 KB)

| Page | Status | Text len | Worker ms | Peak KB | Total ms | Error |
|---:|---|---:|---:|---:|---:|---|
| 0 | ok | 85 | 661 | 3009 | 779 | — |
| 1 | ok | 5578 | 8153 | 40781 | 8351 | — |
| 2 | ok | 6160 | 8363 | 42782 | 8565 | — |
| 3 | ok | 4992 | 7859 | 39175 | 8054 | — |

### PDF_2: `BRENHAM_PHASE_5_New_report_2026-03-23_1774300147.pdf`  (8945 KB)

| Page | Status | Text len | Worker ms | Peak KB | Total ms | Error |
|---:|---|---:|---:|---:|---:|---|
| 0 | ok | 974 | 4690 | 6075 | 4814 | — |
| 1 | ok | 1634 | 5281 | 7832 | 5413 | — |
| 2 | ok | 1709 | 5277 | 8000 | 5406 | — |
| 3 | ok | 1617 | 5290 | 7789 | 5421 | — |
| 4 | ok | 1623 | 5565 | 8113 | 5697 | — |
| 5 | ok | 1649 | 5582 | 8191 | 5714 | — |
| 6 | ok | 1549 | 5576 | 7987 | 5708 | — |
| 7 | ok | 1551 | 5564 | 7992 | 5695 | — |
| 8 | ok | 1689 | 5565 | 8268 | 5696 | — |
| 9 | ok | 1387 | 5435 | 7543 | 5569 | — |
| 10 | ok | 1724 | 5554 | 8313 | 5687 | — |
| 11 | ok | 1593 | 5602 | 8079 | 5734 | — |
| 12 | ok | 1561 | 5458 | 7900 | 5587 | — |
| 13 | ok | 1451 | 5476 | 7685 | 5607 | — |
| 14 | ok | 1455 | 5505 | 7677 | 5636 | — |
| 15 | ok | 1464 | 5363 | 7602 | 5493 | — |
| 16 | ok | 2016 | 5455 | 8768 | 5585 | — |
| 17 | ok | 2074 | 5418 | 8792 | 5549 | — |
| 18 | ok | 2005 | 5592 | 8850 | 5723 | — |
| 19 | ok | 1974 | 5624 | 8812 | 5756 | — |
| 20 | ok | 1885 | 5550 | 8570 | 5681 | — |
| 21 | ok | 1531 | 5433 | 7784 | 5564 | — |
| 22 | ok | 1059 | 5094 | 6641 | 5224 | — |
| 23 | ok | 0 | 4518 | 4453 | 4642 | — |
| 24 | ok | 0 | 4483 | 4556 | 4613 | — |
| 25 | ok | 0 | 4492 | 4351 | 4619 | — |
| 26 | ok | 0 | 4481 | 4472 | 4610 | — |
| 27 | ok | 0 | 4486 | 4350 | 4613 | — |
| 28 | ok | 0 | 4488 | 4412 | 4612 | — |
| 29 | ok | 0 | 4498 | 4491 | 4625 | — |
| 30 | ok | 0 | 4481 | 4339 | 4605 | — |
| 31 | ok | 0 | 4497 | 4505 | 4621 | — |
| 32 | ok | 0 | 4485 | 4408 | 4610 | — |
| 33 | ok | 0 | 4518 | 4353 | 4645 | — |
| 34 | ok | 0 | 4494 | 4501 | 4619 | — |
| 35 | ok | 0 | 4546 | 4425 | 4672 | — |
| 36 | ok | 0 | 4497 | 4507 | 4622 | — |
| 37 | ok | 0 | 4481 | 4463 | 4604 | — |
| 38 | ok | 0 | 4526 | 4516 | 4652 | — |
| 39 | ok | 0 | 4487 | 4479 | 4612 | — |
| 40 | ok | 0 | 4538 | 4549 | 4662 | — |
| 41 | ok | 0 | 4495 | 4492 | 4619 | — |
| 42 | ok | 0 | 4508 | 4487 | 4631 | — |
| 43 | ok | 0 | 4498 | 4481 | 4624 | — |
| 44 | ok | 0 | 4483 | 4457 | 4608 | — |
| 45 | ok | 0 | 4490 | 4504 | 4617 | — |
| 46 | ok | 0 | 4486 | 4530 | 4610 | — |
| 47 | ok | 0 | 4487 | 4452 | 4612 | — |
| 48 | ok | 0 | 4486 | 4477 | 4611 | — |
| 49 | ok | 0 | 4482 | 4453 | 4610 | — |
| 50 | ok | 6 | 4483 | 4559 | 4607 | — |
| 51 | ok | 0 | 4537 | 4351 | 4664 | — |
| 52 | ok | 0 | 4522 | 4472 | 4646 | — |
| 53 | ok | 0 | 4488 | 4350 | 4613 | — |
| 54 | ok | 0 | 4529 | 4412 | 4653 | — |
| 55 | ok | 0 | 4505 | 4491 | 4631 | — |
| 56 | ok | 0 | 4504 | 4339 | 4628 | — |
| 57 | ok | 12 | 4552 | 4510 | 4677 | — |
| 58 | ok | 6 | 4532 | 4411 | 4660 | — |
| 59 | ok | 0 | 4493 | 4353 | 4618 | — |
| 60 | ok | 0 | 4510 | 4501 | 4634 | — |
| 61 | ok | 0 | 4497 | 4383 | 4621 | — |
| 62 | ok | 12 | 4529 | 4431 | 4655 | — |
| 63 | ok | 0 | 4494 | 4351 | 4617 | — |
| 64 | ok | 12 | 4532 | 4513 | 4657 | — |
| 65 | ok | 0 | 4505 | 4464 | 4630 | — |
| 66 | ok | 6 | 4487 | 4519 | 4613 | — |
| 67 | ok | 6 | 4495 | 4482 | 4622 | — |
| 68 | ok | 0 | 4498 | 4549 | 4623 | — |
| 69 | ok | 0 | 4492 | 4492 | 4618 | — |
| 70 | ok | 6 | 4494 | 4490 | 4617 | — |
| 71 | ok | 27 | 4484 | 4490 | 4610 | — |
| 72 | ok | 5 | 4492 | 4420 | 4618 | — |
| 73 | ok | 0 | 4491 | 4457 | 4617 | — |
| 74 | ok | 6 | 4480 | 4507 | 4605 | — |
| 75 | ok | 0 | 4509 | 4385 | 4634 | — |
| 76 | ok | 0 | 4477 | 4530 | 4601 | — |
| 77 | ok | 12 | 4472 | 4457 | 4596 | — |
| 78 | ok | 0 | 4477 | 4477 | 4603 | — |
| 79 | ok | 0 | 4490 | 4262 | 4615 | — |

## Interpretation guide

| Observation | Verdict |
|---|---|
| All pages OK | parser is bounded on this PDF set |
| Any page TIMEOUT | pdfminer pathological-input class confirmed for that page; capture for PE.2 design |
| Any page ERROR | non-timeout exception in extraction; capture error string |
| Peak KB consistently small across OK pages | parser memory cost is modest at this PDF scale |
| Worker ms > 5000 on OK pages | slow but bounded; consider tighter budget in production wrapper |

## Stop conditions encoded in this run

- Per-page hard timeout: **30 s** — exceeded → page recorded as TIMEOUT, orchestrator continues
- Per-count hard timeout: **60 s** — exceeded → PDF skipped, orchestrator continues to next PDF
- Worker exception → recorded as ERROR with stderr captured (first 500 chars); orchestrator continues
- Unparseable worker output → recorded as 'unparseable'; orchestrator continues
