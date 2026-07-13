# 로컬 구동 및 운영 가이드

이 문서는 bizSupportNavigator를 로컬 환경에서 처음 기동하거나 이후 일상적으로 운영(재기동, 데이터 재수집, 트러블슈팅)할 때 필요한 정보를 정리한다.

배경/결정 이력의 단일 소스는 [detailed_plan.md](detailed_plan.md)이며, 다른 컴퓨터로 데이터를 옮길 때는 [BACKUP_RESTORE.md](BACKUP_RESTORE.md)를 참고한다.

## 구성 요소

| 구성 요소 | 역할 | 기본 포트 |
|---|---|---|
| PostgreSQL 16 | 정책/기업/인증 등 관계형 데이터 | 호스트 `9000` → 컨테이너 `5432` |
| Chroma 1.5.9 | 정책 청크 임베딩 벡터 저장소 | `8000` |
| Neo4j 5.26 Community | 정책 간 관계 그래프 | `7474`(HTTP), `7687`(Bolt) |
| FastAPI (backend) | REST API + WebSocket 채팅 | `8000`(uvicorn, `127.0.0.1`) |
| React + Vite (frontend) | 로그인/대시보드/채팅/그래프 UI | `5173` |

> **주의**: Chroma 컨테이너와 uvicorn이 둘 다 포트 `8000`을 쓴다. Chroma는 `0.0.0.0`/`::`(모든 인터페이스)에 바인딩하고 uvicorn은 `127.0.0.1`에만 바인딩하므로, 브라우저가 `localhost`를 IPv6(`::1`)로 풀면 백엔드 대신 Chroma로 요청이 가서 CORS 에러처럼 보이는 문제가 발생한다(원인은 CORS 설정이 아니라 포트 충돌). 프론트엔드 API 기본 URL은 `frontend/src/lib/api.ts`에서 `http://127.0.0.1:8000`으로 명시되어 있으니 임의로 `localhost`로 바꾸지 말 것.

## 사전 준비물

- Docker Desktop (Windows/Mac) 또는 Docker Engine
- Python 3.13 (backend는 이 버전 기준으로 개발/검증됨)
- Node.js (frontend, Vite + React 19 기준)
- (선택) `OPENAI_API_KEY`, `BIZINFO_API_KEY` — 실제 라이브 데이터 재수집 시 필요. 이미 채워진 볼륨을 복원해서 쓰는 경우 당장은 없어도 기동은 가능하지만, 채팅 상담 기능(LLM 호출)은 `OPENAI_API_KEY` 없이는 동작하지 않는다.

## 최초 구동 절차

1. **환경 변수 설정**: 저장소 루트에서 `.env.example`을 `.env`로 복사하고 값을 채운다.

   ```bash
   cp .env.example .env
   ```

   주요 항목:
   - `POSTGRES_*`, `NEO4J_*`: 로컬 개발용 기본값이 이미 들어있어 그대로 써도 됨(운영 배포 시에는 반드시 변경).
   - `OPENAI_API_KEY`: 채팅 상담(LLM) 기능에 필요.
   - `BIZINFO_API_KEY`: bizinfo.go.kr 정책 데이터 재수집(`/api/policies/sync`)에 필요.
   - `JWT_SECRET`: 로그인 토큰 서명 키. 로컬 개발 이상 용도로는 반드시 `change-me`에서 변경.
   - `EMBEDDING_MODEL_NAME`: 기본 `BAAI/bge-m3`. 첫 임베딩 호출 시 HuggingFace에서 자동 다운로드(시간 다소 소요, `HF_TOKEN` 미설정 시 rate limit 경고는 무시 가능).

2. **(선택, 권장) 기존 데이터 복원**: 다른 머신에서 만든 백업이 있다면 `docker compose up`보다 먼저 [BACKUP_RESTORE.md](BACKUP_RESTORE.md)의 절차로 볼륨을 복원한다. 백업이 없으면 6번 단계에서 처음부터 데이터를 수집하면 된다.

3. **인프라 컨테이너 기동** (저장소 루트에서):

   ```bash
   docker compose up -d
   ```

   postgres, chroma, neo4j 3개 컨테이너가 뜬다. `chroma` 이미지 태그(`chromadb/chroma:1.5.9`)는 `backend/requirements.txt`의 `chromadb` 파이썬 클라이언트 버전과 반드시 일치해야 한다 — 버전이 어긋나면 `create_collection`에서 `KeyError('_type')`로 실패한다. 이미지나 클라이언트 라이브러리 버전을 올릴 때는 반드시 둘을 같이 맞출 것.

