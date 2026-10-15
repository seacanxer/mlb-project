import { fcGet } from './client';
import type { DetailedMatch, MatchesResponse } from './types';

const PAGE = 500;
const MAX_CONCURRENT = 2;

export async function fetchAllMatches(): Promise<DetailedMatch[]> {
  const first = await fcGet<MatchesResponse>(`/api/fc/matches?limit=${PAGE}&offset=0`);
  const total = first.pagination?.total ?? first.matches.length;
  const all: DetailedMatch[] = [...first.matches];
  const offsets: number[] = [];
  for (let offset = PAGE; offset < total; offset += PAGE) offsets.push(offset);
  let next = 0;
  const pages: MatchesResponse[] = [];
  const worker = async () => {
    while (next < offsets.length) {
      const offset = offsets[next++];
      pages.push(await fcGet<MatchesResponse>(`/api/fc/matches?limit=${PAGE}&offset=${offset}`));
    }
  };
  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENT, offsets.length) }, worker));
  for (const page of pages.sort((a, b) => (a.pagination?.offset ?? 0) - (b.pagination?.offset ?? 0))) all.push(...page.matches);
  return all;
}