# 축구 배당 분석 SaaS — Claude Code 개발 지침서

> 이 문서를 Claude Code에게 그대로 전달하고 "이 지침서대로 프로젝트를 구축해줘"라고 요청하면 됩니다.
> 본인(1인) 전용 웹앱이며 로그인 기능은 만들지 않습니다. MVP이므로 디자인은 최소한으로, 기능은 완전히 동작해야 합니다.

---

## 0. 프로젝트 한 줄 요약

축구 프리매치 오즈를 API로 수집 → 마진 제거(devig)로 실제 확률 역산 → 한 경기 내 서로 다른 두 개의 단일 베팅(단폴더)을 조합해 **적중률과 EV를 함께 계산**하는 개인용 대시보드. "적중률만 높고 EV는 마이너스인 조합"을 사용자가 착각 없이 알아보도록, 모든 조합에 **손익분기 확률·추정 EV·손익 시나리오표**를 반드시 함께 보여준다.

---

## 1. 환경 제약 조건 (중요, 반드시 준수)

- **가상환경(venv, conda 등) 사용 금지.** 시스템 Python에 `pip install --break-system-packages` 로 직접 설치.
- **Docker/컨테이너 사용 금지.** 모든 프로세스는 시스템에 직접 설치·실행.
- **PostgreSQL은 시스템 패키지로 직접 설치**(`apt install postgresql`), 별도 컨테이너 없이 로컬 서비스로 구동.
- 프로세스 상시 구동은 `systemd` 서비스 유닛 또는 `nohup` + `tmux`/`screen` 방식 중 택1 (systemd 권장, 재부팅 시 자동 시작).
- 단일 서버(VPS) 내에서 백엔드·스케줄러·프론트가 모두 함께 돈다고 가정. 사용자는 자체 VPS(캐디, 클라우드플레어, 가비아 도메인 사용 중)를 운영 중이므로, 리버스 프록시는 **Caddy**를 그대로 활용.

---

## 2. 기술 스택

| 레이어 | 선택 | 이유 |
|---|---|---|
| 언어/백엔드 | **Python 3.11+ / FastAPI** | devig 계산에 pandas/numpy 활용, Pydantic으로 마켓 스키마 검증 |
| DB | **PostgreSQL** (시스템 설치) | fixture-market-odds 관계형 스키마 + JSONB 유연성 |
| ORM | **SQLAlchemy 2.x + Alembic** | 마이그레이션 관리 |
| 스케줄러 | **APScheduler** (FastAPI 프로세스 내 BackgroundScheduler) | 별도 워커 없이 단일 프로세스로 폴링 |
| 프론트 | **FastAPI + Jinja2 서버사이드 렌더링 + HTMX** | 빌드 파이프라인 없이 단일 프로세스, MVP에 최적. React/Node 별도 스택 불필요 |
| 스타일 | **Tailwind CDN (play-CDN, `<script src="https://cdn.tailwindcss.com">`)** | 빌드 없이 바로 사용, 디자인 최소 노력 |
| 프로세스 매니저 | **systemd** | `oddsapp.service` 유닛 등록 |
| 리버스 프록시 | **기존 Caddy** | `oddsapp.내도메인.com { reverse_proxy localhost:8000 }` 한 줄 추가 |
| 오즈 데이터 소스 | **API-Football (API-Sports)** 1차 채택 (가성비, 잡리그 폭). Sportmonks는 예산 확정 후 2차 확장 슬롯으로 설계만 미리 열어둠 | 리서치 보고서 결론 참고 |

> Claude Code에게: Node.js/React 등 별도 프론트엔드 빌드 체인은 만들지 말 것. FastAPI 단일 프로세스 + Jinja2 + HTMX + Tailwind CDN으로 충분하다.

---

## 3. 디렉토리 구조

```
odds-app/
├── app/
│   ├── main.py                 # FastAPI 엔트리포인트, 라우터 등록, APScheduler 시작
│   ├── config.py                # 환경변수 로드 (.env)
│   ├── db.py                    # SQLAlchemy engine/session
│   ├── models/                  # ORM 모델
│   │   ├── fixture.py
│   │   ├── market.py
│   │   ├── odds.py
│   │   └── combo.py             # 조합 계산 결과 캐시(선택)
│   ├── schemas/                 # Pydantic 스키마
│   ├── clients/
│   │   └── odds_api_client.py   # API-Football 연동 클라이언트
│   ├── services/
│   │   ├── ingest.py            # 오즈 수집 파이프라인
│   │   ├── devig.py             # 마진 제거 확률 계산 엔진
│   │   ├── staking.py           # 스테이크 이퀄라이제이션 계산기
│   │   ├── combo_engine.py      # 두 다리 조합 생성 + 랭킹
│   │   └── scheduler.py         # APScheduler job 정의
│   ├── routers/
│   │   ├── fixtures.py
│   │   ├── combos.py
│   │   └── calculator.py        # 수동 이익균등화 계산기 엔드포인트
│   └── templates/               # Jinja2 템플릿
│       ├── base.html
│       ├── dashboard.html
│       ├── fixture_detail.html
│       └── calculator.html
├── alembic/                     # DB 마이그레이션
├── tests/
├── .env                         # API 키 등 (git-ignore)
├── .env.example
├── requirements.txt
└── README.md
```

