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

- Write tests for new features
- Ensure all tests pass before submitting a PR
- Aim for good test coverage

## Reporting Issues

- Use the [GitHub issue tracker](https://github.com/lucasastorian/sec2md/issues)
- Provide a clear description of the issue
- Include steps to reproduce if reporting a bug
- Include your Python version and operating system

## Questions?

Feel free to open an issue for questions or discussions about potential contributions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
