"""Upload converted posts to an Azure AI Search index in batches.

Env vars required:
    SEARCH_ENDPOINT  e.g. https://<service>.search.windows.net
    SEARCH_API_KEY   admin key
    SEARCH_INDEX     e.g. coffee-posts

Usage:
    python upload_docs.py --docs ../out/posts.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    client = SearchClient(
        endpoint=os.environ["SEARCH_ENDPOINT"],
        index_name=os.environ["SEARCH_INDEX"],
        credential=AzureKeyCredential(os.environ["SEARCH_API_KEY"]),
    )

    with args.docs.open() as f:
        docs = json.load(f)

    total = 0
    for i in range(0, len(docs), args.batch):
        chunk = docs[i : i + args.batch]
        result = client.upload_documents(documents=chunk)
        failed = [r for r in result if not r.succeeded]
        total += len(chunk) - len(failed)
        print(f"batch {i // args.batch}: {len(chunk) - len(failed)}/{len(chunk)} ok")
        if failed:
            for r in failed[:3]:
                print("  failed:", r.key, r.error_message)

    print(f"uploaded {total}/{len(docs)} docs")


if __name__ == "__main__":
    main()
