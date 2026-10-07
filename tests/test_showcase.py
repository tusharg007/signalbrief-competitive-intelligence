from fastapi.testclient import TestClient

from signalbrief.api import create_app


def test_only_explicitly_published_approved_records_are_public(settings, store, ready_run):
    settings.showcase_run_ids = ready_run
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/runs').status_code == 401
        assert client.get('/api/showcase/runs').json() == []
        assert client.get('/api/showcase/runs/' + ready_run).status_code == 404
        store.review(ready_run, 1, 'approve', 'Evidence reviewed', 'http://testserver')
        run = client.get('/api/showcase/runs/' + ready_run).json()
        assert run['status'] == 'approved' and run['sources'] and run['audit']
        assert all('payload' not in d and 'receipt' not in d for d in run['deliveries'])
        assert client.get('/api/showcase/runs/' + ready_run + '/report.md').status_code == 200
        assert client.post('/api/runs/' + ready_run + '/review', json={}).status_code == 401
        assert client.post('/api/showcase/runs/' + ready_run).status_code == 405
        assert client.get('/api/showcase/runs/other').status_code == 404


def test_approved_but_unpublished_records_stay_private(settings, store, ready_run):
    store.review(ready_run, 1, 'approve', '', 'http://testserver')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/showcase/runs').json() == []
        assert client.get('/api/showcase/runs/' + ready_run).status_code == 404


def test_readiness_requires_recent_worker_heartbeat(settings, store):
    with TestClient(create_app(settings)) as client:
        assert client.get('/ready').status_code == 503
        store.worker_seen('test-worker')
        assert client.get('/ready').status_code == 200
