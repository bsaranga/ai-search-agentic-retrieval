"""Load Stack Exchange XML dump into Azure SQL.

Creates normalized tables (Users, Posts, Tags, PostTags) from the Coffee
Stack Exchange XML files, then a downstream view (vw_CoffeePostsFlat) can
expose them as the flat shape the Azure AI Search indexer expects.

Usage:
    python scripts/load_sql.py --xml-dir dataset/coffee.stackexchange.com
"""

from __future__ import annotations

import argparse
import os
import re
import struct
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree as ET

import pyodbc
from dotenv import load_dotenv


DDL = """
IF OBJECT_ID('dbo.PostTags', 'U') IS NOT NULL DROP TABLE dbo.PostTags;
IF OBJECT_ID('dbo.Posts',    'U') IS NOT NULL DROP TABLE dbo.Posts;
IF OBJECT_ID('dbo.Tags',     'U') IS NOT NULL DROP TABLE dbo.Tags;
IF OBJECT_ID('dbo.Users',    'U') IS NOT NULL DROP TABLE dbo.Users;

CREATE TABLE dbo.Users (
    Id              INT            NOT NULL PRIMARY KEY,
    DisplayName     NVARCHAR(200)  NULL,
    Reputation      INT            NULL,
    CreationDate    DATETIME2      NULL,
    LastAccessDate  DATETIME2      NULL,
    Location        NVARCHAR(200)  NULL,
    AboutMe         NVARCHAR(MAX)  NULL,
    Views           INT            NULL,
    UpVotes         INT            NULL,
    DownVotes       INT            NULL
);

CREATE TABLE dbo.Posts (
    Id                INT            NOT NULL PRIMARY KEY,
    PostTypeId        INT            NOT NULL,   -- 1=question, 2=answer
    ParentId          INT            NULL,        -- question id for answers
    AcceptedAnswerId  INT            NULL,
    CreationDate      DATETIME2      NULL,
    LastActivityDate  DATETIME2      NULL,
    Score             INT            NULL,
    ViewCount         INT            NULL,
    AnswerCount       INT            NULL,
    CommentCount      INT            NULL,
    Title             NVARCHAR(500)  NULL,
    Body              NVARCHAR(MAX)  NULL,
    OwnerUserId       INT            NULL,
    OwnerDisplayName  NVARCHAR(200)  NULL,
    TagsRaw           NVARCHAR(500)  NULL          -- raw |tag1|tag2| from XML
);
CREATE INDEX IX_Posts_ParentId ON dbo.Posts(ParentId);
CREATE INDEX IX_Posts_PostTypeId ON dbo.Posts(PostTypeId);

CREATE TABLE dbo.Tags (
    Id            INT            NOT NULL PRIMARY KEY,
    TagName       NVARCHAR(100)  NOT NULL,
    Count         INT            NULL,
    ExcerptPostId INT            NULL,
    WikiPostId    INT            NULL
);
CREATE UNIQUE INDEX UX_Tags_TagName ON dbo.Tags(TagName);

CREATE TABLE dbo.PostTags (
    PostId  INT            NOT NULL,
    TagName NVARCHAR(100)  NOT NULL,
    CONSTRAINT PK_PostTags PRIMARY KEY (PostId, TagName)
);
CREATE INDEX IX_PostTags_TagName ON dbo.PostTags(TagName);
"""


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf = StringIO()

    def handle_data(self, data: str) -> None:
        self._buf.write(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("p", "br", "div", "li", "tr"):
            self._buf.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._buf.write("\n")

    def get_text(self) -> str:
        return self._buf.getvalue()


_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def strip_html(s: str | None) -> str | None:
    if not s:
        return s
    p = _HTMLStripper()
    p.feed(s)
    p.close()
    text = p.get_text()
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # Stack Exchange uses "2015-01-27T20:09:32.720"
    return datetime.fromisoformat(s)


def parse_int(s: str | None) -> int | None:
    if s is None or s == "":
        return None
    return int(s)


def split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    # Format: "|storage|whole-bean|"
    return [t for t in raw.split("|") if t]


def iter_rows(xml_path: Path):
    """Stream <row> elements from a Stack Exchange dump without loading all of it."""
    for _event, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag == "row":
            yield elem.attrib
            elem.clear()


def build_conn_str() -> str:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return (
        f"Driver={{{os.environ['AZURE_SQL_DRIVER']}}};"
        f"Server=tcp:{os.environ['AZURE_SQL_SERVER']},{os.environ.get('AZURE_SQL_PORT', '1433')};"
        f"Database={os.environ['AZURE_SQL_DATABASE']};"
        f"Uid={os.environ['AZURE_SQL_USER']};"
        f"Pwd={os.environ['AZURE_SQL_PASSWORD']};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )


def run_ddl(cur: pyodbc.Cursor) -> None:
    for batch in DDL.split(";\n"):
        b = batch.strip()
        if b:
            cur.execute(b)


def load_users(cur: pyodbc.Cursor, xml_dir: Path) -> int:
    rows = []
    for r in iter_rows(xml_dir / "Users.xml"):
        rows.append((
            int(r["Id"]),
            r.get("DisplayName"),
            parse_int(r.get("Reputation")),
            parse_dt(r.get("CreationDate")),
            parse_dt(r.get("LastAccessDate")),
            r.get("Location"),
            strip_html(r.get("AboutMe")),
            parse_int(r.get("Views")),
            parse_int(r.get("UpVotes")),
            parse_int(r.get("DownVotes")),
        ))
    cur.fast_executemany = True
    cur.executemany(
        "INSERT INTO dbo.Users (Id, DisplayName, Reputation, CreationDate, "
        "LastAccessDate, Location, AboutMe, Views, UpVotes, DownVotes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def load_tags(cur: pyodbc.Cursor, xml_dir: Path) -> int:
    rows = []
    for r in iter_rows(xml_dir / "Tags.xml"):
        rows.append((
            int(r["Id"]),
            r["TagName"],
            parse_int(r.get("Count")),
            parse_int(r.get("ExcerptPostId")),
            parse_int(r.get("WikiPostId")),
        ))
    cur.fast_executemany = True
    cur.executemany(
        "INSERT INTO dbo.Tags (Id, TagName, Count, ExcerptPostId, WikiPostId) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def load_posts(cur: pyodbc.Cursor, xml_dir: Path) -> tuple[int, int]:
    post_rows = []
    tag_rows: list[tuple[int, str]] = []
    for r in iter_rows(xml_dir / "Posts.xml"):
        pid = int(r["Id"])
        post_rows.append((
            pid,
            parse_int(r["PostTypeId"]),
            parse_int(r.get("ParentId")),
            parse_int(r.get("AcceptedAnswerId")),
            parse_dt(r.get("CreationDate")),
            parse_dt(r.get("LastActivityDate")),
            parse_int(r.get("Score")),
            parse_int(r.get("ViewCount")),
            parse_int(r.get("AnswerCount")),
            parse_int(r.get("CommentCount")),
            r.get("Title"),
            strip_html(r.get("Body")),
            parse_int(r.get("OwnerUserId")),
            r.get("OwnerDisplayName"),
            r.get("Tags"),
        ))
        for t in split_tags(r.get("Tags")):
            tag_rows.append((pid, t))

    cur.fast_executemany = True
    cur.executemany(
        "INSERT INTO dbo.Posts (Id, PostTypeId, ParentId, AcceptedAnswerId, "
        "CreationDate, LastActivityDate, Score, ViewCount, AnswerCount, "
        "CommentCount, Title, Body, OwnerUserId, OwnerDisplayName, TagsRaw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        post_rows,
    )
    cur.executemany(
        "INSERT INTO dbo.PostTags (PostId, TagName) VALUES (?, ?)",
        tag_rows,
    )
    return len(post_rows), len(tag_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--xml-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "dataset"
        / "coffee.stackexchange.com",
    )
    args = ap.parse_args()

    conn = pyodbc.connect(build_conn_str(), autocommit=False)
    cur = conn.cursor()
    print("connected, creating schema...")
    run_ddl(cur)
    conn.commit()

    print("loading Users...")
    n = load_users(cur, args.xml_dir)
    conn.commit()
    print(f"  inserted {n} users")

    print("loading Tags...")
    n = load_tags(cur, args.xml_dir)
    conn.commit()
    print(f"  inserted {n} tags")

    print("loading Posts + PostTags...")
    np_, nt = load_posts(cur, args.xml_dir)
    conn.commit()
    print(f"  inserted {np_} posts, {nt} post-tag links")

    conn.close()
    print("done.")


if __name__ == "__main__":
    main()
