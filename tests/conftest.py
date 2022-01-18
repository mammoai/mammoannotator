import pytest
import os

@pytest.fixture(scope='session')
def TESTS_PATH():
    return os.path.dirname(__file__)