---

## 4. 데이터베이스 스키마 (핵심 테이블)

```sql
-- 경기(fixture)
CREATE TABLE fixtures (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(64) UNIQUE NOT NULL,   -- API 원본 fixture id
    league_id INT NOT NULL,
    league_name VARCHAR(200) NOT NULL,
    country VARCHAR(100),
    home_team VARCHAR(200) NOT NULL,
    away_team VARCHAR(200) NOT NULL,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'scheduled',    -- scheduled/finished/cancelled
    home_score INT,                             -- 정산용, 경기 후 채움
    away_score INT,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

-- 마켓 정의 (1X2, AH, O/U, 정확한점수, 승리마진, BTTS 등)
CREATE TABLE markets (
    id BIGSERIAL PRIMARY KEY,
    fixture_id BIGINT REFERENCES fixtures(id) ON DELETE CASCADE,
    market_type VARCHAR(50) NOT NULL,   -- '1x2' | 'ah' | 'ou' | 'correct_score' | 'win_margin' | 'btts' | 'dnb'
    line NUMERIC(4,2),                  -- AH/OU의 라인 값 (예: -0.5, 2.5), 없으면 NULL
    bookmaker VARCHAR(50) NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

-- 개별 오즈(선택지별)
CREATE TABLE odds (
    id BIGSERIAL PRIMARY KEY,
    market_id BIGINT REFERENCES markets(id) ON DELETE CASCADE,
    selection VARCHAR(50) NOT NULL,     -- 'home' | 'draw' | 'away' | 'over' | 'under' | '1-0' | 'home_by_1' 등
    decimal_odds NUMERIC(6,3) NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

-- 조합 계산 결과 캐시 (재계산 비용 절감용, 선택적)
CREATE TABLE combo_recommendations (
    id BIGSERIAL PRIMARY KEY,
    fixture_id BIGINT REFERENCES fixtures(id) ON DELETE CASCADE,
    leg_a_market_id BIGINT REFERENCES markets(id),
    leg_a_selection VARCHAR(50),
    leg_b_market_id BIGINT REFERENCES markets(id),
    leg_b_selection VARCHAR(50),
    combo_type VARCHAR(50),             -- 'draw_dnb' | 'ah_plus1_margin1' | 'custom'
    implied_hit_rate NUMERIC(5,4),      -- devig 기반 추정 적중확률
    breakeven_prob NUMERIC(5,4),        -- 손익분기 확률
    estimated_ev_pct NUMERIC(6,3),      -- 추정 EV(%)
    stake_leg_a NUMERIC(12,2),
    stake_leg_b NUMERIC(12,2),
    total_stake NUMERIC(12,2),
    target_profit NUMERIC(12,2),
    computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_fixtures_kickoff ON fixtures(kickoff_utc);
CREATE INDEX idx_markets_fixture ON markets(fixture_id);
CREATE INDEX idx_odds_market ON odds(market_id);
```

Alembic으로 위 스키마를 마이그레이션 파일로 생성할 것.

---

## 5. 오즈 수집 파이프라인 (`services/ingest.py`)

### 5.1 동작 방식
- APScheduler가 **15분 간격**으로 다음 24~72시간 내 예정된 축구 경기 목록을 API-Football에서 가져온다.
- 각 fixture에 대해 오즈 엔드포인트를 호출해 지원되는 모든 마켓(1X2, 아시안핸디캡, 오버언더, 정확한점수, 승리마진, BTTS, DNB)을 가져온다.
- 가져온 원본 오즈는 **매번 새 row로 insert**(update 아님) → 시계열로 오즈 변동 이력을 남긴다. 대시보드/조합계산은 항상 "가장 최근 fetched_at" 값만 사용.
- API 레이트리밋을 고려해 리그 우선순위(5대 리그 → 그 외)를 두고, 경기 시작이 임박할수록(예: 3시간 이내) 폴링 주기를 5분으로 단축.

