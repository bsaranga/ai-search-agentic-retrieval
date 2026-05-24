"""Showcase Azure AI Search's autocomplete + suggest endpoints.

`autocomplete` returns *term completions* — what you'd render under a
search bar as the user types. `suggest` returns *document hits* — what
you'd render as a richer dropdown ("did you mean this article?").

Both rely on the index's suggester (`sg`), which uses
`analyzingInfixMatching` over `title` and `tags`.
"""

from __future__ import annotations

import streamlit as st

from utils.config import SEARCH_INDEX
from utils.search import autocomplete, suggest


st.set_page_config(page_title="Autocomplete · Coffee RAG", page_icon="🔠", layout="wide")
st.title("🔠 Autocomplete & Suggest")
st.caption(f"Index: `{SEARCH_INDEX}` · suggester `sg` over `title`, `tags`")

# ── Controls ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Options")
    mode = st.selectbox(
        "autocompleteMode",
        ["oneTerm", "twoTerms", "oneTermWithContext"],
        index=2,
        help="oneTerm: complete the last word. twoTerms: complete bigrams. "
             "oneTermWithContext: complete the last word using prior words as context.",
    )
    fuzzy = st.toggle("fuzzy", value=True, help="Edit-distance tolerance for typos.")
    top = st.slider("top", min_value=1, max_value=20, value=8)
    show_suggest = st.toggle("Also call /suggest (doc-level)", value=True)

# ── Input ─────────────────────────────────────────────────────────────────
prefix = st.text_input(
    "Start typing…",
    placeholder="e.g. 'esp', 'pour-o', 'whole bean'",
    key="prefix",
)

if not prefix.strip():
    st.info("Type at least one character to see completions.")
    st.stop()

# ── Autocomplete results ──────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("autocomplete")
    st.caption("Term-level completions of the partial word")
    try:
        ac = autocomplete(prefix, mode=mode, fuzzy=fuzzy, top=top)
    except Exception as e:
        st.error(str(e))
        ac = []
    if not ac:
        st.caption("(no completions)")
    for item in ac:
        completion = item.get("text", "")
        full = item.get("queryPlusText", completion)
        # Visually highlight the typed prefix vs the suggested completion
        st.markdown(f"- **{full}**  · _completes from_ `{prefix}`")

with col2:
    st.subheader("suggest")
    st.caption("Document-level matches (titles)")
    if not show_suggest:
        st.caption("Disabled in sidebar.")
    else:
        try:
            sg = suggest(prefix, fuzzy=fuzzy, top=top)
        except Exception as e:
            st.error(str(e))
            sg = []
        if not sg:
            st.caption("(no suggestions)")
        for s in sg:
            title = s.get("@search.text") or s.get("title") or "(no title)"
            doc = s.get("document") or {}
            url = doc.get("url") or ""
            kind = doc.get("kind") or ""
            link = f"[{title}]({url})" if url else f"**{title}**"
            st.markdown(f"- {link}  · _{kind}_")

# ── How it works ──────────────────────────────────────────────────────────
with st.expander("How this works"):
    st.markdown(
        """
        Both endpoints query the index's **suggester** — a verbatim
        character-level structure built at indexing time for the fields in
        `sourceFields`. It supports `analyzingInfixMatching`, meaning
        matches can occur anywhere in the indexed term, not just at the
        start.

        - **`/docs/autocomplete`** returns suggested *terms*. Use it under
          a search bar for instant in-place completion (the classic
          autocomplete UX).
        - **`/docs/suggest`** returns full documents whose suggester
          fields match. Use it for "rich dropdown" UIs that preview hits
          before the user submits.

        Both endpoints are O(prefix length), use no semantic ranker, and
        are billable as standard query units.
        """
    )
