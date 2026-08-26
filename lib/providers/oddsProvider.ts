/**
 * lib/providers/oddsProvider.ts
 *
 * Odds provider stub + manual CSV/JSON import.
 * When ODDS_PROVIDER is not configured, returns null and the UI shows
 * ODDS_PROVIDER_NOT_CONFIGURED. Never invents prices.
 */

import crypto from 'crypto';
import { z } from 'zod';
import { parseOddsToDecimal } from '@/lib/utils/odds';
import { OddsData, FreshnessState } from '@/lib/providers/interfaces';
import type { OddsProvider } from '@/lib/providers/interfaces';
import type { ScheduledGame } from '@/lib/providers/interfaces';

// ---------------------------------------------------------------------------
// Manual import Zod schemas
// ---------------------------------------------------------------------------

export const ManualOddsRow = z.object({
  gameId: z.string(),
  moneylineHomeOrig: z.string().optional(),
  moneylineAwayOrig: z.string().optional(),
  totalLine: z.coerce.number().optional(),
  totalOverOrig: z.string().optional(),
  totalUnderOrig: z.string().optional(),
});
export type ManualOddsRow = z.infer<typeof ManualOddsRow>;

export const ManualOddsPayload = z.array(ManualOddsRow);

// ---------------------------------------------------------------------------
// Stub provider
// ---------------------------------------------------------------------------

export class StubOddsProvider implements OddsProvider {
  isConfigured() {
    return false;
  }

  async getOdds(_gameId: string) {
    return null; // UI should show ODDS_PROVIDER_NOT_CONFIGURED
  }

  async importManual(payload: unknown): Promise<OddsData[]> {
    const rows = ManualOddsPayload.parse(payload);
    return rows.map((row) => parseManualRow(row));
  }
}

// ---------------------------------------------------------------------------
// Helper: parse one manual row
// ---------------------------------------------------------------------------

function safeDecimal(orig?: string): number | undefined {
  if (!orig) return undefined;
  try {
    return parseOddsToDecimal(orig);
  } catch {
    return undefined;
  }
}

export function parseManualRow(row: ManualOddsRow): OddsData {
  return {
    gameId: row.gameId,
    moneylineHome: safeDecimal(row.moneylineHomeOrig),
    moneylineAway: safeDecimal(row.moneylineAwayOrig),
    moneylineHomeOrig: row.moneylineHomeOrig,
    moneylineAwayOrig: row.moneylineAwayOrig,
    totalLine: row.totalLine,
    totalOverDecimal: safeDecimal(row.totalOverOrig),
    totalUnderDecimal: safeDecimal(row.totalUnderOrig),
  };
}

export function makeOddsResult(data: OddsData, raw: unknown) {
  return {
    provider: 'manual-import',
    providerId: data.gameId,
    sourceIdentifier: undefined as string | undefined,
    retrievedAt: new Date(),
    rawChecksum: crypto.createHash('sha256').update(JSON.stringify(raw)).digest('hex').slice(0, 16),
    data,
    freshnessState: 'fresh' as FreshnessState,
    validationWarnings: [] as string[],
  };
}

// ---------------------------------------------------------------------------
// The Odds API (optional, key-backed live provider)
// ---------------------------------------------------------------------------

const OddsApiOutcome = z.object({
  name: z.string(),
  price: z.number(),
  point: z.number().optional(),
});

const OddsApiMarket = z.object({
  key: z.string(),
  last_update: z.string().optional(),
  outcomes: z.array(OddsApiOutcome),
});

const OddsApiBookmaker = z.object({
  key: z.string(),
  title: z.string(),
  last_update: z.string(),
  markets: z.array(OddsApiMarket),
});

const OddsApiEvent = z.object({
  id: z.string(),
  commence_time: z.string(),
  home_team: z.string(),
  away_team: z.string(),
  bookmakers: z.array(OddsApiBookmaker),
});

const OddsApiResponse = z.array(OddsApiEvent);

const OneXbitMarket = z.object({
  G: z.coerce.number(),
  T: z.coerce.number(),
  P: z.coerce.number().nullish(),
  C: z.coerce.number().nullish(),
});

const OneXbitEvent = z.object({
  I: z.union([z.string(), z.number()]),
  L: z.string(),
  O1: z.string(),
  O2: z.string(),
  S: z.coerce.number(),
  E: z.array(OneXbitMarket).default([]),
});

