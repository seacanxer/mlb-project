import { chromium } from 'playwright';

const b = await chromium.launch();
const p = await b.newPage();
const responses = [];
p.on('response', (r) => {
  if (r.url().includes('/_next/static/chunks/app/fc/page-')) responses.push(r.url());
});
await p.goto('https://fc.texasdrill.me/fc', { waitUntil: 'domcontentloaded', timeout: 60000 });
await p.waitForTimeout(6000);
const btn = await p.$('button.btn-primary');
const label = btn ? (await btn.textContent()).trim() : '(none)';
const disabled = btn ? await btn.isDisabled() : null;
const body = ((await p.textContent('body')) || '').replace(/\s+/g, ' ');
console.log('HYDRATED BUTTON:', JSON.stringify(label), '| disabled:', disabled);
console.log('HAS_PICKS:', body.includes('pick lolos gate'));
console.log('PAGE_CHUNK:', responses.slice(0, 2));
await b.close();