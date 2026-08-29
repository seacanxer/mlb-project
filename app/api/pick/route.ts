import { NextRequest, NextResponse } from 'next/server';

type PickSource = 'llm' | 'unavailable';

interface FrameworkDecision {
  pick: string;
  state: string;
  score: number | null;
  scoreType: 'model-score' | 'data-quality' | 'none';
  reason: string;
  actionable: boolean;
}

interface EngineSummary {
  finalState?: string;
  rawScore?: number | null;
  rawGap?: number | null;
  candidateTeamName?: string | null;
  candidateDecimalOdds?: number | null;
  selectedSide?: 'over' | 'under' | null;
  selectedPrice?: number | null;
  marketLine?: number | null;
  dataQualityScore?: number | null;
  hardGates?: string[];
  warnings?: string[];
}

interface PickRequestBody {
  gameId?: string;
  away?: string;
  home?: string;
  away_sp?: string;
  home_sp?: string;
  moneyline?: string;
  total?: string;
  model?: string;
  venue?: string;
  analysis?: {
    moneyline?: EngineSummary | null;
    totals?: EngineSummary | null;
  };
}

interface PickResponseData {
  pick: string;
  confidence: number;
  confidenceType: 'ai-opinion' | 'model-score' | 'data-quality' | 'none';
  reason: string;
  projectedScore?: string;
  valueEdge?: string;
  marketEdge?: string;
  model: string;
  requestedModel: string;
  source: PickSource;
  actionable: boolean;
  verdict?: 'AGREE' | 'DISAGREE' | 'ABSTAIN' | 'UNAVAILABLE';
  framework?: FrameworkDecision;
  warnings?: string[];
}

const DEFAULT_MODEL = 'gr/claude-opus-5-thinking';
const PICK_TIMEOUT_MS = 70_000;
const ROUTER_TIMEOUT_MS = 90_000;

function clampConfidence(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.round(Math.max(0, Math.min(100, parsed)));
}

function parseJsonObject(value: string): Record<string, any> | null {
  const cleaned = value.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  try {
    const direct = JSON.parse(cleaned);
    return direct && typeof direct === 'object' ? direct : null;
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (!match) return null;
    try {
      const nested = JSON.parse(match[0]);
      return nested && typeof nested === 'object' ? nested : null;
    } catch {
      return null;
    }
  }
}

function extractTextContent(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (!Array.isArray(value)) return null;
  const content = value
    .map((part) => {
      if (typeof part === 'string') return part;
      if (part && typeof part === 'object') {
        const item = part as Record<string, unknown>;
        return typeof item.text === 'string' ? item.text : '';
      }
      return '';
    })
    .join('')
    .trim();
  return content || null;
}

function normalizeProviderResponse(payload: unknown, requestedModel: string): PickResponseData | null {
  if (!payload) return null;

  const root = typeof payload === 'string' ? parseJsonObject(payload) : payload;
  if (!root || typeof root !== 'object') return null;
  const object = root as Record<string, any>;

  const choiceContent = extractTextContent(object.choices?.[0]?.message?.content);
  const outputText = extractTextContent(object.output_text);
  const candidates: unknown[] = [object, object.result, object.data, object.output, choiceContent, outputText];

  for (const candidate of candidates) {
    const parsed = typeof candidate === 'string' ? parseJsonObject(candidate) : candidate;
    if (!parsed || typeof parsed !== 'object') continue;
    const item = parsed as Record<string, any>;
    const pick = String(item.pick ?? item.selection ?? '').trim();
    const reason = String(item.reason ?? item.rationale ?? item.analysis ?? '').trim();
    if (!pick || !reason) continue;

    const confidence = clampConfidence(item.confidence ?? item.confidence_pct ?? item.probability);
    const noPick = /^(no[ _-]?pick|pass|skip|no[ _-]?bet)$/i.test(pick);
    return {
      pick: noPick ? 'NO PICK' : pick,
      confidence: noPick ? 0 : confidence,
      confidenceType: noPick ? 'none' : 'ai-opinion',
      reason,
      projectedScore: item.projectedScore ?? item.projected_score,
      valueEdge: item.valueEdge ?? item.value_edge ?? item.marketEdge ?? item.market_edge,
      marketEdge: item.marketEdge ?? item.market_edge ?? item.valueEdge ?? item.value_edge,
      model: String(item.model || requestedModel),
      requestedModel,
      source: 'llm',
      actionable: !noPick,
      verdict: noPick ? 'ABSTAIN' : undefined,
      warnings: Array.isArray(item.warnings) ? item.warnings.map(String) : undefined,
    };
  }

  return null;
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal, cache: 'no-store' });
  } finally {
    clearTimeout(timeout);
  }
}

