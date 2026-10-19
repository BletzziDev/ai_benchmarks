# results/

Run outputs are written here (`results/<run_id>/`, see `aibench/core/artifacts.py` for the layout) and
are git-ignored, except `results/demo/`, which contains curated, clearly labelled demonstration
reports produced with the deterministic scripted adapters (`scripted/reference`, `scripted/noop`).
Those demos validate the pipeline and the graders; they are **not** measurements of any AI model.

Set `AIBENCH_RESULTS_DIR` to write elsewhere.
