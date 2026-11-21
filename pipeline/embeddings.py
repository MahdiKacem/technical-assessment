import os
from dataclasses import dataclass

MODEL_NAME = "gemini-embedding-2"
MODEL_VERSION = "v1"


@dataclass
class EmbeddingResult:
    vector: list[float]
    input_tokens: int | None


def make_gemini_client():
    from dotenv import load_dotenv
    from google import genai

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured (see .env.example).")
    return genai.Client(api_key=api_key)


def _result(response) -> EmbeddingResult:
    usage = getattr(response, "usage_metadata", None)
    tokens = getattr(usage, "prompt_token_count", None) if usage else None
    return EmbeddingResult(vector=list(response.embeddings[0].values), input_tokens=tokens)


def embed_query(client, query: str) -> EmbeddingResult:
    return _result(client.models.embed_content(
        model=MODEL_NAME,
        contents=f"task: search result | title: none | query: {query}",
    ))


def embed_document_text(client, text: str) -> EmbeddingResult:
    return _result(client.models.embed_content(
        model=MODEL_NAME,
        contents=f"task: search result | title: none | text: {text}",
    ))


def embed_image(client, image_bytes: bytes, mime_type: str = "image/jpeg") -> EmbeddingResult:
    from google.genai import types

    if not mime_type.startswith("image/"):
        raise ValueError(f"Only still images may be embedded, got {mime_type}")
    return _result(client.models.embed_content(
        model=MODEL_NAME,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
    ))