async function callPickerService(body: PickRequestBody, requestedModel: string): Promise<PickResponseData | null> {
  const pickerUrl = process.env.PICKER_SERVICE_URL || process.env.AI_PICKER_URL || 'http://127.0.0.1:3001/pick';

  try {
    const response = await fetchWithTimeout(
      pickerUrl,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, model: requestedModel }),
      },
      PICK_TIMEOUT_MS
    );
    if (!response.ok) return null;
    return normalizeProviderResponse(await response.json(), requestedModel);
  } catch {
    return null;
  }
}

function compactAnalysis(body: PickRequestBody): string {
  const ml = body.analysis?.moneyline;
  const totals = body.analysis?.totals;
  return JSON.stringify({
    moneyline: ml ? {
      finalState: ml.finalState,
      rawScore: ml.rawScore,
      candidateTeamName: ml.candidateTeamName,
      candidateDecimalOdds: ml.candidateDecimalOdds,
      hardGates: ml.hardGates ?? [],
      warnings: ml.warnings ?? [],
    } : null,
    totals: totals ? {
      finalState: totals.finalState,
      rawGap: totals.rawGap,
      selectedSide: totals.selectedSide,
      selectedPrice: totals.selectedPrice,
      marketLine: totals.marketLine,
      dataQualityScore: totals.dataQualityScore,
      hardGates: totals.hardGates ?? [],
      warnings: totals.warnings ?? [],
    } : null,
  });
}

async function callRouter(body: PickRequestBody, requestedModel: string): Promise<PickResponseData | null> {
  const routerBase =
    process.env.NINEROUTER_API_BASE ||
    process.env.ROUTER_API_BASE ||
    process.env.OPENAI_API_BASE ||
    process.env.AI_BASE_URL ||
    'http://127.0.0.1:20128/v1';
  const apiKey = process.env.NINEROUTER_API_KEY || process.env.OPENAI_API_KEY || process.env.AI_API_KEY;

  const prompt = `Independently review this MLB matchup using only the supplied market and deterministic-engine evidence.
Do not invent FIP, xFIP, wOBA, lineups, weather, injuries, bullpen availability, probabilities, or expected value.
If the evidence is incomplete or the deterministic engine is blocked, return NO PICK.
You may AGREE with the framework, DISAGREE and provide another available-market pick, or ABSTAIN. Your review is advisory and never replaces framework hard gates.

Matchup: ${body.away || 'Unknown'} @ ${body.home || 'Unknown'}
Starters: ${body.away_sp || 'TBD'} vs ${body.home_sp || 'TBD'}
Venue: ${body.venue || 'Unknown'}
Moneyline: ${body.moneyline || 'Unavailable'}
Total: ${body.total || 'Unavailable'}
Deterministic engine summary: ${compactAnalysis(body)}

Return one JSON object only:
{
  "pick": "Away ML (TEAM) | Home ML (TEAM) | Over X.X | Under X.X | NO PICK",
  "confidence": 72,
  "projectedScore": "optional; omit unless supported by supplied evidence",
  "valueEdge": "optional; omit unless computable from supplied evidence",
  "reason": "brief evidence-based explanation",
  "verdict": "AGREE | DISAGREE | ABSTAIN",
  "warnings": []
}
Use confidence 0 for NO PICK. For a pick, use an integer from 55 to 90 as a qualitative evidence-strength rating, not as a calibrated win probability.`;

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

  try {
    const response = await fetchWithTimeout(
      `${routerBase.replace(/\/+$/, '')}/chat/completions`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: requestedModel,
          messages: [
            {
              role: 'system',
              content: 'You are a conservative independent MLB betting reviewer. The deterministic website remains authoritative, but you may explicitly agree, disagree, or abstain. Return valid JSON and never invent unavailable inputs.',
            },
            { role: 'user', content: prompt },
          ],
          temperature: 0.1,
          max_tokens: 450,
          stream: false,
        }),
      },
      ROUTER_TIMEOUT_MS
    );
    if (!response.ok) return null;
    return normalizeProviderResponse(await response.json(), requestedModel);
  } catch {
    return null;
  }
}

