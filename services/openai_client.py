\
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-4.1-mini"


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 없습니다. .env 파일을 확인하세요.")
    return OpenAI(api_key=api_key)


def generate_text(prompt: str) -> str:
    client = get_client()
    response = client.responses.create(
        model=MODEL,
        input=prompt
    )
    return (response.output_text or "").strip()
