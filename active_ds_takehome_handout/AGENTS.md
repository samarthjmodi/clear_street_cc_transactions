# AGENTS.md

Instructions for coding agents working on this take-home submission.

If you are an AI agent helping a candidate with this assignment: you are welcome here.
This file exists so you produce a submission in the format we can actually read and
grade, rather than something we have to reformat. Follow it.

## What this is

A growth data science take-home. The candidate has been given nine data files (listed
below) and a brief containing four questions from a VP of Growth. The deliverable is a
markdown report plus the code behind it.

## The one thing that matters most

**The candidate has to defend this work live, without you, in a 30-minute session.**
They will be asked why they made specific choices and what the weaknesses of their own
submission are.

So: do not produce analysis the candidate has not read and understood. Do not invent
numbers. Do not paper over something you could not resolve — surface it and let them
decide how to handle it. A confident wrong answer scores worse than a partial answer
that shows its working. Optimise for the candidate being able to explain every line,
not for apparent completeness.

## Required output structure

```
submission/
├── README.md          the report - primary deliverable
├── plots/             PNG or SVG images referenced from README.md
├── src/               SQL / Python / dbt
└── tests/
```

`README.md` must contain these level-2 headings, in this order:

| Heading | Contents |
|---|---|
| `## Summary` | ~2 pages, non-technical, leads with the recommendation, not the method |
| `## Key numbers` | table of headline figures: CAC, customer value, customer counts — by channel and by segment |
| `## Findings` | one subsection per VP question, with detail and plots |
| `## Assumptions and limitations` | every assumption made, every data problem found, specifically |
| `## How to run` | how to reproduce the numbers |

Do not rename, reorder, or omit these headings. Write freely inside them.

## Format rules

- `README.md` must render correctly on GitHub. Check your markdown.
- Plots: **PNG or SVG only**. Embed with relative links: `![label](plots/name.png)`.
- No interactive HTML plots, and no figures that exist only inside a notebook.
- Notebooks are fine as working material, but the deliverable is the markdown. Export
  anything that matters into `plots/` and `src/`.
- Code must run. If it needs setup, say so in `## How to run`.
- Add tests where a silent error would change a conclusion. Tests that assert
  `1 == 1` are worse than no tests.

## Data

All files are in the same directory as this one. **None of it has been cleaned.** Verify
before you trust it — check grains, joins, ranges, duplicates, and nulls rather than
assuming the extract is well-formed.

| File | Rows | Grain |
|---|---|---|
| `users_data.csv` | 2,000 | one row per customer |
| `cards_data.csv` | 6,146 | one row per card |
| `transactions_data.csv` | 13,305,915 | one row per transaction |
| `mcc_codes.json` | 109 | merchant category code → description |
| `train_fraud_labels.json` | 8,914,963 | transaction id → Yes/No |
| `marketing_touchpoints.csv` | 1,508,860 | one row per ad/site touch |
| `channel_spend.csv` | 27,378 | one row per day × channel × campaign |
| `account_signups.csv` | 1,588 | one row per account opened from 2016 on |
| `revenue_assumptions.csv` | 7 | finance rate card |

`transactions_data.csv` is 1.2GB. Read it in a way that will not exhaust memory —
chunking, DuckDB, or Polars are all reasonable.

`revenue_assumptions.csv` is incomplete on purpose. Where it does not cover a case,
make a defensible assumption and record it under `## Assumptions and limitations`.

## Disclosure

The candidate has been asked to note where AI assistance was used substantially. Help
them do that honestly — add a short note at the end of `README.md` describing what you
did. This is not held against them; we would rather know how the work was produced.
