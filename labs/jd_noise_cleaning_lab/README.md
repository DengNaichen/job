# JD Noise Cleaning Lab

Small standalone experiment for testing how to turn a noisy job description into
a cleaner embedding input.

This lab is intentionally separate from the production path. It reuses the
existing `StructuredJD` schema and HTML-to-text utility, but all heuristics live
only in this folder.

## What it does

- loads one sample job payload
- detects common JD sections
- drops obvious noise sections such as company boilerplate, benefits, legal, and
  application flow
- keeps high-signal evidence from responsibilities and requirements
- rebuilds a compact embedding text from:
  - title
  - structured fields
  - selected JD evidence lines

## Run

```bash
./.venv/bin/python labs/jd_noise_cleaning_lab/run.py \
  --input labs/jd_noise_cleaning_lab/sample_job.json
```

Optional output file:

```bash
./.venv/bin/python labs/jd_noise_cleaning_lab/run.py \
  --input labs/jd_noise_cleaning_lab/sample_job.json \
  --output labs/jd_noise_cleaning_lab/sample_output.json
```

Random real-job batch from the configured database:

```bash
./.venv/bin/python labs/jd_noise_cleaning_lab/fetch_real_samples.py \
  --limit 30 \
  --random \
  --output-dir labs/jd_noise_cleaning_lab/real_samples_random_30
```

## Expected use

Use this lab to answer questions like:

- Which sections are mostly noise for retrieval?
- How much of the original JD can be dropped safely?
- Does `title + structured fields + selected evidence` look better than the raw
  JD as embedding input?

This is a heuristic baseline, not a production recommendation by itself.
