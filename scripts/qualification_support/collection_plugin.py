"""Write exact collection identities for the runner's JUnit accounting."""

import json
import os
from pathlib import Path


def pytest_collection_finish(session):
    Path(os.environ["LNF_QUALIFICATION_COLLECTION"]).write_text(
        json.dumps([item.nodeid for item in session.items], indent=2), encoding="utf-8"
    )
