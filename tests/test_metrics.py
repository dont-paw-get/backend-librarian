"""Prometheus HTTP 메트릭 (Micrometer 호환) 검증.

핵심 검증 대상:
- /actuator/prometheus 가 Prometheus 텍스트 포맷을 반환한다.
- 요청이 발생하면 http_server_requests_seconds_count / _bucket 시계열이 생성된다.
  (_bucket 이 있어야 infra 의 p99 histogram_quantile 알림이 동작)
- application 라벨 값이 OTEL_SERVICE_NAME 과 일치한다.
- 상태코드가 outcome 라벨(SUCCESS / CLIENT_ERROR / SERVER_ERROR)로 매핑된다.
- /health, /actuator/prometheus 자신은 메트릭에 집계되지 않는다.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.librarian.observability import metrics as metrics_module
from app.librarian.server import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _scrape(client: AsyncClient) -> str:
    resp = await client.get("/actuator/prometheus")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    return resp.text


class TestPrometheusEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_exposes_micrometer_metric_names(self, client: AsyncClient):
        await client.post("/chat", json={"message": "안녕", "librarian_id": "cat"})
        body = await _scrape(client)

        assert "http_server_requests_seconds_count" in body
        assert "http_server_requests_seconds_bucket" in body
        assert "http_server_requests_seconds_sum" in body

    @pytest.mark.asyncio
    async def test_application_label_matches_service_name(self, client: AsyncClient):
        await client.post("/chat", json={"message": "책 추천", "librarian_id": "cat"})
        body = await _scrape(client)

        assert f'application="{metrics_module._APPLICATION}"' in body
        assert 'uri="/chat"' in body
        assert 'outcome="SUCCESS"' in body
        assert 'status="200"' in body

    @pytest.mark.asyncio
    async def test_client_error_maps_to_client_error_outcome(self, client: AsyncClient):
        # 빈 메시지 → 422
        await client.post("/chat", json={"message": ""})
        body = await _scrape(client)

        assert 'outcome="CLIENT_ERROR"' in body
        assert 'status="422"' in body

    @pytest.mark.asyncio
    async def test_unmapped_path_folds_to_not_found(self, client: AsyncClient):
        await client.get("/definitely-not-a-route")
        body = await _scrape(client)

        assert 'uri="NOT_FOUND"' in body

    @pytest.mark.asyncio
    async def test_health_and_scrape_paths_are_not_counted(self, client: AsyncClient):
        await client.get("/health")
        await client.get("/actuator/prometheus")
        body = await _scrape(client)

        assert 'uri="/health"' not in body
        assert 'uri="/actuator/prometheus"' not in body


class TestOutcomeMapping:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (100, "INFORMATIONAL"),
            (200, "SUCCESS"),
            (301, "REDIRECTION"),
            (404, "CLIENT_ERROR"),
            (500, "SERVER_ERROR"),
            (503, "SERVER_ERROR"),
        ],
    )
    def test_outcome(self, status: int, expected: str):
        assert metrics_module._outcome(status) == expected
