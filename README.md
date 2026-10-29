# Pocket Studio

Local production tools for coding agents making motion graphics and product videos.

Use Claude Code or Codex to direct and author a film from decks, visualisations, screenshots and screen recordings. Pocket Studio keeps the sources, render versions, edits and human feedback together. It works with your existing agent session: no additional model login, subscription pairing or hosted service is required.

Pocket Studio is an early CLI, not an automatic video generator. You choose the creative direction and rendering tools. It provides the production steps around them:

- Import reference files, extract PDF text and page images, and inspect recorded media.
- Run an explicit renderer command and retain its output and logs.
- Trim and join authored shots and recordings, preserving audio and optionally mixing music.
- Compare versions in a local playback page and record timestamped human feedback.
- Carry the same project between Claude Code and Codex through a companion skill.

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
python3 install.py --skills both
```

This installs an editable `pocket-studio` launcher in `~/.local/bin` and a companion skill in both `~/.claude/skills/pocket-studio` and `~/.codex/skills/pocket-studio`. Keep the checkout in place. If needed, add `~/.local/bin` to your shell's PATH. Start a new agent session to discover the skill.

Use `--skills claude`, `--skills codex`, or `--skills none` to select the installation target. The installer refuses to overwrite an unrelated command or a differing existing skill.

Alternatively, install the CLI with `pip install .` in your Python environment and copy `skills/pocket-studio` to your host's skills directory.

```sh
pocket-studio --json doctor
pocket-studio --help
```

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
codex mcp add pocket-studio -- /absolute/path/.venv/bin/pocket-studio-mcp --project /absolute/path/film
```

These local stdio commands follow the official [Claude Code MCP setup](https://code.claude.com/docs/en/mcp) and [Codex MCP setup](https://developers.openai.com/codex/mcp). No additional model login or account pairing is needed. Each process is bound to one configured project; tools cannot choose another root or execute commands.

Tools:

- `project_inspect`: manifest and stable IDs, with current artifact-byte validation.
- `review_show`: `{"ids":["render-ID"]}` or a selected pair of IDs; returns version identity, hashes, persisted status and local `file_uri` targets.
- `feedback_submit`: `id`, `sha256`, `decision` (`approve`/`revise`), `time`, `note`, `author` (`human`), and `request_id`. Returns the authoritative persisted decision and current status. CLI feedback uses the same core operation.

Text-only hosts can open the returned file in a local player, collect human feedback and submit it directly. Rendering and assembly remain CLI operations. Diagnostics use stderr; stdout is exclusively MCP protocol traffic.

### Experimental inline player

Add `--inline` to the server command to enable the optional component. The server attaches `_meta.ui.resourceUri` only to `review_show`, and only when the client advertises `io.modelcontextprotocol/ui` with `text/html;profile=mcp-app`. The `ui://pocket-studio/review` resource uses the official MCP Apps bridge, bundled locally with no runtime CDN dependency.

The player has native video/audio controls, seeking and a time display, A/B selection, a timestamped note, and explicit revision/approval buttons. Buttons capture the active player's current position. Saving, persisted state and submission errors are visible; failed submissions never display success. Native controls, labeled fields and buttons support keyboard operation. Host style variables and size notifications use the standard bridge.

Media uses a session-only `127.0.0.1` server with a random port and opaque URLs for selected registered artifacts. It validates current hashes, supports single byte ranges/HEAD, rejects unregistered paths and traversal, and closes on stdio shutdown or termination. URLs are local bearer capabilities: do not share them. No directory listing, upload, remote storage or public binding is provided. Movies are never embedded in model-visible tool JSON. CSP metadata declares only this loopback media origin.

**Host verification remains required.** Protocol and Chromium tests do not establish Claude Code, Codex, Claude Desktop or ChatGPT embedded-player compatibility. Terminal MCP support alone does not imply inline UI support. A cloud/remote host's iframe may not reach your machine's loopback endpoint; a host can also reject the media origin through CSP, mixed-content or local-network rules. Use the file/player and direct-feedback fallback if the view or media is unavailable. Do not expose the loopback server publicly to work around this.

Before relying on inline review in a particular local host, check that it advertises the extension, renders the view, plays video and audible sound, seeks, changes A/B versions, captures the correct timestamp, persists a decision, and displays an error after bytes change. Human evaluation of creative quality remains separate.

Standards and packaging references: [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview), [OpenAI UI integration](https://developers.openai.com/plugins/build/chatgpt-ui), and [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins). This slice ships local stdio configuration and a shared skill, not host-specific plugin manifests or a remote service.

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
