import { chromium } from 'playwright';

const url = process.argv[2] || 'https://fc.texasdrill.me/fc/schedule';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 2000 } });
await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(4000);

const heads = await p.$$eval('[class*="country-head"], [class*="league-head"], button', (els) =>
  els
    .map((e) => ({
      cls: e.className,
      text: (e.textContent || '').trim().slice(0, 60),
      expanded: e.getAttribute('aria-expanded'),
    }))
    .filter((x) => x.text.length > 0)
    .slice(0, 40),
);

const bodyText = (await p.textContent('body')) || '';
const topIdx = bodyText.indexOf('Top Leagues');
const eplIdx = bodyText.indexOf('Premier League');
console.log('URL:', url);
console.log('BODY_LEN:', bodyText.length);
console.log('TOP_IDX:', topIdx, 'EPL_IDX:', eplIdx);
console.log('JSON_HEADS:', JSON.stringify(heads, null, 1));
console.log('SNIPPET_TOP:', topIdx >= 0 ? bodyText.slice(topIdx, topIdx + 300) : '(not found)');
await b.close();