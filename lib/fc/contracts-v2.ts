/** Isolated v2 boundary. Not imported by the live reader; validation is not model approval. */
import { z } from 'zod';

const id = z.string().refine(v => v.length > 0 && v === v.trim(), 'Identifier must be nonempty and canonical');
const time = z.number().int().nonnegative().max(4102444800); // UTC epoch seconds, not ms
const finite = z.number().finite();
const probability = finite.min(0).max(1);
const version = z.literal('fc-contract-v2');

export const fixtureSchema = z.object({
  fixture_id: id, competition_id: id, season: id,
  home_team_id: id, away_team_id: id, kickoff_utc: time,
}).strict().refine(v => v.home_team_id !== v.away_team_id, 'Teams must differ');

export const contractSchema = z.object({
  contract_id: id, fixture_id: id,
  market: z.enum(['1x2', 'ou', 'ah', 'btts']),
  side: z.enum(['home', 'draw', 'away', 'over', 'under', 'yes', 'no']),
  line_quarters: z.number().int().safe().nullable(),
  period: z.literal('regulation'),
}).strict().superRefine((v, ctx) => {
  const sides = { '1x2': ['home', 'draw', 'away'], ou: ['over', 'under'], ah: ['home', 'away'], btts: ['yes', 'no'] };
  if (!sides[v.market].includes(v.side)) ctx.addIssue({ code: 'custom', message: 'Invalid market side' });
  const needsLine = v.market === 'ou' || v.market === 'ah';
  if (needsLine !== (v.line_quarters !== null)) ctx.addIssue({ code: 'custom', message: 'Invalid line presence' });
  if (v.market === 'ou' && v.line_quarters !== null && v.line_quarters < 0) ctx.addIssue({ code: 'custom', message: 'Negative total' });
});

export const quoteSchema = z.object({
  quote_id: id, contract_id: id, provider: id, bookmaker: id,
  captured_at: time, available_at: time, decimal_odds: finite.gt(1),
  freshness: z.enum(['fresh', 'stale', 'unknown']),
  is_closing: z.boolean(),
}).strict().refine(v => v.available_at <= v.captured_at, 'Availability after capture');

const payoutSchema = z.object({
  full_win: probability, half_win: probability, push: probability,
  half_loss: probability, full_loss: probability,
}).strict().refine(v => Math.abs(Object.values(v).reduce((a, b) => a + b, 0) - 1) <= 1e-8, 'Payout mass must be one');

export const predictionSchema = z.object({
  prediction_id: id, contract_id: id, formula_version: id, calibration_version: id,
  data_hash: z.string().regex(/^[a-f0-9]{64}$/), training_cutoff: time,
  payout: payoutSchema, ev_net: finite, ev_lower: finite.nullable(),
  uncertainty_status: z.enum(['available', 'unavailable']),
  validation_status: z.enum(['unvalidated', 'approved']),
}).strict().refine(v => (v.uncertainty_status === 'available') === (v.ev_lower !== null), 'Uncertainty mismatch');

export const decisionSchema = z.object({
  status: z.enum(['projection_only', 'paper_candidate', 'official_candidate', 'official_locked', 'blocked']),
  policy_version: id, is_top_pick: z.boolean(), reason_codes: z.array(id),
}).strict();

export const snapshotSchema = z.object({
  schema_version: version, run_id: id, decision_at: time,
  fixture: fixtureSchema, contract: contractSchema, quote: quoteSchema.nullable(),
  prediction: predictionSchema.nullable(), decision: decisionSchema,
  capabilities: z.object({
    schedule_available: z.boolean(), prediction_available: z.boolean(),
    model_validated: z.boolean(), official_enabled: z.boolean(),
  }).strict(),
  diagnostics: z.array(z.object({
    code: z.enum(['missing', 'corrupt', 'invalid', 'stale', 'unavailable']), message: id,
  }).strict()),
}).strict().superRefine((v, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: 'custom', message });
  const { quote: q, prediction: p, capabilities: c, decision: d } = v;
  if (v.contract.fixture_id !== v.fixture.fixture_id) fail('Fixture reference mismatch');
  if (q && (q.contract_id !== v.contract.contract_id || q.captured_at > v.decision_at)) fail('Invalid quote reference/time');
  if (p && (p.contract_id !== v.contract.contract_id || p.training_cutoff > v.decision_at)) fail('Invalid prediction reference/time');
  if (c.prediction_available !== (p !== null)) fail('Prediction capability mismatch');
  if (c.model_validated !== (p?.validation_status === 'approved')) fail('Validation capability mismatch');
  const official = d.status === 'official_candidate' || d.status === 'official_locked';
  if (d.is_top_pick && !official) fail('Top pick must be official');
  if (d.status === 'blocked' && d.reason_codes.length === 0) fail('Blocked reason required');
  if (official || d.status === 'paper_candidate') {
    if (!p || !q || q.freshness !== 'fresh' || v.decision_at >= v.fixture.kickoff_utc ||
        p.ev_lower === null || p.ev_lower <= 0) fail('Candidate evidence incomplete');
  }
  if (official && (!c.official_enabled || !c.model_validated)) fail('Official gate closed');
});

export type FcSnapshotV2 = z.infer<typeof snapshotSchema>;
export const DEFAULT_V2_CAPABILITIES = Object.freeze({
  schedule_available: false, prediction_available: false, model_validated: false, official_enabled: false,
});
