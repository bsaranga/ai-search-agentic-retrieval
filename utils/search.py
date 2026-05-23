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


def retrieve(
    question: str,
    *,
    k: int = 8,
    filter_: str | None = "kind eq 'answer'",
    select: str = DEFAULT_SELECT,
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
        "debug": "all",
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
    return r.json()