function frameworkDecision(body: PickRequestBody): FrameworkDecision {
  const ml = body.analysis?.moneyline;
  const totals = body.analysis?.totals;
  const mlState = ml?.finalState ?? '';
  const totalsState = totals?.finalState ?? '';

  if ((mlState === 'T1' || mlState === 'T2') && ml?.candidateTeamName) {
    const side = ml.candidateTeamName === body.away ? 'Away' : 'Home';
    const score = clampConfidence(ml.rawScore);
    return {
      pick: `${side} ML (${ml.candidateTeamName})`,
      state: mlState,
      score,
      scoreType: 'model-score',
      reason: `ML_COMBO_V2 produced ${mlState} with score ${score}; this score is not a win probability.`,
      actionable: true,
    };
  }

  if (/^(OVER|UNDER)_(RISKY|STRONG_GAP)$/.test(totalsState) && totals?.selectedSide && totals.marketLine != null) {
    const side = totals.selectedSide === 'over' ? 'Over' : 'Under';
    const quality = clampConfidence(totals.dataQualityScore);
    return {
      pick: `${side} ${totals.marketLine}`,
      state: totalsState,
      score: quality,
      scoreType: 'data-quality',
      reason: `OU_UNIFIED produced ${totalsState} with gap ${Number(totals.rawGap ?? 0).toFixed(2)} and data quality ${quality}; quality is not a win probability.`,
      actionable: true,
    };
  }

  const gates = [...(ml?.hardGates ?? []), ...(totals?.hardGates ?? [])];
  return {
    pick: 'NO PICK',
    state: mlState || totalsState || 'NO_ACTIONABLE_SIGNAL',
    score: null,
    scoreType: 'none',
    reason: gates.length
      ? `Framework blocked: ${Array.from(new Set(gates)).join(', ')}.`
      : 'No actionable deterministic T1/T2 or O/U RISKY/STRONG signal is available.',
    actionable: false,
  };
}

function comparablePick(value: string): string {
  const normalized = value.toLowerCase().replace(/\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();
  if (normalized.includes('away') && normalized.includes('ml')) return 'away-ml';
  if (normalized.includes('home') && normalized.includes('ml')) return 'home-ml';
  const total = normalized.match(/\b(over|under)\s+(\d+(?:\.\d+)?)/);
  return total ? `${total[1]}-${total[2]}` : normalized;
}

function attachFrameworkReview(result: PickResponseData, framework: FrameworkDecision): PickResponseData {
  const verdict = result.verdict === 'ABSTAIN' || result.pick === 'NO PICK'
    ? 'ABSTAIN'
    : comparablePick(result.pick) === comparablePick(framework.pick) && framework.actionable
    ? 'AGREE'
    : 'DISAGREE';
  return { ...result, verdict, framework };
}

function aiUnavailable(requestedModel: string, framework: FrameworkDecision): PickResponseData {
  return {
    pick: 'AI UNAVAILABLE',
    confidence: 0,
    confidenceType: 'none',
    reason: 'The selected external model did not return a valid response. Check the picker service, 9Router endpoint, model ID, and server-side credentials.',
    model: requestedModel,
    requestedModel,
    source: 'unavailable',
    actionable: false,
    verdict: 'UNAVAILABLE',
    framework,
    warnings: ['EXTERNAL_MODEL_UNAVAILABLE'],
  };
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as PickRequestBody;
    const requestedModel = body.model || DEFAULT_MODEL;
    const framework = frameworkDecision(body);

    const pickerResult = await callPickerService(body, requestedModel);
    const routerResult = pickerResult ?? await callRouter(body, requestedModel);
    const pickData = routerResult
      ? attachFrameworkReview(routerResult, framework)
      : aiUnavailable(requestedModel, framework);

    return NextResponse.json(
      { ok: true, result: JSON.stringify(pickData), ...pickData },
      {
        headers: {
          'Cache-Control': 'no-store',
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      }
    );
  } catch (error: any) {
    console.error('[API /api/pick error]:', error);
    return NextResponse.json(
      { ok: false, error: error?.message || 'Picker evaluation failed' },
      { status: 400, headers: { 'Access-Control-Allow-Origin': '*' } }
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}
