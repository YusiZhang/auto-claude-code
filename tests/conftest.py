"""Shared test fixtures."""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_acc_dir():
    """Give each test its own ACC data directory."""
    _tmp = tempfile.mkdtemp()
    os.environ["ACC_HOME"] = _tmp
    from acc.db import init_db
    init_db()
    yield _tmp
