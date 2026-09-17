# 축구 배당 분석 SaaS (odds-app)

축구 프리매치 오즈를 API-Football에서 수집하고, devig(마진 제거)로 실제 확률을
역산해 한 경기 내 두 개의 단폴더를 조합한 헤지 배팅의 **적중률·손익분기확률·
추정 EV**를 함께 보여주는 개인용 대시보드. 상세 요구사항은 [SPEC.md](../SPEC.md)
참고.

> ⚠ 모든 조합 화면에는 "이 배분은 손익 분산만 줄일 뿐 기대값을 개선하지
> 않습니다"라는 고정 문구가 표시됩니다. 자동 스테이크 증액/마틴게일/
> 손실추격 기능은 의도적으로 구현하지 않았습니다.

## 기술 스택

FastAPI + Jinja2 + HTMX + Tailwind CDN (빌드 파이프라인 없음), **SQLite** +
SQLAlchemy 2.x + Alembic, APScheduler(프로세스 내 스케줄러). venv/Docker 미사용 —
시스템에 직접 설치. 별도 DB 서버 설치/운영이 필요 없다 — 앱 폴더 안의 파일
하나(`oddsapp.db`)가 DB 전체다.

## 빠른 시작: git clone → pm2 실행

새 서버(VPS)에서 처음부터 띄우는 전체 과정이다. 도메인/Caddy 연결은 마지막 절
참고.

### 1. 시스템 준비 (Python + Node/pm2)

```bash
sudo apt update
sudo apt install -y python3-pip git

# pm2는 Node.js 위에서 돌아가므로 Node/npm이 필요하다 (없는 경우만)
sudo apt install -y nodejs npm
sudo npm install -g pm2
```

### 2. 저장소 클론

```bash
cd /opt   # 원하는 배포 경로 — 이후 예시는 전부 /opt/yb1 기준
sudo git clone https://github.com/noob2220202/yb1.git
cd yb1/odds-app
```

### 3. 파이썬 의존성 설치 (venv 없이 시스템에 직접)

```bash
python3 -m pip install --break-system-packages -r requirements.txt
```

> `no such option: --break-system-packages` 에러가 나면, 그 시스템의 pip는
> PEP668 제한이 아예 없는 구버전이라 플래그 자체를 모른다는 뜻이다. 플래그
> 없이 그냥 설치하면 된다: `python3 -m pip install -r requirements.txt`.
> 설치가 조용히 실패하면 이후 모든 단계가 이상하게 꼬이니(예: alembic이
> 설치 안 된 채로 `python3 -m alembic`을 실행하면 `odds-app/alembic/`
> 마이그레이션 폴더를 패키지로 착각해 알 수 없는 에러가 난다), 아래로
> 반드시 설치 확인을 하고 넘어갈 것.

```bash
python3 -c "import fastapi, alembic, sqlalchemy, apscheduler; print('설치 OK')"
```

### 4. 환경변수 설정

```bash
cp .env.example .env
```

`.env`는 기본값 그대로도 바로 동작한다 (`DATABASE_URL=sqlite:///./oddsapp.db`).
축구 배당을 자동 수집하려면 `API_FOOTBALL_KEY`를 채우고, 결제 전이라면 비워두고
`/manual` 페이지로 수동 입력만 써도 된다. 배포 환경에서는 스케줄러를 켜기 위해
`ENABLE_SCHEDULER=true`로 바꿔둔다.

### 5. DB 마이그레이션 (SQLite 파일 생성)

```bash
alembic upgrade head
# odds-app/oddsapp.db 파일이 생성된다
```

> `alembic: command not found`면 pip 스크립트 설치 경로가 PATH에 없는 것이다:
> `export PATH="$HOME/.local/bin:$PATH"` 후 재시도하거나, 그래도 안 되면
> `python3 -c "from alembic.config import main; main(['upgrade','head'])"`로
> 실행할 수 있다. (`python3 -m alembic`은 쓰지 말 것 — 현재 디렉토리에 있는
> `odds-app/alembic/` 마이그레이션 폴더와 이름이 겹쳐서, 실제 alembic이 설치
> 안 된 상태에서 실행하면 혼란스러운 에러가 난다.)