### 5.2 API-Football 연동 시 주의사항
- API 키는 `.env`의 `API_FOOTBALL_KEY`에서 로드, 코드에 하드코딩 금지.
- 요청 실패(레이트리밋, 5xx)는 지수 백오프로 최대 3회 재시도 후 로그만 남기고 스킵(파이프라인 전체가 죽지 않도록).
- 마켓 이름 매핑 테이블(`market_type_mapping.py`)을 만들어 API 응답의 원본 마켓명을 위 스키마의 `market_type`/`selection` 값으로 정규화한다. (API-Football의 odds 응답 구조를 Claude Code가 실제 호출해 구조를 확인한 뒤 매핑 테이블을 확정할 것 — 문서만 보고 추측하지 말고 실제 응답 샘플로 검증)

---

## 6. Devig 엔진 (`services/devig.py`)

### 6.1 요구 함수

```python
def devig_multiplicative(odds: list[float]) -> list[float]:
    """2-way 시장(AH, O/U) 기본. 각 역배당을 합으로 정규화."""

def devig_power(odds: list[float]) -> list[float]:
    """1X2(3-way) 기본. 지수 k를 이분탐색으로 찾아 합=1이 되도록."""

def devig_shin(odds: list[float]) -> list[float]:
    """다결과(정확한 점수, 승리마진) 기본. 내부자 비율 z를 반복법으로 추정."""

def devig_market(market_type: str, odds: list[float]) -> list[float]:
    """market_type에 따라 위 세 함수 중 적절한 것을 자동 선택해 호출하는 라우터."""
```

### 6.2 시장별 방법 매핑 (리서치 결론 반영)

| market_type | devig 방법 |
|---|---|
| `1x2` | power |
| `ah`, `ou`, `dnb` | multiplicative |
| `correct_score`, `win_margin` | shin |
| `btts` | multiplicative |

### 6.3 컨센서스(다북메이커 평균)
- 여러 bookmaker의 동일 `(fixture_id, market_type, line, selection)` de-vig 확률을 **단순 평균**해 `consensus_probability`로 저장(1차 MVP는 단순평균, 추후 가중평균으로 개선 가능하도록 함수 시그니처에 `weights: dict[str, float] | None` 파라미터를 미리 열어둘 것).

### 6.4 EV 계산

```python
def calc_ev(stake: float, decimal_odds: float, true_prob: float) -> float:
    """EV = stake * (decimal_odds * true_prob - 1)"""
```

`true_prob`는 컨센서스 devig 확률을 사용한다.

---

## 7. 스테이크 이퀄라이제이션 계산기 (`services/staking.py`)

리서치에서 검증한 공식을 그대로 구현. **일반화된 다중 결과 균등이익 배분(dutching)** 을 기본으로 하고, push(환급) 규칙이 있는 마켓 조합(DNB, 정수 핸디캡)은 변형식을 적용한다.

### 7.1 기본 dutching 공식 (push 없음)

```python
def equal_profit_stakes(odds_list: list[float], total_stake: float) -> list[float]:
    """
    s_i = total_stake * (1/o_i) / sum(1/o_j for all j)
    반환: 각 결과에 배분할 스테이크 리스트. 어느 결과가 적중해도 동일 지급액.
    """
```

### 7.2 Push 규칙이 있는 2-다리 조합 (핵심 기능)

지원해야 할 조합 타입(마켓별 push 규칙을 파라미터로 명시):

| combo_type | 다리 A | 다리 B | push 조건 | 이익 시나리오 | 손실 시나리오 |
|---|---|---|---|---|---|
| `draw_dnb0` | 무승부 | 정배팀 DNB(AH0) | 무승부 시 다리B push | 무승부, 정배승 | 역배승 |
| `draw_ah05` | 무승부 | 정배팀 AH-0.5 | push 없음 | 무승부, 정배승 | 역배승 |
| `ahplus1_margin1` | 역배팀 AH+1 | 정배팀 정확히1골차승 | 정배 정확히1골차 시 다리A push | 역배승, 무승부, 정배1골차승 | 정배2골차+승 |

각 조합타입에 대해 다음을 계산하는 함수를 작성:

