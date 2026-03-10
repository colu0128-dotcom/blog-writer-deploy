\
def build_title_prompt(keyword: str, sub_keywords: str, platform: str, tone: str, purpose: str) -> str:
    return f"""
너는 검색형 블로그 제목 기획자다.

[입력]
- 메인 키워드: {keyword}
- 서브 키워드: {sub_keywords}
- 플랫폼: {platform}
- 톤: {tone}
- 목적: {purpose}

[규칙]
1. 제목 후보 7개를 작성하라.
2. 제목은 실제 블로그에 바로 쓸 수 있게 자연스럽게 작성하라.
3. 낚시성, 과장형, 너무 광고 같은 표현은 피하라.
4. 번호 목록으로만 출력하라.
5. 메인 키워드는 자연스럽게 포함하라.
"""


def build_outline_prompt(
    keyword: str,
    sub_keywords: str,
    platform: str,
    tone: str,
    purpose: str,
    selected_title: str,
    extra_instruction: str = "",
) -> str:
    return f"""
너는 SEO형 블로그 기획자다.

[입력]
- 메인 키워드: {keyword}
- 서브 키워드: {sub_keywords}
- 플랫폼: {platform}
- 톤: {tone}
- 목적: {purpose}
- 선택 제목: {selected_title}
- 추가 요청: {extra_instruction}

[출력 규칙]
1. 독자 검색 의도 3개
2. 추천 목차 5~7개
3. 글에서 꼭 다뤄야 할 핵심 포인트 5개
4. 글의 흐름을 짧게 설명
5. 광고처럼 보이지 않게 작성
6. 보기 좋게 구분해서 출력
"""


def build_article_prompt(
    keyword: str,
    sub_keywords: str,
    platform: str,
    tone: str,
    purpose: str,
    length: int,
    selected_title: str,
    outline_text: str,
    extra_instruction: str = "",
) -> str:
    return f"""
너는 블로그 최적화 전문 작가다.

아래 조건에 맞춰 최종 블로그 글을 작성하라.

[입력]
- 메인 키워드: {keyword}
- 서브 키워드: {sub_keywords}
- 플랫폼: {platform}
- 톤: {tone}
- 목적: {purpose}
- 분량: {length}자 내외
- 제목: {selected_title}
- 추가 요청: {extra_instruction}

[기획안]
{outline_text}

[중요 규칙]
1. 제목은 본문 맨 위에 한 번만 적어라.
2. 글은 서론-본론-결론 흐름으로 자연스럽게 작성하라.
3. 문장은 실제 사람이 쓴 것처럼 부드럽고 자연스럽게 작성하라.
4. 메인 키워드와 서브 키워드는 과하지 않게 녹여라.
5. 불필요한 반복 문장, 뻔한 AI 표현, 과장형 문장을 피하라.
6. 본문 중간에 이미지 위치는 아래 형식으로만 표시하라.
   [이미지 추천: 장면 설명]
7. 해시태그는 본문에 넣지 마라.
8. 마크다운 기호(##, **, ---)를 쓰지 마라.
9. '보완반영', '보통보정', '추천버전', '플랫폼 버전' 같은 내부 작업 표현은 절대 넣지 마라.
10. 제목 아래부터는 바로 자연스러운 본문으로 시작하라.
"""


def build_rewrite_prompt(
    article_text: str,
    tone: str,
    purpose: str,
    extra_instruction: str = "",
) -> str:
    return f"""
너는 블로그 글을 더 자연스럽게 다듬는 전문 편집자다.

[입력 글]
{article_text}

[조건]
- 톤: {tone}
- 목적: {purpose}
- 추가 요청: {extra_instruction}

[규칙]
1. 전체 의미는 유지하되 문장을 새롭게 다시 써라.
2. 더 자연스럽고 덜 AI스럽게 다듬어라.
3. 반복되는 표현을 줄여라.
4. 해시태그는 넣지 마라.
5. 마크다운 기호를 쓰지 마라.
6. 제목은 맨 위에 한 번만 유지하라.
7. 이미지 추천 줄은 유지하라.
"""


def build_hashtag_prompt(keyword: str, sub_keywords: str, article_text: str, count: int = 10) -> str:
    return f"""
너는 블로그용 해시태그 작성 도우미다.

[입력]
- 메인 키워드: {keyword}
- 서브 키워드: {sub_keywords}
- 본문:
{article_text}

[규칙]
1. 해시태그를 {count}개 작성하라.
2. 중복 없이 작성하라.
3. 실제 블로그 글 하단에 붙이기 좋은 형태로 작성하라.
4. 한 줄에 하나씩 출력하라.
5. 해시태그만 출력하라.
"""
