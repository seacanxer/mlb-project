import { chromium } from 'playwright';

const url = process.argv[2] || 'https://fc.texasdrill.me/fc';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 2000 } });
await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
await p.waitForTimeout(7000);

const title = await p.title();
const h1 = await p.$eval('h1', (e) => e.textContent.trim()).catch(() => '(no h1)');
const navLinks = await p.$$eval('nav a', (els) =>
  els.map((e) => `${(e.textContent || '').trim()} [${e.getAttribute('href')}][${e.className}]`),
);
const body = ((await p.textContent('body')) || '').replace(/\s+/g, ' ').trim();
const emptyTitle = await p.$eval('.fc-empty h3, .fc-empty-title, .empty-title', (e) => e.textContent.trim()).catch(() => '(no empty title el)');

console.log('URL:', url);
console.log('TITLE:', title);
console.log('H1:', h1);
console.log('NAV_LINKS:', JSON.stringify(navLinks, null, 1));
console.log('EMPTY_TITLE:', emptyTitle);
console.log('BODY_SNIPPET:', body.slice(0, 700));
await b.close();