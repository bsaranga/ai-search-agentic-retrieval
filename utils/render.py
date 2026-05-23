"""Streamlit render helpers — kept UI-only so the main app stays slim."""

from __future__ import annotations

import streamlit as st


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


def render_debug(resp: dict) -> None:
    """Render the full Search response into the sidebar debug panel."""
    docs = resp.get("value", [])
    debug = resp.get("@search.debug") or {}
    rewrites = debug.get("queryRewrites") or {}

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
        header = f"{i}. {title}  · score={score:.4f}"
        if rscore is not None:
            header += f" · reranker={rscore:.3f}"
        with st.expander(header):
            st.markdown(
                f"**id:** `{d.get('id')}`  ·  **kind:** {d.get('kind')}  "
                f"·  **accepted:** {d.get('isAccepted')}  "
                f"·  **tags:** {d.get('tags')}"
            )
            if d.get("url"):
                st.markdown(f"[Open source]({d['url']})")
            body = d.get("body") or ""
            st.markdown(body[:1500] + ("..." if len(body) > 1500 else ""))
