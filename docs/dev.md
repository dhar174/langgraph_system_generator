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
