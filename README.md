# Pocket Studio

Local production tools for Claude Code making motion graphics and product videos.

Use Claude Code, the only supported driver, to direct and author a film from decks, visualisations, screenshots and screen recordings. Pocket Studio keeps the sources, render versions, edits and human feedback together. It works with your existing agent session: no additional model login, subscription pairing or hosted service is required.

Pocket Studio is an early CLI, not an automatic video generator. You choose the creative direction and rendering tools. It provides the production steps around them:

- Import reference files, extract PDF text and page images, and inspect recorded media.
- Run an explicit renderer command and retain its output and logs.
- Trim and join authored shots and recordings, preserving audio and optionally mixing music.
- Compare versions in a local playback page and record timestamped human feedback.
- Retain a portable project across Claude Code sessions through a companion skill.

## Requirements

- Python 3.10 or newer on macOS or Linux.
- `ffmpeg` and `ffprobe` on PATH for media operations.
- Optional: Poppler's `pdftotext` and `pdftoppm` for PDF extraction.
- Any additional dependencies required by your chosen renderer.

The CLI itself uses only the Python standard library. On macOS, FFmpeg and Poppler can be installed with `brew install ffmpeg poppler`.

## Install

```sh
git clone https://github.com/xpriment626/pocket-studio.git
cd pocket-studio
python3 install.py
```

This installs an editable `pocket-studio` launcher in `~/.local/bin` and the companion skill in `~/.claude/skills/pocket-studio`. Keep the checkout in place. If needed, add `~/.local/bin` to your shell's PATH. Start a new agent session to discover the skill.

The default is `--skills claude`; use `--skills none` for CLI-only installation. Other driver targets are not supported. Existing installations for other hosts are left untouched; no migration or deletion runs automatically. The installer refuses to overwrite an unrelated command or a differing existing skill.

Alternatively, install the CLI with `pip install .` in your Python environment and copy `skills/pocket-studio` to `~/.claude/skills/pocket-studio`.

```sh
pocket-studio --json doctor
pocket-studio --help
```

## Claude Code drives production

Use the tools actually available in the Claude Code session, directly. The skill
helps Claude ground the story, choose tools, author motion and inspect output; the
CLI supplies storage, rendering, capture, transcript comparison and version-bound
feedback. There is no additional director service or model-CLI wrapper.

Start with code-based motion and available source assets. Claude can create SVG,
Canvas, React or 3D scenes, write disposable scripts and retain reusable components
as appropriate. It can install renderer dependencies where authorized, keeping
project environments, lockfiles and reproducible setup commands. The included
`examples/responsibility_study.py` is a code-authored renderer example; it requires
its documented Pillow/FFmpeg dependencies, not an image generation account.

Discover session capabilities instead of assuming image generation or audio tools.
If no image generator exists, continue with code and existing assets. If a requested
audio operation needs an unavailable connector, report that specific setup need
and continue independent visual work. Never substitute intended script text for
a transcript extracted from real audio or claim an unperformed inspection.

Existing connectors come first. The owner may add an existing ElevenLabs account
connector to Claude Code; discover its actual tools and authentication state there.
Pocket Studio neither connects that account nor copies credentials. No BYOK or
paid generation is required to onboard, and no provider clients are included.
`doctor` reports executables and the supported driver, not connector availability.
Google Drive/Dropbox destination overrides retain their explicit setup errors and
local-only binding contract below.

## Start a project

```sh
pocket-studio init ./film --title 'Product showcase'
pocket-studio source add ./product-deck.pdf --project ./film --role reference
pocket-studio source add ./screen-recording.mov --project ./film --role recording
pocket-studio --json inspect --project ./film
```

Imports copy files into the project and assign stable IDs and SHA-256 hashes. Reimporting the same bytes returns the existing source. PDF extraction is optional; `doctor` reports which tools are available. Importing a document never executes its contents.

