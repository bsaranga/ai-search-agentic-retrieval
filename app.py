"""Coffee RAG — Streamlit chat over an Azure AI Search index.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from utils.config import AOAI_DEPLOYMENT, SEARCH_INDEX
from utils.render import render_debug, render_sources
from utils.search import retrieve
from utils.synthesis import synthesize_stream


st.set_page_config(page_title="Coffee RAG", page_icon="☕", layout="wide")
st.title("☕ Coffee RAG")
st.caption(f"Index: `{SEARCH_INDEX}` · Model: `{AOAI_DEPLOYMENT}`")

if "history" not in st.session_state:
    st.session_state.history = []

# Replay history
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_sources((msg.get("search_response") or {}).get("value", []))

# New turn
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

# Debug sidebar — latest turn only
with st.sidebar:
    st.header("🔍 Search debug")
    last = next(
        (m for m in reversed(st.session_state.history)
         if m["role"] == "assistant" and m.get("search_response")),
        None,
    )
    if last is None:
        st.caption("Ask a question to see search internals here.")
    else:
        render_debug(last["search_response"])