```python
def calc_draw_dnb0_stakes(odds_draw: float, odds_dnb: float, target_profit: float) -> dict:
    """
    s_D = target_profit / (odds_draw - 1)
    s_H = target_profit / (odds_dnb - 1)
    반환: {stake_draw, stake_dnb, total_stake, profit_draw, profit_home_win, loss_away_win}
    """

def calc_draw_ah05_stakes(odds_draw: float, odds_ah05: float, target_profit: float) -> dict:
    """순수 헤지: s_D = target_profit/(odds_draw-1), s_H = target_profit/(odds_ah05-1) 동일 원리(push 없어도 이익시나리오가 2개뿐이므로 동일식)"""

def calc_ahplus1_margin1_stakes(odds_ahplus1: float, odds_margin1: float, target_profit: float) -> dict:
    """
    이익시나리오 3개(역배승/무승부/정배1골차) 중 '역배승 또는 무승부'는 다리A만 승리,
    '정배1골차'는 다리A push + 다리B 승리이므로 목표이익이 다르게 걸린다.
    다리A 단독승리 이익 = target_profit 이 되도록 s_A를 정하고,
    다리A push + 다리B 승리 이익도 target_profit이 되도록 s_B를 정한다:
        s_A = target_profit / (odds_ahplus1 - 1)
        s_B = target_profit / (odds_margin1 - 1)
    """
```

**중요**: 각 계산 결과에는 반드시 다음 필드를 함께 반환할 것 — `breakeven_prob`(손실 시나리오가 일어나지 않아야 하는 최소 확률), `all_scenarios`(시나리오별 손익 dict). 스테이크 숫자만 던지고 끝내지 말 것.

### 7.3 API 엔드포인트 (`routers/calculator.py`)

- `POST /api/calculator/equalize` — body: `{combo_type, odds: {...}, target_profit 또는 total_stake}` → 위 계산 결과 JSON.
- 이 엔드포인트는 실시간 수동 입력용(대시보드의 "이익균등화 계산기" 탭)과, 조합 엔진의 자동 계산 양쪽에서 공용으로 재사용한다.

---

## 8. 조합 생성/랭킹 엔진 (`services/combo_engine.py`)

### 8.1 흐름
1. 특정 fixture의 최신 오즈(모든 마켓, 컨센서스 devig 확률 포함)를 로드.
2. 사전 정의된 `combo_type` 목록(7.2절 표)에 대해, 해당 마켓 데이터가 존재하면 후보 조합을 생성.
3. 각 후보에 대해:
   - `staking.py`로 스테이크 계산 (기본 total_stake는 설정값, 예: 30,000원 — `.env`의 `DEFAULT_TOTAL_STAKE`로 조정 가능)
   - devig 컨센서스 확률로 **조합 전체 EV** 계산 (각 다리 EV의 합)
   - `implied_hit_rate` = 이익 시나리오들의 devig 확률 합
4. **정렬 기준**: 기본은 `implied_hit_rate` 내림차순이나, **EV가 명확히 음수인 항목은 리스트 상단에서 자동으로 밀어내지 말고, 오히려 "⚠ 마이너스 EV" 배지를 붙여 그대로 노출**(사용자가 적중률과 EV를 모두 보고 직접 판단하게 함 — 리스트에서 숨기지 않는다).
5. 결과를 `combo_recommendations` 테이블에 캐시(경기 시작 전까지 유효, kickoff 지나면 자동 정리 job으로 삭제).

### 8.2 절대 금지 사항 (리서치 결론 반영, 반드시 코드 리뷰 시 확인)
- **자동 스테이크 증액/마틴게일 로직을 만들지 말 것.** "이전 픽 실패 시 다음 스테이크를 키운다" 류의 기능은 요구하지 않았고 앞으로도 추가하지 않는다.
- **손실추격(loss-chasing) 자동화(연속 배팅 세트 진행)를 만들지 말 것.**
- 모든 조합 화면에는 **"이 배분은 손익 분산만 줄일 뿐 기대값을 개선하지 않습니다"라는 고정 안내 문구**를 상단에 노출한다(하드코딩된 상수 문자열로, 삭제 옵션 없이).

---

## 9. 대시보드 UI 요구사항 (Jinja2 + HTMX + Tailwind CDN)

### 9.1 페이지 구성
1. **`/` 대시보드**: 오늘/내일 예정 경기 리스트, 리그 필터, 각 경기 옆에 "추천 조합 있음" 배지.
2. **`/fixtures/{id}` 경기 상세**: 해당 경기의 전체 마켓 오즈 원본 테이블 + 조합 후보 카드들.
   - 각 조합 카드에 표시할 것: 조합 설명(예: "무승부 + 홈팀 DNB"), 스테이크 배분, 시나리오별 손익표(표 형태), **적중확률**, **손익분기확률**, **추정 EV%**(양수면 초록, 음수면 빨강 배지).
3. **`/calculator` 수동 계산기**: combo_type 드롭다운 선택 → 오즈 수동 입력 → 목표이익 또는 총예산 입력 → 결과 즉시 표시(HTMX로 페이지 새로고침 없이).

