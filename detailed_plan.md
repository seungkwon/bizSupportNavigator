# 기업지원 종합 사이트 — 상세 실행 계획 (MVP)

> 본 문서는 `plan.md`의 1차 구상을 바탕으로, 질의응답을 통해 확정한 기술/범위 결정을 반영한 상세 계획이다.

## 0. 확정된 전제 조건 (Q&A 결과)

| 항목 | 결정 |
|---|---|
| 기존 기능 처리 범위 | 기업 데모그래픽 추출/저장은 **이미 구현된 것으로 가정**하고 인터페이스(계약)만 정의. **정책 메타/첨부파일 수집은 본 프로젝트에서 기업마당 API로 신규 구현**(2절/3절 참고) |
| 정책 수집 소스 | **기업마당(bizinfo.go.kr) Open API**로 정책 메타정보 + 첨부파일 목록 수집. 첨부파일 중 실제 **공고문 1개는 LLM이 파일명을 근거로 추론하여 선택** 후 다운로드 |
| DB 스택 | **PostgreSQL**(정규화된 관계형 데이터: 기업/정책 메타, 첨부파일 정보) + **Chroma**(벡터 DB, RAG 임베딩 검색) + **Neo4j**(그래프 DB, GraphRAG) |
| 기존 시스템 데이터 위치 | 기업 데모그래픽은 **이미 PostgreSQL에 저장되어 있다고 가정**. 정책 메타/첨부파일 정보는 본 프로젝트의 수집 파이프라인이 직접 PostgreSQL에 적재 |
| HWP 파싱 | **기존 구현 확인 완료** — `C:\Users\main\korean_pdf_rag_langgraph\hwp.py`(`HWPLoader`, 구버전 OLE), `hwpx.py`(`HWPXLoader`, 신버전 ZIP+XML). 두 파일을 그대로 vendoring하여 사용, 파싱 로직은 수정하지 않음 (2.2절) |
| LLM 제공자 | **OpenAI API** (추론/생성: gpt-4o 계열) |
| 임베딩 모델 | **Hugging Face `BAAI/bge-m3`** (OpenAI 임베딩 미사용) — 다국어/한국어 지원 모델, langchain `HuggingFaceEmbeddings` 래퍼로 연동 |
| 첨부파일 형식 | PDF + **HWP/HWPX 포함** |
| 배포 환경 | 미정, **로컬 개발 우선** → Docker Compose 기반 로컬 환경 구성 |
| 인증/멀티테넌시 | 기업 계정 개념을 MVP 데이터 모델에 처음부터 포함(JWT 기반), 단 SSO/역할관리 등 고도화는 후순위 |
| 매칭 결과 형태 | **적합도 점수(0~100) + 근거**(항목별 충족/미충족 사유) |
| 문서 범위 | **MVP** — 핵심 파이프라인(수집→파싱→매칭→채팅)이 동작하는 것을 최우선 목표로 함 |

---

## 1. 시스템 아키텍처

### 1.1 컴포넌트 개요

```
[기업마당 Open API]
        │ (수집 배치/스케줄)
        ▼
[Bizinfo Collector] ── LLM 파일명 추론(공고문 선택) ── 다운로드
        │
        ▼
[PostgreSQL] ◀────────────────────────────────────────────┐
   - 정책 메타, 첨부파일 정보, 매칭결과 캐시                    │
   - 기업 데모그래픽(가정, 기존 시스템 데이터)                   │
        ▲                                                  │
        │                                                  │
[React SPA]                                                │
   ├─ REST 호출 (조회/필터/기업정보) ──▶ [FastAPI REST] ──────┤
   └─ WebSocket (채팅/서버 푸시) ──────▶ [FastAPI WebSocket]  │
                                            │                │
                                            ▼                │
                                   [LangGraph 오케스트레이터]  │
                                    ├─ 메타 필터 노드 (SQL) ───┘
                                    ├─ RAG 검색 노드 (Chroma)
                                    ├─ GraphRAG 추론 노드 (Neo4j)
                                    ├─ LLM 판단/점수화 노드 (OpenAI)
                                    └─ 추가질문 생성 노드 (정보 부족 시)
                                            │
                        ┌───────────────────┼───────────────────┐
                        ▼                   ▼                   ▼
                    [Chroma]             [Neo4j]      [기존 시스템 인터페이스]
                - RAG 임베딩 검색   - 정책별 지식그래프    - 기업 데모그래픽 조회
                  (chunk_id 참조)     (자격/제외요건 관계)    (가정, mock 어댑터)
```

### 1.2 DB 기술 선택 (확정)

- **PostgreSQL**: 기업/정책의 정규화된 메타데이터(기업규모/지역/지원기간 등 구조화 필터)와 첨부파일 정보(경로/포맷/파싱상태)를 저장하는 **단일 진실 소스**. 기업 데모그래픽은 기존 시스템이 이미 저장해두었다고 가정하고, 정책 메타/첨부파일 정보는 본 프로젝트의 수집 파이프라인(3절)이 직접 적재한다.
- **Chroma**: RAG 임베딩 검색 전담 벡터 DB. 원문/메타데이터는 PostgreSQL `document_chunks`에 저장하고, 벡터는 Chroma 컬렉션에 `chunk_id`를 키로 저장하여 상호 참조한다 (같은 값을 두 곳에 중복 저장하지 않음).
- **Neo4j**: GraphRAG(신청자격/제외요건/기업 속성 간 관계 추론) 전담 그래프 DB. LangChain/LangGraph 생태계(`langchain-neo4j`)와의 통합 지원이 좋다.
- 세 DB 모두 리포지토리/어댑터 계층으로 감싸, 향후 배포 환경이 정해지면 각각 관리형 서비스(RDS, Chroma 서버/관리형 벡터DB, Neo4j Aura 등)로 쉽게 이전 가능하도록 한다.

---

## 2. 기존 시스템과의 인터페이스 (가정 · 계약만 정의)

기업 데모그래픽 기능은 실제 구현이 없다고 가정하되, 아래 인터페이스를 "이미 존재하는 것"으로 간주하고 개발한다. 실제 구현 시 이 계약에 맞춰 어댑터만 교체하면 되도록 설계한다. (정책 메타/첨부파일은 더 이상 가정 대상이 아니며, 3절의 수집 파이프라인이 본 프로젝트에서 직접 구현한다.)

### 2.1 기업 데모그래픽 조회 (가정된 기존 기능)
```
GET /internal/companies/{company_id}/demographics
→ {
    "company_id": "string",
    "company_name": "string",
    "biz_registration_no": "string",
    "region": "string",           // 지역 (필터링용)
    "company_size": "string",     // 소상공인/중소/중견 등 (필터링용)
    "industry_code": "string",
    "established_date": "date",
    "employee_count": "int",
    "annual_revenue": "number",
    "raw_business_plan": { ... }  // 원본 사업계획서 JSON
  }
```

이 인터페이스는 신규 기능이 참조만 하며, 본 프로젝트에서는 **mock 어댑터**를 만들어 개발/테스트를 진행한다(4.5절 참고). 실제로는 이 데이터가 이미 PostgreSQL에 존재한다고 가정하므로, 어댑터는 최종적으로 해당 PostgreSQL 테이블을 직접 조회하는 리포지토리로 대체될 것을 전제로 설계한다.

### 2.2 HWP/HWPX 파싱 (재구현으로 변경 — 2025-07-10 갱신)

> **변경 이력**: 원래 계획은 `C:\Users\main\korean_pdf_rag_langgraph\hwp.py`/`hwpx.py`를 그대로 vendoring하는 것이었으나, 실제 개발 머신에 해당 경로/프로젝트가 존재하지 않아 **vendoring이 불가능함을 확인**(Milestone 1 진행 중 발견). 사용자 확인 결과 "HWP는 나중에"로 보류하고 Milestone 1~2를 먼저 진행했고, Milestone 3(파싱 파이프라인) 착수 시점에 실제 수집된 정책 첨부파일 5건 중 3건이 `.hwp`였던 것을 계기로 **아래 로직을 이 프로젝트에서 새로 구현**하기로 확정함. 알고리즘 자체는 원 계획(2.2절 원안)에 기술된 것과 동일한 방식(HWP 5.0 OLE 구조 파싱)을 따르되, 코드는 신규 작성.

