# Persian Equivalence Matrix

## Result summary

The read-only staging matrix used 20 synthetic variants, fresh history, concurrency 1, current General_FAQ data, unchanged retrieval/reranker thresholds, and no answer-generation calls. The exact pair was separately run through final generation.

| Metric | Before | After |
|---|---:|---:|
| Classifier route consistency | 100% | 100% |
| Top-1 consistency with reference | 75% | 95% |
| Mean top-5 overlap with reference | 32.24% | 83.65% |
| Intended FAQ present in selected top 10 | 10% | 100% |
| Exact-pair same normalized text | No | Yes |
| Exact-pair same selected context | No | Yes |
| Exact-pair top-5 overlap | 25% | 100% |
| Exact-pair embedding cosine | 0.737812 | 1.000000 |
| Related-reranker acceptance rate | 2% | 1% |

The reranker acceptance rate is not an answer-quality gate in this application; it describes only related-question suggestions. It was not optimized and its threshold remained 0.1.

## Per-variant matrix

`Target` means point 173 was present anywhere in the answer context. `Rerank top` is the best related-question candidate, not the answer-context selector.

| # | Raw synthetic query | Canonical form | Top retrieval before | Top retrieval after | Target before → after | Rerank top after | Route |
|---:|---|---|---|---|---|---|---|
| 1 | میشه اسم حساب هارو بگی | `میشه اسم حساب هارو بگی` | 703 (.028531) | 703 (.028531) | yes → yes | 703 (.000509) | general |
| 2 | میشه اسم حساب ها رو بگی | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 3 | میشه اسم حساب‌ها رو بگی | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 4 | میشه اسم حسابها رو بگی | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 5 | میشه اسم حساب‌ها را بگی | `میشه اسم حساب هارو بگی` | 703 (.029206) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 6 | میشه اسم حساب ها را بگی | `میشه اسم حساب هارو بگی` | 703 (.029206) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 7 | می‌شه اسم حساب‌ها رو بگی | `میشه اسم حساب هارو بگی` | 703 (.030769) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 8 | می شه اسم حساب ها رو بگی | `میشه اسم حساب هارو بگی` | 703 (.030769) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 9 | می‌شود اسم حساب‌ها را بگویید | `میشه اسم حساب هارو بگویید` | 68 (.027347) | 703 (.028219) | no → yes | 918 (.000573) | general |
| 10 | اسم حساب‌ها چیست؟ | `اسم حساب هارو بگی` | 57 (.027894) | 703 (.029206) | no → yes | 703 (.000066) | general |
| 11 | اسم حساب ها چیست؟ | `اسم حساب هارو بگی` | 57 (.027894) | 703 (.029206) | no → yes | 703 (.000066) | general |
| 12 | اسم حسابها چیست؟ | `اسم حساب هارو بگی` | 57 (.028475) | 703 (.029206) | no → yes | 703 (.000066) | general |
| 13 | leading/trailing spaces | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 14 | repeated spaces | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 15 | Arabic ي form | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 16 | ZWJ suffix separator | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000509) | general |
| 17 | NBSP suffix separator | `میشه اسم حساب هارو بگی` | 703 (.029469) | 703 (.028531) | no → yes | 703 (.000507) | general |
| 18 | Persian question mark | `میشه اسم حساب هارو بگی ؟` | 703 (.029469) | 703 (.028860) | no → yes | 703 (.000466) | general |
| 19 | ASCII question mark | `میشه اسم حساب هارو بگی ?` | 703 (.029274) | 703 (.028860) | no → yes | 703 (.000370) | general |
| 20 | حساب‌های Hibank | `میشه اسم حساب‌های Hibank رو بگی` | 68 (.031754) | 68 (.031754) | yes → yes | 67 (.220846) | general |

## Exact-pair final generation

Both final traces selected:

`703, 918, 68, 97, 705, 173, 102, 766, 595, 425`

Point 173 was rank 6. Both context hashes were identical. Both generated the two intended account types and neither used the fallback. Minor wording/spacing differed because FAQ generation currently uses temperature 1.

## False-equivalence guardrails

Tests assert that normalization does not collapse these pairs:

- `حساب بانکی` versus `حساب کاربری گیت‌هاب`
- `کارت بانکی` versus `کارت گرافیک`
- `رمز Hibank` versus `رمز وای‌فای`

Tests also preserve card/account-number characters, phone-number characters, URLs, and mixed Latin identifiers.

## KB-derived phrase families

| Family | Canonical output |
|---|---|
| `احراز هویت`, `احراز‌هویت`, `احرازهویت`, repeated-space form | `احراز هویت` |
| `افتتاح حساب`, `افتتاح‌حساب`, `افتتاححساب` | `افتتاح حساب` |
| `شماره حساب`, `شماره‌حساب`, `شمارهحساب` | `شماره حساب` |
| `قرض الحسنه`, `قرض‌الحسنه`, `قرضالحسنه` | `قرض الحسنه` |
| `سفر فصلی چیه`, `سفرفصلی چیه` | `سفر فصلی چیه` |

The current checkpoint routes both travel forms to `general` with identical
confidence `0.9990590215`. The KB contains 22 chunks in the `سفر فصلی من`
category, so this is domain-backed rather than generic word segmentation.

## Larger adversarial matrix

A second read-only run sampled six General_FAQ points across account information, account opening, transfers, customer-club loans, checks, and card-to-card service. For every source it generated standard, missing-ZWNJ, extra-space, Arabic `ي/ك`, punctuation-free, colloquial, one-character-typo, and short variants (48 total).

| Metric | Result |
|---|---:|
| Classifier `general` rate | 100% |
| Target point in top 10, all variants | 100% |
| Target point in top 10, orthographic variants | 100% |
| Target point in top 10, colloquial/typo/short variants | 100% |

Sanitized machine results are written to ignored paths and are not committed:

- `benchmarks/results/persian_normalization/equivalence-matrix.json`
- `benchmarks/results/persian_normalization/adversarial-sample.json`

Run both diagnostics with:

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /root/miniconda3/envs/faq/bin/python benchmarks/persian_normalization_diagnostic.py
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /root/miniconda3/envs/faq/bin/python benchmarks/persian_normalization_adversarial.py
```
