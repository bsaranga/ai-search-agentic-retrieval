"""Azure OpenAI answer synthesis driven by jinja2 prompt templates."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from openai import AzureOpenAI

from .config import (
    AOAI_DEPLOYMENT,
    AOAI_ENDPOINT,
    AOAI_KEY,
    AOAI_VERSION,
    PROMPTS_DIR,
)


@lru_cache(maxsize=1)
def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_prompt(template_name: str, **context) -> str:
    """Render a prompt template from /prompts. Strict undefined catches typos."""
    return _jinja_env().get_template(template_name).render(**context)


@lru_cache(maxsize=1)
def _openai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_key=AOAI_KEY,
        api_version=AOAI_VERSION,
    )


def synthesize_stream(
    question: str,
    passages: list[dict],
    *,
    system_template: str = "system.md.j2",
    user_template: str = "user.md.j2",
    system_vars: dict | None = None,
) -> Iterator[str]:
    """Stream answer tokens. Prompts are jinja2 templates under /prompts."""
    system_prompt = render_prompt(system_template, **(system_vars or {}))
    user_prompt = render_prompt(user_template, question=question, passages=passages)

    stream = _openai_client().chat.completions.create(
        model=AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
