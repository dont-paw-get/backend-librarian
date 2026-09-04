# Observability 구현 노트 — 한계 및 미반영 사항

이 문서는 backend-librarian에 OpenTelemetry 트레이싱/JSON 로깅을 적용하면서
발견된 한계와, 이 레포의 책임 범위를 벗어나 반영하지 못한 부분을 정리한다.

## 1. Strands Agent의 예외 span에 IAM ARN이 포함될 수 있음 (미해결)

**현상**: Bedrock 호출이 `AccessDeniedException` 등으로 실패하면, Strands 라이브러리
(`strands/telemetry/tracer.py`의 `Tracer._end_span`)가 `span.record_exception(error)`를
**무조건** 호출한다. botocore의 `ClientError` 예외 메시지 문자열 안에는 다음과 같이
IAM 사용자/정책 ARN이 그대로 들어있다.

```
AccessDeniedException: User: arn:aws:iam::<account-id>:user/<user>
is not authorized ... with an explicit deny in an identity-based policy:
arn:aws:iam::<account-id>:policy/<policy-name>
```

이 값은 access key / secret key / session token 같은 자격증명(credential) 자체는
아니지만, AWS 계정 ID와 IAM 사용자/정책 이름이라는 식별 정보를 포함한다.

**왜 못 고쳤나**: `OTEL_SEMCONV_STABILITY_OPT_IN`으로 강제한 redaction은
`gen_ai.input.messages` / `gen_ai.output.messages` / `gen_ai.system_instructions`
등 프롬프트·응답 콘텐츠에만 적용되도록 Strands 라이브러리에 하드코딩되어 있고,
`span.record_exception()` 호출 경로에는 별도의 redaction 훅이 없다.
즉 애플리케이션 코드(이 레포)에서 끌 수 있는 설정이 아니라 Strands 라이브러리
내부 동작이다.

**애플리케이션 로그는 안전함**: `app/librarian/bedrock_agent.py`의
`_log_agent_failure()`는 `str(error)` 원문이 아니라 `type(error).__name__`
(예: `AccessDeniedException`)만 `extra`로 기록하므로, 우리 JSON 로그(stdout →
Loki)에는 ARN이 남지 않는다. 문제가 되는 지점은 **Tempo로 전송되는 span의
exception 이벤트**뿐이다.

**해결하려면 (이번 범위에서는 미적용)**:
- OTel Collector의 processor(`attributes` processor 등)로 `exception.message`
  값을 정규식으로 마스킹 — dpgy-infra의 Collector 설정에서 처리 가능
- 또는 Strands 쪽에 라이브러리 이슈 제기
- 또는 Bedrock 호출부에서 예외를 캐치해 ARN을 제거한 새 예외로 재발생시키는
  방식(현재는 라이브러리 내부에서 예외가 나기 전에 span이 먼저 열려있어 적용이
  까다로움 — Agent 호출 자체를 우리가 try/except로 감싸도 `record_exception`은
  Strands 내부에서 이미 호출된 뒤이므로 사후 마스킹은 불가)

## 2. Grafana(Alloy/Loki, OTel Collector/Tempo) 연동은 이 레포의 책임 범위 밖

이 레포(backend-librarian)가 하는 일은 다음 두 가지뿐이다.
1. `OTEL_EXPORTER_OTLP_ENDPOINT`로 지정된 곳에 OTLP/HTTP로 span을 보낸다.
2. stdout에 JSON 로그를 찍는다.

그 다음 단계 — Collector가 span을 Tempo에 저장하고, Alloy가 stdout을 읽어
Loki에 넣는 것 — 는 **dpgy-infra 쪽 Kubernetes/Grafana 스택 설정**이며,
이 레포에는 관련 매니페스트가 존재하지 않는다(레포 확인 결과 Dockerfile/k8s/
Kustomize 파일 없음). 이 레포 코드를 배포한 뒤 아래 두 조건만 맞으면
자동으로 연동된다.
- Pod가 stdout으로 로그를 출력 (컨테이너 기본 동작, 추가 설정 불필요)
- Pod 환경변수에 `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.monitoring.svc.cluster.local:4318`
  가 주입되어 있음 (배포/인프라 담당자가 dpgy-infra에서 설정)

즉 "Grafana에 실제로 보이는지"는 이 레포 밖에서 인프라가 맞게 구성됐는지에
달려 있으며, 이 레포 관점에서는 코드가 보낼 준비가 되어 있음을 테스트로
확인했다(`tests/test_observability.py`).

