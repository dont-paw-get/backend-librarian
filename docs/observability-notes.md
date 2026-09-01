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

## 4. OTel Metrics / Prometheus ServiceMonitor는 구현하지 않음

요청 범위에서 명시적으로 제외되었다. 트레이싱(spans)과 로깅(logs)만 구현했고,
메트릭(metrics) 파이프라인은 다루지 않았다.
