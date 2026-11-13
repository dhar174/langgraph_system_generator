# #334-B offline verification

Part of #334; related to #129. The study and the Luna request migration
were exercised offline. Live semantic reviewer quality remains unmeasured.

## Production migration checkpoint

The fetched base was `63576b4efc283e6e8404ec9cfaef6801b77b81e1`
(PR #401). The production migration and fixture generation baseline was
`0da1b02387a1bc15844aa2f7e24207382ec48995`. Tests at that revision used
Python 3.12.2 on Windows, a task-private environment with the project's GCP
extra, and the offline qualification guard. LangChain OpenAI 1.7.2, OpenAI
3.35.1, and nbconvert 7.16.6 were installed in that environment.

| Command at migration checkpoint | Exit | Observed result |
| --- | ---: | --- |
| `python -m pytest tests/unit -k "semantic or credential or endpoint or outcomes or luna" --asyncio-mode=auto -q` | 0 | 395 passed, 1,147 deselected |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 0 | 1,542 passed |
| `python -m pytest tests/patterns/ -v` | 0 | 82 passed |
| `python -m pytest --asyncio-mode=auto -ra` | 0 | 1,661 passed, 7 skipped |
| `python scripts/qualify_durable_backend.py --level sdk --test-timeout 900 --receipts output/qualification/migration-exact-sdk` | 0 | 244 passed, 0 skipped |
| `python scripts/run_generated_notebook_eval.py --qualify-outcomes --output output/migration-exact-381` | 0 | 3 fixtures, 110 assertions, 4 negative controls |
| `python -m pytest tests/unit/test_documentation_coverage.py -q` | 0 | 5 passed |
| `python -m flake8 src tests scripts --count --select=E9,F63,F7,F82 --show-source --statistics` | 0 | 0 findings |

The full suite skipped four Firestore emulator opt-ins and three packaging
install smoke opt-ins. The exact fetched base passed durable SDK
qualification (243 tests, no skips) and the same three #381 fixtures and
four negative controls. The #381 evaluator, its existing fixture source,
and the historical six-case semantic contract set retain their own scope.
The local stub export smoke produced a valid notebook, HTML, and a
four-member ZIP. Its generation outcome carried `not_run` execution
status. The export command exited 0.

```text
python -m langgraph_system_generator.cli generate "Create a router-based customer support chatbot with billing and technical routes." --mode stub --output ./output/334-b-stub-verified --formats ipynb html zip
```

Broad static diagnostics at the migration checkpoint were compared with
the exact fetched base. Both revisions returned exit 1 for each broad
command.

| Command | Base | Migration checkpoint | Added diagnostics |
| --- | ---: | ---: | ---: |
| `python -m ruff check src tests scripts examples --output-format=json` | 1,375 | 1,375 | 0 |
| `python -m black --check src tests scripts examples` | 89 files | 88 files | 0 |
| `python -m mypy src` | 104 | 101 | 0 |