### 6. 로컬에서 한 번 확인

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 6666 &
curl http://127.0.0.1:6666/health   # {"status":"ok","db":true}
kill %1   # 확인 후 종료 (pm2로 다시 띄울 것이므로)
```

### 7. pm2로 상시 구동

저장소에 `ecosystem.config.js`가 이미 포함되어 있다 (`python3 -m uvicorn ...`을
pm2 프로세스로 등록):

```bash
cd /opt/yb1/odds-app
pm2 start ecosystem.config.js
pm2 status                # odds-app 프로세스가 online인지 확인
pm2 logs odds-app --lines 50   # 로그 확인
```

### 8. 재부팅 후에도 자동 시작되도록 등록

```bash
pm2 save                  # 현재 pm2 프로세스 목록 저장
pm2 startup               # 출력되는 sudo 명령을 그대로 한 번 복사해서 실행
```

이후로는 서버가 재부팅돼도 pm2가 `odds-app`을 자동으로 다시 띄운다.

### 자주 쓰는 pm2 명령

```bash
pm2 restart odds-app      # 코드 수정 후 재시작
pm2 stop odds-app
pm2 delete odds-app       # 프로세스 목록에서 완전히 제거
pm2 logs odds-app         # 실시간 로그
```

코드를 업데이트할 때는:

```bash
cd /opt/yb1
git pull
cd odds-app
python3 -m pip install --break-system-packages -r requirements.txt   # 의존성 변경 시
alembic upgrade head                                                  # 스키마 변경 시
pm2 restart odds-app
```

## API 키 없이 수동으로 쓰기 (`/manual`)

API-Football은 유료이므로, 키를 결제하기 전에도 조합 추천 엔진을 그대로 쓸 수
있도록 수동 입력 기능을 제공한다.

- 상단 네비게이션의 **수동 입력** → **+ 새 경기 입력**에서 팀명/킥오프와
  오즈를 직접 입력한다.
- 입력 항목은 조합 계산에 실제로 쓰이는 마켓만: **1X2(필수)**, DNB, 아시안
  핸디캡 ±0.5/±1, 승리마진(홈 1골차/홈 2골차+/무승부/원정 1골차/원정 2골차+).
  모르는 값은 비워두면 해당 마켓이 필요한 조합만 자동으로 생략된다.
- 핸디캡 두 라인(±0.5, ±1) 모두 "정배팀(홈/원정)"을 한 번만 고르면 되고,
  나머지는 그 팀 기준 오즈만 입력하면 된다 — 어느 팀이 실제 정배인지는
  1X2 오즈로 devig 엔진이 다시 한번 검증해서 조합을 만든다.
- 저장하면 자동 수집 경기와 동일한 `/fixtures/{id}` 페이지로 이동해 조합
  추천(적중확률/손익분기확률/EV%)을 바로 확인할 수 있다.
- 수동 입력 경기는 대시보드(`/`)에는 나오지 않고 `/manual` 목록에서만 관리한다.
- 오즈가 바뀌면(라인업 발표 등) 같은 경기를 다시 "수정"하면 되며, 저장할
  때마다 기존 값은 덮어써진다(시계열 이력 없음 — 자동 수집과 다른 점).

## API-Football 키 연동 (중요 — 실제 데이터 수집을 위한 필수 단계)

이 저장소의 `app/services/market_type_mapping.py`는 API-Football v3 공개 문서를
기준으로 작성된 **초안**이다. 실제 API 키를 발급받은 뒤 아래 스크립트로 실제
응답 구조를 캡처해 매핑표를 검증/보정해야 한다 (SPEC.md 5.2절 요구사항):

```bash
# .env에 API_FOOTBALL_KEY 설정 후
python3 scripts/inspect_api_response.py
```

이 스크립트는 실제 bet 이름 목록과 현재 매핑표를 대조해 누락된 항목을 알려준다.
파이프라인 로직 자체(파싱/그룹핑/insert-only 시계열)는 `tests/test_ingest.py`의
mock 데이터로 이미 end-to-end 검증되어 있다.

## 테스트

```bash
python3 -m pytest -q
```

테스트는 파일 기반 DB와 분리된 인메모리 SQLite를 사용하므로 (`tests/conftest.py`),
별도 테스트 DB 설정 없이 바로 실행된다. `services/devig.py`, `services/staking.py`,
`services/combo_engine.py`, `services/ingest.py`, `services/manual_entry.py`에 대한
단위/통합 테스트가 포함되어 있으며, 스테이킹 계산기는 SPEC.md 12절의 실측 검증
수치를 회귀 테스트로 고정해뒀다.

## 수동 시딩(개발용)

실제 API 키 없이 대시보드/조합 엔진을 눈으로 확인하려면, `run_ingest_cycle`에
mock 클라이언트를 주입해 샘플 fixture를 넣을 수 있다. 예시는
`tests/test_ingest.py`의 `FakeOddsApiClient`를 참고.

## Caddy 리버스 프록시로 도메인 연결 (선택)

pm2가 `127.0.0.1:6666`(정확히는 `0.0.0.0:6666`)에서 서비스를 띄우고 있으므로,
기존 Caddy에 한 줄만 추가하면 된다 (`deploy/Caddyfile.snippet` 참고):

```
odds.본인도메인.com {
    reverse_proxy localhost:6666
}
```

```bash
sudo systemctl reload caddy
```

## systemd를 쓰고 싶다면 (pm2 대신 — 둘 다 필요하지는 않음)

pm2 대신 systemd로 상시 구동하고 싶다면 `deploy/oddsapp.service`를 참고한다
(`ExecStart`/`WorkingDirectory`의 경로를 실제 클론 위치로 맞출 것):

```bash
sudo cp deploy/oddsapp.service /etc/systemd/system/oddsapp.service
sudo systemctl daemon-reload
sudo systemctl enable --now oddsapp
sudo systemctl status oddsapp
```

배포 전 `.env`의 `ENABLE_SCHEDULER=true`로 설정해야 APScheduler가 오즈 수집을
자동으로 시작한다 (기본값은 개발 편의를 위해 로컬 `.env`에서 `false`로 되어있음).
pm2 방식을 쓴다면 이 절은 건너뛰어도 된다.

## 디렉토리 구조

```
odds-app/
├── app/
│   ├── main.py                 # FastAPI 엔트리포인트
│   ├── config.py                # .env 로드
│   ├── db.py                    # SQLAlchemy engine/session
│   ├── templating.py            # Jinja2Templates 공용 인스턴스
│   ├── models/                  # ORM 모델 (fixture/market/odds/combo)
│   ├── schemas/                 # Pydantic 스키마
│   ├── clients/odds_api_client.py
│   ├── services/
│   │   ├── ingest.py             # 오즈 수집 파이프라인
│   │   ├── market_type_mapping.py
│   │   ├── devig.py              # 마진 제거 확률 계산
│   │   ├── staking.py            # 이익균등화 계산기
│   │   ├── combo_engine.py       # 조합 생성/랭킹
│   │   ├── manual_entry.py       # API 키 없이 수동 오즈 입력
│   │   └── scheduler.py          # APScheduler job 정의
│   ├── routers/ (fixtures.py, manual.py, calculator.py)
│   └── templates/ (base/dashboard/fixture_detail/calculator/manual_list/manual_form.html)
├── alembic/
├── tests/
├── scripts/inspect_api_response.py
├── deploy/ (oddsapp.service, Caddyfile.snippet)
├── ecosystem.config.js         # pm2 프로세스 정의
├── oddsapp.db                   # SQLite DB 파일 (git-ignored, 마이그레이션으로 생성)
├── .env.example
└── requirements.txt
```

## 알려진 제약 (다음 단계)

- `API_FOOTBALL_KEY`가 없는 환경에서 개발되어, 실제 API 응답으로 매핑표를
  최종 검증하지 못했다. 키 발급 후 `scripts/inspect_api_response.py` 실행 필수.
- 프로덕션 VPS에 systemd/Caddy를 실제로 적용하는 마지막 단계는 사용자의 실제
  서버 접근이 필요해 이 저장소 작업만으로는 수행할 수 없다 — 위 배포 절차를
  그대로 따르면 된다.
