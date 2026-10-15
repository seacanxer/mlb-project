import { fcGet } from './client';
import type { DetailedMatch, MatchesResponse } from './types';

// One 500-match page is ~75 MB of JSON and takes ~27 s through the Cloudflare
// tunnel, which exceeds the 15 s client timeout and aborts with
// "Request timed out, try again." Keep pages small enough to land well inside
// the fetch timeout, render the first page immediately, and stream the rest.
const PAGE = 100;
const MAX_CONCURRENT = 2;
const PAGE_TIMEOUT_MS = 45000;

export async function fetchAllMatches(
  onInitial?: (rows: DetailedMatch[]) => void,
): Promise<DetailedMatch[]> {
  const first = await fcGet<MatchesResponse>(
    `/api/fc/matches?limit=${PAGE}&offset=0`,
    PAGE_TIMEOUT_MS,
  );
  const total = first.pagination?.total ?? first.matches.length;
  const all: DetailedMatch[] = [...first.matches];
  if (onInitial) onInitial([...all]);

  const offsets: number[] = [];
  for (let offset = PAGE; offset < total; offset += PAGE) offsets.push(offset);
  if (!offsets.length) return all;

  const pages: MatchesResponse[] = [];
  const merge = () =>
    [...all, ...[...pages]
      .sort((a, b) => (a.pagination?.offset ?? 0) - (b.pagination?.offset ?? 0))
      .flatMap((p) => p.matches)];

  let next = 0;
  const worker = async () => {
    while (next < offsets.length) {
      const offset = offsets[next++];
      pages.push(
        await fcGet<MatchesResponse>(
          `/api/fc/matches?limit=${PAGE}&offset=${offset}`,
          PAGE_TIMEOUT_MS,
        ),
      );
      if (onInitial) onInitial(merge());
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(MAX_CONCURRENT, offsets.length) }, worker),
  );
  return merge();
}