- **`HWPLoader`** (`backend/app/loaders/hwp.py`, `.hwp` = HWP 5.0 OLE 컴파운드 파일 구조): `olefile`로 OLE 스트림을 열어 `FileHeader`로 압축 여부 확인 후 `BodyText/Section*`을 순회, (압축 시) raw deflate로 압축 해제, 레코드 헤더(4바이트: tag 10bit/level 10bit/size 12bit, size가 0xFFF면 확장 4바이트 추가)를 파싱하여 `HWPTAG_PARA_TEXT`(태그값 67)레코드만 `utf-16-le`로 디코딩. 한자(CJK 통합 한자)·제어문자 제거 후 단일 `Document` 1개로 반환. 생성자: `HWPLoader(file_path: str)`. 유효하지 않은 HWP 구조(`FileHeader`/`HwpSummaryInformation` 스트림 없음)면 `ValueError`.
- **`HWPXLoader`** (`backend/app/loaders/hwpx.py`, `.hwpx` = ZIP+XML 구조): ZIP 내 `Contents/section*.xml`을 섹션 번호 순으로 순회하며 (네임스페이스 무관) `t` 텍스트 노드를 모아 단일 `Document` 1개로 반환. 생성자: `HWPXLoader(file_path: str)`. ZIP/XML 파싱 실패 시 `RuntimeError`.
- 두 로더 모두 **표/서식 구조 없이 순수 텍스트만** 추출한다 (섹션 구분이나 페이지 정보도 없음) — 자격요건이 표로 정리된 공고문의 경우 정보 유실 가능성 있음 (11절 리스크 참고). 한자 제거 과정에서 ㎡·㎢ 등 특수기호 유실 가능성도 원안과 동일하게 유효함.
- 실제 수집된 HWP 샘플(`PBLN_000000000124198`, `124199`, `124200`) 3건으로 파싱 결과를 조기 검증함 (11절 리스크 항목 대응).

```python
# backend/app/loaders/factory.py
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from .hwp import HWPLoader      # 기존 구현 vendoring, 수정 없이 그대로 사용
from .hwpx import HWPXLoader    # 기존 구현 vendoring, 수정 없이 그대로 사용
from langchain_community.document_loaders import PyPDFLoader

class AttachmentLoaderFactory:
    """파일 포맷에 맞는 langchain Loader 인스턴스를 반환하는 어댑터."""

    _LOADERS = {
        "pdf": PyPDFLoader,
        "hwp": HWPLoader,
        "hwpx": HWPXLoader,
    }

    def get_loader(self, file_path: str, file_format: str) -> BaseLoader:
        loader_cls = self._LOADERS[file_format]
        return loader_cls(file_path)

    def load(self, file_path: str, file_format: str) -> list[Document]:
        return self.get_loader(file_path, file_format).load()
```

- 파싱 결과(`list[Document]`)는 4.1/4.2절의 청킹·임베딩 파이프라인 입력으로 그대로 사용
- 두 로더 모두 결과가 `Document` 1개(파일 전체 텍스트)이므로, 4.2절의 "섹션 기반 청킹"은 이 로더의 출력이 아니라 **파이프라인 후처리 단계에서 텍스트를 정규식/헤더 패턴으로 재분할**하는 방식으로 구현해야 함

---

## 3. 정책 메타/첨부파일 수집 (기업마당 API 연동, 신규 구현)

기업마당(bizinfo.go.kr) Open API를 통해 정책(정책자금/지원사업) 목록과 메타정보를 수집하고, 각 정책의 첨부파일 목록 중 실제 **공고문**(신청자격·제외요건이 담긴 문서) **1개**를 LLM으로 판별하여 다운로드한다. 이 파이프라인은 본 프로젝트에서 새로 구현하는 부분이다.

- API 명세 참고: [기업마당 지원사업 정보 API](https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi) — 실제 요청/응답 필드는 이 문서를 기준으로 확정
- **인증키는 하드코딩하지 않고 `.env`(`BIZINFO_API_KEY` 등)로 관리**하며, 소스 저장소에는 커밋하지 않는다 (9절 로컬 개발 환경 참고)

### 3.1 수집 파이프라인 개요

1. `fetch_policy_list` — 기업마당 Open API 호출(페이지네이션/증분 수집: `updated_since` 등)로 정책 목록 + 메타(지원대상, 지역, 지원기간 등) + 첨부파일 목록(파일명, 다운로드 URL) 획득
2. `select_announcement_file` — 첨부파일명 목록을 LLM에 전달하여 **공고문에 해당하는 파일 1개**를 선택 (신청서 양식, 별첨 서식, 개인정보 동의서 등 비공고문과 구분)
3. `download_attachment` — 선택된 1개 파일만 다운로드하여 스토리지(로컬 파일시스템 → 추후 오브젝트 스토리지로 이전 가능하게 어댑터화)에 저장
4. `persist_policy_meta` — 정책 메타 + 다운로드된 파일 경로를 PostgreSQL(`policies`, `policy_attachments`)에 저장
5. 배치/스케줄 실행(예: 일 1회 또는 수동 트리거)을 전제로 하며, `updated_since` 기준 증분 수집으로 중복 처리를 최소화

### 3.2 공고문 판별 로직 (LLM 파일명 추론)

- **입력**: 한 정책의 첨부파일명 리스트 (예: `["2025년_OO지원사업_공고문.hwp", "신청서_양식.hwp", "개인정보_동의서.hwp"]`)
- **1차 필터(규칙 기반)**: "공고", "공고문", "시행공고", "모집공고" 등 키워드 포함 파일과 "신청서", "서식", "동의서", "리플릿" 등 제외 키워드 파일을 우선 구분해 후보를 좁힘 (LLM 호출 비용 절감)
- **2차 판단(LLM)**: 1차로 좁혀진 후보(또는 애매한 전체 목록)를 LLM에 전달, **structured output**으로 아래 형태의 응답을 받아 최종 1개 파일 확정
  ```json
  {"selected_filename": "2025년_OO지원사업_공고문.hwp", "reason": "‘공고문’ 키워드를 포함하고 신청서/서식 성격의 파일명이 아님"}
  ```
- **모호/저신뢰 처리**: 후보가 여러 개거나(동일 신뢰도 다중 매치) 전혀 매치되지 않는 경우, 자동 선택하지 않고 **수동 검수 큐**로 분기 (11절 리스크 참고)
- 선택 결과(`is_announcement`, `selection_reason`)는 `policy_attachments`에 함께 저장하여 추후 오탐 검수·재학습 근거로 활용

### 3.3 데이터 모델 (수집 관련)

| 테이블 | 주요 컬럼 |
|---|---|
| `policies` | policy_id(PK), title, meta(JSONB: 기업규모/지역/지원기간 등), source(`bizinfo`), collected_at |
| `policy_attachments` | id, policy_id(FK), file_name, download_url, is_announcement(bool), selection_reason, downloaded_path, format(pdf/hwp/hwpx), parse_status |

---

## 4. 핵심 매칭 파이프라인 설계

### 4.1 첨부파일 파싱
- **PDF**: langchain의 PDF loader(`PyPDFLoader` 등)로 텍스트+표 추출. 표 형태의 신청자격 요건이 많으므로 표 구조 보존에 신경 쓴다. (PDF는 페이지 단위로 `Document`가 여러 개 반환됨)
- **HWP/HWPX**: 2.2절의 `AttachmentLoaderFactory`를 통해 **기존에 구현된 `HWPLoader`/`HWPXLoader`**를 그대로 호출 (본 프로젝트에서 파싱 로직을 새로 구현하지 않음). 단, 두 로더는 파일 전체를 **`Document` 1개**로 반환하고 페이지/섹션 구분이 없으므로, PDF와 달리 후속 청킹(4.2절)에서 텍스트를 다시 나눠야 함
- 파싱 대상 파일은 3절 수집 파이프라인이 다운로드한 `policy_attachments.downloaded_path`(공고문으로 선택된 1개 파일)
- 파싱 신뢰도가 낮은 경우를 대비해 **파싱 실패/저품질 문서 큐**를 두어 수동 검수 경로로 분기 — `HWPLoader`는 `FileHeader`/`HwpSummaryInformation` 스트림이 없으면 `ValueError`, `HWPXLoader`는 파싱 실패 시 `RuntimeError`를 던지므로 이 예외를 잡아 큐에 적재
- 파싱 결과(`Document` 리스트)는 원문 텍스트 + 섹션 메타(제목, 페이지 등 — HWP/HWPX는 페이지 정보 없음)를 갖는 `document_chunks` 테이블에 저장

