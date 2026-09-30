# Stage 0.7 — access to the script Google Doc (checked 2026-09-30)

Doc: «МОЙ ЮТУБ_МОДНАЯ ПРОПАГАНДА», id `1ZfKaT_PS7PbRUqQhY4b_1Cdl_KYPUhV_EtNGQJJJZRI` (owner lukutinadar@gmail.com, shared with Artem).
It was **not** findable by title search in the connector - open it by id (the id is in the saved `.mhtml`).

| Route | Text | Comments | Comment -> anchored text | Resolved comments |
|---|---|---|---|---|
| Drive connector `read_file_content(includeComments)` | yes, with `<comment_start id=kix.…>` markers | 146 threads (140 open, 6 resolved), replies included | **no** (kix ids ≠ thread ids) | yes |
| Drive connector `download_file_content` as .docx | yes | 193 (140 threads + 53 replies) | **yes** (`commentRangeStart/End` ids) | **no** |
| Google Drive API `comments.list` with `quotedFileContent` (service account or OAuth) | via Docs API | yes | yes | yes (`includeDeleted=false`, filter on `resolved`) |

Both connector routes work in this environment. For the product (Windows app) the API route is the target;
the service account from `premiere-assembler-python\credentials` was **not** tested (folder not connected here).

Facts for `docs_reader.py`: cue lines look like `**001 ЛАЙВ …**` / `**СТЕНДАП**`; links are markdown links;
timecodes of the live fragment sit on the following bold line (`1:15:13 text — 1:15:16`).
Doc size 2.3 MB, ~38 600 paragraphs (mostly empty); the text export is ~0.9 MB.

Keyed-Video on Drive: id `1jqqKVvFxZKk82__4z40hunxHrrR1Sl1S`, 44 759 985 836 bytes, owner makashenets@prb.team, in folder `12RPrcIfqdFZce9y1NqSft6FNrLnr3Fl3`.
