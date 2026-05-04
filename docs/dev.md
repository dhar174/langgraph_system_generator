# Development Quickstart

1. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -e ".[full,dev]"
   ```

3. **Configure environment**
   - Copy `.env.example` to `.env`
   - Populate API keys and other settings as needed

4. **Run tests**
   ```bash
   python -m pytest
   ```

   Release-readiness gates:

   ```bash
   python scripts/run_release_eval.py --no-upload
   RUN_PACKAGING_SMOKE=1 PACKAGING_SMOKE_SCENARIOS=minimal,api python -m pytest tests/integration/test_packaging_install_smoke.py -q
   RUN_PACKAGING_SMOKE=1 PACKAGING_SMOKE_SCENARIOS=full python -m pytest tests/integration/test_packaging_install_smoke.py -q
   ```

5. **Import the package**
   ```python
   import langgraph_system_generator
   from langgraph_system_generator.utils.config import settings
   ```

## Logging and diagnostics

- The CLI now accepts `--log-level` (default comes from `LNF_LOG_LEVEL` or `INFO`)
  so you can enable verbose output without modifying code.
- The API layer configures the same logging helper on startup; set
  `LNF_LOG_LEVEL=DEBUG` when running uvicorn to surface detailed traces.
- Logs are formatted consistently as ISO timestamps with level, logger name, and
  message to simplify grepping and log aggregation.

## Release metadata

- The root `LICENSE` file is the MIT license source used by GitHub and package
  metadata.
- `CHANGELOG.md` records release-facing changes.
- `setup.py` and `src/langgraph_system_generator/__init__.py` must carry the
  same package version before tagging a release.