const OneXbitResponse = z.object({
  Success: z.boolean(),
  Value: z.array(OneXbitEvent).default([]),
});

export type SlateOddsResult = ReturnType<typeof makeOddsResult> & {
  quoteUpdatedAt: Date;
};

export interface SlateOddsFetchResult {
  odds: SlateOddsResult[];
  warnings: string[];
  quotaRemaining?: string;
}

export class TheOddsApiProvider {
  private readonly apiKey: string;
  private readonly regions: string;
  private readonly bookmaker?: string;
  private readonly baseUrl: string;

  constructor(options?: { apiKey?: string; regions?: string; bookmaker?: string; baseUrl?: string }) {
    this.apiKey = options?.apiKey ?? process.env.ODDS_API_KEY ?? '';
    this.regions = options?.regions ?? process.env.ODDS_REGIONS ?? 'us';
    this.bookmaker = options?.bookmaker ?? (process.env.ODDS_BOOKMAKER || undefined);
    this.baseUrl = options?.baseUrl ?? process.env.ODDS_API_BASE_URL ?? 'https://api.the-odds-api.com';
  }

  isConfigured(): boolean {
    return Boolean(this.apiKey);
  }

  async getOddsForGames(games: ScheduledGame[]): Promise<SlateOddsFetchResult> {
    if (!this.apiKey) {
      return { odds: [], warnings: ['ODDS_API_KEY_MISSING'] };
    }
    if (games.length === 0) return { odds: [], warnings: [] };

    const times = games.map((game) => game.startTimeUtc.getTime());
    // The Odds API requires whole-second ISO timestamps and rejects the
    // millisecond component emitted by Date#toISOString().
    const oddsApiTimestamp = (value: number) => new Date(value).toISOString().replace(/\.\d{3}Z$/, 'Z');
    const from = oddsApiTimestamp(Math.min(...times) - 6 * 3600_000);
    const to = oddsApiTimestamp(Math.max(...times) + 6 * 3600_000);
    const query = new URLSearchParams({
      apiKey: this.apiKey,
      regions: this.regions,
      markets: 'h2h,totals',
      oddsFormat: 'decimal',
      dateFormat: 'iso',
      commenceTimeFrom: from,
      commenceTimeTo: to,
    });
    if (this.bookmaker) query.set('bookmakers', this.bookmaker);

    const response = await fetch(`${this.baseUrl}/v4/sports/baseball_mlb/odds/?${query}`, {
      headers: { Accept: 'application/json', 'User-Agent': 'mlb-analytics/0.1' },
      cache: 'no-store',
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) {
      const body = (await response.text()).slice(0, 300);
      throw new Error(`The Odds API error ${response.status}: ${body}`);
    }

    const raw = OddsApiResponse.parse(await response.json());
    const unused = new Set(raw.map((event) => event.id));
    const warnings: string[] = [];
    const odds: SlateOddsResult[] = [];

    for (const game of games) {
      const event = findMatchingEvent(game, raw.filter((candidate) => unused.has(candidate.id)));
      if (!event) {
        warnings.push(`ODDS_EVENT_NOT_FOUND:${game.gameId}`);
        continue;
      }
      unused.delete(event.id);

      const bookmaker = chooseBookmaker(event.bookmakers, this.bookmaker);
      if (!bookmaker) {
        warnings.push(`ODDS_MARKETS_NOT_FOUND:${game.gameId}`);
        continue;
      }

      const h2h = bookmaker.markets.find((market) => market.key === 'h2h');
      const totals = bookmaker.markets.find((market) => market.key === 'totals');
      const home = h2h?.outcomes.find((outcome) => sameTeam(outcome.name, game.homeTeamName));
      const away = h2h?.outcomes.find((outcome) => sameTeam(outcome.name, game.awayTeamName));
      const over = totals?.outcomes.find((outcome) => outcome.name.toLowerCase() === 'over');
      const under = totals?.outcomes.find((outcome) => outcome.name.toLowerCase() === 'under');
      const quoteUpdatedAt = newestMarketTime(bookmaker, h2h, totals);
      const normalized: OddsData = {
        gameId: game.gameId,
        moneylineHome: home?.price,
        moneylineAway: away?.price,
        moneylineHomeOrig: home?.price != null ? String(home.price) : undefined,
        moneylineAwayOrig: away?.price != null ? String(away.price) : undefined,
        totalLine: over?.point ?? under?.point,
        totalOverDecimal: over?.price,
        totalUnderDecimal: under?.price,
      };
      odds.push({
        ...makeOddsResult(normalized, { event, bookmaker: bookmaker.key }),
        provider: `the-odds-api:${bookmaker.key}`,
        providerId: event.id,
        quoteUpdatedAt,
      });
    }

    return {
      odds,
      warnings,
      quotaRemaining: response.headers.get('x-requests-remaining') ?? undefined,
    };
  }
}

/**
 * Optional unofficial odds adapter supplied by the user.
 *
 * The bundled Python is not executed. This adapter validates the payload,
 * restricts it to MLB, and matches both teams plus start time to MLB game IDs.
 */
export class OneXbitOddsProvider {
  private readonly domains: string[];

