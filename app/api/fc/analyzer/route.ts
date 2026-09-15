import fs from 'node:fs';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

type Team = { att?: number; def?: number };
type Rating = { league_avg?: number; home_adv?: number; teams?: Record<string, Team> };
type Match = { info?: { home?: string; away?: string; league?: string; start_ts?: number }; picks?: Array<Record<string, unknown>> };

const ALLOWED = [/^England\. Premier League$/i,/^Spain\. La Liga$/i,/^Germany\. Bundesliga$/i,/^Italy\. Serie A$/i,/^France\. Ligue 1$/i,/^Japan\. J1 League$/i,/^South Korea\. K-League 1$/i,/^Saudi Arabia\. Professional League$/i,/^China\. Super League$/i,/^Australia\. A-League$/i,/^England\. FA Cup$/i,/^England\. League Cup$/i,/^UEFA\. Champions League$/i,/^UEFA\. Europa League$/i,/^UEFA\. Europa Conference League$/i,/^AFC Champions League Elite$/i,/^AFC Champions League 2$/i,/^Champions League$/i,/^Europa League$/i,/^Conference League$/i];
const root = path.join(process.cwd(), 'betting-machine-fc');
const read = <T>(name: string, fallback: T): T => { try { return JSON.parse(fs.readFileSync(path.join(root, name), 'utf8')) as T; } catch { return fallback; } };
const poisson = (lambda: number, k: number) => Math.exp(-lambda) * Math.pow(lambda, k) / factorial(k);
const factorial = (n: number): number => n < 2 ? 1 : n * factorial(n - 1);
const norm = (s: string) => s.toLowerCase().replace(/\b(fc|sc|afc|cf)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
const findTeam = (teams: Record<string, Team>, name: string) => { const n = norm(name); const key = Object.keys(teams).find((k) => norm(k) === n || norm(k).includes(n) || n.includes(norm(k))); return key ? teams[key] : undefined; };
const probs = (lh: number, la: number) => { let home = 0, draw = 0, away = 0, over25 = 0, btts = 0; for (let h=0; h<=8; h++) for (let a=0; a<=8; a++) { const p=poisson(lh,h)*poisson(la,a); if(h>a) home+=p; else if(h===a) draw+=p; else away+=p; if(h+a>2) over25+=p; if(h>0&&a>0) btts+=p; } return {home,draw,away,over25,btts}; };
const pick = (p: Record<string, number>, home: string, away: string) => { const ah = p.home >= p.away + p.draw ? {pick:`${home} -0.5`, probability:p.home} : {pick:`${away} +0.5`, probability:p.away + p.draw}; const ou = p.over25 >= 0.5 ? {pick:'Over 2.5', probability:p.over25} : {pick:'Under 2.5', probability:1-p.over25}; const btts = p.btts >= 0.5 ? {pick:'BTTS Yes', probability:p.btts} : {pick:'BTTS No', probability:1-p.btts}; return {ah,ou,btts}; };

export async function GET() {
 const matches=read<Match[]>('matches_detailed.json',[]); const ratings=read<Rating>('data/ratings_E0_2526.json',{});
 const out=matches.filter(m=>ALLOWED.some(r=>r.test(m.info?.league ?? '')) && Number(m.info?.start_ts ?? 0)>Date.now()/1000).map(m=>{ const i=m.info ?? {}; const home=i.home ?? '', away=i.away ?? ''; const ht=findTeam(ratings.teams ?? {},home), at=findTeam(ratings.teams ?? {},away); const lh=(ratings.league_avg ?? 1.2)*(ht?.att ?? 1)*(at?.def ?? 1)*(ratings.home_adv ?? 1.1); const la=(ratings.league_avg ?? 1.2)*(at?.att ?? 1)*(ht?.def ?? 1); const p=probs(lh,la); const best=pick(p,home,away); const confidence=(best.ah.probability+best.ou.probability+best.btts.probability)/3; return {info:{home,away,league:i.league,start_ts:i.start_ts,coverage_status:ht&&at?'rated':'market_only'},picks:[{market:'ah',pick:best.ah.pick,probability:best.ah.probability,odds:null},{market:'ou',pick:best.ou.pick,probability:best.ou.probability,odds:null},{market:'btts',pick:best.btts.pick,probability:best.btts.probability,odds:null}],analyzer:{consensus:confidence>=0.55&&Boolean(ht&&at),confidence,data_status:ht&&at?'rated':'market_only',model_goals:{home:Number(lh.toFixed(3)),away:Number(la.toFixed(3))},odds_available:false}}; });
 return NextResponse.json({source:'standalone-ai-analyzer',matches:out,generated_at:new Date().toISOString()});
}
