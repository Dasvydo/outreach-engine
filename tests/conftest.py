import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from engine import ledger


@pytest.fixture
def clean_ledger(tmp_path):
    """An isolated ledger shim per test, so dedup tests are not order dependent."""
    ledger.use_shim_dir(tmp_path / "ledger")
    yield ledger
    ledger.use_shim_dir(ledger.SHIM_DIR)