Use `BRIEF.md` to define the audience, product facts, creative freedom and human acceptance criteria. Use `TREATMENTS.md` to develop visual and sonic direction. Reference slides supply information and visual vocabulary; they are not automatically turned into a slideshow.

## Render an authored shot

Write a renderer specification:

```json
{
  "label": "Opening study, version 1",
  "source_refs": ["source-ID"],
  "argv": ["python3", "{project}/scene.py", "--output", "{output}"]
}
```

```sh
pocket-studio render --project ./film --spec ./render.json
```

The adapter runs the argument array in the project directory without a shell. `{project}` becomes the project directory; `{output}` becomes a fresh MP4 path. Any installed renderer that can write that file can be used. This is a command adapter, **not a sandbox**: inspect render specs before executing them and keep secrets out of arguments and logs.

Each render receives a new ID. Its request, stdout and stderr are retained beside the output. Failed commands retain their logs but are not registered as successful renders. New renders begin unreviewed.

### Try a procedural example

The included example renders a six-second 3D motion study with a moving camera and selectively activated blocks. It requires Pillow in the Python environment used to render it:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install Pillow
pocket-studio init ./study --title 'Selective activation'
cp examples/responsibility_study.py ./study/scene.py
.venv/bin/python - <<'PY'
import json, sys
from pathlib import Path
Path('render.json').write_text(json.dumps({
    'label': 'Selective activation',
    'argv': [sys.executable, '{project}/scene.py', '--output', '{output}']
}))
PY
pocket-studio render --project ./study --spec ./render.json
pocket-studio review --project ./study
```

The example demonstrates the adapter; it is not a template that every film should follow.

## Assemble shots and recordings

Create a cut specification using paths returned by `inspect`:

```json
{
  "label": "Product film, version 1",
  "clips": [
    {"path": "renders/render-ID/video.mp4", "in": 0, "duration": 6},
    {"path": "sources/source-ID/screen-recording.mov", "in": 2, "duration": 4}
  ],
  "music": {"path": "sources/source-ID/music.wav", "gain": 0.2}
}
```

```sh
pocket-studio assemble --project ./film --spec ./cut.json
```

Paths must resolve inside the project. The assembler normalises clips to the width, height and frame rate in `motion.json`, using letterbox fitting and straight cuts. Source audio is retained; silent shots receive a silent audio track. Music is optional, mixed at the specified linear gain, and is not automatically looped. It can come from any source you are entitled to use, including a separately configured generation provider.

Author camera movement, transitions, crops, compositing and detailed sound design in the shots themselves. Stills can be used by those renderers; the assembler expects video clips.

## Review with a human

```sh
pocket-studio review --project ./film
```

Open the returned `reviews/index.html` in a browser, or open the artifact's video file in a system player. The standalone page retains its downloadable JSON feedback fallback.

For conversational feedback, use the artifact ID and SHA-256 from `inspect` directly:

```sh
pocket-studio feedback --project ./film --id render-ID --sha256 SHA256 \
  --decision revise --time 1.25 --note 'Hold this frame longer' --request-id review-note-1
