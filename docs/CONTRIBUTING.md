# Contributing to Sophia

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Clone the repo
git clone https://github.com/your-org/sophia-ai.git
cd sophia-ai

# Install dependencies (including dev extras)
uv sync --all-extras

# Copy environment config
cp .env.example .env
# Edit .env with your API keys
```

### Running the Server

```bash
uv run uvicorn sophia.main:app --reload
```

### Running Tests

```bash
uv run pytest
```

Tests use mock LLM providers — no API keys needed to run the test suite.

## Project Structure

```
sophia/
├── api/          # FastAPI routes and schemas
├── core/         # Pipeline: input gate, proposer, executor, loop
├── hats/         # Hat system: schema, loader, registry, prompt assembler
├── llm/          # LLM providers and core prompts
├── memory/       # Memory store (loads from active hat)
├── tools/        # Tool ABC and registry
├── config.py     # Settings via pydantic-settings
└── main.py       # FastAPI app entry point

hats/             # Hat implementations (outside the sophia package)
├── customer-service/
└── (your hat here)

tests/
├── core/         # Unit tests for pipeline components
├── hats/         # Unit tests for hat system
├── integration/  # Full pipeline integration tests
└── conftest.py   # Shared fixtures and mock LLM
```

## How to Contribute

### Building a New Hat

The most impactful way to contribute is creating a new Hat for a domain. See [Creating Hats](CREATING_HATS.md) for a full walkthrough.

### Fixing Bugs or Adding Features

1. Check the [phase roadmap](ARCHITECTURE.md#phase-roadmap) to understand what's planned.
2. Open an issue describing what you want to change and why.
3. Fork the repo and create a branch from `main`.
4. Make your changes with tests.
5. Run the full test suite: `uv run pytest`
6. Run the linter: `uv run ruff check .`
7. Submit a pull request.

### Writing Tests

- **Unit tests** go in `tests/core/` or `tests/hats/` depending on what they cover.
- **Integration tests** go in `tests/integration/`.
- Use the `MockLLMProvider` from `tests/conftest.py` — never make real API calls in tests.
- Use `pytest-asyncio` for async tests (the project uses `asyncio_mode = "auto"`).
- Use the shared fixtures (`mock_llm`, `tool_registry`, `cs_hat_config`) from `conftest.py`.

Example:

```python
import pytest
from tests.conftest import MockLLMProvider

@pytest.mark.asyncio
async def test_my_feature(mock_llm: MockLLMProvider, tool_registry):
    mock_llm.set_responses(["..."])
    # test logic here
```

## Code Style

- **Formatter/linter**: [Ruff](https://docs.astral.sh/ruff/)
- **Line length**: 100 characters
- **Target version**: Python 3.11
- **Type hints**: Use them on public interfaces. Don't over-annotate internal code.
- **Docstrings**: Only where the purpose isn't obvious from the name and signature.

Run the linter before submitting:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Architecture Guidelines

- **Hats, not hardcoding.** Domain logic belongs in a Hat, never in `sophia/core/` or `sophia/tools/`.
- **Propose, don't execute.** The LLM suggests actions. The pipeline decides whether to carry them out.
- **Keep the core minimal.** The framework should work with any domain. If your change only applies to one domain, it belongs in a Hat.
- **Mock everything external.** Tests should never require API keys, network access, or databases.
- **Async by default.** Tools and pipeline components are async. Use `async def` and `await`.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
