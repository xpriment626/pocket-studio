# Source-faithful rehearsal

Read the Pocket Studio skill's ui-production.md first. Mount the real product shell/components in your own capture route, with fixtures at its service boundary. No Stageshow faux controls or a.set() state swaps are included. This folder is optional; the CLI never runs npm or arbitrary scene code during setup.

1. `npm ci --ignore-scripts` (Node >=20.19). Install Chrome or set CHROME_PATH explicitly. Retain runtime, Chrome version, fonts, source revision/patch hashes, seed/clock, theme, viewport/density and setup/reset commands in ENVIRONMENT.md.
2. Wrap the actual UI with `.ps-stage.ss-stage` and `.ps-camera`; import stage.css. Use the actual product's responsive layout, tokens and type. Do not simplify or replace product controls to pass geometry checks.
3. Import `launch` from `./scripts/browser.mjs` and `Rehearsal` from `./driver.mjs` in a Playwright capture script. Supply provenance fields revision, component, stateOwner, serviceBoundary and resetCommand. Every click/fill/press requires an async outcome assertion; errors propagate and failed assertions remain in the trace. Call report() in finally so failures are retained too. For example:

```js
const r = new Rehearsal(page, { out: 'traces/take-1', provenance })
try {
  await r.beat('opening')
  await r.click('[data-target="save"]', async page => {
    await page.getByText('Saved', { exact: true }).waitFor()
    // Also assert actual requests/persistence at the fixture boundary.
  })
  await r.beat('saved')
} finally { await r.report() }
```

Playwright supplies actual mouse/keyboard input and actionability checks; it never sets application state to manufacture success. Bounds are measured on the mounted control. `camera(selector, {scale: 1.2})` animates only the editorial `.ps-camera` wrapper. Reset between takes through the application's documented reset boundary. A verifier is caller code, not authenticated proof. Trace the source handler/state/service chain in the project; provenance strings alone do not establish fidelity.

The synthetic `fixture/` is an executable example with a real submit callback and manually resolved transport, not a reconstruction of Atlas. The repository test `tests/rehearsal.test.mjs` exercises saving, success, failure and repeat reset. Import production React components in place of this fixture using the product's own build and locked dependencies.

## Inspect the mounted scene

Selected Stageshow scripts are vendored unchanged; revision and license are in UPSTREAM.md. No brand artwork is included.

```sh
node scripts/layout.mjs http://127.0.0.1:PORT/scene --width 1280 --report traces/layout-wide.json --screenshot traces/layout-wide.png --strict
node scripts/layout.mjs http://127.0.0.1:PORT/scene --width 390 --report traces/layout-compact.json --strict
node scripts/jumps.mjs http://127.0.0.1:PORT/scene --ms 4000 --report traces/motion.json --strict
node scripts/film.mjs http://127.0.0.1:PORT/scene --states --states-for 4000 --out traces/states.png --report traces/film.json
node scripts/film.mjs http://127.0.0.1:PORT/scene --reduced --still --out traces/poster.png
```

These URLs must point to YOUR configured capture route, with the actual flow driven from reset. A separate browser opened by a QA script does not inherit your other browser's state. Arrange capture through that route or import the core QA functions into your driver; do not mistake an idle page scan for interaction coverage. Beat marks use stage data-mark. For a reduced-motion poster, exercise the real flow to its payoff before taking the still; the driver does not synthesize the result state. No default short loop overrides narration timing.

Geometry checks produce candidates and manual-review obligations. Incomplete coverage stays inconclusive; do not hide findings by removing controls or marking an entire subtree data-snap. Review opening, payoff, busy transitions, every click and loop seam at actual output dimensions. Read same-box text/icon and camera omissions. Inspect actual motion and sound separately. Keep REHEARSAL.md with observed findings, intentional editorial cuts, inspected modalities, source action trace, state-to-frame mapping and remaining limitations. Technical checks never approve a film.

## Encode and retain evidence

film.mjs produces PNG stills/contact sheets, not MP4. Use your existing renderer/browser video capture and the explicit `pocket-studio render --spec ...` adapter to encode video. Register source references, source patch and trace assets. Then capture named cues against the exact encoded artifact/hash with `evidence capture`; `evidence sheet --project PATH --id evidence-ID` creates a PNG sheet plus timestamp-labeled HTML from those same decoded frames. Browser beat wall times are not encoded-video timestamps: retain and validate the mapping before deriving cues. `evidence inspect` rechecks media and frame/sheet hashes. Narration phrase timestamps remain the pacing authority.
