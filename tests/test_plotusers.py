import json
from unittest.mock import patch, MagicMock


def test_plotusers_no_history(client, mocker):
    """Returns 200 with a no-data message when no history exists."""
    mocker.patch('src.routes.db.get_setting', return_value=None)
    response = client.get('/plotusers')
    assert response.status_code == 200
    assert b'no data' in response.data.lower()


def test_plotusers_with_history(client, mocker):
    """Returns 200 and embeds the points JSON and updated date."""
    points = [
        {'month': '2012-09', 'count': 320},
        {'month': '2026-05', 'count': 314925},
    ]
    history = json.dumps({'updated': '2026-05-20', 'points': points})
    mocker.patch('src.routes.db.get_setting', return_value=history)

    response = client.get('/plotusers')

    assert response.status_code == 200
    assert b'314925' in response.data
    assert b'2026-05-20' in response.data


def test_plotusers_loads_local_plotly(client, mocker):
    """Template references the local plotlyVP7.min.js, not a CDN."""
    mocker.patch('src.routes.db.get_setting', return_value=None)
    response = client.get('/plotusers')
    assert b'plotlyVP7.min.js' in response.data


def test_update_user_count_no_auth_header(client):
    """Returns 403 when Authorization header is absent."""
    response = client.get('/admin/update-user-count')
    assert response.status_code == 403


def test_update_user_count_appends_new_point(client, mocker):
    """Appends a new data point to existing history and returns 200."""
    existing = {
        'updated': '2026-04-01',
        'points': [{'month': '2012-09', 'count': 320}],
    }
    mocker.patch('src.routes.db.count_users', return_value=314925)
    mocker.patch('src.routes.db.get_setting', return_value=json.dumps(existing))
    set_mock = mocker.patch('src.routes.db.set_setting')

    mock_claim = {'email': 'test-sa@example.iam.gserviceaccount.com'}
    with patch('src.routes._SCHEDULER_SA', 'test-sa@example.iam.gserviceaccount.com'), \
         patch('src.routes._SCHEDULER_AUDIENCE', 'https://example.com/admin/update-user-count'), \
         patch('google.oauth2.id_token.verify_oauth2_token', return_value=mock_claim):
        response = client.get(
            '/admin/update-user-count',
            headers={'Authorization': 'Bearer faketoken'}
        )

    assert response.status_code == 200
    _key, written_value = set_mock.call_args[0]
    written = json.loads(written_value)
    assert len(written['points']) == 2
    assert written['points'][-1]['count'] == 314925
    assert written['points'][-1]['month'][4] == '-'
    assert written.get('updated') != '2026-04-01'


def test_update_user_count_creates_history_when_missing(client, mocker):
    """Creates a new history entry when none exists."""
    mocker.patch('src.routes.db.count_users', return_value=100)
    mocker.patch('src.routes.db.get_setting', return_value=None)
    set_mock = mocker.patch('src.routes.db.set_setting')

    mock_claim = {'email': 'test-sa@example.iam.gserviceaccount.com'}
    with patch('src.routes._SCHEDULER_SA', 'test-sa@example.iam.gserviceaccount.com'), \
         patch('src.routes._SCHEDULER_AUDIENCE', 'https://example.com/admin/update-user-count'), \
         patch('google.oauth2.id_token.verify_oauth2_token', return_value=mock_claim):
        response = client.get(
            '/admin/update-user-count',
            headers={'Authorization': 'Bearer faketoken'}
        )

    assert response.status_code == 200
    set_mock.assert_called_once()
    _key, written_value = set_mock.call_args[0]
    written = json.loads(written_value)
    assert len(written['points']) == 1
    assert written['points'][0]['count'] == 100