## 3. prod 설정은 이번 작업에서 변경하지 않음

요청 범위가 dev 한정이었으므로 prod용 OTel 환경변수 설정은 건드리지 않았다.
prod에 트레이싱을 켜려면 별도로 `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_TRACES_SAMPLER_ARG`(prod는 보통 1.0보다 낮은 값 권장) 등을 dpgy-infra의
prod 설정에 추가하는 별도 작업이 필요하다.

## 4. Prometheus HTTP 메트릭 / ServiceMonitor (CLIAR-222 후속으로 추가됨)

> 최초 CLIAR-222 범위에서는 메트릭이 제외되어 있었으나, infra 의 "HTTP 5xx 에러율" /
> "p99 레이턴시" 알림 규칙이 이 서비스의 Micrometer 형식 메트릭을 전제로 하므로 후속 작업에서 추가했다.

**구현 방식** (`app/librarian/observability/metrics.py`):
- FastAPI(비-Spring) 서비스지만 Spring Boot / Micrometer 와 **동일한 메트릭 이름·라벨**을
  노출한다. `prometheus_client.Histogram("http_server_requests_seconds", ...)` 하나가
  `http_server_requests_seconds_count` / `_sum` / `_bucket` 시계열을 파생하며,
  `_bucket` 이 있어 `histogram_quantile()` 기반 p99 알림이 그대로 동작한다.
- 라벨: `application`(= `OTEL_SERVICE_NAME` = `backend-librarian`), `method`, `uri`,
  `status`, `outcome`(Micrometer 분류: SUCCESS / CLIENT_ERROR / SERVER_ERROR ...).
- 순수 ASGI 미들웨어(`PrometheusMiddleware`)로 모든 요청을 계측한다.
  `BaseHTTPMiddleware` 를 피해 `stream=true` StreamingResponse 와의 충돌을 방지한다.
- `/actuator/prometheus` 로 노출(Micrometer 호환 경로). 헬스체크/스크레이핑/probe 경로는
  집계에서 제외한다(트레이스 `_EXCLUDED_URLS` 정책과 일치).
- 매핑되지 않은 경로(스캐너 등)는 `uri="NOT_FOUND"` 로 접어 카디널리티를 방어한다.

**스크레이핑** (`k8s/overlays/dev/servicemonitor.yaml`):
- `ServiceMonitor/backend-librarian` (namespace `dpyb-librarian-dev`), `interval: 30s`,
  `path: /actuator/prometheus`, Service 의 `http` 포트(8000) 대상.
- monitoring 스택은 dev 클러스터에만 있으므로 base 가 아닌 dev overlay 에만 둔다.

**이 레포 밖**: Prometheus 가 실제로 이 ServiceMonitor 를 픽업하는지(=
`serviceMonitorSelectorNilUsesHelmValues=false` 설정, RBAC)는 dpgy-infra 책임이다.

## 5. OTLP 프로토콜/파이프라인 명시 (dev overlay)

`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_METRICS_EXPORTER=none`,
`OTEL_LOGS_EXPORTER=none` 를 dev configmap 에 추가했다. infra Collector 는 traces
파이프라인만 받고 gRPC(4317)는 미개방이므로 http/protobuf + 4318 를 강제한다.
메트릭은 Prometheus 스크레이핑, 로그는 stdout→Alloy→Loki 경로를 쓰므로 OTLP
metrics/logs export 는 끈다.

## 6. Bedrock 모델 ID — global 크로스리전 inference profile

베어 모델 ID 는 ap-northeast-2 에서 on-demand 호출이 거부되므로 크로스리전
inference profile 로 호출한다. 현재 `global.anthropic.claude-haiku-4-5-20251001-v1:0`(global 크로스리전
프로파일, 전 리전 라우팅)를 쓴다.

- **적용 범위**: dev configmap(`k8s/overlays/dev/configmap-patch.yaml`), base configmap
  (`k8s/base/configmap.yaml`, prod 상속), `app/librarian/agent.py` 의 `DEFAULT_MODEL_ID`
  까지 모두 동일한 global 프로파일로 통일했다.
- **전제**: 계정에서 Claude Haiku 4.5 model access 가 enable 되어 있고
  `global.anthropic.claude-haiku-4-5-20251001-v1:0` 프로파일이 존재해야 한다
  (`aws bedrock list-inference-profiles` 로 확인).
- `top_p` 등 deprecated 파라미터나 assistant prefill 은 코드에서 사용하지 않는다(`BedrockModel`
  에 `model_id` / `region_name` 만 전달).
