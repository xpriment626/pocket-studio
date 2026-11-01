// Editorial choreography around real Playwright input. No product-state setters.
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

export class Rehearsal {
  constructor(page, { out, provenance, stage = '.ss-stage' }) {
    for (const field of ['revision', 'component', 'stateOwner', 'serviceBoundary', 'resetCommand']) {
      if (typeof provenance?.[field] !== 'string' || !provenance[field].trim()) throw new Error(`Missing provenance: ${field}`)
    }
    this.page = page; this.out = out; this.provenance = provenance; this.stage = stage
    this.trace = []; this.beats = []; this.editorial = []; this.started = Date.now()
  }
  async action(kind, selector, value, verify) {
    if (typeof verify !== 'function') throw new Error('Every action requires an outcome assertion')
    const entry = { kind, selector, startedMs: Date.now() - this.started, status: 'failed' }
    this.trace.push(entry)
    try {
      const target = this.page.locator(selector)
      await target.waitFor({ state: 'visible' })
      if (await target.count() !== 1) throw new Error(`Ambiguous target: ${selector}`)
      const bounds = await target.boundingBox()
      if (!bounds) throw new Error(`No visible bounds: ${selector}`)
      entry.bounds = bounds
      await this.page.evaluate(() => {
        if (document.querySelector('[data-ps-pointer]')) return
        const pointer = document.createElement('div')
        pointer.dataset.psPointer = ''; pointer.className = 'ss-cursor'
        pointer.setAttribute('aria-hidden', 'true')
        pointer.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:24px;pointer-events:none;z-index:2147483647;visibility:hidden'
        pointer.innerHTML = '<svg viewBox="0 0 18 24"><path d="M1 1L1 20L6 15L10 23L13 21L9 14L16 14Z" fill="#111" stroke="white" stroke-width="1.5"/></svg>'
        document.body.append(pointer)
        document.addEventListener('mousemove', event => {
          pointer.style.transform = `translate(${event.clientX}px,${event.clientY}px)`
          pointer.style.visibility = 'visible'
        })
      })
      // Actual mouse input supplies hover handlers. Locators recheck actionability
      // and current bounds before the final input if layout changed meanwhile.
      await this.page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2, { steps: 18 })
      if (kind === 'click') await target.click()
      else if (kind === 'fill') await target.fill(value)
      else if (kind === 'press') await target.press(value)
      else throw new Error(`Unknown action: ${kind}`)
      if (await verify(this.page) === false) throw new Error(`Outcome assertion failed: ${selector}`)
      entry.status = 'verified'
    } catch (error) {
      entry.error = error.message
      throw error
    } finally {
      entry.endedMs = Date.now() - this.started
    }
  }
  click(selector, verify) { return this.action('click', selector, null, verify) }
  fill(selector, value, verify) { return this.action('fill', selector, value, verify) }
  press(selector, key, verify) { return this.action('press', selector, key, verify) }
  async beat(name) {
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(name) || this.beats.some(b => b.name === name)) throw new Error('Beat names must be unique safe identifiers')
    await mkdir(this.out, { recursive: true })
    const stage = this.page.locator(this.stage)
    await stage.evaluate((el, name) => { el.dataset.mark = name }, name)
    const file = `${String(this.beats.length).padStart(3, '0')}-${name}.png`
    await stage.screenshot({ path: join(this.out, file), animations: 'allow' })
    this.beats.push({ name, file, atMs: Date.now() - this.started, actionCount: this.trace.length })
  }
  async camera(selector, { scale = 1, duration = 500 } = {}) {
    if (!Number.isFinite(scale) || scale < 1 || scale > 4 || !Number.isFinite(duration) || duration < 0 || duration > 10000) throw new Error('Invalid editorial camera')
    const stage = this.page.locator(this.stage)
    const box = await stage.boundingBox(), focus = await this.page.locator(selector).boundingBox()
    if (!box || !focus) throw new Error('Camera needs visible measured bounds')
    await stage.locator('.ps-camera').evaluate(async (el, { box, focus, scale, duration }) => {
      el.classList.add('ss-camera')
      const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
      const current = new DOMMatrix(getComputedStyle(el).transform)
      const wrapper = el.getBoundingClientRect()
      const localX = (focus.x + focus.width / 2 - wrapper.x) / current.a
      const localY = (focus.y + focus.height / 2 - wrapper.y) / current.d
      const x = box.x + box.width / 2 - (wrapper.x - current.e) - localX * scale
      const y = box.y + box.height / 2 - (wrapper.y - current.f) - localY * scale
      const transform = `translate(${x}px,${y}px) scale(${scale})`
      const animation = el.animate([{ transform: getComputedStyle(el).transform }, { transform }], { duration: reduced ? 0 : duration, fill: 'forwards', easing: 'ease-in-out' })
      await animation.finished
      el.style.transform = transform; animation.cancel()
    }, { box, focus, scale, duration })
    this.editorial.push({ kind: 'camera', selector, scale, duration, endedMs: Date.now() - this.started })
  }
  async report() {
    await mkdir(this.out, { recursive: true })
    const report = { schema_version: 1, provenance: this.provenance, viewport: this.page.viewportSize(),
      actions: this.trace, beats: this.beats, editorial: this.editorial,
      status: this.trace.length && this.trace.every(a => a.status === 'verified') ? 'assertions-passed' : 'incomplete',
      limits: 'Fixture-backed input and caller assertions; no live integration or creative acceptance. Beat timestamps are rehearsal wall time, not encoded-video time.' }
    await writeFile(join(this.out, 'rehearsal.json'), JSON.stringify(report, null, 2) + '\n')
    return report
  }
}