# For a longer note, replace --note with --note-file ./note.txt.
# Existing exported feedback remains supported:
pocket-studio feedback --project ./film --file ./motion-feedback.json
```

Use `--decision approve` only for actual human approval of that exact version. Attribution is caller supplied, not authenticated identity. Agent critique and technical checks cannot approve creative work. New renders and cuts start unreviewed, even when their source shots are approved.

Reuse the same request ID and unchanged fields after a timeout or uncertain response. Identical retries return the original decision plus `current_status`; conflicting reuse fails. Without a request ID, each CLI submission is a new decision. Timestamps must be finite and within the artifact's duration. Missing artifacts, changed bytes and stale hashes fail without recording approval.

New decisions and retry records are stored together in `motion.json` under `feedback_history`. Existing `reviews/*.json` history remains intact. Cooperating CLI/MCP writers use a project lock and atomic manifest replacement. Locks cover render/assembly too, so feedback can wait for a long render. Use local macOS/Linux filesystems; concurrent manual manifest edits, external media overwrites and network-filesystem locking are outside this guarantee.

## Optional local MCP and inline review

The CLI remains standard-library only. Install the adapter separately in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[mcp]'
```

Use absolute paths to the virtual environment executable and project below. The shared skill can still be installed with `install.py`; that script does not install MCP dependencies.

```sh
claude mcp add --transport stdio pocket-studio -- /absolute/path/.venv/bin/pocket-studio-mcp --project /absolute/path/film
```

This local stdio command configures the optional adapter for Claude Code. No additional model login or account pairing is needed. Each process is bound to one configured project; tools cannot choose another root or execute commands.

Tools:

- `project_inspect`: manifest and stable IDs, with current artifact-byte validation.
- `review_show`: `{"ids":["render-ID"]}` or a selected pair of IDs; returns version identity, hashes, persisted status and local `file_uri` targets.
- `feedback_submit`: `id`, `sha256`, `decision` (`approve`/`revise`), `time`, `note`, `author` (`human`), and `request_id`. Returns the authoritative persisted decision and current status. CLI feedback uses the same core operation.

Text-only hosts can open the returned file in a local player, collect human feedback and submit it directly. Rendering and assembly remain CLI operations. Diagnostics use stderr; stdout is exclusively MCP protocol traffic.

### Experimental inline player

Add `--inline` to the server command to enable the optional component. The server attaches `_meta.ui.resourceUri` only to `review_show`, and only when the client advertises `io.modelcontextprotocol/ui` with `text/html;profile=mcp-app`. The `ui://pocket-studio/review` resource uses the official MCP Apps bridge, bundled locally with no runtime CDN dependency.

The player has native video/audio controls, seeking and a time display, A/B selection, a timestamped note, and explicit revision/approval buttons. Buttons capture the active player's current position. Saving, persisted state and submission errors are visible; failed submissions never display success. Native controls, labeled fields and buttons support keyboard operation. Host style variables and size notifications use the standard bridge.

Media uses a session-only `127.0.0.1` server with a random port and opaque URLs for selected registered artifacts. It validates current hashes, supports single byte ranges/HEAD, rejects unregistered paths and traversal, and closes on stdio shutdown or termination. URLs are local bearer capabilities: do not share them. No directory listing, upload, remote storage or public binding is provided. Movies are never embedded in model-visible tool JSON. CSP metadata declares only this loopback media origin.

**Host verification remains required.** Protocol and Chromium tests do not establish Claude Code embedded-player compatibility. Claude Code is the supported driver; use the local player and direct feedback as the baseline review flow. Terminal MCP support alone does not imply inline UI support. A cloud/remote host's iframe may not reach your machine's loopback endpoint; a host can also reject the media origin through CSP, mixed-content or local-network rules. Use the file/player and direct-feedback fallback if the view or media is unavailable. Do not expose the loopback server publicly to work around this.

Before relying on inline review in a particular local host, check that it advertises the extension, renders the view, plays video and audible sound, seeks, changes A/B versions, captures the correct timestamp, persists a decision, and displays an error after bytes change. Human evaluation of creative quality remains separate.

The optional inline resource retains the MCP Apps protocol implementation. This package ships a Claude Code skill and optional local stdio adapter, not a plugin marketplace manifest or remote service. Inline support is experimental and must be detected; the CLI, files and direct feedback do not depend on it.

## Project format and CLI output

`motion.json` stores the project format, source inventory, render records and cuts. `sources/`, `renders/`, `cuts/` and `reviews/` hold their files. Keep the whole folder for a portable handoff. New projects ignore those media directories in Git by default; decide explicitly which source files and authored assets to version.

Commands return JSON:

```json
{"ok": true, "data": {"project": "/path/to/film"}}
```

Runtime failures exit with status 1:

```json
{"ok": false, "error": {"type": "ValueError", "message": "Project already exists; refusing to overwrite"}}
```

`--json` before the command selects the same stable output contract. Help and argument errors use normal CLI text and exit codes. `inspect` returns the full manifest, including source and artifact IDs.

## Current limits

There is no render queue, remote MCP server, provider integration, authenticated review service or autonomous creative director. No files are uploaded. External asset generation and model use stay with the host agent and its configured tools. A renderer command may itself access the network; Pocket Studio does not isolate it.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Media tests require FFmpeg and ffprobe. Tests use generated fixtures in temporary directories.

For the full protocol and browser suite:

```sh
python -m pip install '.[mcp,test]'
npm --prefix ui ci
npm --prefix ui run build
python -m playwright install chromium
python -m unittest discover -s tests -v
```

Set `POCKET_CHROMIUM` to an installed Chrome/Chromium executable with H.264 and AAC support if needed. CI explicitly uses the runner's full Google Chrome; codec support is asserted before playback rather than skipping media checks. The browser harness uses the official host bridge, enforced media CSP, and the real stdio adapter. It checks video/audio decoding, seeking, A/B selection, timestamp capture, persistence and failed submission. It is not a real-host compatibility test. `ui/` contains editable source and a lockfile; the generated packaged HTML includes the bridge so end users do not need Node. Rebuild and commit it when changing the UI.

## License

MIT. See [LICENSE](LICENSE).

## Managed projects (additive foundation)

```sh
pocket-studio init --title 'Product film'
pocket-studio projects list
pocket-studio projects open project-ID
pocket-studio init --home /path/to/studio --title 'Another film'
pocket-studio projects --home /path/to/studio list
pocket-studio projects register ./existing-film
```

The default home is `~/.pocket-studio`; `POCKET_STUDIO_HOME` overrides it and an
explicit `--home` takes precedence. A managed init creates
`projects/project-ID/motion.json`, BRIEF.md and TREATMENTS.md and records the stable
project ID/path/title in `registry.json`. `open` verifies identity and returns the
path; it does not change your shell directory or launch an application. Pass that
path to existing commands' `--project` argument. Missing projects remain listed
with `available: false`; no entry or file is automatically deleted.

`init ./film --title 'Film'` still creates a portable standalone project, without
writing the registry. Add `--home PATH` to register it in that home, or explicitly
use `projects register`. Registering an old project adds a project ID but moves no
files. Repeated registration is idempotent. Copies with the same ID at a different
path are rejected rather than silently relocating the project. Home and project
locks serialize cooperating local writers. Registry and project writes are atomic
individually; interrupted registration can be retried. They are not a distributed
transaction, and manual concurrent edits or network filesystems are unsupported.

Existing `sources/source-ID` are retained originals/assets, and immutable
`renders/render-ID` and `cuts/cut-ID` are takes/versions with hashes. There is no
second revision scheme. Keep authored scene code, specifications and notes in the
project. No disposable cache manager, automatic migration, synchronization, or
cleanup is introduced. Preserve the entire directory for handoff.

## Host-observed destination binding (no upload transport)

The CLI cannot see Claude Code session tools. The host agent discovers exposed connectors,
checks authentication, resolves a specific account/folder, and checks upload
permission. It supplies a **non-secret assertion** of those observations. The CLI
validates and pins it locally; it does not independently authenticate the assertion.
Google Drive and Dropbox provider labels currently share this same fixture-tested
contract. Neither has a working upload integration here.

Example receipt schema (replace IDs and timestamps with actual host observations;
this dated illustration will expire):

```json
{
  "schema_version": 1,
  "provider": "google_drive",
  "host": "claude-code",
  "status": "ready",
  "account_id": "account-ID",
  "folder_id": "folder-ID",
  "can_upload": true,
  "observed_at": "2026-10-29T10:00:00Z",
  "expires_at": "2026-10-29T11:00:00Z"
}
```

```sh
pocket-studio destination bind --project /path/to/film --receipt ./observation.json
pocket-studio destination status --project /path/to/film
```

A ready observation must be current, timezone-aware, and expire within 24 hours
of observation. `account_id`, `folder_id`, and `host` accept 1–200 ASCII letters,
digits and `_.:@-`; other ID formats are currently unsupported. `can_upload` must
be boolean true, based on explicit host capability/permission checks. A readable
folder alone is insufficient. Repeating an identical observation returns the same
binding; a new observation replaces the current binding. Failed binds leave the
previous binding intact. Status reports expiry without deleting the binding.
Binding never transfers files; local originals remain the working copy.

A host can instead submit `{ "schema_version": 1, "provider": "google_drive",
"status": "auth_required" }` to receive a stable error code and relay the setup
requirement. Supported failure statuses are `missing_connector`, `auth_required`,
`account_selection`, `permission_denied`, `network_error`, `stale_observation`,
`unsupported_host`, and `uncertain_transfer`. The last is reserved for future
transport reconciliation; no transfers occur today. Invalid schema and providers
return `invalid_observation` and `unsupported_provider`. No rejected receipt values
or unknown field names are echoed. Unknown fields are rejected. Only supply
non-secret identifiers: validation cannot detect a secret deliberately placed in
an allowed identifier field. Raw tool responses, signed URLs, keys and tokens must
never enter this interface. Future direct-provider BYOK support must use credential
references rather than stored secret values; no credential input is accepted now.

The existing project-scoped MCP `project_inspect` returns the same persisted project
ID and destination metadata. Registration and binding are CLI operations; no new
MCP account discovery or transport tools are claimed.

## Deferred buildout and local retest

The production infrastructure includes the merged headless-review, managed-storage and evidence helpers. It does not implement
contact sheets, automatic transcription/forced alignment,
render dependency snapshots, a current-take pointer, targeted rebuilds, remote
transfers or provider clients. Existing source references and immutable artifact
hashes remain available; they are not an incremental-render cache.

When back at the laptop: install the reviewed wheel/skill in a test environment,
create a temporary managed project, register an existing disposable project, and
verify list/open, render, inspect and actual owner feedback. Configure the optional
MCP adapter against that returned project path, verify CLI/MCP manifest parity and
review fallback, then test actual Claude Code tool discovery. Exercise optional
image or audio connectors only if exposed and authorized; verify the code-only path
works without them. Test inline playback, sound, seeking and failure feedback in the real host
before relying on it. Real connector authentication, folder permissions and upload
transport E2E tests remain separate; fixture success does not establish them.

## Cue-relative frame evidence

Capture frames against an existing render, cut, or registered video source. Supply
its ID and expected hash from `inspect`, plus a small capture spec:

```json
{
  "cues": [
    {"name": "opening", "start": 0, "end": 1},
    {"name": "approval", "start": 1, "end": 2}
  ],
  "captures": [
    {"cue": "opening", "anchor": "start", "offset": 0.25},
    {"cue": "approval", "anchor": "end", "offset": -0.1}
  ]
}
```

```sh
pocket-studio evidence capture --project PATH --id render-ID --sha256 SHA256 --spec cues.json
pocket-studio evidence inspect --project PATH --id evidence-ID
```

Cues are explicit named spans in seconds, ordered and non-overlapping. Gaps are
allowed. Names are unique ASCII letters/digits/underscores/hyphens (1–80 characters).
Capture times are relative to cue start or end, must lie inside the cue, and are
never silently clamped. Limits: 1–1000 cues and 1–100 captures per request.
The helper decodes from the beginning and selects the first video frame at or
after each requested time. This prioritizes reproducible timing over fast seeks.
It records both requested and decoded timestamps, relative to the first decoded
video frame, and rejects a frame that would land outside the cue. Capture PNGs
are scaled to at most 960 pixels wide. This is a frame helper, not a contact-sheet
layout engine or a replacement for watching motion and hearing sound.

Each request creates a fresh `evidence/evidence-ID` containing the request and
frames. Hashes of those files, the target ID/hash and timestamps are stored in the
manifest and attached via `evidence_refs` to the existing source/render/cut record.
Original media is rehashed before attachment; existing evidence is never overwritten.
Failed captures can leave unregistered files for diagnosis; no cleanup deletes
originals. `evidence inspect` revalidates the target and evidence files. The ordinary
CLI/MCP project inspection returns evidence metadata but does not rehash evidence
files: use `evidence inspect` before relying on them. Manifest hashes provide change
detection, not authentication against a caller who edits both files and manifest.
Capture status is **not visually inspected**. An agent must actually view the frames
and inspect other relevant modalities before reporting a creative hypothesis.

## Transcript evidence and separate timing validation

This helper accepts a transcript extracted from actual recorded audio by an
available host transcription tool. It does not call any transcription provider.
Keep the intended script separate from the raw tool result. The host supplies a
normalized spec, asserting which tool produced the raw result and which exact
media bytes were transcribed:

```json
{
  "schema_version": 1,
  "method": "audio_transcription",
  "tool": "your-exposed-transcription-tool",
  "media_sha256": "SHA256_OF_REGISTERED_AUDIO_OR_VIDEO",
  "raw_sha256": "SHA256_OF_RAW_TRANSCRIPTION_FILE",
  "text": "Click approve then type go go.",
  "segments": [
    {"start": 0, "end": 1, "text": "Click approve"},
    {"start": 1, "end": 2, "text": "then type go go."}
  ]
}
```

```sh
pocket-studio transcript compare --project PATH --id source-ID --sha256 SHA256 \
  --script original-script.txt --raw raw-transcription.json --spec transcript.json
pocket-studio evidence inspect --project PATH --id evidence-ID
```

Use a registered voice source or an exact rendered artifact containing audio.
The first audio stream must have a positive finite duration in ffprobe metadata;
containers without that information are currently rejected instead of guessing
from a longer video track. Timing is relative to that audio stream's start. The
helper retains exact script bytes, raw transcription bytes, normalized transcript,
provenance and hash-bound results in a fresh evidence directory. It rejects stale
media/raw hashes, a script reused as the raw input file (including hard links),
unsupported fields and nonfinite timestamps. Provenance and normalization remain
**caller asserted**, not independently authenticated; a valid receipt cannot prove
that the host really transcribed audio or normalized its tool output faithfully.
Never use an intended script as observed transcript evidence.

Text comparison casefolds Unicode and compares alphanumeric words, ignoring
punctuation. It returns explicit insert/delete/replace ranges and intended/observed
words, with no quality score or acceptance threshold. `words_equal` says nothing
about timing, intonation, emphasis, audibility or creative quality. Repeated words
are not timing anchors; text diff alignment never infers cue times.

Optional segments are checked independently for positive duration, audio bounds,
ordering/overlap, and consistency of segment text with the full transcript. Missing
segments report `not_provided`. Well-formed but out-of-bounds or overlapping timing
is retained with `timing.status: invalid` and explicit issues, even when every word
matches. A successful CLI command means evidence was recorded, not that timing or
content passed. `valid` means only those structural checks passed; it is not forced
alignment against the audio. Limits are 200,000 characters each for script and
transcript, 5,000 words per input, and 10,000 segments. No creative approval or automatic revision occurs.

Local retest additions: capture frames around a known cue, open the returned PNGs,
check decoded timestamps against playback, and submit a real transcription-tool
result for a disposable audio take. Verify a changed artifact or raw transcript
hash is rejected and incorrect timing remains visible even with correct words.
