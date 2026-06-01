import pytest
from pathlib import Path
import tempfile
import os


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_home():
    """Mock HOME for config/session tests."""
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        os.environ["HOME"] = d
        os.environ["USERPROFILE"] = d
        yield Path(d)
        if old:
            os.environ["HOME"] = old
            os.environ["USERPROFILE"] = old
