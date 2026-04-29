# Development Quickstart

1. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   - Copy `.env.example` to `.env`
   - Populate API keys and other settings as needed

4. **Run tests**
   ```bash
   python -m pytest
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