  constructor(options?: { domains?: string[] }) {
    this.domains = options?.domains
      ?? (process.env.ODDS_1XBIT_DOMAINS || 'https://1xbit.com')
        .split(',')
        .map((domain) => domain.trim().replace(/\/$/, ''))
        .filter(Boolean);
  }

  isConfigured(): boolean {
    return this.domains.length > 0;
  }

  async getOddsForGames(games: ScheduledGame[]): Promise<SlateOddsFetchResult> {
    if (games.length === 0) return { odds: [], warnings: [] };

    const { domain, events } = await this.fetchFeed();
    const mlbEvents = events.filter((event) => event.L.trim().toLowerCase() === 'usa. mlb');
    const unused = new Set(mlbEvents.map((event) => String(event.I)));
    const warnings: string[] = [];
    const odds: SlateOddsResult[] = [];

    for (const game of games) {
      const event = findOneXbitEvent(
        game,
        mlbEvents.filter((candidate) => unused.has(String(candidate.I)))
      );
      if (!event) {
        warnings.push(`ODDS_EVENT_NOT_FOUND:${game.gameId}`);
        continue;
      }
      unused.delete(String(event.I));

      const homeMoneyline = findOneXbitPrice(event.E, 1, 1);
      const awayMoneyline = findOneXbitPrice(event.E, 1, 3);
      const total = findOneXbitTotal(event.E);
      if (homeMoneyline === undefined || awayMoneyline === undefined) {
        warnings.push(`ODDS_MONEYLINE_INCOMPLETE:${game.gameId}`);
        continue;
      }
      if (!total) warnings.push(`ODDS_TOTAL_INCOMPLETE:${game.gameId}`);

      const normalized: OddsData = {
        gameId: game.gameId,
        moneylineHome: homeMoneyline,
        moneylineAway: awayMoneyline,
        moneylineHomeOrig: String(homeMoneyline),
        moneylineAwayOrig: String(awayMoneyline),
        totalLine: total?.line,
        totalOverDecimal: total?.over,
        totalUnderDecimal: total?.under,
      };
      const retrievedAt = new Date();
      odds.push({
        ...makeOddsResult(normalized, event),
        provider: '1xbit-linefeed-unofficial',
        providerId: String(event.I),
        sourceIdentifier: `${domain}/service-api/LineFeed/BestGamesExtZip?sports=5&count=60&lng=en&mode=4`,
        retrievedAt,
        quoteUpdatedAt: retrievedAt,
        validationWarnings: [
          'UNOFFICIAL_REVERSE_ENGINEERED_ODDS_SOURCE',
          'ODDS_QUOTE_TIMESTAMP_UNAVAILABLE',
        ],
      });
    }

    return { odds, warnings };
  }

