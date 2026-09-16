"""오즈 수집 파이프라인 end-to-end 테스트.

실제 API-Football 키 없이도 파이프라인 로직(파싱, upsert, insert-only 시계열,
market/line 그룹핑)을 검증하기 위해 FakeOddsApiClient로 실제 API-Football v3
문서 구조를 흉내낸 응답을 주입한다.

** 실제 API 키가 준비되면 scripts/inspect_api_response.py로 실제 응답을 캡처해
   이 mock 데이터와 market_type_mapping.py의 매핑표를 재검증할 것. **
"""
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.ingest import ingest_odds_for_fixture, run_ingest_cycle, upsert_fixture

FAKE_FIXTURE_RAW = {
    "fixture": {"id": 999001, "date": "2026-09-18T15:00:00+00:00", "status": {"short": "NS"}},
    "league": {"id": 39, "name": "Premier League", "country": "England"},
    "teams": {"home": {"name": "Test United"}, "away": {"name": "Test City"}},
    "goals": {"home": None, "away": None},
}

FAKE_ODDS_RESPONSE = [
    {
        "bookmakers": [
            {
                "name": "Bet365",
                "bets": [
                    {
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": "1.90"},
                            {"value": "Draw", "odd": "3.40"},
                            {"value": "Away", "odd": "4.20"},
                        ],
                    },
                    {
                        "name": "Asian Handicap",
                        "values": [
                            {"value": "Home -0.5", "odd": "1.95"},
                            {"value": "Away +0.5", "odd": "1.85"},
                        ],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "2.00"},
                            {"value": "Under 2.5", "odd": "1.80"},
                        ],
                    },
                    {
                        "name": "Draw No Bet",
                        "values": [
                            {"value": "Home", "odd": "1.55"},
                            {"value": "Away", "odd": "2.45"},
                        ],
                    },
                    {
                        "name": "Both Teams Score",
                        "values": [
                            {"value": "Yes", "odd": "1.80"},
                            {"value": "No", "odd": "2.00"},
                        ],
                    },
                    {
                        "name": "Winning Margin",
                        "values": [
                            {"value": "Home by 1", "odd": "3.5"},
                            {"value": "Home by 2", "odd": "6.0"},
                            {"value": "Draw", "odd": "3.4"},
                            {"value": "Away by 1", "odd": "7.0"},
                        ],
                    },
                    {
                        "name": "Exact Score",
                        "values": [
                            {"value": "1-0", "odd": "7.5"},
                            {"value": "2-1", "odd": "9.0"},
                            {"value": "0-0", "odd": "9.5"},
                        ],
                    },
                ],
            }
        ]
    }
]


class FakeOddsApiClient:
    def get_fixtures_between(self, date_from, date_to):
        return [FAKE_FIXTURE_RAW]

    def get_odds_for_fixture(self, fixture_external_id):
        return FAKE_ODDS_RESPONSE


def test_upsert_fixture_creates_and_updates(db_session):
    fixture = upsert_fixture(db_session, FAKE_FIXTURE_RAW)
    db_session.commit()
    assert fixture.external_id == "999001"
    assert fixture.home_team == "Test United"
    assert fixture.league_name == "Premier League"

    # 같은 external_id로 다시 upsert하면 새 row가 생기지 않고 갱신되어야 함
    updated_raw = dict(FAKE_FIXTURE_RAW)
    updated_raw["teams"] = {"home": {"name": "Renamed United"}, "away": {"name": "Test City"}}
    upsert_fixture(db_session, updated_raw)
    db_session.commit()

    count = db_session.query(Fixture).filter(Fixture.external_id == "999001").count()
    assert count == 1
    refreshed = db_session.query(Fixture).filter(Fixture.external_id == "999001").one()
    assert refreshed.home_team == "Renamed United"


def test_ingest_odds_creates_markets_and_odds_grouped_by_line(db_session):
    fixture = upsert_fixture(db_session, FAKE_FIXTURE_RAW)
    db_session.commit()

    client = FakeOddsApiClient()
    inserted = ingest_odds_for_fixture(db_session, client, fixture)

    # Match Winner(3) + AH 1라인(2) + O/U 1라인(2) + DNB(2) + BTTS(2) + Winning Margin(4) + Exact Score(3)
    assert inserted == 3 + 2 + 2 + 2 + 2 + 4 + 3

    markets = db_session.query(Market).filter(Market.fixture_id == fixture.id).all()
    market_types = {m.market_type for m in markets}
    assert market_types == {"1x2", "ah", "ou", "dnb", "btts", "win_margin", "correct_score"}

    ah_market = next(m for m in markets if m.market_type == "ah")
    assert float(ah_market.line) == -0.5  # 홈 기준으로 정규화된 라인
    ah_odds = db_session.query(Odds).filter(Odds.market_id == ah_market.id).all()
    ah_selections = {o.selection for o in ah_odds}
    assert ah_selections == {"home", "away"}  # 같은 라인의 양면이 한 market row로 묶임


def test_ingest_odds_is_insert_only_time_series(db_session):
    """오즈는 매번 새 row로 insert되어야 한다(update 아님) — 시계열 이력 보존."""
    fixture = upsert_fixture(db_session, FAKE_FIXTURE_RAW)
    db_session.commit()

    client = FakeOddsApiClient()
    ingest_odds_for_fixture(db_session, client, fixture)
    first_count = db_session.query(Market).filter(Market.fixture_id == fixture.id).count()

    ingest_odds_for_fixture(db_session, client, fixture)
    second_count = db_session.query(Market).filter(Market.fixture_id == fixture.id).count()

    assert second_count == first_count * 2  # 두 번째 수집도 새 row로 추가됨


def test_run_ingest_cycle_end_to_end(db_session):
    client = FakeOddsApiClient()
    summary = run_ingest_cycle(db_session, client=client, urgent_only=False)

    assert summary["fixtures_upserted"] == 1
    assert summary["fixtures_processed"] == 1
    assert summary["odds_inserted"] > 0

    fixture = db_session.query(Fixture).filter(Fixture.external_id == "999001").one()
    assert fixture.home_team == "Test United"
