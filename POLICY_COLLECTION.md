# 정책 데이터 수집 파이프라인 실행 가이드

정책 메타/첨부파일 수집부터 벡터 인덱스(Chroma)·GraphRAG(Neo4j) 구축까지 4단계를 순서대로 호출하는 방법을 정리한다. 배경/설계는 [detailed_plan.md](detailed_plan.md) 3절/4절 참고.

백엔드가 `http://127.0.0.1:8000`에서 떠 있고, `docker compose up -d`로 postgres/chroma/neo4j가 기동된 상태를 전제로 한다 ([RUNNING_LOCALLY.md](RUNNING_LOCALLY.md) 참고).

## 파이프라인 순서

**sync → parse → embed → graph/build** 순서를 반드시 지킬 것 — 뒷 단계는 앞 단계가 만든 데이터(다운로드된 첨부파일 → document_chunks → 임베딩)에 의존한다.

### 1. 정책 동기화 (`POST /api/policies/sync`)

기업마당 API에서 정책 메타 + 첨부파일 목록을 가져오고, 공고문으로 판별된 첨부파일 1개씩 다운로드한다.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/policies/sync?max_pages=5&page_unit=50" \
  -o sync_out.json -w "http_status:%{http_code} time:%{time_total}s\n"
cat sync_out.json
```

- `page_unit`(1~100) × `max_pages`(1~50) = 이번 호출에서 가져올 최대 건수. 최신순으로 가져오므로, 이미 수집된 정책은 다시 만나면 `updated`로 카운트되고 새 정책만 `created`로 늘어난다.
- 응답: `{"fetched", "created", "updated", "attachments_downloaded", "manual_review_count", "errors"}`.
- `BIZINFO_API_KEY`가 `.env`에 필요하다.
- 네트워크/LLM 파일명 판별 호출이 섞여 있어 정책 수백 건 기준 수 분 걸릴 수 있다 — 아래처럼 백그라운드로 돌리고 완료를 기다리는 걸 권장.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/policies/sync?max_pages=5&page_unit=50" \
  -o sync_out.json -w "http_status:%{http_code} time:%{time_total}s\n" &
```

### 2. 첨부파일 파싱 (`POST /api/policies/parse`)

다운로드된 첨부파일(PDF/HWP/HWPX)을 파싱해 `document_chunks`에 적재한다.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/policies/parse?limit=200" \
  -o parse_out.json -w "http_status:%{http_code} time:%{time_total}s\n"
cat parse_out.json
```

- **`limit` 최대값이 200**이라(라우터 제약, `le=200`), 대기 건수가 200을 넘으면 여러 번 나눠 호출해야 한다. 남은 건수는 아래 쿼리로 확인:

  ```bash
  cd backend && .venv/Scripts/python.exe -c "
  from sqlalchemy import text
  from app.db.postgres import SessionLocal
  db = SessionLocal()
  print('pending:', db.execute(text(\"select count(*) from policy_attachments where downloaded_path is not null and parse_status = 'pending'\")).scalar())
  db.close()
  "
  ```

- `pending`이 0이 될 때까지 `limit=200`으로 반복 호출.
- 응답의 `failed`/`errors`는 개별 파일 파싱 실패(예: 손상된 HWP, 지원 안 하는 포맷인 `.docx`, 일부 PDF의 pypdf 버그)로, 파이프라인 전체를 막지 않고 `parse_status='failed'`로 남아 수동 검수 큐로 빠진다. 재호출 시 자동으로 재시도된다.

### 3. 임베딩 (`POST /api/policies/embed`)

`document_chunks` 중 아직 임베딩 안 된 것을 bge-m3로 임베딩해 Chroma에 upsert한다.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/policies/embed?limit=2000" \
  -o embed_out.json -w "http_status:%{http_code} time:%{time_total}s\n"
cat embed_out.json
```

- `limit` 최대 2000이라 보통 한 번으로 충분하다.
- **CPU 로컬 추론**이라 청크 수천 개 기준 수 분~십수 분 걸릴 수 있다. 백그라운드로 돌리고 진행 상황은 Chroma 벡터 개수로 어림잡을 수 있다(64개씩 배치 upsert되며, Postgres의 `embedded_at`은 전체 요청이 끝나야 한 번에 커밋되어 중간 값은 안 보임):

  ```bash
  cd backend && .venv/Scripts/python.exe -c "
  from app.db.chroma import get_chunk_collection
  print('chroma vectors:', get_chunk_collection().count())
  "
  ```

### 4. 지식그래프 구축 (`POST /api/policies/graph/build`)

정책별 자격/제외요건을 LLM으로 추출해 Neo4j에 적재한다 (`(:Policy)-[:REQUIRES]->(:EligibilityCriterion)` 등).

```bash
curl -s -X POST "http://127.0.0.1:8000/api/policies/graph/build?limit=200" \
  -o graph_out.json -w "http_status:%{http_code} time:%{time_total}s\n"
cat graph_out.json
```

- `limit` 최대 200 — 정책이 200건을 넘으면 이것도 나눠 호출.
- `OPENAI_API_KEY` 필요. 정책당 OpenAI 호출 1회 이상이라 역시 시간이 걸린다.

### (선택) 매칭 재계산

수집이 끝난 뒤 특정 기업의 매칭 점수를 갱신하려면:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/companies/demo-001/matches/refresh" \
  -H "Authorization: Bearer $TOKEN"
```

(`$TOKEN`은 `POST /auth/login`으로 발급)

## 전체 현황 한 번에 확인하기

```bash
cd backend && .venv/Scripts/python.exe -c "
from sqlalchemy import text
from app.db.postgres import SessionLocal
db = SessionLocal()
print('정책:', db.execute(text('select count(*) from policies')).scalar())
print('다운로드된 첨부파일:', db.execute(text('select count(*) from policy_attachments where downloaded_path is not null')).scalar())
print('파싱 완료:', db.execute(text(\"select count(*) from policy_attachments where parse_status = 'parsed'\")).scalar())
print('파싱 실패:', db.execute(text(\"select count(*) from policy_attachments where parse_status = 'failed'\")).scalar())
print('document_chunks:', db.execute(text('select count(*) from document_chunks')).scalar())
print('임베딩 완료:', db.execute(text('select count(*) from document_chunks where embedded_at is not null')).scalar())
print('그래프 구축 완료 정책:', db.execute(text('select count(*) from policies where graph_built_at is not null')).scalar())
db.close()
"
```

## ⚠️ 완료 즉시 백업할 것

이 파이프라인은 시간과 API 비용(OpenAI, bizinfo)이 들어간 결과물이고, **Docker 볼륨은 로컬 상태라 Docker Desktop이 죽거나 데이터 디스크가 손상되면 백업 없이는 전부 사라진다** (2026-07-13 실제로 한 번 겪음 — Docker Desktop이 `com.docker.build` 버그로 반복 크래시하다 데이터 디스크가 초기화되어 방금 수집한 정책 250건이 통째로 날아갔었음). 4단계가 끝나면 바로:

```bash
bash scripts/backup-volumes.sh
```

자세한 내용은 [BACKUP_RESTORE.md](BACKUP_RESTORE.md) 참고.
