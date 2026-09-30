"""Read a Google Doc script into a RawDoc (text + comments).

Two routes:
- `GoogleDocsReader` — the product route: Drive API v3 `files.export(text/markdown)` for the text
  (Google Docs markdown export exists since July 2024) and `comments.list` with `quotedFileContent`
  for each comment's anchored text. Takes an already-built Drive `service` object, so credentials
  (service account / OAuth) stay outside this module. NOT yet verified against the real doc: stage 0.7
  tested only the Claude Drive connector (docs/bench/gdoc_access.md).
- `load_connector_export` — the files saved in stage 0.7 through the Drive connector (test fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from markflow.domain.script_model import RawComment, RawDoc

COMMENT_FIELDS = (
    "nextPageToken,comments(id,author/displayName,content,quotedFileContent/value,"
    "resolved,deleted,replies(author/displayName,content,deleted))"
)


class DriveService(Protocol):  # the object returned by googleapiclient.discovery.build("drive", "v3")
    def files(self) -> Any: ...
    def comments(self) -> Any: ...


class GoogleDocsReader:
    def __init__(self, service: DriveService):
        self._service = service

    def read(self, doc_id: str) -> RawDoc:
        meta = self._service.files().get(fileId=doc_id, fields="name").execute()
        body = self._service.files().export(fileId=doc_id, mimeType="text/markdown").execute()
        markdown = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        return RawDoc(title=meta.get("name", doc_id), markdown=markdown, comments=tuple(self._comments(doc_id)))

    def _comments(self, doc_id: str) -> list[RawComment]:
        out: list[RawComment] = []
        token = None
        while True:
            page = self._service.comments().list(
                fileId=doc_id, fields=COMMENT_FIELDS, includeDeleted=False, pageSize=100, pageToken=token
            ).execute()
            for c in page.get("comments", []):
                if c.get("deleted"):
                    continue
                out.append(RawComment(
                    id=c["id"],
                    author=c.get("author", {}).get("displayName", ""),
                    text=c.get("content", ""),
                    anchor_text=(c.get("quotedFileContent") or {}).get("value") or None,
                    resolved=bool(c.get("resolved")),
                    replies=tuple(r.get("content", "") for r in c.get("replies", [])
                                  if not r.get("deleted") and r.get("content")),
                ))
            token = page.get("nextPageToken")
            if not token:
                return out


def load_connector_export(text_and_threads: Path, anchored_comments: Path | None = None) -> RawDoc:
    """Build a RawDoc from the stage-0.7 connector files.

    `text_and_threads`: fileContent (markdown with <comment_start id=kix..> marks) + commentThreads
    (all threads incl. resolved, but no anchor text). `anchored_comments`: the .docx route, which has the
    anchor text of every open comment. Open comments come from the .docx; resolved threads (absent there)
    come from the thread list without an anchor.
    """
    doc = json.loads(Path(text_and_threads).read_text(encoding="utf-8"))
    threads = doc.get("commentThreads", [])
    if anchored_comments is None:
        comments = [_thread_to_comment(t) for t in threads]
    else:
        anchored = json.loads(Path(anchored_comments).read_text(encoding="utf-8"))["comments"]
        replies: dict[str, list[str]] = {}
        for c in anchored:
            if c.get("is_reply") and c.get("text"):
                replies.setdefault(c["parent_id"], []).append(c["text"])
        comments = [
            RawComment(
                id=f"docx-{c['id']}", author=c.get("author", ""), text=c.get("text", ""),
                anchor_text=c.get("anchor_text") or None, resolved=bool(c.get("resolved")),
                replies=tuple(replies.get(c["id"], ())),
            )
            for c in anchored if not c.get("is_reply")
        ]
        comments += [_thread_to_comment(t) for t in threads if t.get("status") == "RESOLVED"]
    return RawDoc(title=doc.get("title", ""), markdown=doc["fileContent"], comments=tuple(comments))


def _thread_to_comment(thread: dict[str, Any]) -> RawComment:
    head = thread.get("headPost", {})
    return RawComment(
        id=thread["commentId"], author=head.get("authorName", ""), text=head.get("content", ""),
        resolved=thread.get("status") == "RESOLVED",
        replies=tuple(r["content"] for r in thread.get("replies", []) if r.get("content")),
    )
