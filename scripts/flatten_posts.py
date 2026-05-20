"""Flatten nested posts.json (question with answers[]) into one doc per
question OR answer, sharing a unified schema for Azure AI Search.

Every output doc has the same fields. Question-only fields (viewCount,
answerCount, acceptedAnswerId) stay null on answer docs; answer-only fields
(isAccepted, parentScore) stay null/false on question docs. Title and tags
are denormalized onto answer docs so a single answer hit carries its
topical anchor for BM25, vectors, and semantic ranking.

Usage:
    python flatten_posts.py --in ../posts.json --out ../out/posts_flat.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def flatten(questions: list[dict]) -> list[dict]:
    out: list[dict] = []
    for q in questions:
        qid = q["id"]
        title = q.get("title", "")
        tags = q.get("tags", [])
        q_score = q.get("score", 0)
        q_url = q.get("url", "")

        out.append(
            {
                "id": f"q-{qid}",
                "kind": "question",
                "questionId": qid,
                "title": title,
                "body": q.get("body", ""),
                "tags": tags,
                "score": q_score,
                "parentScore": None,
                "viewCount": q.get("viewCount"),
                "answerCount": q.get("answerCount"),
                "acceptedAnswerId": q.get("acceptedAnswerId"),
                "isAccepted": False,
                "commentCount": q.get("commentCount", 0),
                "creationDate": q.get("creationDate"),
                "lastActivityDate": q.get("lastActivityDate"),
                "ownerUserId": q.get("ownerUserId"),
                "ownerDisplayName": q.get("ownerDisplayName", ""),
                "url": q_url,
                "chunk": f"{title}\n\n{q.get('body', '')}".strip(),
            }
        )

        for a in q.get("answers", []):
            aid = a["id"]
            out.append(
                {
                    "id": f"a-{aid}",
                    "kind": "answer",
                    "questionId": qid,
                    "title": title,                                # denormalized
                    "body": a.get("body", ""),
                    "tags": tags,                                  # denormalized
                    "score": a.get("score", 0),
                    "parentScore": q_score,
                    "viewCount": None,
                    "answerCount": None,
                    "acceptedAnswerId": None,
                    "isAccepted": bool(a.get("isAccepted")),
                    "commentCount": a.get("commentCount", 0),
                    "creationDate": a.get("creationDate"),
                    "lastActivityDate": a.get("creationDate"),    # answers don't track LAD
                    "ownerUserId": a.get("ownerUserId"),
                    "ownerDisplayName": a.get("ownerDisplayName", ""),
                    "url": f"https://coffee.stackexchange.com/a/{aid}",
                    "chunk": f"Q: {title}\n\nA: {a.get('body', '')}".strip(),
                }
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    with args.inp.open() as f:
        questions = json.load(f)

    docs = flatten(questions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    n_q = sum(1 for d in docs if d["kind"] == "question")
    n_a = sum(1 for d in docs if d["kind"] == "answer")
    print(f"wrote {len(docs)} docs ({n_q} questions, {n_a} answers) to {args.out}")


if __name__ == "__main__":
    main()
