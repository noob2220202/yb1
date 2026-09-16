# 축구 배당 분석 SaaS (odds-app)

축구 프리매치 오즈를 API-Football에서 수집하고, devig(마진 제거)로 실제 확률을
역산해 한 경기 내 두 개의 단폴더를 조합한 헤지 배팅의 **적중률·손익분기확률·
추정 EV**를 함께 보여주는 개인용 대시보드. 상세 요구사항은 [SPEC.md](../SPEC.md)
참고.

> ⚠ 모든 조합 화면에는 "이 배분은 손익 분산만 줄일 뿐 기대값을 개선하지
> 않습니다"라는 고정 문구가 표시됩니다. 자동 스테이크 증액/마틴게일/
> 손실추격 기능은 의도적으로 구현하지 않았습니다.

## 기술 스택

FastAPI + Jinja2 + HTMX + Tailwind CDN (빌드 파이프라인 없음), PostgreSQL +
SQLAlchemy 2.x + Alembic, APScheduler(프로세스 내 스케줄러). venv/Docker 미사용 —
시스템에 직접 설치.

## 로컬 개발 환경 설정

```bash
sudo apt update
sudo apt install -y python3-pip postgresql postgresql-contrib
pip install --break-system-packages -r requirements.txt
```

### PostgreSQL 초기 설정

```bash
sudo -u postgres createuser oddsapp
sudo -u postgres createdb oddsapp_db -O oddsapp
sudo -u postgres psql -c "ALTER USER oddsapp WITH PASSWORD '설정할비밀번호';"

# 테스트용 DB (pytest가 사용)
sudo -u postgres createdb oddsapp_test -O oddsapp
```

`.env.example`을 `.env`로 복사하고 `DATABASE_URL`, `API_FOOTBALL_KEY` 등을 채운다.

```bash
cp .env.example .env
```

### DB 마이그레이션

```bash
python3 -m alembic upgrade head
```

### 헬스체크

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
curl http://127.0.0.1:8000/health   # {"status":"ok","db":true}
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

`services/devig.py`, `services/staking.py`, `services/combo_engine.py`,
`services/ingest.py`에 대한 단위/통합 테스트가 포함되어 있으며, 스테이킹
계산기는 SPEC.md 12절의 실측 검증 수치를 회귀 테스트로 고정해뒀다.

## 수동 시딩(개발용)

실제 API 키 없이 대시보드/조합 엔진을 눈으로 확인하려면, `run_ingest_cycle`에
mock 클라이언트를 주입해 샘플 fixture를 넣을 수 있다. 예시는
`tests/test_ingest.py`의 `FakeOddsApiClient`를 참고.

## 배포 (venv/Docker 없이, systemd + 기존 Caddy)

### systemd 서비스

`/etc/systemd/system/oddsapp.service`:

```ini
[Unit]
Description=Odds Analysis App
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/odds-app
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
EnvironmentFile=/opt/odds-app/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now oddsapp
sudo systemctl status oddsapp
```

배포 전 `.env`의 `ENABLE_SCHEDULER=true`로 설정해야 APScheduler가 오즈 수집을
자동으로 시작한다 (기본값은 개발 편의를 위해 로컬 `.env`에서 `false`로 되어있음).

### Caddy 리버스 프록시 (기존 Caddyfile에 추가)

```
odds.본인도메인.com {
    reverse_proxy localhost:8000
}
```

```bash
sudo systemctl reload caddy
```

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
├── .env.example
└── requirements.txt
```

## 알려진 제약 (다음 단계)

- `API_FOOTBALL_KEY`가 없는 환경에서 개발되어, 실제 API 응답으로 매핑표를
  최종 검증하지 못했다. 키 발급 후 `scripts/inspect_api_response.py` 실행 필수.
- 프로덕션 VPS에 systemd/Caddy를 실제로 적용하는 마지막 단계는 사용자의 실제
  서버 접근이 필요해 이 저장소 작업만으로는 수행할 수 없다 — 위 배포 절차를
  그대로 따르면 된다.