### 4.2 청킹 & 임베딩 (RAG)
- 신청자격/제외요건/지원한도 등 의미 단위로 청킹 (고정 길이보다 섹션 기반 청킹 우선, 예: "1. 지원대상", "2. 제외대상" 헤더 기준 분리)
- **Hugging Face `BAAI/bge-m3`** 임베딩 모델(langchain `HuggingFaceEmbeddings` 래퍼)로 벡터화 → **Chroma**에 저장, 원문/메타는 PostgreSQL `document_chunks`에 저장(`chunk_id`로 연결)
- 정책 변경 시 재파싱/재임베딩을 위한 버전 관리(`policy_document_version`)
- `bge-m3`는 로컬(CPU/GPU) 추론으로 구동 (로컬 개발 우선 방침에 맞음); 추후 처리량이 커지면 전용 임베딩 서버(예: TEI - Text Embeddings Inference)로 분리 검토

### 4.3 지식 그래프 구축 (GraphRAG)
- LLM(OpenAI)을 이용해 파싱된 텍스트에서 엔티티/관계 추출:
  - 엔티티: 정책(Policy), 자격요건(EligibilityCriterion), 제외요건(ExclusionCriterion), 기업속성(CompanyAttribute: 규모/업력/지역/업종 등)
  - 관계: `(:Policy)-[:REQUIRES]->(:EligibilityCriterion)`, `(:Policy)-[:EXCLUDES]->(:ExclusionCriterion)`, `(:EligibilityCriterion)-[:APPLIES_TO]->(:CompanyAttribute)` 등
- Neo4j에 적재, 정책 단위로 서브그래프 구성
- 추출 프롬프트는 스키마(허용 엔티티/관계 타입)를 강제하여 일관성 확보 (structured output 사용)

### 4.4 메타 필터링
- 기업규모/지역/지원기간 등은 **그래프/RAG 이전에** SQL로 1차 필터링하여 후보 정책 집합을 줄인다 (비용/속도 최적화)
- 이 필터는 3.3절 `policies.meta` 필드를 그대로 사용

### 4.5 LangGraph 매칭 오케스트레이션
상태 그래프 노드 구성 (예):
1. `load_company_profile` — 기존 시스템 인터페이스(mock 어댑터, 2.1절)에서 기업 정보 로드
2. `meta_filter` — `policies.meta`로 1차 후보 필터링
3. `rag_search` — 후보 정책의 자격/제외요건 관련 청크를 Chroma에서 검색
4. `graph_reasoning` — Neo4j에서 관련 서브그래프 순회, 조건 간 관계(AND/OR/제외) 파악
5. `llm_judge` — 검색된 근거 + 그래프 관계를 컨텍스트로 LLM이 항목별 충족여부 판단
6. `score_aggregate` — 항목별 결과를 0~100 점수로 집계 + 근거 목록 생성
7. `ask_clarification` (조건부) — 판단에 필요한 정보가 기업 프로필에 없을 경우, 부족한 정보를 **선택형 질문**으로 변환해 채팅으로 반환하고 그래프를 일시 중단(pause) 후 답변 수신 시 재개

### 4.6 매칭 결과 스키마 (예)
```json
{
  "policy_id": "string",
  "score": 82,
  "reasons": [
    {"criterion": "기업규모: 소상공인", "status": "충족", "evidence": "..."},
    {"criterion": "설립 3년 이내", "status": "미충족", "evidence": "..."},
    {"criterion": "특정 업종 제외 대상 아님", "status": "정보부족", "evidence": null}
  ]
}
```

---

## 5. 채팅 인터페이스 설계

- WebSocket 채널을 통해 서버가 먼저 "부족한 정보"에 대한 질문을 **선택지(버튼/칩) 형태**로 push
- 메시지 프로토콜(예):
```json
// 서버 → 클라이언트
{"type": "question", "question_id": "q1", "text": "설립일이 3년 이내인가요?",
 "options": [{"label": "예", "value": "yes"}, {"label": "아니오", "value": "no"}]}

// 클라이언트 → 서버
{"type": "answer", "question_id": "q1", "value": "yes"}
```
- 자유 텍스트 입력도 허용하되(예외적 케이스 대응), 기본 UX는 선택형
- 세션 상태(LangGraph state)는 대화 세션 ID로 Postgres에 스냅샷 저장 → 재접속 시 이어서 진행 가능

---

## 6. 인증 / 멀티테넌시

- MVP에서도 **company_id를 모든 신규 테이블의 기준 키**로 설계 (나중에 붙이면 마이그레이션 비용이 큼)
- 인증은 단순 JWT 발급(이메일/비밀번호 또는 기존 시스템의 로그인 결과를 넘겨받는 방식) — SSO/역할(RBAC)/관리자 화면은 MVP 이후로 명시적으로 제외
- FastAPI 의존성 주입으로 `current_company` 컨텍스트를 모든 REST/WebSocket 핸들러에 전달, row-level에서 `company_id` 필터 강제

---

## 7. 데이터 모델 (전체 신규 테이블 초안)

| 테이블 | 주요 컬럼 |
|---|---|
| `companies_auth` | company_id(PK), email, password_hash, created_at |
| `policies` | policy_id(PK), title, meta(JSONB), source(bizinfo), collected_at |
| `policy_attachments` | id, policy_id(FK), file_name, download_url, is_announcement(bool), selection_reason, downloaded_path, format(pdf/hwp/hwpx), parse_status |
| `document_chunks` | chunk_id, policy_id, section_title, content, page_no *(벡터는 Chroma에 별도 저장, chunk_id로 연결)* |
| `match_results` | id, company_id, policy_id, score, reasons(JSONB), computed_at |
| `chat_sessions` | session_id, company_id, langgraph_state(JSONB), updated_at |
| `chat_messages` | id, session_id, role, content, options(JSONB), created_at |

Neo4j 그래프는 별도 스키마(라벨/관계 타입)로 관리하며 위 관계형 테이블과는 `policy_id`로 연결.

---

