from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI


load_dotenv(Path(__file__).parent / ".env")

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY      = os.environ["AZURE_SEARCH_API_KEY"]
SEARCH_INDEX    = os.environ["AZURE_SEARCH_INDEX"]
SEMANTIC_CONFIG = os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIG", "default-semantic")

AOAI_ENDPOINT   = os.environ["AZURE_OPENAI_ENDPOINT"]
AOAI_KEY        = os.environ["AZURE_OPENAI_API_KEY"]
AOAI_DEPLOYMENT = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
AOAI_VERSION    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")


SEARCH_API_VERSION = "2024-11-01-preview"  # supports queryRewrites


@st.cache_resource
def get_openai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_key=AOAI_KEY,
        api_version=AOAI_VERSION,
    )


def retrieve(question: str, k: int = 8) -> dict:
    """Hybrid query: BM25 + vector, semantic-reranked, with generative query rewrites.

    Returns the full response JSON. The list of documents is in `["value"]`;
    rewrites and debug info live at top level (`@search.debug`, etc.).
    """
    url = (
        f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/search"
        f"?api-version={SEARCH_API_VERSION}"
    )
    body = {
        "search": question,
        "vectorQueries": [{
            "kind": "text",
            "text": question,
            "fields": "chunkVector",
            "k": 50,
        }],
        "queryType": "semantic",
        "semanticConfiguration": SEMANTIC_CONFIG,
        "queryRewrites": "generative",
        "queryLanguage": "en-us",
        "debug": "queryRewrites",
        "top": k,
        "filter": "kind eq 'answer'",
        "select": (
            "id,kind,title,body,tags,score,isAccepted,url,questionId"
        ),
    }
    r = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": SEARCH_KEY},
        json=body,
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Search {r.status_code}: {r.text}")
    return r.json()


def render_debug(resp: dict) -> None:
    """Render the search response into the sidebar debug panel."""
    docs = resp.get("value", [])
    debug = resp.get("@search.debug") or {}
    rewrites = (debug.get("queryRewrites") or {})

    st.subheader("Query rewrites")
    text_rewrites = (rewrites.get("text") or {}).get("rewrites") or []
    vector_rewrites = (rewrites.get("vector") or {}).get("rewrites") or []
    if not text_rewrites and not vector_rewrites:
        st.caption("(none returned)")
    if text_rewrites:
        st.markdown("**Text query variants**")
        for q in text_rewrites:
            st.markdown(f"- {q}")
    if vector_rewrites:
        st.markdown("**Vector query variants**")
        for q in vector_rewrites:
            st.markdown(f"- {q}")

    st.divider()
    st.subheader(f"Retrieved documents ({len(docs)})")
    for i, d in enumerate(docs, 1):
        score = d.get("@search.score")
        rscore = d.get("@search.rerankerScore")
        title = d.get("title") or "(no title)"
        with st.expander(
            f"{i}. {title}  · score={score:.4f}"
            + (f" · reranker={rscore:.3f}" if rscore is not None else "")
        ):
            st.markdown(
                f"**id:** `{d.get('id')}`  ·  **kind:** {d.get('kind')}  "
                f"·  **accepted:** {d.get('isAccepted')}  "
                f"·  **tags:** {d.get('tags')}"
            )
            if d.get("url"):
                st.markdown(f"[Open source]({d['url']})")
            body = d.get("body") or ""
            st.markdown(body[:1500] + ("..." if len(body) > 1500 else ""))


def render_sources(passages: list[dict]) -> None:
    """Compact source list shown inline at the end of an assistant message."""
    if not passages:
        return
    with st.expander(f"Sources ({len(passages)})"):
        for i, p in enumerate(passages, 1):
            title = p.get("title") or "(no title)"
            url = p.get("url") or ""
            link = f"[{title}]({url})" if url else f"**{title}**"
            st.markdown(f"{i}. {link}")


SYSTEM_PROMPT = """\
You answer questions about coffee using passages retrieved from the Coffee
Stack Exchange community. Lead with a direct, practical 1–3 sentence
answer, then expand with reasoning, alternatives, and caveats. Cite the
source post titles you used inline like (source: <title>). When sources
disagree, surface the disagreement instead of picking arbitrarily. If the
passages don't address the question at all, say so plainly.
"""


def synthesize_stream(question: str, passages: list[dict]):
    client = get_openai_client()
    context = "\n\n---\n\n".join(
        f"[{i+1}] title: {p.get('title')}\n"
        f"kind: {p.get('kind')} | score: {p.get('score')} | accepted: {p.get('isAccepted')}\n"
        f"{p.get('body','')}"
        for i, p in enumerate(passages)
    )
    stream = client.chat.completions.create(
        model=AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Question: {question}\n\nRetrieved passages:\n{context}"},
        ],
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ── UI ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Coffee RAG", page_icon="☕", layout="wide")
st.title("☕ Coffee RAG")
st.caption(f"Index: `{SEARCH_INDEX}` · Model: `{AOAI_DEPLOYMENT}`")

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_sources((msg.get("search_response") or {}).get("value", []))

if question := st.chat_input("Ask a coffee question..."):
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            resp = retrieve(question)
        passages = resp.get("value", [])
        answer = st.write_stream(synthesize_stream(question, passages))
        render_sources(passages)

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "search_response": resp}
    )

# ── Debug sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Search debug")
    last_assistant = next(
        (m for m in reversed(st.session_state.history)
         if m["role"] == "assistant" and m.get("search_response")),
        None,
    )
    if last_assistant is None:
        st.caption("Ask a question to see search internals here.")
    else:
        render_debug(last_assistant["search_response"])
