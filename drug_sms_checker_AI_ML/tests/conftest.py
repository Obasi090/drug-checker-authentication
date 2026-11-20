import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATALOGUE_CSV = ROOT / "data" / "test_drugs.csv"


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run the opt-in live Gemini tests (requires a configured GEMINI_API_KEY).",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: opt-in live Gemini API test, never part of the offline suite")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="live Gemini tests require --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="module")
def live_client():
    """Opt-in live client. The key value is never printed."""
    from src.gemini import GeminiClient

    client = GeminiClient(force_mock=False)
    if not client.available:
        pytest.skip("GEMINI_API_KEY is not configured (or AI_ML_MOCK is enabled)")
    return client
