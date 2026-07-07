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
        # hard timeouts + retries: one hung TLS handshake must not kill a film
        _client = OpenAI(api_key=key, base_url=config.BASE_URL,
                         timeout=90.0, max_retries=2)
    return _client


def chat(stage: str, model: str, system: str, user: str, ledger: Ledger,
         json_mode: bool = False, thinking: bool = True, search: bool = False,
         on_delta=None) -> str:
    """on_delta(text_so_far, kind): live token stream — kind is 'thinking' or 'text'.
    Streaming lets the UI SHOW the model working instead of a spinner."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    extra: dict = {}
    if not thinking:
        # enable_thinking:false cuts qwen3.x latency ~5x where depth isn't needed
        extra["enable_thinking"] = False
    if search:
        # enable_search alone is only a permission; forced_search makes the web call real
        extra["enable_search"] = True
        extra["search_options"] = {"forced_search": True}
    if extra:
        kwargs["extra_body"] = extra

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    if on_delta is None:
        resp = client().chat.completions.create(model=model, messages=messages, **kwargs)
        usage = resp.usage
        ledger.record(stage=stage, model=model,
                      tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens)
        return resp.choices[0].message.content

    stream = client().chat.completions.create(
        model=model, messages=messages, stream=True,
        stream_options={"include_usage": True}, **kwargs)
    text, think = "", ""
    usage = None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        r = getattr(delta, "reasoning_content", None)
        if r:
            think += r
            on_delta(think, "thinking")
        if delta.content:
            text += delta.content
            on_delta(text, "text")
    if usage:
        ledger.record(stage=stage, model=model,
                      tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens)
    return text


def chat_json(stage: str, model: str, system: str, user: str, ledger: Ledger,
              thinking: bool = True, search: bool = False, on_delta=None) -> dict:
    raw = chat(stage, model, system, user, ledger, json_mode=True, thinking=thinking,
               search=search, on_delta=on_delta)
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
