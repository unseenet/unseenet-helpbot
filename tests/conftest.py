"""Shared test setup, as in unseenet's own tests."""
import pytest

from unseenet.core import ripening


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Keys' state files go to the test's folder, never ~/.unseenet."""
    monkeypatch.setenv("UNSEENET_STATE_DIR", str(tmp_path / "keys"))


@pytest.fixture(autouse=True)
def fast_ripening():
    """Key ripening (UN-RFC 0025) with thresholds divided by 2^16 and no rules, so a
    test's new keys post at once; the bot still ripens and publishes ripe@."""
    ripening.scale_for_tests(16, rules=False)
    yield
    ripening.scale_for_tests(0)
