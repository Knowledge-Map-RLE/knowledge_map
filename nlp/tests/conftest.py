import pytest

@pytest.fixture()
def before_after():
    print('\nBefore')
    yield
    print('\nAfter')