import pytest
from unittest.mock import MagicMock, patch
from main import app as flask_app


@pytest.fixture
def app():
    with patch('src.auth.GRL', True), \
         patch('google.cloud.ndb.Client', return_value=MagicMock()):
        flask_app.config.update({"TESTING": True})
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def mock_auth(mocker):
    mocker.patch('src.auth.is_logged_in', return_value=False)
    mocker.patch('src.auth.get_user_info', return_value=None)