  private async fetchFeed(): Promise<{ domain: string; events: z.infer<typeof OneXbitEvent>[] }> {
    const failures: string[] = [];
    for (const domain of this.domains) {
      const url = `${domain}/service-api/LineFeed/BestGamesExtZip?sports=5&count=60&lng=en&mode=4`;
      try {
        const response = await fetch(url, {
          headers: { Accept: 'application/json', 'User-Agent': 'Mozilla/5.0' },
          cache: 'no-store',
          signal: AbortSignal.timeout(15_000),
        });
        if (!response.ok) {
          failures.push(`${domain}:HTTP_${response.status}`);
          continue;
        }
        const parsed = OneXbitResponse.parse(await response.json());
        if (!parsed.Success || parsed.Value.length === 0) {
          failures.push(`${domain}:EMPTY`);
          continue;
        }
        return { domain, events: parsed.Value };
      } catch (error) {
        failures.push(`${domain}:${error instanceof Error ? error.message : String(error)}`);
      }
    }
    throw new Error(`Unofficial odds feed unavailable (${failures.join('; ')})`);
  }
}

function normalizeTeam(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function findOneXbitEvent(game: ScheduledGame, events: z.infer<typeof OneXbitEvent>[]) {
  const maximumStartDifferenceMs = 12 * 3600_000;
  return events
    .filter((event) => {
      // Verified feed convention: O1 is home and O2 is away.
      const teamsMatch = sameTeam(event.O1, game.homeTeamName) && sameTeam(event.O2, game.awayTeamName);
      const startDifference = Math.abs(event.S * 1000 - game.startTimeUtc.getTime());
      return teamsMatch && startDifference <= maximumStartDifferenceMs;
    })
    .sort((a, b) => (
      Math.abs(a.S * 1000 - game.startTimeUtc.getTime())
      - Math.abs(b.S * 1000 - game.startTimeUtc.getTime())
    ))[0];
}

function findOneXbitPrice(
  markets: z.infer<typeof OneXbitMarket>[],
  group: number,
  type: number
): number | undefined {
  const price = markets.find((market) => market.G === group && market.T === type)?.C;
  return price != null && price > 1 ? price : undefined;
}

function findOneXbitTotal(markets: z.infer<typeof OneXbitMarket>[]) {
  const totals = new Map<number, { over?: number; under?: number }>();
  for (const market of markets) {
    if (market.G !== 17 || market.P == null || market.C == null || market.C <= 1) continue;
    const pair = totals.get(market.P) ?? {};
    if (market.T === 9) pair.over = market.C;
    if (market.T === 10) pair.under = market.C;
    totals.set(market.P, pair);
  }
  const complete = [...totals.entries()].filter(([, pair]) => pair.over != null && pair.under != null);
  if (complete.length !== 1) return undefined;
  const [line, pair] = complete[0];
  return { line, over: pair.over, under: pair.under };
}

function sameTeam(left: string, right: string): boolean {
  const a = normalizeTeam(left);
  const b = normalizeTeam(right);
  return a === b || a.endsWith(b) || b.endsWith(a);
}

function findMatchingEvent(game: ScheduledGame, events: z.infer<typeof OddsApiEvent>[]) {
  return events
    .filter((event) => sameTeam(event.home_team, game.homeTeamName) && sameTeam(event.away_team, game.awayTeamName))
    .sort((a, b) => {
      const aDiff = Math.abs(new Date(a.commence_time).getTime() - game.startTimeUtc.getTime());
      const bDiff = Math.abs(new Date(b.commence_time).getTime() - game.startTimeUtc.getTime());
      return aDiff - bDiff;
    })[0];
}

function chooseBookmaker(bookmakers: z.infer<typeof OddsApiBookmaker>[], preferred?: string) {
  if (preferred) return bookmakers.find((book) => book.key === preferred);
  return [...bookmakers]
    .filter((book) => book.markets.some((market) => market.key === 'h2h' || market.key === 'totals'))
    .sort((a, b) => {
      const marketCount = (book: typeof a) => Number(book.markets.some((market) => market.key === 'h2h'))
        + Number(book.markets.some((market) => market.key === 'totals'));
      return marketCount(b) - marketCount(a)
        || new Date(b.last_update).getTime() - new Date(a.last_update).getTime();
    })[0];
}

function newestMarketTime(
  bookmaker: z.infer<typeof OddsApiBookmaker>,
  ...markets: Array<z.infer<typeof OddsApiMarket> | undefined>
): Date {
  const timestamps = [bookmaker.last_update, ...markets.map((market) => market?.last_update).filter(Boolean) as string[]]
    .map((value) => new Date(value).getTime())
    .filter(Number.isFinite);
  return timestamps.length > 0 ? new Date(Math.max(...timestamps)) : new Date();
}
