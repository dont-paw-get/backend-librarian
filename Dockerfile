# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# 파이썬 런타임 최적화 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # uv: 가상환경 없이 시스템 파이썬에 설치
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

WORKDIR /app

# uv 설치 (의존성 설치/락파일 동기화용)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 의존성 먼저 설치 (레이어 캐시 활용)
# 락파일 기반으로 재현 가능한 설치. dev 그룹은 제외.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system -r requirements.txt

# 애플리케이션 소스
COPY app ./app

# 비루트 사용자로 실행
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 사서 HTTP 서버 (FastAPI/uvicorn). 포트/호스트는 아래에 고정.
CMD ["uvicorn", "app.librarian.server:app", "--host", "0.0.0.0", "--port", "8000"]
