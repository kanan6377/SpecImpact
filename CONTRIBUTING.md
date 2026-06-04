# Contributing

Use Python 3.11 or later. Before submitting a change, run:

```powershell
python -m pip install -e .[dev]
pytest
ruff check
specimpact release-check ./examples/evaluation/release_cases.yml
```

New extraction behavior must include evidence, source location, parser tests, and an evaluation
case. Do not add external provider calls to unit tests.
