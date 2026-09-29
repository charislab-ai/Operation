# 프로덕션 통합 배포용 Dockerfile (Railway 등에서 사용)
# 프론트엔드(React/Vite)를 빌드해 백엔드(FastAPI) 하나가 정적 파일 + API를 모두 서빙한다.
# 로컬 개발용 backend/Dockerfile, frontend/Dockerfile, infra/docker-compose.yml은 그대로 유지(별개 용도).

# --- 1단계: 프론트엔드 빌드 ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# 같은 오리진에서 서빙되므로 API_BASE는 빈 값(상대경로)으로 빌드
ENV VITE_API_BASE_URL=""
ARG VITE_GOOGLE_OAUTH_CLIENT_ID
ENV VITE_GOOGLE_OAUTH_CLIENT_ID=$VITE_GOOGLE_OAUTH_CLIENT_ID
RUN npm run build

# --- 2단계: 백엔드 + 정적 파일 서빙 ---
FROM python:3.12-slim
WORKDIR /app

# Claude Code CLI - LLM 호출을 구독 사용량으로 처리하기 위해 설치한다(없으면 API 종량제로
# 폴백). 예전엔 서버에 CLI 자체가 없어서 1순위 경로가 항상 건너뛰어졌다.
# CLAUDE_CODE_OAUTH_TOKEN(= claude setup-token 결과)이 있어야 헤드리스로 인증된다.
RUN apt-get update     && apt-get install -y --no-install-recommends curl ca-certificates     && curl -fsSL https://deb.nodesource.com/setup_22.x | bash -     && apt-get install -y --no-install-recommends nodejs     && npm install -g @anthropic-ai/claude-code@latest     && npm cache clean --force     && apt-get purge -y curl && apt-get autoremove -y     && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /app/frontend/dist ./static
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
