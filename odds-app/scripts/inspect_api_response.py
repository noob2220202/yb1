"""API_FOOTBALL_KEY가 준비된 후, 실제 응답 구조를 확인하기 위한 1회성 스크립트.

사용법:
    python3 scripts/inspect_api_response.py

동작:
    1. 다음 3일 내 예정 경기 하나를 가져온다.
    2. 그 경기의 오즈 응답을 가져와 bookmaker별 bet 이름 목록을 출력한다.
    3. `app/services/market_type_mapping.py`의 BET_NAME_TO_MARKET_TYPE 키와
       실제 응답의 bet 이름을 비교해 누락된 매핑이 있으면 경고한다.

이 스크립트는 실제 API 키 없이는 실행할 수 없다 (SPEC.md 5.2절: "문서만 보고
추측하지 말고 실제 응답 샘플로 검증할 것"의 검증 도구).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.odds_api_client import ApiFootballError, OddsApiClient  # noqa: E402
from app.config import settings  # noqa: E402
from app.services.market_type_mapping import BET_NAME_TO_MARKET_TYPE  # noqa: E402


def main() -> None:
    if not settings.api_football_key:
        print("API_FOOTBALL_KEY가 .env에 설정되어 있지 않습니다. 먼저 키를 추가하세요.")
        sys.exit(1)

    client = OddsApiClient()
    try:
        fixtures = client.get_fixtures_between(date.today(), date.today() + timedelta(days=3))
    except ApiFootballError as exc:
        print(f"fixture 목록 조회 실패: {exc}")
        sys.exit(1)

    if not fixtures:
        print("예정된 경기가 없습니다(응답은 정상). 기간을 늘려 다시 시도하세요.")
        return

    sample_fixture = fixtures[0]
    fixture_id = sample_fixture["fixture"]["id"]
    print(f"샘플 fixture: {fixture_id} — {sample_fixture['teams']['home']['name']} vs {sample_fixture['teams']['away']['name']}")
    print(json.dumps(sample_fixture, indent=2, ensure_ascii=False)[:2000])

    try:
        odds = client.get_odds_for_fixture(str(fixture_id))
    except ApiFootballError as exc:
        print(f"오즈 조회 실패: {exc}")
        sys.exit(1)

    if not odds:
        print("이 fixture에는 아직 오즈가 없습니다. 다른 fixture로 재시도하세요.")
        return

    seen_bet_names: set[str] = set()
    for entry in odds:
        for bookmaker in entry.get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                seen_bet_names.add(bet.get("name", ""))

    print("\n실제 응답에서 발견된 bet 이름들:")
    for name in sorted(seen_bet_names):
        mapped = BET_NAME_TO_MARKET_TYPE.get(name)
        status = f"-> {mapped}" if mapped else "!! 매핑 없음 (market_type_mapping.py에 추가 필요)"
        print(f"  - {name} {status}")

    print("\n전체 오즈 응답 샘플 (첫 bookmaker):")
    if odds and odds[0].get("bookmakers"):
        print(json.dumps(odds[0]["bookmakers"][0], indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
