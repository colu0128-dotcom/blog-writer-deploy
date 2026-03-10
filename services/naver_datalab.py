
import json
import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


def get_naver_headers() -> Dict[str, str]:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 이 없습니다. .env 파일을 확인하세요.")

    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }


def search_keyword_trend(
    main_keyword: str,
    sub_keywords: List[str] | None = None,
    start_date: str = "2025-01-01",
    end_date: str = "2025-03-31",
    time_unit: str = "month",
) -> Dict[str, Any]:
    main_keyword = (main_keyword or "").strip()
    sub_keywords = [x.strip() for x in (sub_keywords or []) if x.strip()]

    if not main_keyword:
        raise ValueError("메인키워드가 비어 있습니다.")

    keywords = [main_keyword] + sub_keywords[:4]

    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": [
            {
                "groupName": main_keyword,
                "keywords": keywords
            }
        ]
    }

    response = requests.post(
        NAVER_DATALAB_URL,
        headers=get_naver_headers(),
        data=json.dumps(payload),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def summarize_trend_result(result: Dict[str, Any]) -> str:
    results = result.get("results", [])
    if not results:
        return "검색 결과가 없습니다."

    data = results[0].get("data", [])
    if not data:
        return "추이 데이터가 없습니다."

    lines = []
    title = results[0].get("title", "키워드")
    lines.append(f"키워드 그룹: {title}")

    for row in data:
        period = row.get("period", "")
        ratio = row.get("ratio", "")
        lines.append(f"- {period}: {ratio}")

    if len(data) >= 2:
        first = data[0].get("ratio", 0)
        last = data[-1].get("ratio", 0)
        if last > first:
            lines.append(f"요약: 최근 관심도가 상승했습니다. ({first} → {last})")
        elif last < first:
            lines.append(f"요약: 최근 관심도가 하락했습니다. ({first} → {last})")
        else:
            lines.append(f"요약: 최근 관심도가 비슷한 수준입니다. ({first} → {last})")

    return "\n".join(lines)
