# Accountable agents

Several assistants and coding agents can drive Lumiere's Hoard at the same time, over MCP or `POST /api/agent/call`. Every change
one of them makes can be traced to an agent and a session, comes with a reason, and can be taken back. The web interface is not an
agent: it runs the same tools without a reason and without the journal, and it is not affected by any of this.

The library behind it is Hoard Link 0.8.2 (`lumiere_hoard/hoard_link/`, vendored); the hooks of each tool are in
`lumiere_hoard/agent_undo.py`.

## 1. Who calls

The MCP bridge (`mcp_server.py`) sends two headers read from the environment of whoever launches it:

```
HOARD_AGENT_ID=my-agent  HOARD_AGENT_SESSION=run-42
```

(`X-Agent-Id`, `X-Agent-Session`; a body `agent` / `caller` and `_session` / `session` work as well). The session is any opaque id: the chat or
run of the agent. A call without a session is still journaled, but a whole session can only be undone when it has one.

## 2. A reason on every change

Every tool that is not read-only needs a `reason` of 3 to 300 characters, in the body (`{"name", "arguments", "reason"}`) or among the
arguments. Without it nothing runs:

```json
400 {"error": "This tool changes data, so the call needs a reason.", "code": "reason_required",
     "hint": "Add a `reason` (3-300 characters): one sentence on why you are making this change. ..."}
```

`GET /api/agent/tools` lists `reason` as a required property of those tools, so a model sees it in the schema. Reading tools (`project_get`,
`media_list`, `job_status`, `transcript_get`...) need none and are not journaled.

## 3. The journal

Every change that reached its tool, successful or not, is a line of `data/agent_journal.jsonl` (rotated at about 5 MB): tool, agent, session,
reason, a digest and a masked summary of the arguments, the ids it touched, the objects (`project:prj_...`, `media:med_...`), a fingerprint of
the result, time, and whether it can be undone. Secrets are masked. The event `agent.write` goes to the family bus (never the arguments).

`GET /api/agent/journal?session=&agent=&kind=&since=&limit=` (Bearer token) reads it.

## 4. Undo a session

```
POST /api/agent/undo {"session": "run-42", "dry_run": true}                          what would be taken back
POST /api/agent/undo {"session": "run-42", "confirm": true, "reason": "..."}         do it, newest change first
```

Only the changes of that session (and agent, if given) are looked at; other sessions are never touched. Each project is put back by saving
its earlier timeline as a **new step of its history** ("Deshacer cambios del agente"): nothing is lost, and the editor's own Undo and Redo keep
working. A change is reported as a **conflict**, and left as it is, when another session wrote to the same object later or when the object no
longer looks like the change left it (the person edited the timeline in the editor, for instance).

| Undone by | What it does |
| --- | --- |
| `timeline_edit`, `edit_command`, `text_cut`, `multicam_create`, `multicam_switch`, `multicam_auto`, `music_pick` (with `add`), `broll_suggest` (with `place`), `clip_freeze`, `timeline_history` (undo, redo, restore) | the project goes back to the timeline it had before the call (a preview, a replayed `request_id` or a missing analysis changed nothing and there is nothing to do) |
| `timeline_nest` | the timeline goes back and the sequence project it made is deleted |
| `project_create`, `project_from_timeline`, `short_from_range`, `template_save` | the project is deleted, unless the person edited it, another project nests it or it was exported (a conflict) |
| `plan_create` | the draft plan is deleted |
| `plan_apply` | the timeline goes back to before the plan and the plan is a draft again; renders the plan queued are not cancelled |
| `media_import`, `media_shared`, `media_receive` | the entries it added leave the library (the files are never touched); the project it created or extended is put back; entries a project uses stay |
| `media_tag` | the labels come back |
| `transcript_fix`, `speakers_edit` (rename, assign, merge, clear) | the transcript and the speakers come back |
| `subtitles_translate` with `fix` or `delete` | the translated cues come back |
| `settings` | the previous values come back |

**Not undoable** (reported under `not_undoable`, with `reason: "no_handler"`): `media_delete`, `project_delete`, `media_analyze`, `clip_stabilize`,
`render_start`, `frame_snapshot`, `project_contact_sheet`, `subtitles_export`, `project_export_otio`, `job_cancel` and the `creative_*` tools.
Some tools have one part that cannot be taken back, and that single call is reported as not undoable with the reason: a translation or a
voice separation produced by a background job (`subtitles_translate` with `translate`, `speakers_edit` with `diarize`), and a refresh of a
shared original (`media_shared`). The history keeps the last 300 steps of a project; an earlier version beyond that cannot be restored.

## 5. Tokens and profiles

The main token (`data/mcp-token`) can do everything. Extra tokens, one per agent, are stored hashed in `data/agent_tokens.json`:

```
python -m lumiere_hoard.hoard_link.tokens mint   --app-data-dir data --agent my-agent --profile drafts      # prints the token once
python -m lumiere_hoard.hoard_link.tokens list   --app-data-dir data
python -m lumiere_hoard.hoard_link.tokens revoke --app-data-dir data --agent my-agent
```

(or `GET/POST /api/agent/tokens` and `DELETE /api/agent/tokens/{id}` with the main token). The agent runs its bridge with `LUMIERE_TOKEN` set to
that token instead of reading `mcp-token`. A scoped token fixes the agent name of its calls, sees only its own journal lines, and can undo only with
the `all` profile.

| Profile | May call |
| --- | --- |
| `read_only` | the tools that change nothing |
| `drafts` | those, plus the tools that create or edit drafts and never delete, export or publish: `media_import`, `media_shared`, `media_receive`, `media_tag`, `media_analyze`, `transcript_fix`, `speakers_edit`, `project_create`, `project_from_timeline`, `short_from_range`, `template_save`, `timeline_edit`, `timeline_history`, `timeline_nest`, `edit_command`, `text_cut`, `plan_create`, `multicam_create`, `multicam_switch`, `multicam_auto`, `music_pick`, `broll_suggest`, `clip_freeze`, `clip_stabilize`, `frame_snapshot`, `project_contact_sheet` |
| `all` | everything (but the token administration) |

A call a profile does not allow answers `403 profile_forbidden` with a hint.
