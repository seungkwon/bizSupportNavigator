# 백업 및 복원 가이드

이 프로젝트의 로컬 상태(정책/청크/그래프 데이터)는 Docker 볼륨 3개(`postgres_data`, `chroma_data`, `neo4j_data`)에 저장된다. `git clone`만으로는 이 데이터가 옮겨지지 않으므로, 다른 컴퓨터로 이어서 작업하거나 데이터를 안전하게 보관하려면 아래 스크립트로 볼륨을 tar로 백업/복원한다.

관련 배경: [detailed_plan.md](detailed_plan.md) 13절.

## 방식 요약

- `docker-compose.yml`의 세 데이터 볼륨을 각각 `alpine` 컨테이너로 마운트해 tar로 묶는 **파일시스템 레벨 통째 복사** 방식이다.
- `pg_dump`, `neo4j-admin dump` 같은 DB별 전용 도구를 쓰지 않고 하나의 스크립트로 세 DB를 모두 처리한다(가장 단순한 방법을 선호하기로 한 결정에 따름).
- 백업 파일은 `volumes/backup/*.tar.gz`에 생성되며, 이 디렉터리는 `.gitignore`의 `volumes/` 규칙에 포함되어 **git으로는 옮겨지지 않는다** — USB나 원격 복사 등으로 직접 옮겨야 한다.

## 백업하기

원본 머신의 저장소 루트에서:

```bash
bash scripts/backup-volumes.sh
```

- 대상 볼륨: `postgres_data`, `chroma_data`, `neo4j_data` (실제 볼륨명은 컴포즈 프로젝트 접두사가 붙어 `bizsupportnavigator_postgres_data` 등)
- 결과물: `volumes/backup/postgres_data.tar.gz`, `volumes/backup/chroma_data.tar.gz`, `volumes/backup/neo4j_data.tar.gz`
- 생성된 tar.gz 파일들을 USB/원격 복사 등으로 새 머신의 **같은 상대 경로**(`volumes/backup/`)에 옮긴다.

### 참고 (일관성 caveat)

컨테이너를 멈추지 않고(`docker compose stop` 없이) 라이브 상태에서 볼륨을 떠도 스크립트는 동작한다. 개발/데모 데이터 용도로는 충분하지만, WAL/체크포인트 시점에 따라 완전히 일관된 스냅샷이 아닐 수 있다. **완벽한 일관성이 필요하면** 백업 전에 세 컨테이너를 먼저 멈춘다.

```bash
docker compose stop
bash scripts/backup-volumes.sh
docker compose start
```

## 복원하기

새 머신에서, **`docker compose up -d`를 실행하기 전에** 아래 순서로 진행한다.

1. 저장소를 clone하고 `.env.example`을 `.env`로 복사한 뒤 실제 값(`OPENAI_API_KEY`, `BIZINFO_API_KEY`, `JWT_SECRET`, DB 비밀번호 등)을 채워 넣는다. 비밀값은 git으로 옮겨지지 않으므로 별도의 안전한 경로로 가져와야 한다.
2. 원본 머신에서 만든 `volumes/backup/*.tar.gz`를 새 머신의 저장소 루트 아래 같은 경로(`volumes/backup/`)에 둔다.
3. 복원 스크립트를 실행한다.

   ```bash
   bash scripts/restore-volumes.sh
   ```

   - 대상 볼륨이 없으면 자동으로 생성한다(`docker volume create`).
   - 각 볼륨의 기존 데이터를 삭제(`rm -rf /data/*`)하고 tar.gz 내용으로 덮어쓴다.
   - 대응하는 `volumes/backup/<name>.tar.gz` 파일이 없는 볼륨은 건너뛴다(스킵 메시지 출력).
4. 컨테이너를 기동한다.

   ```bash
   docker compose up -d
   ```

   이후 postgres/chroma/neo4j가 이미 채워진 데이터로 시작되므로, 정책 재수집(`sync`/`parse`/`embed`/`graph/build`) 단계를 생략할 수 있다.

백업이 없거나 일부만 있는 경우, 해당 서비스만 빈 상태로 시작되며 [detailed_plan.md](detailed_plan.md) 13절의 6번 단계(데이터 재수집 API 호출 순서)로 채우면 된다.

## Git Bash(MSYS) 경로 변환 주의

Windows에서 Git Bash로 스크립트를 실행할 경우, `docker run -v ...:/backup` 같은 컨테이너 내부 경로가 자동으로 Windows 경로로 오변환되는 문제가 있다(예: `/backup/x.tar.gz` → `C:/Program Files/Git/backup/x.tar.gz`). 두 스크립트 모두 이를 회피하기 위해 `docker run` 앞에 `MSYS_NO_PATHCONV=1`을 이미 붙여두었으므로, 스크립트를 그대로 실행하면 된다. 직접 유사한 `docker run` 명령을 실행할 때는 동일하게 `MSYS_NO_PATHCONV=1` 접두사를 붙일 것.

## 스크립트 위치

- [scripts/backup-volumes.sh](scripts/backup-volumes.sh)
- [scripts/restore-volumes.sh](scripts/restore-volumes.sh)
