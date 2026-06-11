# Evaluation

## Fixtures

`klave_engine.evals.fixtures` builds a deterministic synthetic project
(`write_demo_project`): a 2×2 grid (A/B × 1/2), two columns with circles and
footings, one duplicate column tag far off-grid, a beam with tag, a slab
polyline, a wall pair, and two detail references (one resolved, one dangling).
`DEMO_GOLD` holds the expected detections, semantic node counts, quantities,
and risk types.

## Metrics

- **Detection eval** (`detection_eval.py`): per detection type, labels matched
  as multisets → precision, recall, F1, FP/FN counts.
- **Graph eval** (`graph_eval.py`): semantic node counts by type vs expected;
  detail-reference resolution summary.
- **Takeoff eval** (`takeoff_eval.py`): absolute and percentage error per
  quantity; pass threshold 5%.

## Running

```bash
make eval-demo          # or: uv run python -m klave_engine.evals.regression_suite
```

Writes `reports/eval_summary.json` and `reports/eval_summary.md` with an
overall PASS/FAIL.

## Regression policy

When a bug is found: add a failing test, fix the bug, keep the test. The demo
gold labels pin the end-to-end behavior; change them only when the change in
behavior is intentional and reviewed.
