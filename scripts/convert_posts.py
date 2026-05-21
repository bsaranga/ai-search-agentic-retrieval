"""Convert Stack Exchange Posts.xml (+ optional Users.xml) into flat JSON
documents shaped for an Azure AI Search index.

Output: one JSON file with an array of docs — one per question and one per
answer — sharing a unified schema. Title and tags are denormalized onto
answer docs so a single answer hit carries its topical anchor for BM25,
vector, and semantic ranking. Body HTML is stripped to plain text.

Usage:
    python convert_posts.py \
        --dataset ../dataset/coffee.stackexchange.com \
        --out ../out/posts_flat.json
"""

from __future__ import annotations

import argparse
import json
import re
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return WS_RE.sub(" ", TAG_RE.sub(" ", unescape(s))).strip()


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t for t in raw.strip("|").split("|") if t]


def iter_rows(path: Path):
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == "row":
            yield elem.attrib
            elem.clear()


def load_users(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {r["Id"]: r.get("DisplayName", "") for r in iter_rows(path)}


def build_docs(dataset: Path) -> list[dict]:
    users = load_users(dataset / "Users.xml")

    questions: dict[str, dict] = {}
    answers_by_parent: dict[str, list[dict]] = {}

    for r in iter_rows(dataset / "Posts.xml"):
        post_type = r.get("PostTypeId")
        owner_id = r.get("OwnerUserId")
        common = {
            "id": r["Id"],
            "body": strip_html(r.get("Body")),
            "score": int(r.get("Score", 0)),
            "commentCount": int(r.get("CommentCount", 0)),
            "creationDate": r.get("CreationDate"),
            "lastActivityDate": r.get("LastActivityDate"),
            "ownerUserId": owner_id,
            "ownerDisplayName": users.get(owner_id or "", ""),
        }
        if post_type == "1":
            questions[r["Id"]] = {
                **common,
                "title": r.get("Title", ""),
                "tags": parse_tags(r.get("Tags")),
                "viewCount": int(r.get("ViewCount", 0)),
                "answerCount": int(r.get("AnswerCount", 0)),
                "acceptedAnswerId": r.get("AcceptedAnswerId"),
            }
        elif post_type == "2":
            answers_by_parent.setdefault(r.get("ParentId", ""), []).append(common)

    out: list[dict] = []
    for qid, q in questions.items():
        title = q["title"]
        tags = q["tags"]
        q_score = q["score"]
        accepted_id = q.get("acceptedAnswerId")

        out.append(
            {
                "id": f"q-{qid}",
                "kind": "question",
                "questionId": qid,
                "title": title,
                "body": q["body"],
                "tags": tags,
                "score": q_score,
                "parentScore": None,
                "viewCount": q["viewCount"],
                "answerCount": q["answerCount"],
                "acceptedAnswerId": accepted_id,
                "isAccepted": False,
                "commentCount": q["commentCount"],
                "creationDate": q["creationDate"],
                "lastActivityDate": q["lastActivityDate"],
                "ownerUserId": q["ownerUserId"],
                "ownerDisplayName": q["ownerDisplayName"],
                "url": f"https://coffee.stackexchange.com/questions/{qid}",
                "chunk": f"Question: {title}\n\n{q['body']}".strip(),
            }
        )

        for a in sorted(answers_by_parent.get(qid, []), key=lambda x: -x["score"]):
            aid = a["id"]
            out.append(
                {
                    "id": f"a-{aid}",
                    "kind": "answer",
                    "questionId": qid,
                    "title": title,
                    "body": a["body"],
                    "tags": tags,
                    "score": a["score"],
                    "parentScore": q_score,
                    "viewCount": None,
                    "answerCount": None,
                    "acceptedAnswerId": None,
                    "isAccepted": aid == accepted_id,
                    "commentCount": a["commentCount"],
                    "creationDate": a["creationDate"],
                    "lastActivityDate": a["creationDate"],
                    "ownerUserId": a["ownerUserId"],
                    "ownerDisplayName": a["ownerDisplayName"],
                    "url": f"https://coffee.stackexchange.com/a/{aid}",
                    "chunk": f"Question: {title}\n\nAnswer: {a['body']}".strip(),
                }
            )

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    docs = build_docs(args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    n_q = sum(1 for d in docs if d["kind"] == "question")
    n_a = sum(1 for d in docs if d["kind"] == "answer")
    print(f"wrote {len(docs)} docs ({n_q} questions, {n_a} answers) to {args.out}")


if __name__ == "__main__":
    main()
