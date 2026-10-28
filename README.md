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

- Python 3.10 or newer.
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

Open the returned `reviews/index.html` in a browser. If your browser restricts local media, serve the project on loopback:

```sh
python3 -m http.server 8768 --bind 127.0.0.1 --directory ./film
```

Then visit `http://127.0.0.1:8768/reviews/index.html`. Stop the server with Ctrl-C when finished.

The page provides video playback and a feedback form. A reviewer can select a version, enter a timestamp and note, choose approve or revise, and download a feedback JSON file:

```sh
pocket-studio feedback --project ./film --file ./motion-feedback.json
pocket-studio review --project ./film
```

Feedback applies to the exact artifact hash. Changed media requires a new review. Approval of one shot does not approve an assembled film. Human attribution is caller supplied, not authenticated identity; agents should import actual user feedback rather than invent approval. Technical validity alone does not establish creative quality.

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

Use one writer per project. There is no render queue, remote MCP server, provider integration, authenticated review service or autonomous creative director. No files are uploaded. External asset generation and model use stay with the host agent and its configured tools. A renderer command may itself access the network; Pocket Studio does not isolate it.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Media tests require FFmpeg and ffprobe. Tests use generated fixtures in temporary directories.

## License

MIT. See [LICENSE](LICENSE).
