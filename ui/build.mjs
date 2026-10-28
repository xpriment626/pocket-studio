import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
const result = await build({entryPoints:[new URL('./review.js',import.meta.url).pathname],bundle:true,write:false,format:'esm',minify:true,legalComments:'inline'});
const template = await readFile(new URL('./review.html',import.meta.url),'utf8');
await writeFile(new URL('../src/pocket_studio/ui/review.html',import.meta.url), template.replace('/* BUNDLE */',()=>result.outputFiles[0].text.replaceAll('</script','<\\/script')));
// Preserve the licenses of dependencies bundled into the offline resource.
const packages = ['@modelcontextprotocol/client','@modelcontextprotocol/core','@modelcontextprotocol/ext-apps','zod','pkce-challenge','eventsource-parser','eventsource','jose'];
let licenses = 'Third-party software bundled in review.html\n';
for (const name of packages) {
  const base = new URL(`./node_modules/${name}/`,import.meta.url);
  const metadata = JSON.parse(await readFile(new URL('package.json',base),'utf8'));
  let license;
  for (const filename of ['LICENSE','LICENSE.md','LICENSE.txt']) {
    try {license = await readFile(new URL(filename,base),'utf8'); break;} catch {}
  }
  if (!license) throw new Error(`Missing license for ${name}`);
  licenses += `\n--- ${name} ${metadata.version} ---\n${license}\n`;
}
await writeFile(new URL('../src/pocket_studio/ui/THIRD_PARTY_LICENSES.txt',import.meta.url),licenses);
