"""Shared fixtures: no test may hit the network.

The single live Open-Meteo call was recorded once to
``tests/fixtures/openmeteo_bells.json``. Here every HTTP attempt fails
fast so an accidental network dependency surfaces as an error, while
stale-cache fallback paths still work (they catch ``httpx.HTTPError``).
"""

import sys
from pathlib import Path

import httpx
import pytest

# Repo root on sys.path so `wavereader` imports however pytest is invoked
# (subset runs must not depend on other test modules' bootstraps).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    class _DeadClient:
        def __init__(self, *a, **k):
            raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(httpx, "Client", _DeadClient)
    yield
