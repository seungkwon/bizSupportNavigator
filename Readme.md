# RAG + Graph RAG 를 이용한 정책 자금 추천

1. 일차 계획  plan.md
2. 클로드의 상세 계획 : detailed_plan.md
3. 데이터 백업 방법: BACKUP_RESTORE.md
4. 로컬 운영 방법: RUNNING_LOCALLY.md
5. 정책 데이터 수집 파이프라인 실행 방법: POLICY_COLLECTION.md

## Revision History

- **2026-07-13**:
  - 대시보드 추천 카드에서 "이 정책에 대해 질문 답하고 재계산" 버튼으로 채팅 페이지 진입 시 해당 정책에 한해 확인 불가 요건을 모두 질문(라운드 상한 없음, 일반 채팅은 기존처럼 3라운드 상한 유지)하도록 연결.
  - 채팅 답변은 세션이 아닌 기업 단위(`company_facts` 테이블)로 저장해 서버 재기동/세션 종료와 무관하게 유지되며, 이후 다른 정책을 판정할 때도 bge-m3 임베딩 유사도로 관련 답변을 찾아 재사용(같은 내용을 정책마다 다시 묻지 않음).
  - 기업 데모그래픽을 하드코딩 mock(`app/mock/demographics.py`)에서 실제 DB 테이블(`company_profiles`)로 전환. 새 "기업 정보 관리" 화면(`/profile`)에서 데모그래픽 프로필과 `company_facts`(채팅 수집 사실) 목록을 직접 조회/수정/삭제/추가 가능.
  - 프론트엔드에 Tailwind CSS v4 + DaisyUI(테마: forest) + Pretendard 폰트 적용. 기존 손으로 짠 `App.css`는 제거하고 로그인/대시보드/채팅/그래프/기업정보 5개 화면과 네비바 전부 Tailwind 유틸리티 + DaisyUI 컴포넌트로 재작성.
  - Docker Desktop 크래시(`com.docker.build` 버그, 4.44.0에서 상류 수정)로 인한 데이터 볼륨 유실 후, 정책 250건 재수집(sync) → 첨부파일 파싱(243/247건) → 청크 1750개 전량 임베딩 → 지식그래프 236개 정책 구축까지 전체 파이프라인 재실행. 총 소요 약 1시간 18분. 완료 즉시 `scripts/backup-volumes.sh`로 볼륨 백업(postgres+chroma+neo4j 합계 약 34.9MB) 수행. 수집 파이프라인 실행 가이드를 POLICY_COLLECTION.md로 별도 문서화.
  - 매칭 재계산 속도 개선: 후보 개수 기본값을 10→5로 낮추고(`/matches/refresh`, 채팅 시작), 정책별 LLM 판정(OpenAI 호출 1회/정책)을 순차 실행 대신 `ThreadPoolExecutor`로 병렬 실행하도록 변경(약 33.5초 → 16.1초). 겸사겸사 `save_match_results`가 이전 재계산 결과 중 이번엔 빠진 정책 행을 삭제하지 않던 버그를 수정(후보 수를 줄였는데도 화면에 예전 개수가 그대로 남던 원인).
  - 대시보드 "다시 계산" 버튼에 진행 표시 추가: 버튼에 스피너, 하단에 좌→우로 반복 이동하는 진행바(`indeterminate-bar`, `index.css`) 표시. 네이티브 `<progress>`(값 없는 indeterminate)는 Tailwind preflight/DaisyUI 조합에서 애니메이션이 멈춰 보이는 문제가 있어, 순수 CSS keyframe 애니메이션으로 대체.
