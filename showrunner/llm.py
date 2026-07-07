"""Thin OpenAI-compatible client for Qwen Cloud with ledger recording."""

import json
import os

from openai import OpenAI

from . import config
from .ledger import Ledger

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("DASHSCOPE_API_KEY")
        if not key:
            raise SystemExit("DASHSCOPE_API_KEY missing — copy .env.example to .env")
        _client = OpenAI(api_key=key, base_url=config.BASE_URL)
    return _client


def chat(stage: str, model: str, system: str, user: str, ledger: Ledger,
         json_mode: bool = False, thinking: bool = True) -> str:
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    if not thinking:
        # enable_thinking:false cuts qwen3.x latency ~5x where depth isn't needed
        kwargs["extra_body"] = {"enable_thinking": False}
    resp = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        **kwargs,
    )
    usage = resp.usage
    ledger.record(stage=stage, model=model,
                  tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens)
    return resp.choices[0].message.content


def chat_json(stage: str, model: str, system: str, user: str, ledger: Ledger,
              thinking: bool = True) -> dict:
    raw = chat(stage, model, system, user, ledger, json_mode=True, thinking=thinking)
    return json.loads(raw)


def chat_vision_json(stage: str, model: str, system: str, text: str,
                     images_b64: list[str], ledger: Ledger) -> dict:
    """VL call: JPEG frames (base64) + text in, JSON out. Thinking off — verdicts
    need speed, not depth (same finding as the verify agent: 45s → ~8s)."""
    content = [{"type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images_b64]
    content.append({"type": "text", "text": text})
    resp = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": content}],
        response_format={"type": "json_object"},
        extra_body={"enable_thinking": False},
    )
    usage = resp.usage
    ledger.record(stage=stage, model=model,
                  tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens)
    return json.loads(resp.choices[0].message.content)
