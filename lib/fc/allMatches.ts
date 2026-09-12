import { fcGet } from './client';
import type { DetailedMatch, MatchesResponse } from './types';

const PAGE = 200;

export async function fetchAllMatches(): Promise<DetailedMatch[]> {
  const first = await fcGet<MatchesResponse>(`/api/fc/matches?limit=${PAGE}&offset=0`);
  const total = first.pagination?.total ?? first.matches.length;
  const all: DetailedMatch[] = [...first.matches];
  let offset = all.length;
  let guard = 0;
  while (all.length < total && guard < 100) {
    const next = await fcGet<MatchesResponse>(`/api/fc/matches?limit=${PAGE}&offset=${offset}`);
    if (!next.matches.length) break;
    all.push(...next.matches);
    offset += next.matches.length;
    guard += 1;
  }
  return all;
}