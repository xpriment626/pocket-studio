import { App, applyHostStyleVariables } from '@modelcontextprotocol/ext-apps';
const app = new App({name:'Pocket Studio review',version:'0.1.0'});
const el = id => document.getElementById(id);
const player = el('player');
let versions = [], busy = false, pending = null;
const active = () => versions[Number(el('version').value)];
function controls() {
  el('version').disabled = busy || !versions.length;
  for (const id of ['revise','approve']) el(id).disabled = busy || !versions.length || !Number.isFinite(player.duration);
  el('note').disabled = busy;
}
function select() {
  player.pause();
  const item = active();
  el('identity').textContent = `${item.label} · ${item.id} · SHA-256 ${item.sha256}`;
  el('approval').textContent = `Persisted state: ${item.creative_status}`;
  el('media-error').textContent = '';
  player.src = item.media_url || '';
  el('status').textContent = 'Review motion and sound before deciding.';
  controls();
}
app.ontoolresult = result => {
  if (busy) return;
  const data = result.structuredContent;
  if (!data?.versions) return;
  versions = data.versions;
  el('version').replaceChildren(...versions.map((item,i) => new Option(`${i ? 'B' : 'A'} — ${item.label}`,String(i))));
  select();
};
app.onhostcontextchanged = context => {
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
  if (context.theme) document.documentElement.style.colorScheme = context.theme;
};
el('version').onchange = select;
player.ontimeupdate = () => el('clock').textContent = `${player.currentTime.toFixed(2)} / ${Number.isFinite(player.duration) ? player.duration.toFixed(2) : '…'} s`;
player.onloadedmetadata = controls;
player.onerror = () => {
  el('media-error').textContent = 'Media unavailable in this host. Open the file_uri from review_show in a local player and submit feedback through CLI or MCP.';
  controls();
};
async function submit(decision) {
  const item = active();
  if (!item || busy) return;
  player.pause();
  const fields = {id:item.id,sha256:item.sha256,decision,time:player.currentTime,note:el('note').value,author:'human'};
  const key = JSON.stringify(fields);
  // Preserve request ID after an ambiguous failure; edited feedback is a new request.
  if (!pending || pending.key !== key) pending = {key, request_id:Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2,'0')).join('')};
  busy = true; controls(); el('status').textContent = 'Saving…';
  try {
    const result = await app.callServerTool({name:'feedback_submit',arguments:{...fields,request_id:pending.request_id}});
    if (result.isError) throw new Error(result.content?.map(x=>x.text || '').join(' ') || 'Submission rejected');
    const saved = result.structuredContent;
    if (!saved || saved.artifact !== item.id || saved.sha256 !== item.sha256) throw new Error('No authoritative saved state returned');
    item.creative_status = saved.current_status;
    el('approval').textContent = `Persisted state: ${saved.current_status}`;
    el('status').textContent = `Saved ${saved.id} at ${fields.time.toFixed(2)} s`;
    pending = null;
  } catch (error) {
    el('status').textContent = `Could not confirm save: ${error.message}. Retry unchanged feedback to reconcile.`;
  } finally {busy = false; controls();}
}
el('revise').onclick = () => submit('revise');
el('approve').onclick = () => submit('approve');
app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx?.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
}).catch(error => {el('status').textContent = `Host connection failed: ${error.message}. Use CLI feedback.`;});
