"""
법제처 MCP 서버 (FastMCP 기반)

Claude Desktop / Claude Code에 등록하면 법제처 OPEN API + 양형기준 검색이
표준 도구로 노출되어, LLM이 자율적으로 호출 가능.

등록 방법 (Claude Desktop):
  ~/.claude/claude_desktop_config.json 에 추가:
  {
    "mcpServers": {
      "law-go-kr": {
        "command": "python",
        "args": ["d:/.../submission_법제처/mcp_law/server.py"],
        "env": {"LAW_API_MODE": "real", "LAW_API_KEY": "..."}
      }
    }
  }
"""
from __future__ import annotations
import sys
from pathlib import Path

# 프로젝트 루트를 import path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_law.api_client import LawAPIClient

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("⚠ mcp 패키지 미설치. pip install mcp fastmcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("law-go-kr")
client = LawAPIClient()


@mcp.tool()
def search_law(query: str, display: int = 10) -> dict:
    """대한민국 법령 본문 검색 (법제처 OPEN API).

    Args:
        query: 검색어 (예: "형법", "사기죄")
        display: 결과 개수 (1~100, 기본 10)

    Returns:
        법령 검색 결과 딕셔너리 (법령명·법령ID·시행일·조문 인덱스)
    """
    return client.search_law(query, display)


@mcp.tool()
def search_precedent(query: str, display: int = 10) -> dict:
    """판례 검색 (법제처 OPEN API).

    Args:
        query: 사건 키워드 (예: "사기 5천만원 초범")
        display: 결과 개수

    Returns:
        익명화된 판례 본문·사건번호·선고일·법원·결과
    """
    return client.search_precedent(query, display)


@mcp.tool()
def search_ordinance(query: str, display: int = 10) -> dict:
    """자치법규 검색 (시·도·구·군 조례·규칙)."""
    return client.search_ordinance(query, display)


@mcp.tool()
def search_admin_rule(query: str, display: int = 10) -> dict:
    """행정규칙·고시 검색."""
    return client.search_admin_rule(query, display)


@mcp.tool()
def get_law_history(law_id: str) -> dict:
    """법령 개정 이력 조회.

    Args:
        law_id: 법제처 법령 ID

    Returns:
        해당 법령의 개정·시행 이력
    """
    return client.get_law_history(law_id)


@mcp.tool()
def search_sentencing_guideline(query: str, persona: str = "judge", top_k: int = 5) -> dict:
    """대법원 양형기준 2025판 검색 (909페이지 PDF 인덱스).

    검사·변호인·판사 시점에서 양형기준 조문을 다각도로 검색.

    Args:
        query: 사건 키워드
        persona: "prosecutor" (가중 요소) | "defender" (감경 요소) | "judge" (종합)
        top_k: 상위 매칭 조문 수

    Returns:
        매칭된 양형기준 조문 + 근거 페이지 + 가중·감경 분류

    Note:
        본 도구는 형량을 예측하지 않습니다. 양형기준 조문 매칭만 제공.
    """
    # core/retriever.py 위임 (인덱스 빌드 후 동작)
    try:
        from core.retriever import retrieve_sentencing
        return retrieve_sentencing(query, persona=persona, top_k=top_k)
    except FileNotFoundError:
        return {
            "error": "양형기준 인덱스 미빌드. scripts/build_index.py 먼저 실행 필요.",
            "_persona": persona,
        }


if __name__ == "__main__":
    mcp.run()
