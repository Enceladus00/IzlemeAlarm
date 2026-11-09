import pytest

from backend.rate_limit import limiter


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """The limiter is process-wide; one test's requests must not count against another."""
    limiter.reset()
    yield
    limiter.reset()
