"""Convert Stack Exchange Posts.xml (+ optional Comments.xml, Users.xml) into
JSON documents shaped for an Azure AI Search index.

Output: one JSON file with an array of question documents. Answers are nested
under each question as `answers`, so a single index doc gives the LLM full
Q&A context for RAG.

Usage:
    python convert_posts.py \
        --dataset ../dataset/coffee.stackexchange.com \
        --out ../out/posts.json
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
        body_text = strip_html(r.get("Body"))
        base = {
            "id": r["Id"],
            "body": body_text,
            "score": int(r.get("Score", 0)),
            "creationDate": r.get("CreationDate"),
            "lastActivityDate": r.get("LastActivityDate"),
            "ownerUserId": r.get("OwnerUserId"),
            "ownerDisplayName": users.get(r.get("OwnerUserId", ""), ""),
            "commentCount": int(r.get("CommentCount", 0)),
        }
        if post_type == "1":
            questions[r["Id"]] = {
                **base,
                "title": r.get("Title", ""),
                "tags": parse_tags(r.get("Tags")),
                "viewCount": int(r.get("ViewCount", 0)),
                "answerCount": int(r.get("AnswerCount", 0)),
                "acceptedAnswerId": r.get("AcceptedAnswerId"),
                "url": f"https://coffee.stackexchange.com/questions/{r['Id']}",
                "answers": [],
            }
        elif post_type == "2":
            answers_by_parent.setdefault(r.get("ParentId", ""), []).append(base)

    for qid, q in questions.items():
        for a in sorted(answers_by_parent.get(qid, []), key=lambda x: -x["score"]):
            q["answers"].append(
                {
                    "id": a["id"],
                    "body": a["body"],
                    "score": a["score"],
                    "creationDate": a["creationDate"],
                    "ownerDisplayName": a["ownerDisplayName"],
                    "isAccepted": a["id"] == q.get("acceptedAnswerId"),
                }
            )
        # Concatenated field handy for embeddings / semantic search
        answers_blob = "\n\n".join(a["body"] for a in q["answers"])
        q["content"] = (q["title"] + "\n\n" + q["body"] + "\n\n" + answers_blob).strip()

    return list(questions.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    docs = build_docs(args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"wrote {len(docs)} question docs to {args.out}")


if __name__ == "__main__":
    main()
