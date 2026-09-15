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
const pick = (p: Record<string, number>, home: string, away: string) => { const lines = [{label:`${home} -0.5`, value:p.home},{label:`${away} +0.5`, value:p.away+p.draw},{label:'Over 2.5',value:p.over25},{label:'Under 2.5',value:1-p.over25},{label:'BTTS Yes',value:p.btts},{label:'BTTS No',value:1-p.btts}]; return lines.sort((a,b)=>b.value-a.value)[0]; };

export async function GET() {
 const matches=read<Match[]>('matches_detailed.json',[]); const ratings=read<Rating>('data/ratings_E0_2526.json',{});
 const out=matches.filter(m=>ALLOWED.some(r=>r.test(m.info?.league ?? '')) && Number(m.info?.start_ts ?? 0)>Date.now()/1000).map(m=>{ const i=m.info ?? {}; const home=i.home ?? '', away=i.away ?? ''; const ht=findTeam(ratings.teams ?? {},home), at=findTeam(ratings.teams ?? {},away); const lh=(ratings.league_avg ?? 1.2)*(ht?.att ?? 1)*(at?.def ?? 1)*(ratings.home_adv ?? 1.1); const la=(ratings.league_avg ?? 1.2)*(at?.att ?? 1)*(ht?.def ?? 1); const p=probs(lh,la); const best=pick(p,home,away); return {info:{home,away,league:i.league,start_ts:i.start_ts,coverage_status:ht&&at?'rated':'market_only'},picks:[{market:'ah',pick:`${home} -0.5 / ${away} +0.5`,probability:Math.max(p.home,p.away+p.draw),odds:null},{market:'ou',pick:p.over25>=0.5?'Over 2.5':'Under 2.5',probability:Math.max(p.over25,1-p.over25),odds:null},{market:'btts',pick:p.btts>=0.5?'BTTS Yes':'BTTS No',probability:Math.max(p.btts,1-p.btts),odds:null}],analyzer:{consensus:best.value>=0.55&&Boolean(ht&&at),data_status:ht&&at?'rated':'market_only',model_goals:{home:Number(lh.toFixed(3)),away:Number(la.toFixed(3))},odds_available:false}}; });
 return NextResponse.json({source:'standalone-ai-analyzer',matches:out,generated_at:new Date().toISOString()});
}