## 8. API 개요

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/policies/sync` | 기업마당 API 수집 파이프라인 수동 트리거 (3절) |
| GET | `/api/companies/{id}/matches` | 저장된 매칭 결과 조회 |
| POST | `/api/companies/{id}/matches/refresh` | 매칭 재계산 트리거 (LangGraph 실행) |
| GET | `/api/policies` | 정책 목록/필터 조회 |
| GET | `/api/policies/{id}` | 정책 상세 + 첨부파일/파싱 상태 |
| WS | `/ws/chat/{session_id}` | 채팅 세션 (질문/답변 스트리밍) |
| POST | `/auth/login` | 로그인, JWT 발급 |

---

## 9. 로컬 개발 환경

- `docker-compose.yml`로 다음 구성:
  - `postgres` (관계형 DB)
  - `chroma` (벡터 DB 서버 모드)
  - `neo4j` (community edition)
  - `backend` (FastAPI, uvicorn --reload) — `BAAI/bge-m3` 임베딩 모델 로드(CPU/GPU)
  - `frontend` (React dev server)
- `.env`로 OpenAI API 키, 기업마당 Open API 인증키, DB/Chroma/Neo4j 접속정보 관리
- 기업 데모그래픽 인터페이스(2.1절)는 로컬 mock 서버(FastAPI 서브앱 또는 별도 스텁)로 대체하여 독립 개발 가능하게 함

---

## 10. 개발 로드맵 (MVP 마일스톤)

1. ✅ **기반 구축**: 저장소 구조, Docker Compose, FastAPI/React 스캐폴드, 기업 데모그래픽 mock 서버
2. ✅ **정책 수집 파이프라인**: 기업마당 API 연동, 첨부파일 목록 수집, 공고문 LLM 판별 + 다운로드, `policies`/`policy_attachments` 적재 확인
3. ✅ **파싱 파이프라인**: PDF loader 연동 + 기존 HWP loader 어댑터(2.2절) 연결 + `document_chunks` 적재 확인
4. ✅ **RAG 기본 매칭**: `bge-m3` 임베딩/Chroma 검색 + 메타 필터만으로 1차 매칭(점수 없이 후보 리스트) — 구현 완료 (아래 10.1 갱신 이력 참고)
5. ✅ **GraphRAG 연동**: 지식그래프 구축 + LangGraph에 `graph_reasoning` 노드 추가 — 구현 완료 (아래 10.2 갱신 이력 참고)
6. ✅ **점수화 & 근거 생성**: `llm_judge` + `score_aggregate` 노드, 매칭 결과 API 완성 — 구현 완료 (아래 10.3 갱신 이력 참고)
7. ✅ **채팅 UX**: WebSocket 프로토콜, 선택형 질문 흐름, 세션 재개 — 구현 완료 (아래 10.4 갱신 이력 참고, 프론트엔드 연동은 별도 진행 예정)
8. ✅ **인증/멀티테넌시**: JWT, company 스코프 적용 — 구현 완료 (아래 10.5 갱신 이력 참고)
9. ✅ **통합 검증**: 실제 기업마당 정책 샘플(HWP 포함) 몇 건으로 end-to-end 시나리오 검증 — 완료, 실제 버그 2건 발견/수정 (아래 10.6 갱신 이력 참고)

### 10.1 Milestone 4 구현 메모 (2026-07-10 갱신)

- **chromadb 빌드 블로커 해소**: `backend/requirements.txt`에 남아있던 이전 메모("chroma-hnswlib가 C++ 빌드 툴체인 필요, 이 머신엔 없음")는 더 이상 유효하지 않음 — `chromadb==1.5.9`가 Windows용 prebuilt wheel(`win_amd64`)을 제공하는 것을 확인하고 `chromadb`/`sentence-transformers`/`langchain-huggingface`를 정식 설치함. `langchain-neo4j`/`neo4j`/`langchain-openai`는 Milestone 5로 계속 보류.
- **`document_chunks.embedded_at`** 컬럼 추가 (`backend/app/models/document_chunk.py`) — 청크별 Chroma 임베딩 완료 시각을 기록해 재실행 시 중복 임베딩을 방지. 기존 테이블에 컬럼을 추가해야 해서 `Base.metadata.create_all`(신규 테이블만 생성)로는 부족 — `backend/app/db/migrations.py`에 멱등적 `ADD COLUMN IF NOT EXISTS` 방식의 경량 마이그레이션을 추가하고 `main.py` lifespan에서 `create_all` 직후 실행.
- **Chroma 연동**: `backend/app/db/chroma.py`(HTTP 클라이언트 + 컬렉션 획득), `backend/app/services/embeddings.py`(`HuggingFaceEmbeddings`로 `bge-m3` 지연 로딩/캐싱), `backend/app/services/embedding_pipeline.py`(`embedded_at IS NULL`인 청크를 배치로 임베딩해 Chroma에 upsert).
- **매칭(후보 검색)**: `backend/app/services/matching.py` — `apply_end_date`로 SQL 메타 필터(4.4절) 후, Chroma 벡터 유사도 검색(4.5절 `rag_search`)으로 정책별 최상위 청크를 모아 정책 단위로 랭킹. 점수화(`llm_judge`/`score_aggregate`)는 아직 없음 — Milestone 6에서 추가.
- **신규 API**: `POST /api/policies/embed`(대기 청크 임베딩 트리거), `GET /api/companies/{company_id}/policy-candidates`(쿼리 미지정 시 기업 프로필로 자동 생성해 후보 정책 목록 반환).
- **docker-compose.yml**: `chroma`(`chromadb/chroma:0.6.3`, 8000 포트, `chroma_data` 볼륨) 서비스 추가.

### 10.2 Milestone 5 구현 메모 (2026-07-10 갱신)

- **`langchain-openai`/`langchain-neo4j` 대신 `openai`(직접 SDK) + `neo4j`(공식 드라이버)** 조합을 선택함 — Milestone 2의 `announcement_selector.py`가 이미 `openai` SDK의 `client.chat.completions.parse(response_format=<pydantic 모델>)` 구조화 출력 패턴을 쓰고 있어, 지식그래프 엔티티/관계 추출도 같은 패턴을 재사용(`app/services/knowledge_graph.py`). Neo4j도 손으로 작성한 고정 스키마 Cypher만 실행하므로 `langchain-neo4j` 래퍼 없이 `neo4j` 드라이버(`app/db/neo4j.py`)로 충분하다고 판단.
- **`policies.graph_built_at`** 컬럼 추가 — 정책별 지식그래프 구축 완료 시각 기록(재실행 시 중복 추출 방지). `document_chunks.embedded_at`과 동일하게 `app/db/migrations.py`의 멱등적 마이그레이션에 추가.
- **지식그래프 구축**: `app/services/knowledge_graph.py` — 정책별 `document_chunks`를 모아(자격/대상/제외/요건 키워드가 포함된 섹션 우선, 약 12,000자 예산) OpenAI 구조화 출력으로 신청자격/제외요건 목록(+연관 기업속성명)을 추출한 뒤, Neo4j에 `(:Policy)-[:REQUIRES]->(:EligibilityCriterion)-[:APPLIES_TO]->(:CompanyAttribute)` / `(:Policy)-[:EXCLUDES]->(:ExclusionCriterion)-[:APPLIES_TO]->(:CompanyAttribute)` 형태로 적재. 재실행 시 해당 정책의 criterion 노드만 지우고 다시 씀(멱등).
- **`graph_reasoning` 노드**: `app/services/graph_reasoning.py` — 후보 정책 목록을 받아 Neo4j에서 각 정책의 자격/제외 요건(+기업속성)을 조회해 반환. AND/OR 관계 해석이나 기업 충족 여부 판단은 아직 없음(Milestone 6 `llm_judge`/`score_aggregate` 몫) — 여기서는 구조화된 근거만 표면화.
- **LangGraph 오케스트레이터**: `app/services/orchestrator.py` — `langgraph`의 `StateGraph`로 `meta_filter → rag_search → graph_reasoning` 3개 노드를 연결(`app/services/matching.py`를 `meta_filter_policy_ids`/`rag_search_candidates` 두 개의 공개 함수로 분리해 각각 노드에 매핑). `load_company_profile`(4.5절 1단계)은 그래프 상태로 옮기지 않고 라우터에서 mock 어댑터를 직접 호출하는 방식 유지(그래프 상태로 관리할 만큼의 복잡도가 아니라고 판단).
- **API 변경**: `GET /api/companies/{company_id}/policy-candidates`가 이제 오케스트레이터를 호출하며, 응답에 정책별 `eligibility_criteria`/`exclusion_criteria`(각 `description`/`company_attribute`) 필드가 추가됨. 신규: `POST /api/policies/graph/build`(대기 정책 지식그래프 구축 트리거).
- **docker-compose.yml**: `neo4j`(`neo4j:5.26-community`, 7474/7687 포트, `neo4j_data` 볼륨, `.env`의 `NEO4J_USER`/`NEO4J_PASSWORD`로 인증) 서비스 추가.
- **버그 수정 (Milestone 2 코드에도 영향)**: 설치된 `openai==1.59.7`에서는 구조화 출력 편의 메서드가 `client.chat.completions.parse`가 아니라 `client.beta.chat.completions.parse`에 있음을 실제 그래프 구축 테스트 중 발견. `announcement_selector.py`(Milestone 2)도 같은 잘못된 경로를 쓰고 있었는데, 지금까지 실제 샘플에서는 규칙 기반 필터가 항상 후보를 1개로 좁혀 LLM 판별 경로 자체가 호출된 적이 없어 드러나지 않았음(실패해도 "수동 검수 큐"로 조용히 빠지는 예외 처리 때문에 더욱 눈에 안 띔). 두 파일 모두 `client.beta.chat.completions.parse`로 수정.
- **구조화 출력 소소한 이슈**: LLM이 `company_attribute`가 없을 때 실제 null 대신 문자열 `"null"`을 반환하는 경우가 있어(실측 확인), `ExtractedCriterion`에 pydantic `field_validator`를 추가해 빈 문자열/"null"/"none"(대소문자 무관)을 `None`으로 정규화.

### 10.3 Milestone 6 구현 메모 (2026-07-10 갱신)

- **`llm_judge`**: `app/services/llm_judge.py` — 그래프에서 가져온 자격/제외 요건을 기업 프로필(지역/규모/업종/설립일/매출 등, mock 어댑터 `app/mock/demographics.py`)과 매칭 청크 발췌를 근거로 OpenAI 구조화 출력에 넘겨 항목별 충족/미충족/정보부족을 판정. **제외요건은 "~에 해당하지 않음" 형태로 뒤집어서** 질의하므로, 자격/제외 요건 모두 "충족 = 기업에 좋음"이라는 하나의 상태 어휘로 통일됨(4.6절 예시 스키마의 단일 `reasons` 리스트와 일치). OpenAI 키 미설정이거나 LLM 호출 실패 시 해당 요건들은 모두 "정보부족"으로 폴백(수동 검수 없이 조용히 성능 저하, 기존 서비스들과 동일 패턴).
- **`score_aggregate`**: `app/services/score_aggregate.py` — 항목별 상태에 가중치(충족=1, 정보부족=0.5, 미충족=0)를 매김. **실측 중 발견한 버그**: 처음에는 전체 항목을 하나로 평균냈는데, 자격요건 2개가 모두 미충족(예: 서울 소재 기업에 충남/제천 소재 요건)인 정책이 제외요건 9개가 전부 충족("해당 없음")이라는 이유로 82점이 나오는 오류가 실측으로 확인됨 — 제외요건 개수가 많으면 소수의 핵심 자격요건 실패를 희석시킴. **수정**: 자격요건 평균과 제외요건 평균을 각각 구해 70:30(자격:제외) 가중합으로 점수 산출("자격이 안 되면 제외조항을 아무리 통과해도 의미 없다"는 직관 반영). **하드룰**은 유지: 제외요건 기반 문장("~에 해당하지 않음")이 "미충족"으로 나오면(= 실제로 제외 대상에 해당) 다른 요건 충족도와 무관하게 점수를 0으로 강제.
- **오케스트레이터 확장**: `app/services/orchestrator.py`에 `llm_judge → score_aggregate` 노드를 추가해 전체 파이프라인(`meta_filter → rag_search → graph_reasoning → llm_judge → score_aggregate`)을 구성하는 `run_full_matching()`을 신설. 기존 `run_policy_matching()`(그래프 근거까지만, LLM 판정 없음)은 비용이 들지 않는 디버그용 `/policy-candidates`에서 계속 사용. `ask_clarification`(4.5절 7단계, 정보 부족 시 조건부 분기)은 아직 구현하지 않음 — 정보 부족은 일단 "정보부족" 사유로만 노출되고, 실제 채팅 일시중단/재개 흐름은 Milestone 7(WebSocket)에서 붙임.
- **`match_results` 캐시 테이블**: `app/models/match_result.py` 신규 테이블(company_id+policy_id 유니크 제약, 재계산 시 upsert). `app/services/match_results.py`가 저장/조회 담당. `company_id`는 실제 FK가 아님(기업 인증 테이블이 아직 없음, 6절/8절 참고).
- **API 완성** (8절 표와 일치): `POST /api/companies/{company_id}/matches/refresh`(전체 파이프라인 재계산 + 저장), `GET /api/companies/{company_id}/matches`(캐시된 결과 조회, 점수 내림차순). 기존 `/policy-candidates`는 저비용 디버그 엔드포인트로 유지.

### 10.4 Milestone 7 구현 메모 (2026-07-10 갱신)

- **LangGraph `interrupt()`/체크포인터 미사용**: 5절의 "그래프를 일시 중단 후 답변 수신 시 재개"는 LangGraph 공식 `interrupt()` + 체크포인터로 구현할 수도 있었으나, 비동기 Postgres 체크포인터 패키지를 새로 검증해야 하고 후보 정책이 몇 건 안 되는 MVP 규모에서는 매 턴마다 `meta_filter`/`rag_search`/`graph_reasoning`/`llm_judge`를 다시 돌려도 비용이 크지 않다고 판단해, **직접 작성한 턴 기반 제어 흐름**(`app/services/chat_service.py`)으로 구현. `chat_sessions.langgraph_state`는 LangGraph의 내부 체크포인트 포맷이 아니라 자체 제어 상태(질의 파라미터, 수집된 답변, 대기 중인 질문 1개, 라운드 수)를 담은 평범한 JSON 스냅샷.
- **범위 축소**: 채팅으로는 **RAG 랭킹 1위 후보 정책에 한해, 한 번에 질문 1개씩, 최대 3라운드**만 명확화 질문을 함(5개 정책 전체·전체 요건에 대해 물으면 대화가 지나치게 길어짐). 질문에 응답하면 해당 사실이 모든 후보의 재판정에 반영됨(`llm_judge`의 `extra_facts`로 전달, `app/services/llm_judge.py`). 질문/응답이 끝나면(또는 라운드 상한 도달) 전체 후보를 재판정·재점수화해 `match_results`에 저장.
- **WebSocket 프로토콜** (5절과 일치): `POST` 없이 `/ws/chat/{session_id}`. `{"type":"start","company_id":...}` → 질문 또는 결과 push, `{"type":"answer","question_id":...,"value":"yes"|"no"}` → 다음 질문 또는 결과. 재접속 시 세션이 존재하면 대기 중인 질문 또는 완료된 결과를 즉시 재전송(`resume_payload`).
- **`chat_sessions`/`chat_messages` 테이블** (7절 스키마 그대로): 신규 테이블(마이그레이션 불필요, `create_all`로 생성).
- **실측 중 발견한 버그 2건**:
  1. **이벤트 루프 블로킹**: WebSocket 핸들러(비동기)에서 동기 함수(bge-m3 임베딩 추론, Neo4j 드라이버, OpenAI HTTP 호출 — 수 초~수십 초 소요)를 직접 호출하면 이벤트 루프가 막혀 keepalive ping/pong을 처리하지 못하고 `1011 keepalive ping timeout`으로 연결이 끊김. `asyncio.to_thread()`로 감싸서 해결.
  2. **JSONB in-place mutation 미감지**: `session.langgraph_state`(일반 `dict`, `MutableDict` 미사용)를 in-place로 수정한 뒤 같은 객체를 `session.langgraph_state = state`로 재할당하면 SQLAlchemy가 "변경 없음"으로 판단해 커밋해도 실제로 DB에 반영되지 않음(자체 스크립트로 재현 확인 — 답변을 기록해도 `collected_facts`가 계속 빈 배열로 남고 같은 질문이 무한 반복됨). `sqlalchemy.orm.attributes.flag_modified(session, "langgraph_state")`를 각 변경 지점마다 명시 호출해 해결.
- **프론트엔드 연동은 아직 없음**: 이번 마일스톤은 백엔드 WebSocket 프로토콜/세션 관리까지만 구현. React 채팅 UI는 사용자 요청에 따라 백엔드 기능이 모두 확정된 이후 별도로 진행하기로 함.

### 10.5 Milestone 8 구현 메모 (2026-07-10 갱신)

- **`bcrypt`/`passlib` 호환성 버그 (실측 중 발견)**: `passlib[bcrypt]==1.7.4`(사실상 미유지보수)는 백엔드 감지 시 `bcrypt.__about__`을 참조하는데, `bcrypt`가 4.1부터 이 속성을 제거해 최신 `bcrypt`(설치 시 5.0.0)와 조합하면 해시 생성 시점에 `AttributeError`/`password cannot be longer than 72 bytes`로 즉시 실패함. **`bcrypt==4.0.1`로 고정**해 해결(`backend/requirements.txt`에 사유 기록).
- **`companies_auth` 테이블** (7절 스키마 그대로): `app/models/company_auth.py`. 회원가입 API는 8절 API 표에 없어서(로그인만 명시), **`app/db/seed.py`가 기동 시 mock 데모 기업(`demo-001`/`demo-002`, `app/mock/demographics.py`) 계정을 고정 비밀번호(`demo1234`)로 시드**해 로그인을 실제로 테스트 가능하게 함. 로컬 개발용 결정이며 실제 배포 시 회원가입/초대 흐름으로 대체 필요.
- **JWT 발급/검증**: `app/core/security.py`(`python-jose` + `passlib`), `POST /auth/login`(`app/routers/auth.py`, 이메일/비밀번호 → `{access_token, token_type, company_id}`).
- **`current_company` 의존성 주입 및 row-level 스코프** (6절): `app/core/deps.py`의 `require_company_scope`가 REST 라우트의 `company_id` 경로 파라미터를 토큰의 company와 대조해 불일치 시 403. `/api/companies/{company_id}/policy-candidates`, `/matches`, `/matches/refresh` 세 엔드포인트 모두 적용. `GET /internal/companies/{company_id}/demographics`(2.1절, 가정된 기존 내부 시스템 인터페이스)와 `/api/policies/*`(정책 수집 파이프라인, 특정 기업 소유 자원이 아닌 공용 데이터)는 의도적으로 이 스코프 밖에 둠 — 전자는 내부 서비스 간 호출을 가정, 후자는 운영 파이프라인이라 별도 관리자 인증이 필요하면 그건 후속 과제.
- **WebSocket 인증**: 브라우저 WebSocket 핸드셰이크는 커스텀 `Authorization` 헤더를 못 보내므로 `?token=` 쿼리 파라미터로 JWT 전달(`app/routers/chat.py`). 토큰 없음/무효 시 `accept()` 전에 `close(code=1008)`로 핸드셰이크 자체를 거부(클라이언트에는 HTTP 403으로 관측됨). 재접속 시 기존 세션의 `company_id`가 토큰과 다르면 거부, `start` 메시지의 `company_id`가 토큰과 다르면 에러 응답 — 세션 ID를 추측해도 다른 기업 세션을 가로챌 수 없도록 이중으로 확인.
- **실측 검증**: 토큰 없이 REST 호출 시 401, 정상 토큰이지만 경로의 `company_id`가 다르면 403, WebSocket도 토큰 없으면 핸드셰이크 거부·타 기업 세션 재개 거부·`start`의 company_id 불일치 거부까지 스크립트로 확인.

### 10.6 Milestone 9 구현 메모 (2026-07-10 갱신)

실제 기업마당 API에서 정책을 추가로 수집(`/api/policies/sync`)해 총 25건(HWP/HWPX 다수 포함)으로 늘린 뒤, 수집 → 파싱 → 임베딩 → 그래프 구축 → 매칭(`/matches/refresh`)까지 전체 파이프라인을 처음부터 재실행하며 검증. 이 과정에서 실제 버그 2건을 새로 발견해 수정함(둘 다 "몇 건 안 되는 초기 샘플"로는 드러나지 않고 실제 재실행/실사용 규모에서만 드러나는 종류):

- **[치명] 재동기화 시 이미 처리된 데이터가 삭제되는 버그**: `sync_attachments`(Milestone 2, `app/services/policy_collector.py`)가 매번 정책의 첨부파일 행을 전부 삭제 후 재생성하고 있었음 — 원래 의도는 "사라진 후보가 안 남게" 하려던 것이었으나, **이미 파싱까지 끝난 정책을 다시 sync해도 무조건 삭제 후 재생성**되어 `document_chunks`가 FK CASCADE로 통째로 삭제됨. 배치로 매일 재동기화하는 운영 조건에서는 **모든 정책이 매번 처음부터 재파싱/재임베딩**되는 셈이고, 재다운로드가 실패하면 기존에 잘 처리된 데이터까지 영구 소실됨. 실제로 정책 124198(녹색경영 시상)로 재현: 재sync 한 번으로 73개 chunk가 사라지고 첨부파일이 "download_failed" 상태가 됨. **수정**: `download_url` 기준으로 기존 첨부파일과 diff — 후보 목록에서 사라진 것만 삭제하고, 이미 있는 것은 그대로 두어(파싱 상태 보존) 재sync가 안전하도록 변경. 로컬에 남아있던 원본 파일로 해당 정책 데이터를 복구하고, 수정 후 동일 시나리오로 재현·검증(첨부파일 id와 chunk 73건 모두 보존됨을 확인).
- **[중간] `.hwpx` 확장자인데 실제로는 구버전 OLE(HWP 5.0) 포맷인 첨부파일**: 정책 124250의 공고문이 파일명은 `.hwpx`이지만 실제 바이트는 ZIP이 아니라 OLE 컴파운드 파일 시그니처(`D0 CF 11 E0 A1 B1 1A E1`)였음 — `HWPXLoader`가 "File is not a zip file"로 실패, `parse_status='failed'`로 수동 검수 큐行. bizinfo 첨부파일의 확장자가 실제 포맷을 보장하지 않는다는 것을 실측으로 확인(11절 리스크에도 추가). **수정**: `AttachmentLoaderFactory.load()`가 hwp/hwpx 포맷일 때 파일의 매직 바이트를 먼저 확인해 실제 컨테이너 포맷(OLE vs ZIP)에 맞는 로더를 선택하도록 변경 — 확장자보다 내용을 신뢰. 수정 후 해당 파일이 정상적으로 `HWPLoader`로 파싱되어 14개 chunk 생성됨을 확인.
- **최종 규모 검증**: 25개 정책 중 24개 지식그래프 구축 완료(나머지 1개는 공고문 첨부파일 미확보로 chunk 자체가 없어 정상적으로 스킵), chunk 230개 전부 임베딩 완료, 파싱 실패 0건(위 hwpx 버그 수정 후). `demo-001`로 `/matches/refresh` 재실행 시 8건의 정책이 합리적인 점수 분포(0~82점)로 반환됨을 확인.

---

## 11. 리스크 및 미결정 사항

- **공고문 판별 오탐**: 파일명만으로는 공고문 여부가 애매한 경우가 있을 수 있음(예: 명확한 키워드가 없는 파일명) → 규칙 기반 1차 필터 + LLM 2차 판단 + 저신뢰 건 수동 검수 큐로 리스크 완화
- **기업마당 API 제약**: 호출 한도(rate limit), 응답 스키마 변경, 인증키 관리 등 외부 API 의존 리스크 → 재시도/백오프, 스키마 검증 로직 필요
- **HWP/HWPX 파싱 신뢰도 및 구조 손실**: 기존 `HWPLoader`/`HWPXLoader`는 표/서식 구조 없이 순수 텍스트만 추출하고 페이지·섹션 구분도 없음 → 표로 정리된 자격요건(예: 지원한도 표, 기업규모별 조건표)이 한 줄로 뭉쳐 파싱될 수 있어, 4.2절 청킹 시 텍스트 패턴 기반으로 항목을 재구성하는 로직이 정확도에 큰 영향을 줌. `HWPLoader`는 중국어/제어문자를 제거하는 과정에서 일부 특수기호(예: ㎡, ㎢ 등 조례 표기)가 유실될 가능성도 있음 → 실제 공고문 샘플로 파싱 결과를 조기에 검증 필요
- **HWP/HWPX 파싱 실패 처리**: `HWPLoader`는 유효하지 않은 HWP 구조일 때 `ValueError`, `HWPXLoader`는 파싱 오류 시 `RuntimeError`를 던짐 → 파이프라인에서 이를 포착해 수동 검수 큐로 분기하는 예외 처리 필요 (4.1절)
- **첨부파일 확장자가 실제 포맷을 보장하지 않음 (Milestone 9에서 실측 확인, 조치 완료)**: bizinfo 첨부파일 중 파일명은 `.hwpx`이지만 실제 바이트는 구버전 OLE 포맷(HWP 5.0)인 경우를 확인(정책 124250). `AttachmentLoaderFactory`가 매직 바이트로 hwp/hwpx를 재판별하도록 수정해 해결(10.6절 참고) — 다만 pdf↔hwp류처럼 완전히 다른 포맷 간 오인 사례는 아직 못 봤고, 향후 발견되면 같은 방식(내용 스니핑)으로 확장 필요.
- **배포 환경 미정**: 현재는 로컬 우선이지만, 추후 클라우드/온프레미스 결정 시 PostgreSQL/Chroma/Neo4j 이전 계획 별도 수립 필요
- **LLM 비용/속도**: GraphRAG + LLM 판단 단계가 정책 수 증가 시 비용이 커질 수 있음 → 캐싱(`match_results`)과 배치 재계산 전략 필요
- **기업 데모그래픽 실제 스키마와의 불일치 가능성**: 2.1절의 인터페이스는 가정이므로, 실제 구현 연동 시 어댑터 수정이 필요할 수 있음
- **PDF 텍스트 추출 시 줄바꿈 손실로 인한 섹션 헤더 미검출 (Milestone 3에서 실측 확인)**: `PyPDFLoader`로 추출한 일부 PDF는 페이지 내 줄바꿈이 거의 없어(예: "2신청자격 □ 충남 소재..."처럼 번호와 제목이 공백 없이 붙어 한 덩어리로 추출됨) 4.2절의 줄 단위 헤더 정규식(`^\d{1,2}[.)]\s*...`)이 매치되지 않고, 해당 페이지 전체가 길이 기반(1500자) 청킹으로만 분리됨 — 섹션 제목 없이 저장되어 4.3절 GraphRAG 엔티티 추출 시 문맥 단서가 줄어듦. HWP/HWPX(문단 단위로 자연스러운 줄바꿈 보존)에서는 발생하지 않음. 임시 대응: 길이 기반 폴백으로 텍스트 자체는 보존됨(유실 아님). 향후 개선 후보: 레이아웃 인식 PDF 추출기(예: `pdfplumber`) 도입 또는 줄 경계에 의존하지 않는 정규식(연속 텍스트 내 헤더 키워드 매칭)으로 교체.

---

## 12. 프론트엔드 UI 구현 계획 (앞으로 할 일 — 2026-07-10 기록)

백엔드 마일스톤 1~9(수집·파싱·RAG·GraphRAG·점수화·채팅·인증·통합검증)가 모두 끝난 시점에 기록. 프론트엔드는 아직 Milestone 1 스캐폴드 그대로(`frontend/src/App.tsx`, `/health` 확인용 placeholder뿐)이고, 라우터/데이터 페칭 라이브러리/UI 킷 등 추가 의존성은 하나도 없는 상태(`frontend/package.json`에 `react`/`react-dom`만 있음). 아래는 다음 세션에서 이어갈 작업 목록이며, 아직 구현되지 않았다.

### 12.1 붙여야 할 백엔드 계약 (이미 구현·검증됨)
- 인증: `POST /auth/login` (email/password) → `{access_token, token_type, company_id}`. 데모 계정: `demo-001@example.com`/`demo-002@example.com`, 비밀번호 `demo1234` (`app/db/seed.py`).
- 매칭: `GET /api/companies/{company_id}/matches`(캐시 조회), `POST /api/companies/{company_id}/matches/refresh`(재계산) — 둘 다 `Authorization: Bearer <token>` 필요, 토큰의 company와 경로의 `company_id`가 다르면 403.
- 디버그/보조: `GET /api/companies/{company_id}/policy-candidates`(그래프 근거까지, 점수 없음), `GET /api/policies`, `GET /api/policies/{policy_id}`.
- 채팅: `ws://.../ws/chat/{session_id}?token=<JWT>` — 프로토콜은 5절 참고. `{"type":"start","company_id":...}` → 질문 또는 결과, `{"type":"answer","question_id":...,"value":"yes"|"no"}` → 다음 질문 또는 결과. 재접속 시 서버가 대기 질문/완료 결과를 자동 재전송.

### 12.2 화면 구성 (제안)
1. **로그인 화면**: email/password 입력 → `/auth/login` 호출 → JWT를 저장(우선 메모리/`localStorage`, 새로고침 유지가 필요하면 `localStorage`)하고 이후 요청에 `Authorization` 헤더로 부착.
2. **매칭 대시보드** (로그인 후 기본 화면): `GET /matches`로 캐시된 결과를 카드/테이블로 표시(정책명, 점수, 근거 리스트 — `criterion`/`status`(충족/미충족/정보부족)/`evidence`). "다시 계산" 버튼으로 `POST /matches/refresh` 호출(응답이 수 초~수십 초 걸릴 수 있으니 로딩 상태 표시 필수 — 백엔드가 LLM/임베딩 호출을 동기로 처리함).
3. **채팅 화면**: WebSocket 연결 후 `start` 전송 → 서버가 질문을 보내면 5절 설계대로 **선택지 버튼(예/아니오)** 위주로 렌더링(자유 텍스트 입력은 보조 수단으로만). 결과 수신 시 매칭 대시보드와 동일한 형태로 표시. 세션 재개: 페이지 새로고침 시 같은 `session_id`로 재연결하면 서버가 이어서 진행(`session_id`는 클라이언트가 생성해 URL이나 로컬 저장소에 유지).
4. **정책 그래프 탐색 화면**: `GET /api/policies/graph/overview`(카테고리→정책 노드/엣지)를 force-directed 그래프로 렌더링, 정책 노드(가운데 노드) 클릭 시 `GET /api/policies/{policy_id}/graph`(정책 중심 자격/제외요건/기업속성 그래프)로 드릴다운.
5. (선택) **정책 탐색 화면**: `GET /api/policies` 목록 + 상세(첨부파일 파싱 상태) — 운영/디버그 관점에서 유용하지만 최종 사용자 화면에는 필수 아님.

### 12.3 기술 스택 결정 (2026-07-13 확정)
- 그래프 시각화: **`react-force-graph`**(force-graph/d3-force 기반) — 백엔드가 반환하는 `{nodes, edges}` JSON을 그대로 소비 가능.
- 라우팅: **`react-router`** 도입 — 로그인/대시보드/채팅/그래프탐색 화면을 URL로 구분.
- 데이터 페칭: **`fetch` + `useState`/`useEffect`**(react-query 등 추가 의존성 없이 시작).
- 인증 토큰: **`localStorage`에 저장**, 새로고침에도 로그인 유지. API 401 응답 수신 시 로그인 화면으로 리다이렉트(만료 시 재로그인 유도).
- 채팅 WebSocket 재접속: **자동 재시도(짧은 백오프)** — 연결이 끊기면 몇 초 뒤 자동 재연결 시도, `session_id`로 서버가 자동 resume.

### 12.4 진행 방식
사용자가 "UI 작업 시작"을 요청하면 위 12.2 화면부터 우선순위대로 구현. 백엔드는 이미 완결된 상태이므로 프론트 작업 중 API 계약 변경이 필요하면 그 시점에 백엔드도 같이 조정.

### 12.5 그래프 탐색 API (2026-07-13 추가, `backend/app/routers/policies.py`)
- `GET /api/policies/graph/overview` — 카테고리(`policies.meta.pldirSportRealmLclasCodeNm`, 없으면 "기타") 노드 + 정책 노드, 카테고리→정책 `has_policy` 엣지. 인증 불필요(공용 데이터, 8절 API 표의 `/api/policies/*`와 동일한 스코프 방침).
- `GET /api/policies/{policy_id}/graph` — 정책을 중심 노드로 자격요건(`requires`)/제외요건(`excludes`) 노드, 각 요건에서 연관 기업속성(`applies_to`)으로 뻗는 노드-엣지 그래프. `graph_reasoning.fetch_graph_evidence()`(Neo4j 조회, 4.5절)를 노드/엣지 형태로 재구성한 것 — 기존 `/{policy_id}/criteria`(같은 데이터를 평평한 리스트로 반환, matching.py의 `/policy-candidates`와 같은 데이터 모델)와 데이터 소스는 동일하고 응답 형태만 시각화용으로 다름.

### 12.6 프론트엔드 구현 완료 (2026-07-13, Playwright로 실제 브라우저 검증)

12.2~12.3의 4개 화면(로그인/매칭 대시보드/채팅/그래프 탐색) 모두 구현 완료. 12.3의 스택 결정(react-router, fetch+useState, react-force-graph-2d, localStorage 토큰, 채팅 자동 재접속)을 그대로 적용.

- `frontend/src/lib/api.ts` — 공용 `apiFetch()`: `Authorization` 헤더 자동 부착, 401 수신 시 `localStorage` 정리 + `auth:unauthorized` 이벤트 발행.
- `frontend/src/lib/auth.tsx` — `AuthProvider`/`useAuth`/`RequireAuth`(라우트 가드, 미인증 시 `/login`으로 리다이렉트하며 원래 목적지를 `location.state`에 보존).
- `frontend/src/pages/{Login,Dashboard,Chat,Graph}Page.tsx`, `frontend/src/App.tsx`(라우팅 + 상단 네비게이션).
- **실측 중 발견한 버그**: 프론트 API 기본 URL을 `http://localhost:8000`으로 뒀더니 CORS 에러(`No 'Access-Control-Allow-Origin' header`)가 발생 — 원인은 CORS 설정이 아니라 **포트 충돌**이었음. `docker-compose.yml`의 Chroma가 8000번을 모든 인터페이스(`0.0.0.0`/`::`)에 바인딩하는데, `uvicorn`은 `127.0.0.1`(IPv4)에만 바인딩되어 있어서, 크로미움이 `localhost`를 IPv6(`::1`)로 먼저 풀면 백엔드가 아니라 **Chroma의 docker-proxy로 요청이 감**(CORS 헤더가 없는 Chroma가 응답하니 프리플라이트가 실패). **수정**: `frontend/src/lib/api.ts`의 기본값을 `http://127.0.0.1:8000`으로 명시(주석에 원인 기록). 같은 증상이 재발하면 백엔드가 아니라 이 포트 충돌을 먼저 의심할 것.

---

## 13. 다른 컴퓨터에서 이어서 작업하기 (체크리스트 — 2026-07-10 기록, 2026-07-13 방침 변경)

> **변경 이력(2026-07-13)**: 원래는 "새 컴퓨터에서 라이브 API로 재수집"이 방침이었으나(정책 25건 규모일 때 결정), 이후 정책 100건 + chunk 712개 + 그래프 93건까지 데이터가 커지면서 재수집에 드는 시간(임베딩·그래프 구축에 각각 수 분~10분 이상)이 아까워져 **Docker 볼륨을 tar로 백업/복원하는 방식**으로 변경. `scripts/backup-volumes.sh`/`scripts/restore-volumes.sh` 참고(13.1절).

`git clone` + `.env`만으로는 로컬 상태(Docker 볼륨 데이터)가 옮겨지지 않는다는 점은 여전히 유효하지만, 아래 13.1절 스크립트로 볼륨 자체를 옮기면 재수집 없이 그대로 이어갈 수 있다.

### 13.1 볼륨 백업/복원 (`scripts/backup-volumes.sh`, `scripts/restore-volumes.sh`)

- `docker-compose.yml`의 세 데이터 볼륨(`postgres_data`, `chroma_data`, `neo4j_data`, 컴포즈 프로젝트 접두사가 붙어 실제로는 `bizsupportnavigator_postgres_data` 등)을 각각 `alpine` 컨테이너로 마운트해 tar로 묶는 방식 — pg_dump/neo4j-admin dump 같은 DB별 도구 대신 **파일시스템 레벨 통째 복사**라 세 DB 모두 같은 스크립트로 처리 가능(가장 단순한 방법을 선호한다는 결정에 따름).
- 사용법: 원본 머신에서 `bash scripts/backup-volumes.sh` → `volumes/backup/*.tar.gz` 생성(이 디렉터리는 `.gitignore`의 `volumes/` 규칙에 이미 포함되어 git으로는 옮겨지지 않음, **USB/원격복사 등으로 직접 옮겨야 함**) → 새 머신에 저장소를 clone하고 같은 경로에 `volumes/backup/*.tar.gz`를 둔 뒤 `bash scripts/restore-volumes.sh` 실행(볼륨이 없으면 생성) → `docker compose up -d`.
- **Git Bash(MSYS) 경로 변환 주의**: `docker run -v ...:/backup` 같은 컨테이너 내부 경로가 Git Bash에서 자동으로 Windows 경로로 오변환되는 문제가 실측으로 확인되어(`/backup/x.tar.gz` → `C:/Program Files/Git/backup/x.tar.gz`), 두 스크립트 모두 `docker run` 앞에 `MSYS_NO_PATHCONV=1`을 붙여 회피함.
- **일관성 caveat**: 컨테이너를 멈추지 않고(`docker compose stop` 없이) 라이브 상태에서 볼륨을 tar로 떴음 — 개발/데모 데이터 용도로는 충분하지만, WAL/체크포인트 시점에 따라 완전히 일관된 스냅샷이 아닐 수 있음. 완벽한 일관성이 필요하면 백업 전 `docker compose stop`으로 세 컨테이너를 멈추고 뜰 것.
- 2026-07-13 시점 백업 크기: `postgres_data` 10.7MB, `chroma_data` 7.9MB, `neo4j_data` 0.7MB(정책 100건/청크 712개/그래프 93건 데이터 포함).

1. `git clone` 후 저장소 루트에서 `.env.example`을 `.env`로 복사하고, `OPENAI_API_KEY`/`BIZINFO_API_KEY`/`JWT_SECRET`/DB 비밀번호 등 실제 값을 채워 넣는다(비밀값은 git으로 옮겨지지 않으므로 별도 안전한 경로로 직접 가져와야 함).
2. **(선택, 권장) 볼륨 복원**: 원본 머신에서 만든 `volumes/backup/*.tar.gz`(13.1절)를 새 머신의 같은 경로에 두고 `bash scripts/restore-volumes.sh` 실행 — 이후 `docker compose up -d` 하면 정책/청크/그래프 데이터가 이미 채워진 채로 시작됨. 백업이 없으면 5번 단계에서 재수집하면 된다.
3. Docker Desktop 설치·실행 후 저장소 루트에서 `docker compose up -d` (postgres, chroma, neo4j 3개 컨테이너 기동). **`chroma` 이미지 태그(`chromadb/chroma:1.5.9`)는 `backend/requirements.txt`의 `chromadb` 파이썬 클라이언트 버전과 반드시 맞춰야 함**(10.1절 — 버전 불일치 시 `KeyError('_type')`로 실패).
4. `backend/`에서 venv 생성 후 `pip install -r requirements.txt` (Python 3.13 기준으로 개발/검증함). `bcrypt==4.0.1` 고정 이유는 10.5절 참고 — 다른 버전으로 임의 업그레이드하지 말 것.
5. 백엔드 기동: `uvicorn app.main:app --reload` (backend/ 디렉터리에서). 최초 기동 시 `lifespan`이 테이블 생성 + 마이그레이션 + 데모 로그인 계정 시드(`demo-001@example.com`/`demo-002@example.com`, 비밀번호 `demo1234`)까지 자동 처리(`app/main.py`). **2번에서 볼륨을 복원했다면 이 단계로 충분 — 아래 데이터 재수집은 생략.**
6. **(2번을 건너뛴 경우만) 데이터 재수집**(빈 DB에서 순서대로 호출, 8절 API 표 참고):
   `POST /api/policies/sync` → `POST /api/policies/parse` → `POST /api/policies/embed` → `POST /api/policies/graph/build` → `POST /api/companies/{company_id}/matches/refresh`. bge-m3 모델은 첫 임베딩 호출 시 다운로드되므로 시간이 걸릴 수 있음(HF_TOKEN 미설정 시 rate limit 경고는 무시 가능).
7. 프론트엔드: `frontend/`에서 `npm install` → `npm run dev` (`http://localhost:5173`). 로그인/매칭 대시보드/채팅 상담/정책 그래프 탐색 4개 화면 구현 완료(12.6절).
8. 이 문서(`detailed_plan.md`)가 지금까지의 모든 결정/버그/검증 이력의 단일 소스이므로, 새 컴퓨터에서 세션을 시작할 때 이 문서를 먼저 읽고 이어가면 됨. Claude Code의 로컬 메모리(사용자 선호/프로젝트 메모)는 이 저장소 경로에 종속되어 **다른 컴퓨터로 자동 이관되지 않음** — 필요한 맥락은 전부 이 문서와 git 커밋 메시지에 있음.
