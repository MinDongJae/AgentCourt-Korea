"""
법제처 OPEN API 클라이언트

공식 문서: https://open.law.go.kr/LSO/openApi/guideList.do

Mock 모드 지원: API 키 없이도 구조 검증 가능
"""
from __future__ import annotations
import os
import json
import httpx
from typing import Any
from pathlib import Path

LAW_API_BASE = os.getenv("LAW_API_BASE", "https://www.law.go.kr/DRF")
LAW_API_KEY = os.getenv("LAW_API_KEY", "")
MODE = os.getenv("LAW_API_MODE", "mock")

MOCK_FIXTURES_DIR = Path(__file__).parent.parent / "data" / "mock_fixtures"


class LawAPIClient:
    """법제처 국가법령정보 OPEN API 클라이언트.

    real 모드: 법제처 OPEN API 호출
    mock 모드: data/mock_fixtures/*.json 파일 반환 (API 키 없이 동작 검증)
    """

    def __init__(self, mode: str | None = None):
        self.mode = mode or MODE
        self.api_key = LAW_API_KEY
        self.base = LAW_API_BASE
        if self.mode == "real" and not self.api_key:
            raise RuntimeError("LAW_API_KEY 환경변수 미설정 — mock 모드로 전환하거나 .env 파일 확인")

    def _mock(self, fixture_name: str) -> dict[str, Any]:
        # 1) 정확 매칭 우선
        path = MOCK_FIXTURES_DIR / f"{fixture_name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        # 2) 타깃별 default fixture 폴백 (예: prec_default.json)
        target = fixture_name.split("_")[0]
        default_path = MOCK_FIXTURES_DIR / f"{target}_default.json"
        if default_path.exists():
            return json.loads(default_path.read_text(encoding="utf-8"))
        # 3) 빈 응답
        return {"_mock": True, "_fixture": fixture_name, "results": []}

    def _request(self, target: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "mock":
            return self._mock(f"{target}_{params.get('query', 'default')}")
        params = {**params, "OC": self.api_key, "type": "JSON"}
        url = f"{self.base}/lawSearch.do"
        with httpx.Client(timeout=10.0) as cli:
            r = cli.get(url, params={**params, "target": target})
            r.raise_for_status()
            return r.json()

    # ─── 공개 도구 ─────────────────────────────────

    def search_law(self, query: str, display: int = 10) -> dict[str, Any]:
        """법령 본문 검색.

        예: search_law("형법") → 형법 본문 + 조문 인덱스
        """
        return self._request("law", {"query": query, "display": display})

    def search_precedent(
        self,
        query: str,
        display: int = 10,
        search: int = 2,
        ref_law: str | None = None,
        court_type: str | None = None,
        date_range: str | None = None,
    ) -> dict[str, Any]:
        """판례 검색.

        Args:
            query: 검색어 (부분일치). 예: "사기"
            display: 결과 개수 (1~100, 기본 10)
            search: 검색 범위 — 1=판례명만, 2=본문검색 (기본). 공식 가이드 확인 결과.
            ref_law: 참조법령명 필터 (예: "형법", "민법") — JO 파라미터
            court_type: 법원종류 — "400201"(대법원) | "400202"(하급심)
            date_range: 선고일자 범위 (예: "20200101~20251231") — prncYd 파라미터

        Returns:
            법제처 판례 응답. 응답 구조:
            {"PrecSearch": {"totalCnt": N, "prec": [{"사건번호": ..., "법원명": ...}]}}
        """
        params: dict[str, Any] = {"query": query, "display": display, "search": search}
        if ref_law:
            params["JO"] = ref_law
        if court_type:
            params["org"] = court_type
        if date_range:
            params["prncYd"] = date_range
        return self._request("prec", params)

    def search_ordinance(self, query: str, display: int = 10) -> dict[str, Any]:
        """자치법규 검색."""
        return self._request("ordin", {"query": query, "display": display})

    def search_admin_rule(self, query: str, display: int = 10) -> dict[str, Any]:
        """행정규칙·고시 검색."""
        return self._request("admrul", {"query": query, "display": display})

    def get_law_history(self, law_id: str) -> dict[str, Any]:
        """법령 개정이력."""
        return self._request("lawHist", {"ID": law_id})


if __name__ == "__main__":
    # 동작 검증용 (mock 모드)
    cli = LawAPIClient(mode="mock")
    result = cli.search_precedent("사기 5천만원 초범")
    print(json.dumps(result, ensure_ascii=False, indent=2))
