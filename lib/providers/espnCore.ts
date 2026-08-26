import crypto from 'crypto';
import type { FreshnessState, ScheduledGame } from '@/lib/providers/interfaces';

const BASE = process.env.ESPN_CORE_API_BASE_URL || 'https://sports.core.api.espn.com';
const REQUEST_TIMEOUT_MS = 15_000;
const MAX_ATTEMPTS = 3;

export type FallbackProbableStarter = {
  gameId: string;
  side: 'home' | 'away';
  fullName: string;
  espnEventId: string;
  espnAthleteId: string;
};

export type FallbackProbableStarterResult = {
  provider: string;
  providerId: string;
  sourceIdentifier: string;
  retrievedAt: Date;
  season: number;
  sourceTimezone: string;
  rawChecksum: string;
  data: FallbackProbableStarter;
  freshnessState: FreshnessState;
  validationWarnings: string[];
};

async function fetchEspnJson(urlOrPath: string): Promise<any> {
  const url = urlOrPath
    .replace(/^http:\/\/sports\.core\.api\.espn\.com/i, BASE)
    .replace(/^https:\/\/sports\.core\.api\.espn\.com/i, BASE);
  const absoluteUrl = url.startsWith('http') ? url : `${BASE}${url}`;
  let lastError: unknown;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(absoluteUrl, {
        headers: { Accept: 'application/json', 'User-Agent': 'mlb-analytics/0.1' },
        cache: 'no-store',
        signal: controller.signal,
      });
      if (response.ok) return response.json();
      const error = new Error(`ESPN Core API error ${response.status}: ${absoluteUrl}`);
      if (response.status < 500 && response.status !== 429) throw error;
      lastError = error;
    } catch (error) {
      lastError = error;
    } finally {
      clearTimeout(timeout);
    }
    if (attempt < MAX_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, attempt * 250));
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

function checksum(data: unknown): string {
  return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
}

function normalizeName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function teamNameMatches(left: string, right: string): boolean {
  const a = normalizeName(left);
  const b = normalizeName(right);
  return a === b || a.includes(b) || b.includes(a);
}

function eventMatchesGame(event: any, game: ScheduledGame): boolean {
  const [awayName, homeName] = String(event.name ?? '').split(' at ');
  if (!awayName || !homeName) return false;
  const timeDelta = Math.abs(new Date(event.date).getTime() - game.startTimeUtc.getTime());
  return timeDelta <= 30 * 60 * 1000
    && teamNameMatches(awayName, game.awayTeamName)
    && teamNameMatches(homeName, game.homeTeamName);
}

async function mapLimit<T, R>(items: T[], limit: number, worker: (item: T) => Promise<R>): Promise<R[]> {
  const output = new Array<R>(items.length);
  let nextIndex = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      output[index] = await worker(items[index]);
    }
  });
  await Promise.all(workers);
  return output;
}

/**
 * Secondary probable-starter adapter. It is called only for sides that the
 * official MLB schedule and game feed still leave empty.
 */
export class EspnCoreProbableStarterProvider {
  async getMissingStarters(games: ScheduledGame[]): Promise<FallbackProbableStarterResult[]> {
    const missingGames = games.filter((game) =>
      !game.homeStarterPersonId || !game.homeStarterName
      || !game.awayStarterPersonId || !game.awayStarterName
    );
    if (missingGames.length === 0) return [];

    const date = missingGames[0].date;
    if (!missingGames.every((game) => game.date === date)) {
      throw new Error('ESPN starter fallback requires games from one slate date');
    }

    const dateKey = date.replace(/-/g, '');
    const indexPath = `/v2/sports/baseball/leagues/mlb/events?limit=100&dates=${dateKey}`;
    const index = await fetchEspnJson(indexPath);
    const events = await mapLimit(index.items ?? [], 4, (item: any) => fetchEspnJson(item.$ref));
    const results: FallbackProbableStarterResult[] = [];

    for (const game of missingGames) {
      const event = events.find((candidate) => eventMatchesGame(candidate, game));
      if (!event) continue;
      const competition = event.competitions?.[0];

      for (const side of ['home', 'away'] as const) {
        const alreadyPresent = side === 'home'
          ? game.homeStarterPersonId && game.homeStarterName
          : game.awayStarterPersonId && game.awayStarterName;
        if (alreadyPresent) continue;

        const competitor = competition?.competitors?.find((entry: any) => entry.homeAway === side);
        const probable = competitor?.probables?.find(
          (entry: any) => entry.name === 'probableStartingPitcher' && entry.athlete?.$ref
        );
        if (!probable) continue;

        const athlete = await fetchEspnJson(probable.athlete.$ref);
        const fullName = String(athlete.fullName ?? athlete.displayName ?? '').trim();
        if (!fullName || !athlete.id) continue;

        const normalized: FallbackProbableStarter = {
          gameId: game.gameId,
          side,
          fullName,
          espnEventId: String(event.id),
          espnAthleteId: String(athlete.id),
        };
        results.push({
          provider: 'espn-core-api',
          providerId: `${event.id}:${side}:${athlete.id}`,
          sourceIdentifier: String(event.$ref ?? `${BASE}${indexPath}`),
          retrievedAt: new Date(),
          season: game.season,
          sourceTimezone: 'America/New_York',
          rawChecksum: checksum({ eventId: event.id, competitor, probable, athlete }),
          data: normalized,
          freshnessState: 'fresh',
          validationWarnings: ['PROBABLE_STARTER_FALLBACK_ESPN_CORE'],
        });
      }
    }

    return results;
  }
}