### 9.2 디자인 지침
- MVP이므로 커스텀 CSS 최소화, Tailwind 유틸리티 클래스만 사용.
- 다크 테마 기본(사용자가 다른 프로젝트에서도 다크 UI 선호 — 참고만 하되 강제하지 않아도 됨).
- 반응형 불필요(본인 전용, 데스크톱 브라우저 기준으로만 만들어도 무방). 모바일 여지가 있으면 최소한의 반응형만.

---

## 10. 배포 (venv/Docker 없이)

### 10.1 설치
```bash
sudo apt update
sudo apt install -y python3-pip postgresql postgresql-contrib
pip install --break-system-packages -r requirements.txt
```

### 10.2 PostgreSQL 초기 설정
```bash
sudo -u postgres createuser oddsapp
sudo -u postgres createdb oddsapp_db -O oddsapp
sudo -u postgres psql -c "ALTER USER oddsapp WITH PASSWORD '설정할비밀번호';"
```
`.env`의 `DATABASE_URL=postgresql://oddsapp:비밀번호@localhost/oddsapp_db`

### 10.3 systemd 서비스 (`/etc/systemd/system/oddsapp.service`)
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
```

### 10.4 Caddy 설정 추가 (기존 Caddyfile에 추가)
```
odds.본인도메인.com {
    reverse_proxy localhost:8000
}
```
```bash
sudo systemctl reload caddy
```

---

## 11. 개발 순서 (마일스톤)

Claude Code는 아래 순서대로 단계별로 진행하고, **각 단계가 끝날 때마다 실제로 동작하는지 확인**한 뒤 다음 단계로 넘어갈 것 (한번에 전체를 만들고 마지막에 몰아서 디버깅하지 말 것).

1. **뼈대**: FastAPI 프로젝트 구조 생성, PostgreSQL 연결, Alembic 초기 마이그레이션(4절 스키마) → `/health` 엔드포인트로 DB 연결 확인.
2. **오즈 수집**: API-Football 클라이언트 작성 → 실제 API 호출해서 응답 구조 확인 → 마켓 매핑 테이블 확정 → fixtures/markets/odds 테이블에 실제 데이터 적재 성공 확인.
3. **Devig 엔진**: 6절 함수들을 단위 테스트와 함께 작성 (알려진 오즈 예시로 합=1 검증, 리서치 보고서의 검증 수치 재현).
4. **스테이킹 계산기**: 7절 함수 작성 → 리서치 보고서의 스크린샷 검증 수치(예: 무승부 4,100원/DNB 16,600원, 목표이익 10,076원)로 단위 테스트 통과 확인 → `/calculator` 엔드포인트/페이지 완성.
5. **조합 엔진**: 8절 로직 작성 → 실제 수집된 fixture 하나로 end-to-end 조합 추천이 나오는지 확인.
6. **대시보드**: 9절 페이지들 Jinja2로 완성.
7. **스케줄러 상시 구동**: APScheduler를 systemd 서비스로 안정화, 재부팅 후에도 자동 수집되는지 확인.
8. **배포**: Caddy 연결, 실제 도메인으로 접속 확인.

---

## 12. 테스트 요구사항

- `services/devig.py`, `services/staking.py`는 **반드시 pytest 단위 테스트 포함**(계산 로직이 핵심이므로 회귀 방지 필수).
- 스테이킹 계산기는 본 지침서 7.2절 표의 세 가지 조합 타입 각각에 대해, 이 대화에서 검증한 실제 숫자 예시를 회귀 테스트 케이스로 그대로 넣을 것:
  - `draw_dnb0`: odds_draw=3.46, odds_dnb=1.854, target_profit≈10076 → stake_draw≈4100, stake_dnb=16600 근사 검증
  - `ahplus1_margin1`: odds_ahplus1=1.93, odds_margin1=3.8, target_profit≈10071~10080 → stake≈14700/3600 근사 검증

---

## 13. Claude Code에게 전달할 최초 프롬프트 예시

이 지침서 파일 자체를 프로젝트 루트에 `SPEC.md`로 저장해두고, Claude Code에게는 다음과 같이 요청하는 것을 권장합니다:

> "SPEC.md 파일의 내용대로 프로젝트를 처음부터 구축해줘. 11번 섹션의 마일스톤 순서를 따르고, 각 단계마다 실제로 동작하는지 나에게 확인받은 뒤 다음 단계로 넘어가줘. 가상환경과 Docker는 쓰지 말고 시스템에 직접 설치해줘."