4. **백엔드 설치 및 기동**:

   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate      # Windows
   # source venv/bin/activate  # macOS/Linux
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

   - `bcrypt==4.0.1`로 버전이 고정되어 있음 — 임의로 업그레이드하지 말 것(상위 버전 호환성 이슈로 고정됨, [detailed_plan.md](detailed_plan.md) 10.5절 참고).
   - 최초 기동 시 FastAPI `lifespan`이 자동으로 다음을 수행한다: 테이블 생성 → 마이그레이션 → 데모 로그인 계정 시드.
   - **데모 계정**: `demo-001@example.com` / `demo-002@example.com`, 비밀번호 공통 `demo1234` (`backend/app/db/seed.py`). 로컬 개발/데모 전용이며 실제 운영 배포에는 쓰지 말 것.

5. **프론트엔드 설치 및 기동**:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   `http://localhost:5173`에서 접속. 로그인 → 매칭 대시보드 → 채팅 상담 → 정책 그래프 탐색 4개 화면이 구현되어 있다.

6. **(볼륨을 복원하지 않고 빈 DB로 시작한 경우만) 정책 데이터 재수집**: 아래 순서대로 API를 호출한다.

   ```
   POST /api/policies/sync
   POST /api/policies/parse
   POST /api/policies/embed
   POST /api/policies/graph/build
   POST /api/companies/{company_id}/matches/refresh
   ```

   `sync`는 `BIZINFO_API_KEY`가, `embed`는 `OPENAI_API_KEY`(또는 로컬 임베딩 모델 다운로드)가 필요하다.

## 일상 운영

### 재기동

이미 `.env`와 볼륨이 준비된 상태에서 다시 작업을 시작할 때:

```bash
docker compose up -d          # 인프라 3종
cd backend && uvicorn app.main:app --reload   # 백엔드
cd frontend && npm run dev                     # 프론트엔드
```

### 중지

```bash
docker compose stop     # 컨테이너만 정지, 볼륨 데이터는 보존
docker compose down     # 컨테이너 제거 (volumes: 섹션에 명시된 볼륨은 기본적으로 유지됨, -v 옵션을 주면 볼륨까지 삭제되니 주의)
```

### 헬스체크 / 상태 확인

- `GET /health` — 백엔드 생존 확인.
- `docker compose ps` — 인프라 컨테이너 상태 확인(postgres는 `pg_isready` 헬스체크 내장).

### 주요 API 그룹

| 라우터 | prefix | 용도 |
|---|---|---|
| `auth.py` | `/auth` | 로그인 (`POST /auth/login`) |
| `policies.py` | `/api/policies` | 정책 동기화/파싱/임베딩/그래프 빌드, 정책·청크·그래프 조회 |
| `matching.py` | `/api/companies` | 기업별 정책 후보/매칭 결과 조회·갱신 |
| `chat.py` | (root) | `WS /ws/chat/{session_id}` 채팅 상담 웹소켓 |
| `health.py` | (root) | `GET /health` |

### 데이터 백업

운영 중 데이터를 안전하게 보관하거나 다른 머신으로 옮기려면 [BACKUP_RESTORE.md](BACKUP_RESTORE.md)의 `scripts/backup-volumes.sh` / `scripts/restore-volumes.sh`를 사용한다.

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 프론트에서 `No 'Access-Control-Allow-Origin' header` CORS 에러 | 포트 8000 충돌(Chroma가 uvicorn 대신 응답) | `frontend/src/lib/api.ts`의 API 기본 URL이 `http://127.0.0.1:8000`인지 확인, `localhost`로 바꾸지 말 것 |
| Chroma `create_collection` 시 `KeyError('_type')` | `chromadb` 이미지와 파이썬 클라이언트 버전 불일치 | `docker-compose.yml`의 `chromadb/chroma` 태그와 `backend/requirements.txt`의 `chromadb` 버전을 맞출 것 |
| `bcrypt` 관련 로그인/해시 오류 | `bcrypt` 버전을 임의로 올림 | `bcrypt==4.0.1`로 고정 유지 |
| 임베딩 첫 호출이 느리거나 rate limit 경고 | `bge-m3` 모델이 HuggingFace에서 처음 다운로드됨 | 정상 동작, `HF_TOKEN` 미설정 시 경고는 무시 가능 |

## 참고 문서

- [detailed_plan.md](detailed_plan.md) — 전체 설계/결정/버그 이력의 단일 소스.
- [BACKUP_RESTORE.md](BACKUP_RESTORE.md) — 볼륨 백업/복원 절차.
