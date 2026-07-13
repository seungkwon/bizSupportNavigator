# RAG + Graph RAG 를 이용한 정책 자금 추천

1. 일차 계획  plan.md
2. 클로드의 상세 계획 : detailed_plan.md
3. 데이터 백업 방법: BACKUP_RESTORE.md
4. 로컬 운영 방법: RUNNING_LOCALLY.md

## Revision History

- **2026-07-13**:
  - 대시보드 추천 카드에서 "이 정책에 대해 질문 답하고 재계산" 버튼으로 채팅 페이지 진입 시 해당 정책에 한해 확인 불가 요건을 모두 질문(라운드 상한 없음, 일반 채팅은 기존처럼 3라운드 상한 유지)하도록 연결.
  - 채팅 답변은 세션이 아닌 기업 단위(`company_facts` 테이블)로 저장해 서버 재기동/세션 종료와 무관하게 유지되며, 이후 다른 정책을 판정할 때도 bge-m3 임베딩 유사도로 관련 답변을 찾아 재사용(같은 내용을 정책마다 다시 묻지 않음).
  - 기업 데모그래픽을 하드코딩 mock(`app/mock/demographics.py`)에서 실제 DB 테이블(`company_profiles`)로 전환. 새 "기업 정보 관리" 화면(`/profile`)에서 데모그래픽 프로필과 `company_facts`(채팅 수집 사실) 목록을 직접 조회/수정/삭제/추가 가능.
