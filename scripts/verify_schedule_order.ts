import { groupByCountryLeague } from '../lib/fc/grouping';

const BASE = process.env.FC_BASE ?? 'http://localhost:8000';
const PAGE = 200;

async function main() {
  let all: any[] = [];
  let offset = 0;
  let total = Infinity;
  while (all.length < total) {
    const res = await fetch(`${BASE}/api/fc/matches?limit=${PAGE}&offset=${offset}`);
    const body: any = await res.json();
    total = body.pagination?.total ?? 0;
    if (!body.matches?.length) break;
    all = all.concat(body.matches);
    offset += body.matches.length;
  }
  const groups = groupByCountryLeague(all);
  console.log('total matches:', all.length);
  console.log('sections:', groups.length);
  for (const g of groups.slice(0, 8)) {
    console.log(`- ${g.featured ? '⭐ ' : ''}${g.country} (${g.total})`);
    for (const l of g.leagues.slice(0, 6)) console.log(`    ${l.league}: ${l.matches.length}`);
  }
}

main();