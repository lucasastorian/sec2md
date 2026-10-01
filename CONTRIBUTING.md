# Contributing to sec2md

Thank you for considering contributing to `sec2md`! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/sec2md.git`
3. Create a virtual environment: `python -m venv venv`
4. Activate it: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
5. Install in development mode: `pip install -e ".[dev]"`

## Development Workflow

1. Create a new branch for your feature: `git checkout -b feature-name`
2. Make your changes
3. Run tests: `pytest`
4. Format code: `black src/ tests/`
5. Lint: `ruff check src/ tests/`
6. Commit your changes: `git commit -m "Description of changes"`
7. Push to your fork: `git push origin feature-name`
8. Open a pull request

## Code Style

- We use [Black](https://black.readthedocs.io/) for code formatting (100 char line length)
- We use [Ruff](https://docs.astral.sh/ruff/) for linting
- Write docstrings for all public functions and classes
- Add type hints where possible

## Testing

`pytest` runs offline in a few seconds:

- unit tests per module;
- golden tests (`tests/test_golden.py`): seven real filings in `tests/fixtures/`, one per layout
  family (listed in `tests/snapshot.py`), whose markdown and structure (elements, XBRL text blocks,
  sections, chunks, table cells lost) must match `tests/golden/` byte for byte. After an intended
  output change, run `python -m tests.snapshot` and let the reviewer read `git diff tests/golden`;
- invariants every parse must keep (`tests/test_invariants.py`).

A change to the parser is also measured on a larger corpus of filings (any directory of .html files):

    python benchmarks/bench.py run -j 8 --corpus path/to/filings -o before.json
    # ...the change...
    python benchmarks/bench.py run -j 8 --corpus path/to/filings -o after.json
    python benchmarks/bench.py compare before.json after.json

A refactor leaves every output hash unchanged and says so; any other change is a behavior change to
review (`run --dump DIR` writes the outputs for `diff -r`).

## Reporting Issues

- Use the [GitHub issue tracker](https://github.com/lucasastorian/sec2md/issues)
- Provide a clear description of the issue
- Include steps to reproduce if reporting a bug
- Include your Python version and operating system

## Questions?

Feel free to open an issue for questions or discussions about potential contributions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
