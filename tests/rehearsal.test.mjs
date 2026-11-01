// Real Chromium, real source callback, controlled service boundary; no live services.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { launch } from '../src/pocket_studio/rehearsal/scripts/browser.mjs'
import { Rehearsal } from '../src/pocket_studio/rehearsal/driver.mjs'
import { auditLayout, layoutResult } from '../src/pocket_studio/rehearsal/scripts/layout-core.mjs'
import { record, analyse } from '../src/pocket_studio/rehearsal/scripts/jumps-core.mjs'
import { instrumentationSource, coverage, reportResult } from '../src/pocket_studio/rehearsal/scripts/verification.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../src/pocket_studio/rehearsal')
const out = process.env.REHEARSAL_TEST_OUT || await mkdtemp(join(tmpdir(), 'pocket-rehearsal-'))
const allowed = new Set(['/fixture/index.html', '/fixture/contact-form.mjs', '/stage.css'])
const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname
  if (!allowed.has(path)) { res.writeHead(404).end(); return }
  res.setHeader('Content-Type', extname(path) === '.mjs' ? 'text/javascript' : extname(path) === '.css' ? 'text/css' : 'text/html')
  res.end(await readFile(join(root, path)))
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await launch()
try {
  const url = `http://127.0.0.1:${server.address().port}/fixture/index.html`
  for (const [take, width, fail, reduced] of [['wide', 1280, false, false], ['compact', 390, false, false], ['failure', 390, true, false], ['poster', 390, false, true]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: reduced ? 'reduce' : 'no-preference' })
    const errors = []; page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript({ content: instrumentationSource(record, '.ss-stage') })
    await page.goto(url)
    await page.waitForFunction(() => window.fixtureReady)
    const r = new Rehearsal(page, { out: join(out, take), provenance: {
      revision: 'repository fixture at tested source head', component: 'fixture/contact-form.mjs:mountContactForm',
      stateOwner: 'mountContactForm state', serviceBoundary: 'service.create', resetCommand: 'reload isolated fixture route'
    } })
    try {
      await r.beat('opening')
      await r.fill('input[name=name]', 'Ada Example', async p => assert.equal(await p.locator('input').inputValue(), 'Ada Example'))
      await r.click('button', async p => {
        await p.waitForFunction(() => window.requests.length === 1 && window.state.saving)
        assert.equal(await p.locator('[role=status]').textContent(), 'Saving')
        assert.equal(await p.locator('button').isDisabled(), true)
        assert.deepEqual(await p.evaluate(() => window.requests.map(r => r.input)), [{ name: 'Ada Example' }])
        assert.equal(await p.evaluate(() => window.persisted.length), 0)
        await r.beat('saving')
        await p.evaluate(fail => fail ? window.requests[0].reject() : window.requests[0].resolve(), fail)
        await p.waitForFunction(() => !window.state.saving)
        assert.equal(await p.locator('[role=status]').textContent(), fail ? 'Could not save contact' : 'Contact added')
        assert.equal(await p.evaluate(() => window.persisted.length), fail ? 0 : 1)
        assert.equal(await p.locator('li').count(), fail ? 0 : 1)
      })
      await r.beat(fail ? 'failure' : 'payoff')
      const layout = layoutResult([{ selector: '.ss-stage', ...await page.locator('.ss-stage').evaluate(auditLayout) }], errors, true)
      await writeFile(join(out, take, 'layout.json'), JSON.stringify(layout, null, 2))
      assert.equal(layout.errors.length, 0)
      assert.equal(layout.scopes.flatMap(s => s.findings).length, 0)
      await r.camera('h1', { scale: 1.1, duration: 150 })
      await r.beat('editorial-closeup')
      await page.waitForTimeout(400)
      const snapshot = await page.evaluate(() => { window.__ssVerification.stopped = true; return window.__ssVerification })
      const stages = Object.entries(snapshot.stages).map(([key, stage]) => ({ key, coverage: coverage(stage.frames), findings: analyse(stage.frames), manual: ['Camera/text changes require visual review'] }))
      const motion = reportResult({ stages, errors: snapshot.errors, strict: true })
      await writeFile(join(out, take, 'motion.json'), JSON.stringify(motion, null, 2))
      assert.ok(stages.length > 0)
      // Motion candidates are retained, not silently treated as approval.
      assert.deepEqual(errors, [])
      if (take === 'failure') {
        await assert.rejects(r.click('button', async () => false), /Outcome assertion failed/)
      }
    } finally {
      const result = await r.report()
      assert.equal(result.status, take === 'failure' ? 'incomplete' : 'assertions-passed')
      await page.close()
    }
  }
  // Exercise the actual vendored film entry point, not only imported QA cores.
  const film = await promisify(execFile)(process.execPath, [join(root, 'scripts/film.mjs'), url,
    '--width', '390', '--every', '100', '--count', '3', '--cols', '3',
    '--out', join(out, 'browser-contact-sheet.png'), '--report', join(out, 'film.json')], { timeout: 45000 })
    .catch(error => { if (error.code === 1 || error.code === 2) return error; throw error })
  assert.ok((await readFile(join(out, 'browser-contact-sheet.png'))).length > 100)
  const filmReport = JSON.parse(await readFile(join(out, 'film.json'), 'utf8'))
  assert.ok(filmReport.stages.length > 0)
  await writeFile(join(out, 'film.log'), film.stdout + film.stderr)
  console.log(`Source callback, saving/success/failure, reset, compact, camera, reduced-motion and QA smoke passed. Evidence: ${out}`)
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
