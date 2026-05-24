"""Azure AI Search REST client.

The SDK lags behind on newest features like `queryRewrites`, so we hit REST
directly. Keeps a single retrieve() entrypoint with sensible defaults.
"""

from __future__ import annotations

import requests

from .config import (
    SEARCH_API_VERSION,
    SEARCH_ENDPOINT,
    SEARCH_INDEX,
    SEARCH_KEY,
    SEMANTIC_CONFIG,
)


DEFAULT_SELECT = "id,kind,title,body,tags,score,isAccepted,url,questionId"

APPLY_RERANKER_THRESHOLD = True
RERANKER_SCORE_THRESHOLD = 2.91


def retrieve(
    question: str,
    *,
    k: int = 8,
    filter_: str | None = "kind eq 'answer'",
    select: str = DEFAULT_SELECT,
    apply_threshold: bool | None = None,
    threshold: float | None = None,
) -> dict:
    """Hybrid query: BM25 + vector, semantic-reranked, with generative query rewrites.

    Returns the full response JSON. Documents are in `["value"]`; rewrites
    live under `["@search.debug"]["queryRewrites"]`.
    """
    url = (
        f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/search"
        f"?api-version={SEARCH_API_VERSION}"
    )
    body: dict = {
        "search": question,
        "vectorQueries": [{
            "kind": "text",
            "text": question,
            "fields": "chunkVector",
            "k": 50,
        }],
        "queryType": "semantic",
        "semanticConfiguration": SEMANTIC_CONFIG,
        "queryRewrites": "generative|count-3",
        "queryLanguage": "en-us",
        "debug": "queryRewrites",
        "top": k,
        "select": select,
    }
    if filter_:
        body["filter"] = filter_

    r = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": SEARCH_KEY},
        json=body,
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Search {r.status_code}: {r.text}")
    resp = r.json()

    enabled = APPLY_RERANKER_THRESHOLD if apply_threshold is None else apply_threshold
    cutoff = RERANKER_SCORE_THRESHOLD if threshold is None else threshold
    if enabled:
        kept = [
            d for d in resp.get("value", [])
            if (d.get("@search.rerankerScore") or 0.0) >= cutoff
        ]
        resp["@search.rerankerThreshold"] = {
            "applied": True,
            "value": cutoff,
            "kept": len(kept),
            "dropped": len(resp.get("value", [])) - len(kept),
        }
        resp["value"] = kept
    return resp


def autocomplete(
    prefix: str,
    *,
    suggester: str = "sg",
    mode: str = "oneTermWithContext",
    fuzzy: bool = True,
    top: int = 8,
) -> list[dict]:
    """Term-level autocomplete — completes the partial word the user is typing.

    Modes:
      * `oneTerm`            — complete only the last word.
      * `twoTerms`            — complete the last word + the previous bigram.
      * `oneTermWithContext`  — complete the last word using prior words as context.
    """
    if not prefix.strip():
        return []
    url = (
        f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/autocomplete"
        f"?api-version={SEARCH_API_VERSION}"
    )
    body = {
        "search": prefix,
        "suggesterName": suggester,
        "autocompleteMode": mode,
        "fuzzy": fuzzy,
        "top": top,
    }
    r = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": SEARCH_KEY},
        json=body,
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"Autocomplete {r.status_code}: {r.text}")
    return r.json().get("value", [])


def suggest(
    prefix: str,
    *,
    suggester: str = "sg",
    fuzzy: bool = True,
    top: int = 8,
    select: str = "id,title,kind,url,score,isAccepted",
) -> list[dict]:
    """Document-level suggestions — returns matching docs (not just terms)."""
    if not prefix.strip():
        return []
    url = (
        f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX}/docs/suggest"
        f"?api-version={SEARCH_API_VERSION}"
    )
    body = {
        "search": prefix,
        "suggesterName": suggester,
        "fuzzy": fuzzy,
        "top": top,
        "select": select,
    }
    r = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": SEARCH_KEY},
        json=body,
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"Suggest {r.status_code}: {r.text}")
    return r.json().get("value", [])
