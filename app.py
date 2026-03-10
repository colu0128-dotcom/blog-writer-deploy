import json
import os
import re
import textwrap as tw
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from services.prompts import (
    build_title_prompt,
    build_outline_prompt,
    build_article_prompt,
    build_rewrite_prompt,
    build_hashtag_prompt,
)
from services.openai_client import generate_text, MODEL
from services.postprocess import normalize_text, split_title_and_body

load_dotenv()

st.set_page_config(page_title="블로그 반자동 글쓰기", page_icon="✨", layout="wide", initial_sidebar_state="collapsed")

SNIPPET_FILE = Path("saved_common_snippets.json")
NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"

def safe_filename(text: str) -> str:
    text = (text or "blog_post").strip()
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80] or "blog_post"

def parse_title_candidates(text: str):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    items = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
        cleaned = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", cleaned)
        cleaned = re.sub(r"^[-•]\s*", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items

def wrap_preview_text(text: str, width: int = 38) -> str:
    text = normalize_text(text or "")
    if not text:
        return ""
    blocks = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if para.startswith("[이미지"):
            blocks.append(para)
            continue
        blocks.append(tw.fill(para, width=width, break_long_words=False, break_on_hyphens=False))
    return "\n\n".join(blocks).strip()

def format_text_for_preview(title: str, body: str, common_text: str = "", hashtags_text: str = "", image_prompts: str = "") -> str:
    blocks = []
    if title:
        blocks.append(title.strip())
    for para in [p.strip() for p in (body or "").split("\n\n") if p.strip()]:
        blocks.append(wrap_preview_text(para))
    if image_prompts.strip():
        blocks.append(image_prompts.strip())
    if common_text.strip():
        blocks.append(wrap_preview_text(common_text.strip()))
    if hashtags_text.strip():
        blocks.append(hashtags_text.strip())
    return "\n\n".join([b for b in blocks if b.strip()]).strip()

def load_snippets_db():
    if not SNIPPET_FILE.exists():
        return {}
    try:
        return json.loads(SNIPPET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_snippets_db(data: dict):
    SNIPPET_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def set_and_refresh(**kwargs):
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.rerun()

def get_naver_headers():
    cid = os.getenv("NAVER_CLIENT_ID", "").strip()
    secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 이 없습니다.")
    return {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret, "Content-Type": "application/json"}

def search_keyword_trend(main_keyword: str, sub_keywords=None, start_date="2025-01-01", end_date="2025-03-31", time_unit="month"):
    main_keyword = (main_keyword or "").strip()
    sub_keywords = [x.strip() for x in (sub_keywords or []) if x.strip()]
    if not main_keyword:
        raise ValueError("검색 키워드를 입력하세요.")
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": [{"groupName": main_keyword, "keywords": [main_keyword] + sub_keywords[:4]}],
    }
    res = requests.post(NAVER_DATALAB_URL, headers=get_naver_headers(), data=json.dumps(payload), timeout=20)
    res.raise_for_status()
    return res.json()

def summarize_trend_result(result: dict) -> str:
    results = result.get("results", [])
    if not results:
        return "관심도 확인 불가"
    data = results[0].get("data", [])
    if not data:
        return "관심도 확인 불가"
    if len(data) >= 2:
        first, last = data[0].get("ratio", 0), data[-1].get("ratio", 0)
        if last > first + 10:
            return f"상승 ({first} → {last})"
        elif last < first - 10:
            return f"하락 ({first} → {last})"
        else:
            return f"보통 ({first} → {last})"
    return f"보통 ({data[-1].get('ratio', 0)})"


def generate_keyword_suggestions(main_keyword: str, category: str, current_sub_keywords: str = ""):
    main_keyword = (main_keyword or "").strip()
    if not main_keyword:
        raise ValueError("메인키워드를 먼저 입력하세요.")
    prompt = f"""
너는 블로그 글쓰기용 키워드 추천 도우미다.

아래 조건에 맞게 메인키워드와 함께 쓰기 좋은 추천 키워드 10개를 제안하라.

[주제/업종]
{category}

[메인키워드]
{main_keyword}

[현재 서브키워드]
{current_sub_keywords}

[규칙]
1. 추천 키워드는 한국어로 10개만 출력한다.
2. 한 줄에 하나씩 출력한다.
3. 너무 비슷한 표현만 반복하지 말고, 검색형/정보형/후기형/확장형이 섞이게 한다.
4. 메인키워드와 실제 글 제목/본문에 바로 넣기 좋은 표현으로 만든다.
5. 번호, 설명, 따옴표 없이 키워드만 출력한다.
"""
    raw = normalize_text(generate_text(prompt))
    lines = [re.sub(r"^\d+[\.)]\s*", "", x).strip() for x in raw.splitlines() if x.strip()]
    cleaned = []
    for x in lines:
        if x and x not in cleaned:
            cleaned.append(x)
    return cleaned[:10]

def get_platform_rules(platform: str) -> str:
    if platform == "네이버블로그":
        return "네이버 블로그용 글쓰기 규칙:\n1. 제목과 본문 초반에서 검색 의도를 자연스럽게 바로 풀어준다.\n2. 메인 키워드와 연관 표현을 자연스럽게 섞는다.\n3. 실제 경험담, 상황 예시, 현실적인 설명을 넣는다.\n4. 소주제는 자연스럽고 읽기 편하게 구성한다."
    return "티스토리용 글쓰기 규칙:\n1. 검색 의도에 바로 답하는 정보형 구조를 우선한다.\n2. 소주제별 핵심이 분명해야 한다.\n3. 정의, 이유, 방법, 비교, 정리 구조를 명확히 한다.\n4. 문장은 군더더기 없이 명료하게 작성한다."

def get_image_count_by_length(length: int) -> int:
    if length <= 1800:
        return 4
    if length <= 2600:
        return 5
    if length <= 3500:
        return 6
    if length <= 4500:
        return 7
    return 8

def build_structured_brief(platform_value=None):
    platform_value = platform_value or st.session_state.get("platform", "")
    parts = [
        f"주제/업종: {st.session_state.get('category', '')}",
        f"메인키워드: {st.session_state.get('keyword', '')}",
        f"서브키워드: {st.session_state.get('sub_keywords', '')}",
        f"플랫폼: {platform_value}",
        f"버전: {st.session_state.get('version_type', '')}",
        f"목표 글자수: {st.session_state.get('length', '')}자",
        f"소주제 개수: {st.session_state.get('subtitle_count', '')}개",
        f"말투: {st.session_state.get('tone_style', '')}",
    ]
    if st.session_state.get("direction_text", "").strip():
        parts.append(f"강조할 내용: {st.session_state.get('direction_text', '')}")
    if st.session_state.get("exclude_text", "").strip():
        parts.append(f"제외할 내용: {st.session_state.get('exclude_text', '')}")
    return "\n".join(parts)

def build_effective_sub_keywords(platform_value=None):
    platform_value = platform_value or st.session_state.get("platform", "")
    parts = []
    if st.session_state.get("sub_keywords", "").strip():
        parts.append(st.session_state["sub_keywords"].strip())
    if st.session_state.get("direction_text", "").strip():
        parts.append("강조: " + st.session_state["direction_text"].strip())
    if st.session_state.get("exclude_text", "").strip():
        parts.append("제외: " + st.session_state["exclude_text"].strip())
    parts.append("업종: " + st.session_state.get("category", ""))
    parts.append("플랫폼: " + platform_value)
    return " / ".join([x for x in parts if x])

def build_effective_extra_instruction(platform_value=None):
    platform_value = platform_value or st.session_state.get("platform", "")
    tone_map = {
        "전문해설형(아나운서)": "문장은 또렷하고 안정적인 전달력으로, 아나운서처럼 정돈된 말투로 작성한다.",
        "3040대 밝은 여성형": "문장은 밝고 호감 있게, 3040대 여성 화자처럼 자연스럽고 친근하게 작성한다.",
        "3040대 밝은 남성형": "문장은 밝고 편안하게, 3040대 남성 화자처럼 현실감 있게 작성한다.",
        "20대형": "문장은 20대 화자처럼 가볍고 친근하게 작성하되, ㅎㅎ, ㅋㅋ, ~했어용 같은 표현을 자연스럽게 섞는다.",
        "친구형": "문장은 친구에게 이야기하듯 편안하고 부담 없이 작성한다.",
        "정중상담형": "문장은 상담하듯 친절하고 공손한 존댓말 위주로 작성한다.",
    }
    version_rule = "PC 버전이므로 문단 흐름은 비교적 길게 유지한다." if st.session_state.get("version_type") == "PC 버전" else "모바일 버전이므로 문단을 짧게 끊는다."
    instructions = [
        build_structured_brief(platform_value),
        get_platform_rules(platform_value),
        version_rule,
        f"소주제는 정확히 {st.session_state.get('subtitle_count', 3)}개로 작성한다.",
        tone_map.get(st.session_state.get("tone_style", ""), ""),
        "제목 아래부터 바로 본문이 시작되게 작성한다.",
        "AI 티가 나는 어색한 연결어, 뻔한 서론, 반복 문장을 줄인다.",
        "한 문단이 너무 길어지지 않게 조절한다.",
    ]
    extra = st.session_state.get("extra_instruction", "").strip()
    if extra:
        instructions.append("추가 요청:\n" + extra)
    return "\n\n".join([x for x in instructions if x.strip()])

def generate_image_prompts_from_body(article_title: str, article_body: str):
    image_count = get_image_count_by_length(int(st.session_state.get("length", 2500)))
    prompt = f"""
너는 블로그 글에 넣을 이미지 기획자다.
아래 글을 읽고, 본문 중간중간에 넣기 좋은 이미지 프롬프트를 {image_count}개 작성하라.

[입력 정보]
주제/업종: {st.session_state.get("category", "")}
메인키워드: {st.session_state.get("keyword", "")}
제목: {article_title}

[본문]
{article_body}

[규칙]
1. 각 줄은 아래 형식으로만 출력하라.
[이미지 1] 위치: 도입부 / 프롬프트: ...
2. 프롬프트는 한국어로 작성하라.
3. 글 흐름상 어디에 넣는지 위치도 함께 적어라.
"""
    return normalize_text(generate_text(prompt))

def build_article_with_images(article_title: str, article_body: str, image_prompts_text: str, common_text: str, hashtags_text: str):
    paragraphs = [p.strip() for p in (article_body or "").split("\n\n") if p.strip()]
    image_lines = [line.strip() for line in (image_prompts_text or "").splitlines() if line.strip()]
    blocks = [article_title.strip()] if article_title.strip() else []
    if not paragraphs:
        return "\n\n".join([b for b in [article_title, common_text, hashtags_text] if (b or "").strip()])
    image_positions = []
    if image_lines:
        step = max(1, len(paragraphs) // (len(image_lines) + 1))
        idx = step
        for _ in image_lines:
            image_positions.append(min(idx, len(paragraphs)))
            idx += step
    img_map = {}
    for pos, img in zip(image_positions, image_lines):
        img_map.setdefault(pos, []).append(img)
    for i, para in enumerate(paragraphs, start=1):
        blocks.append(para)
        if i in img_map:
            blocks.extend(img_map[i])
    if common_text.strip():
        blocks.append(common_text.strip())
    if hashtags_text.strip():
        blocks.append(hashtags_text.strip())
    return "\n\n".join([b for b in blocks if b.strip()])

st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #fcfcff 0%, #f6f7fb 100%); }
.block-container { max-width: 1260px; padding-top: 1.2rem; padding-bottom: 2rem; }
.hero-box { background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%); color: white; padding: 24px 26px; border-radius: 24px; margin-bottom: 18px; box-shadow: 0 14px 40px rgba(124, 58, 237, 0.16);}
.hero-title { font-size: 32px; font-weight: 800; margin-bottom: 6px; }
.hero-sub { font-size: 15px; opacity: 0.95; }
.soft-card { background: rgba(255,255,255,0.92); border: 1px solid #ebeef5; border-radius: 22px; padding: 18px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04); margin-bottom: 14px; }
.section-title { font-size: 20px; font-weight: 800; margin-bottom: 4px; }
.section-sub { color: #6b7280; font-size: 14px; margin-bottom: 14px; }
.step-guide { color: #6b7280; font-size: 13px; margin: -4px 0 10px 2px; }
.info-box { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; border-radius: 16px; padding: 12px 14px; font-size: 13px; margin-bottom: 12px; }
.footer-note { text-align: center; color: #6b7280; font-size: 13px; margin-top: 8px; }
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stSelectbox"] > div, div[data-testid="stNumberInput"] input { border-radius: 14px !important; }
button[kind="primary"] { border-radius: 14px !important; border: none !important; background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%) !important; }
button[kind="secondary"] { border-radius: 14px !important; }
</style>
""", unsafe_allow_html=True)

DEFAULTS = {
    "page_step": "1. 입력", "category": "부동산/건축", "keyword": "", "sub_keywords": "",
    "direction_text": "", "exclude_text": "", "platform": "네이버블로그", "version_type": "PC 버전",
    "tone_style": "전문해설형(아나운서)", "purpose": "정보전달형", "length": 2500, "subtitle_count": 3,
    "hashtag_count": 10, "extra_instruction": "과장하지 말고 자연스럽게 써줘. 본문에 해시태그 넣지 말고 글만 깔끔하게 써줘.",
    "title_candidates": "", "title_choice_idx": 1, "selected_title": "", "outline_text": "",
    "article_raw": "", "article_title": "", "article_body": "", "common_snippet_name": "",
    "common_snippet_text": "", "applied_common_text": "", "naver_article_title": "",
    "naver_article_body": "", "tistory_article_title": "", "tistory_article_body": "",
    "naver_hashtags_text": "", "tistory_hashtags_text": "", "naver_image_prompts_text": "",
    "tistory_image_prompts_text": "", "keyword_trend_result_text": "", "recommended_keywords": "",
    "search_keyword_input": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

steps = ["1. 입력", "2. 제목/기획안", "3. 본문"]
category_options = ["부동산/건축","법률/세무","의료/건강","뷰티/패션","IT/기술","음식점/맛집","교육/학원","금융/투자","여행/레저","인테리어/리빙","육아/자녀교육","반려동물","자동차","쇼핑몰/제품리뷰","기타"]
tone_options = ["전문해설형(아나운서)", "3040대 밝은 여성형", "3040대 밝은 남성형", "20대형", "친구형", "정중상담형"]

st.markdown(f"""
<div class="hero-box">
    <div class="hero-title">블로그 반자동 글쓰기</div>
    <div class="hero-sub">추천 버전 · {datetime.now().strftime("%Y-%m-%d")}</div>
</div>
""", unsafe_allow_html=True)

step_cols = st.columns(3, gap="small")
for i, step_name in enumerate(steps):
    is_current = st.session_state["page_step"] == step_name
    label = f"● {step_name}" if is_current else step_name
    if step_cols[i].button(label, use_container_width=True, type="primary" if is_current else "secondary"):
        set_and_refresh(page_step=step_name)
st.markdown('<div class="step-guide">위 단계 버튼을 눌러 화면을 이동하세요.</div>', unsafe_allow_html=True)

if st.session_state["page_step"] == "1. 입력":
    left, right = st.columns([1.12, 0.88], gap="large")
    with left:
        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        category = st.selectbox("📌 필수 주제/업종", category_options, index=category_options.index(st.session_state["category"]))
        keyword = st.text_input("📌 필수 메인키워드", value=st.session_state["keyword"])
        sub_keywords = st.text_input("서브키워드", value=st.session_state["sub_keywords"])
        direction_text = st.text_area("강조할 내용", value=st.session_state["direction_text"], height=90)
        exclude_text = st.text_area("제외할 내용", value=st.session_state["exclude_text"], height=80)
        a1, a2 = st.columns(2)
        with a1:
            version_type = st.radio("버전 선택", ["PC 버전", "모바일 버전"], index=["PC 버전", "모바일 버전"].index(st.session_state["version_type"]), horizontal=True)
            length = st.selectbox("목표 글자수", [1500, 2000, 2500, 3000, 3500, 4000, 5000], index=[1500, 2000, 2500, 3000, 3500, 4000, 5000].index(st.session_state["length"]))
        with a2:
            purpose = st.selectbox("목적", ["정보전달형", "체험형", "상품후기형", "상담전환용"], index=["정보전달형", "체험형", "상품후기형", "상담전환용"].index(st.session_state["purpose"]))
            subtitle_count = st.selectbox("소주제 개수", [3, 4, 5, 6, 7, 8], index=[3, 4, 5, 6, 7, 8].index(st.session_state["subtitle_count"]))
            hashtag_count = st.selectbox("해시태그 개수", [5, 8, 10, 12], index=[5, 8, 10, 12].index(st.session_state["hashtag_count"]))
        tone_style = st.selectbox("말투", tone_options, index=tone_options.index(st.session_state["tone_style"]))
        extra_instruction = st.text_area("추가 요청", value=st.session_state["extra_instruction"], height=110)
        if st.button("입력정보 적용", use_container_width=True, type="primary"):
            set_and_refresh(
                category=category,
                keyword=keyword,
                sub_keywords=sub_keywords,
                direction_text=direction_text,
                exclude_text=exclude_text,
                version_type=version_type,
                length=length,
                purpose=purpose,
                subtitle_count=subtitle_count,
                hashtag_count=hashtag_count,
                tone_style=tone_style,
                extra_instruction=extra_instruction,
            )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        saved_snippets = load_snippets_db()
        saved_names = ["선택 안 함"] + list(saved_snippets.keys())
        st.session_state["common_snippet_name"] = st.text_input("저장 이름", value=st.session_state["common_snippet_name"])
        st.session_state["common_snippet_text"] = st.text_area("문구/링크 내용", value=st.session_state["common_snippet_text"], height=120)
        selected_saved_name = st.selectbox("저장된 문구 선택", saved_names, index=0)
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("저장", use_container_width=True):
                name = st.session_state["common_snippet_name"].strip()
                content = st.session_state["common_snippet_text"].strip()
                if not name or not content:
                    st.warning("저장 이름과 내용을 모두 입력하세요.")
                else:
                    saved_snippets[name] = content
                    save_snippets_db(saved_snippets)
                    set_and_refresh()
        with b2:
            if st.button("불러오기", use_container_width=True):
                if selected_saved_name != "선택 안 함":
                    set_and_refresh(common_snippet_name=selected_saved_name, common_snippet_text=saved_snippets.get(selected_saved_name, ""))
        with b3:
            if st.button("현재글 적용하기", use_container_width=True):
                set_and_refresh(applied_common_text=st.session_state["common_snippet_text"].strip())
        if st.session_state["applied_common_text"].strip():
            st.text_area("현재 적용된 문구/링크", value=st.session_state["applied_common_text"], height=90, disabled=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">키워드 추천</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">메인키워드 관심도와 글에 바로 넣기 좋은 추천 키워드를 확인합니다.</div>', unsafe_allow_html=True)

        interest_cols = st.columns([1, 1])
        with interest_cols[0]:
            if st.button("메인키워드 관심도 확인", use_container_width=True):
                try:
                    sub_kw_list = [x.strip() for x in st.session_state["sub_keywords"].split(",") if x.strip()]
                    result = search_keyword_trend(st.session_state["keyword"], sub_kw_list)
                    set_and_refresh(keyword_interest_label=summarize_trend_result(result))
                except Exception as e:
                    st.error(f"관심도 확인 오류: {e}")
        with interest_cols[1]:
            st.text_input("메인키워드 관심도", value=st.session_state.get("keyword_interest_label", ""), disabled=True)

        st.markdown('<div class="section-sub">추천 키워드 10개</div>', unsafe_allow_html=True)
        if st.button("🔁 추천 키워드받기", use_container_width=True):
            try:
                suggestions = generate_keyword_suggestions(
                    st.session_state["keyword"],
                    st.session_state["category"],
                    st.session_state["sub_keywords"],
                )
                set_and_refresh(recommended_keywords=suggestions)
            except Exception as e:
                st.error(f"추천키워드 생성 오류: {e}")

        recommended_text = ", ".join(st.session_state.get("recommended_keywords", []))
        st.text_area("추천 키워드", value=recommended_text, height=180, disabled=True)

        search_keyword_input = st.text_input("추가 키워드 검색", value=st.session_state["search_keyword_input"])
        k1, k2 = st.columns(2)
        with k1:
            if st.button("키워드 적용하기", use_container_width=True):
                current = [x.strip() for x in st.session_state["sub_keywords"].split(",") if x.strip()]
                recommended = st.session_state.get("recommended_keywords", [])
                merged = current[:]
                for kw in recommended:
                    if kw not in merged:
                        merged.append(kw)
                set_and_refresh(sub_keywords=", ".join(merged))
        with k2:
            if st.button("입력정보에 반영", use_container_width=True):
                set_and_refresh(search_keyword_input=search_keyword_input)
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state["page_step"] == "2. 제목/기획안":
    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        if st.button("추천 제목 생성", use_container_width=True):
            try:
                prompt = build_title_prompt(
                    keyword=st.session_state["keyword"] or st.session_state["category"],
                    sub_keywords=build_effective_sub_keywords(),
                    platform=st.session_state["platform"],
                    tone=st.session_state["tone_style"],
                    purpose=st.session_state["purpose"],
                    extra_instruction=build_effective_extra_instruction(),
                )
                generated = normalize_text(generate_text(prompt))
                parsed = parse_title_candidates(generated)
                selected = parsed[0] if parsed else ""
                set_and_refresh(title_candidates=generated, title_choice_idx=1, selected_title=selected)
            except Exception as e:
                st.error(f"제목 후보 생성 오류: {e}")
        parsed_titles = parse_title_candidates(st.session_state["title_candidates"])
        options = [f"{idx}. {title}" for idx, title in enumerate(parsed_titles, start=1)]
        st.text_area("제목 후보", value="\n".join(options) if options else st.session_state["title_candidates"], height=230, disabled=True)
        if options:
            selected_option = st.selectbox("제목 번호 선택", options, index=max(0, min(len(options), st.session_state["title_choice_idx"]) - 1))
            selected_idx = options.index(selected_option) + 1
            st.session_state["title_choice_idx"] = selected_idx
            st.session_state["selected_title"] = parsed_titles[selected_idx - 1]
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        st.text_input("선택 제목", value=st.session_state["selected_title"], disabled=True)
        if st.button("기획안 생성", use_container_width=True):
            try:
                title_for_outline = st.session_state["selected_title"].strip() or (st.session_state["keyword"].strip() or st.session_state["category"])
                prompt = build_outline_prompt(
                    keyword=st.session_state["keyword"] or st.session_state["category"],
                    sub_keywords=build_effective_sub_keywords(),
                    platform=st.session_state["platform"],
                    tone=st.session_state["tone_style"],
                    purpose=st.session_state["purpose"],
                    selected_title=title_for_outline,
                    extra_instruction=build_effective_extra_instruction(),
                )
                set_and_refresh(outline_text=normalize_text(generate_text(prompt)))
            except Exception as e:
                st.error(f"기획안 생성 오류: {e}")
        st.text_area("기획안 결과", value=st.session_state["outline_text"], height=330, disabled=True)
        if st.button("본문 작성하러 가기", use_container_width=True):
            set_and_refresh(page_step="3. 본문")
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state["page_step"] == "3. 본문":
    st.markdown('<div class="soft-card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("글생성", use_container_width=True):
            try:
                title_for_article = st.session_state["selected_title"].strip() or (st.session_state["keyword"].strip() or st.session_state["category"])
                naver_prompt = build_article_prompt(
                    st.session_state["keyword"] or st.session_state["category"],
                    build_effective_sub_keywords("네이버블로그"),
                    "네이버블로그",
                    st.session_state["tone_style"],
                    st.session_state["purpose"],
                    st.session_state["length"],
                    title_for_article,
                    st.session_state["outline_text"],
                    build_effective_extra_instruction("네이버블로그"),
                )
                naver_article = normalize_text(generate_text(naver_prompt))
                naver_title, naver_body = split_title_and_body(naver_article)

                tistory_prompt = build_article_prompt(
                    st.session_state["keyword"] or st.session_state["category"],
                    build_effective_sub_keywords("티스토리"),
                    "티스토리",
                    st.session_state["tone_style"],
                    st.session_state["purpose"],
                    st.session_state["length"],
                    title_for_article,
                    st.session_state["outline_text"],
                    build_effective_extra_instruction("티스토리"),
                )
                tistory_article = normalize_text(generate_text(tistory_prompt))
                tistory_title, tistory_body = split_title_and_body(tistory_article)

                set_and_refresh(
                    naver_article_title=naver_title,
                    naver_article_body=naver_body,
                    tistory_article_title=tistory_title,
                    tistory_article_body=tistory_body,
                    article_raw=naver_article,
                    article_title=naver_title,
                    article_body=naver_body,
                )
            except Exception as e:
                st.error(f"비교 글 생성 오류: {e}")
    with c2:
        if st.button("네이버 다시쓰기", use_container_width=True):
            try:
                source = (st.session_state["naver_article_title"] + "\n\n" + st.session_state["naver_article_body"]).strip()
                if not source:
                    st.warning("먼저 글생성을 하세요.")
                else:
                    prompt = build_rewrite_prompt(source, st.session_state["tone_style"], st.session_state["purpose"], build_effective_extra_instruction("네이버블로그"))
                    article = normalize_text(generate_text(prompt))
                    title, body = split_title_and_body(article)
                    set_and_refresh(naver_article_title=title, naver_article_body=body, article_raw=article, article_title=title, article_body=body)
            except Exception as e:
                st.error(f"네이버 다시쓰기 오류: {e}")
    with c3:
        if st.button("티스토리 다시쓰기", use_container_width=True):
            try:
                source = (st.session_state["tistory_article_title"] + "\n\n" + st.session_state["tistory_article_body"]).strip()
                if not source:
                    st.warning("먼저 글생성을 하세요.")
                else:
                    prompt = build_rewrite_prompt(source, st.session_state["tone_style"], st.session_state["purpose"], build_effective_extra_instruction("티스토리"))
                    article = normalize_text(generate_text(prompt))
                    title, body = split_title_and_body(article)
                    set_and_refresh(tistory_article_title=title, tistory_article_body=body)
            except Exception as e:
                st.error(f"티스토리 다시쓰기 오류: {e}")

    left, right = st.columns(2, gap="large")
    with left:
        naver_preview = format_text_for_preview(
            st.session_state["naver_article_title"],
            st.session_state["naver_article_body"],
            st.session_state["applied_common_text"],
            st.session_state["naver_hashtags_text"],
            st.session_state["naver_image_prompts_text"],
        )
        st.text_area("네이버 블로그 글", value=naver_preview, height=620)
        n1, n2 = st.columns(2)
        with n1:
            if st.button("네이버 해시태그 생성", use_container_width=True):
                try:
                    source = (st.session_state["naver_article_title"] + "\n\n" + st.session_state["naver_article_body"]).strip()
                    if source:
                        prompt = build_hashtag_prompt(
                            st.session_state["keyword"] or st.session_state["category"],
                            build_effective_sub_keywords("네이버블로그"),
                            source,
                            st.session_state["hashtag_count"],
                        )
                        set_and_refresh(naver_hashtags_text=normalize_text(generate_text(prompt)))
                except Exception as e:
                    st.error(f"네이버 해시태그 생성 오류: {e}")
        with n2:
            naver_output = build_article_with_images(
                st.session_state["naver_article_title"],
                st.session_state["naver_article_body"],
                st.session_state["naver_image_prompts_text"],
                st.session_state["applied_common_text"],
                st.session_state["naver_hashtags_text"],
            )
            st.download_button(
                "네이버 TXT 저장",
                data=wrap_preview_text(naver_output, width=38),
                file_name=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_filename(st.session_state['naver_article_title'] or st.session_state['keyword'])}_naver.txt",
                mime="text/plain",
                use_container_width=True,
            )

    with right:
        tistory_preview = format_text_for_preview(
            st.session_state["tistory_article_title"],
            st.session_state["tistory_article_body"],
            st.session_state["applied_common_text"],
            st.session_state["tistory_hashtags_text"],
            st.session_state["tistory_image_prompts_text"],
        )
        st.text_area("티스토리 글", value=tistory_preview, height=620)
        t1, t2 = st.columns(2)
        with t1:
            if st.button("티스토리 해시태그 생성", use_container_width=True):
                try:
                    source = (st.session_state["tistory_article_title"] + "\n\n" + st.session_state["tistory_article_body"]).strip()
                    if source:
                        prompt = build_hashtag_prompt(
                            st.session_state["keyword"] or st.session_state["category"],
                            build_effective_sub_keywords("티스토리"),
                            source,
                            st.session_state["hashtag_count"],
                        )
                        set_and_refresh(tistory_hashtags_text=normalize_text(generate_text(prompt)))
                except Exception as e:
                    st.error(f"티스토리 해시태그 생성 오류: {e}")
        with t2:
            tistory_output = build_article_with_images(
                st.session_state["tistory_article_title"],
                st.session_state["tistory_article_body"],
                st.session_state["tistory_image_prompts_text"],
                st.session_state["applied_common_text"],
                st.session_state["tistory_hashtags_text"],
            )
            st.download_button(
                "티스토리 TXT 저장",
                data=wrap_preview_text(tistory_output, width=38),
                file_name=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_filename(st.session_state['tistory_article_title'] or st.session_state['keyword'])}_tistory.txt",
                mime="text/plain",
                use_container_width=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="footer-note">현재 버전: 추천 버전 · 반자동 글쓰기 · 메인키워드 관심도 · 추천 키워드</div>', unsafe_allow_html=True)