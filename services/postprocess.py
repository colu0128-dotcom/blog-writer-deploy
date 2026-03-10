\
import re


BANNED_PHRASES = [
    "보완반영",
    "보통보정",
    "추천버전",
    "플랫폼 버전",
]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def remove_banned_phrases(text: str) -> str:
    for phrase in BANNED_PHRASES:
        text = text.replace(phrase, "")
    return text


def split_title_and_body(text: str):
    text = normalize_text(remove_banned_phrases(text))
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "", ""

    title = lines[0]
    body = "\n\n".join(lines[1:]).strip()
    return title, body


def extract_hashtags(text: str):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    cleaned = []
    seen = set()

    for line in lines:
        if not line.startswith("#"):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)

    return cleaned


def to_html(title: str, body: str, hashtags=None) -> str:
    hashtags = hashtags or []
    parts = []

    if title:
        parts.append(f"<h1>{title}</h1>")

    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        if block.startswith("[이미지 추천:"):
            parts.append(f"<p><strong>{block}</strong></p>")
        else:
            parts.append(f"<p>{block}</p>")

    if hashtags:
        parts.append("<hr>")
        parts.append("<p>" + " ".join(hashtags) + "</p>")

    return "\n".join(parts)
