import re
import time
import unicodedata
import urllib.request
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

_CACHE = {"ts": 0.0, "index": None, "ttl": 600}

ALIASES = {
    "manchester united": ["man utd", "manchester utd", "man united"],
    "manchester city": ["man city", "manchester c"],
    "tottenham hotspur": ["tottenham", "spurs", "tottenham hotspur fc"],
    "internazionale milano": ["inter", "inter milan", "fc interna", "inter milano", "internazionale"],
    "ac milan": ["milan", "ac milan"],
    "as roma": ["roma"],
    "ss lazio": ["lazio"],
    "ssc napoli": ["napoli"],
    "fiorentina": ["acf fiorentina"],
    "atalanta": ["atalanta bergamasca"],
    "torino": ["torino fc"],
    "udinese": ["udinese calcio"],
    "bologna": ["bologna fc"],
    "empoli": ["empoli fc"],
    "verona": ["hellas verona"],
    "lecce": ["us lecce"],
    "parma": ["parma calcio"],
    "venezia": ["venezia fc"],
    "monza": ["monza 1912", "ac monza"],
    "frosinone": ["frosinone calcio"],
    "cagliari": ["cagliari calcio"],
    "padova": ["calcio padova", "padova calcio"],
    "sassuolo": ["sassuolo calcio"],
    "ascoli": ["ascoli calcio 1898", "ascoli calcio"],
    "avellino": ["avellino 1912", "us avellino"],
    "vicenza": ["vicenza calcio", "l.r. vicenza"],
    "carrarese": ["carrarese calcio"],
    "stade brestois 29": ["brest", "stade brestois"],
    "stade rennais": ["rennes", "stade rennais fc"],
    "rc lens": ["lens"],
    "rc strasbourg": ["strasbourg", "rc strasbourg alsace"],
    "racing club de lens": ["lens"],
    "fc lorient": ["lorient"],
    "troyes": ["troyes ac", "estac troyes"],
    "angiers": ["angers sco", "angers"],
    "olympique lyonnais": ["lyon"],
    "paris saint-germain": ["psg", "paris sg", "paris saint germain"],
    "monaco": ["asm monaco", "as monaco"],
    "nantes": ["fc nantes"],
    "nice": ["ogc nice"],
    "lille": ["losc", "lille osc"],
    "le havre": ["le havre ac", "havre ac"],
    "auxerre": ["aj auxerre"],
    "strasbourg": ["rc strasbourg"],
    "bayer 04 leverkusen": ["bayer leverkusen", "leverkusen"],
    "bayer leverkusen": ["leverkusen"],
    "rb leipzig": ["rasenballsport leipzig", "rasenballsport", "leipzig"],
    "rasenballsport leipzig": ["leipzig", "rb leipzig"],
    "borussia dortmund": ["dortmund", "bvb"],
    "fc koln": ["koln", "1. koln", "b. koln", "koln"],
    "1. koln": ["koln", "fc koln"],
    "borussia monchengladbach": ["gladbach", "b. monchengladbach", "borussia mg", "monchengladbach"],
    "1899 hoffenheim": ["hoffenheim", "tsg 1899 hoffenheim", "tsg hoffenheim"],
    "tsg 1899 hoffenheim": ["hoffenheim"],
    "1. fsv mainz 05": ["mainz", "fsv mainz", "mainz 05"],
    "fsv mainz 05": ["mainz"],
    "vfb stuttgart": ["stuttgart"],
    "1899 hoffenheim": ["hoffenheim"],
    "werder bremen": ["bremen"],
    "fc augsburg": ["augsburg"],
    "vfl bochum": ["bochum"],
    "fc union berlin": ["union berlin", "1. fc union berlin"],
    "1. fc union berlin": ["union berlin"],
    "eintracht frankfurt": ["frankfurt"],
    "hamburger sv": ["hamburger", "hsv", "hamburg"],
    "hamburg": ["hamburger sv", "hsv"],
    "borussia dortmund": ["dortmund"],
    "sporting kansas city": ["sporting kc", "kansas city"],
    "sporting kc": ["kansas city"],
    "la galaxy": ["los angeles galaxy", "la galaxy"],
    "los angeles galaxy": ["la galaxy"],
    "los angeles fc": ["lafc", "los angeles fc"],
    "new york red bulls": ["ny red bulls", "new york rb"],
    "new york city fc": ["nyc fc", "new york city"],
    "dc united": ["d.c. united", "dc united"],
    "philadelphia union": ["philly union"],
    "inter miami": ["inter miami cf", "inter miami"],
    "atlanta united": ["atlanta united fc"],
    "charlotte fc": ["charlotte"],
    "orlando city": ["orlando city sc"],
    "minnesota united": ["minnesota united fc"],
    "nashville sc": ["nashville"],
    "cincinnati": ["fc cincinnati"],
    "portland timbers": ["portland timbers fc"],
    "seattle sounders": ["seattle sounders fc"],
    "vancouver whitecaps": ["vancouver whitecaps fc"],
    "san jose earthquakes": ["san jose"],
    "houston dynamo": ["houston dynamo fc"],
    "austin fc": ["austin"],
    "colorado rapids": ["colorado rapids"],
    "salt lake": ["real salt lake", "rsl"],
    "real salt lake": ["rsl"],
    "spartak moscow": ["spartak", "spartak moskva"],
    "cska moscow": ["cska", "cska moskva"],
    "zenit st. petersburg": ["zenit", "zenit saint petersburg", "zenit spb"],
    "zenit saint petersburg": ["zenit"],
    "lokomotiv moscow": ["lokomotiv", "lokomotiv moskva"],
    "dynamo moscow": ["dynamo", "dinamo moscow", "dynamo moskva"],
    "fk krasnodar": ["krasnodar"],
    "rostov": ["fk rostov"],
    "akhmat grozny": ["akhmat"],
    "krylia sovetov": ["krylya sovetov", "krylia sovetov samara"],
    "orenburg": ["fk orenburg"],
    "rubin kazan": ["rubin"],
    "fakel voronezh": ["fakel"],
    "baltika kaliningrad": ["baltika"],
    "rodina moscow": ["rodina"],
    "gremio": ["gremio"],
    "internacional": ["sc internacional", "internacional rs"],
    "vasco da gama": ["vasco", "cr vasco da gama"],
    "cruzeiro": ["cruzeiro esporte clube", "cruzeiro ec"],
    "sao paulo": ["sao paulo fc"],
    "atletico mineiro": ["clube atletico mineiro", "atletico mg"],
    "flamengo": ["cr flamengo"],
    "corinthians": ["sc corinthians"],
    "palmeiras": ["se palmeiras"],
    "santos fc": ["santos"],
    "bragantino": ["red bull bragantino", "rb bragantino"],
    "ec vitoria": ["vitoria salvador", "vitoria"],
    "fluminense": ["fluminense fc"],
    "botafogo": ["botafogo fr"],
    "fortaleza": ["fortaleza ec"],
    "athletico paranaense": ["athletico-pr", "athletico pr"],
    "cuiaba": ["cuiaba ec"],
    "juventude": ["ec juventude"],
    "gremio": ["gremio"],
    "charlton athletic": ["charlton"],
    "watford": ["watford fc"],
    "west ham united": ["west ham"],
    "brighton hove albion": ["brighton", "brighton & hove albion", "brighton and hove albion"],
    "newcastle united": ["newcastle"],
    "leeds united": ["leeds"],
    "nottingham forest": ["nottingham"],
    "sunderland": ["sunderland afc"],
    "fulham": ["fulham fc"],
    "crystal palace": ["crystal palace"],
    "wolverhampton": ["wolves", "wolverhampton wanderers"],
    "wolverhampton wanderers": ["wolves"],
    "stoke city": ["stoke"],
    "derby county": ["derby"],
    "swansea city": ["swansea"],
    "middlesbrough": ["middlesbrough fc"],
    "west bromwich albion": ["west brom"],
    "norwich city": ["norwich"],
    "burnley": ["burnley fc"],
    "preston north end": ["preston"],
    "hull city": ["hull"],
    "coventry city": ["coventry"],
    "bristol city": ["bristol"],
    "portsmouth": ["portsmouth fc"],
    "millwall": ["millwall fc"],
    "southampton": ["southampton fc"],
    "sheffield united": ["sheffield utd"],
    "sheffield wednesday": ["sheffield weds"],
    "blackburn rovers": ["blackburn"],
    "blackpool": ["blackpool fc"],
    "luton town": ["luton"],
    "qpr": ["queens park rangers"],
    "queens park rangers": ["qpr"],
    "cardiff city": ["cardiff"],
    "birmingham city": ["birmingham"],
    "bristol rovers": ["bristol r"],
    "lincoln city": ["lincoln"],
    "leyton orient": ["leyton orient"],
    "wigan athletic": ["wigan"],
    "bolton wanderers": ["bolton"],
    "reading": ["reading fc"],
    "exeter city": ["exeter"],
    "stevenage": ["stevenage fc"],
    "cheltenham town": ["cheltenham"],
    "gillingham": ["gillingham fc"],
    "notts county": ["notts co"],
    "salford city": ["salford"],
    "harrogate town": ["harrogate"],
    "crawley town": ["crawley"],
    "swindon town": ["swindon"],
    "newport county": ["newport"],
    "walsall": ["walsall fc"],
    "milton keynes dons": ["mk dons"],
    "accrington stanley": ["accrington"],
    "tranmere rovers": ["tranmere"],
    "colchester united": ["colchester"],
    "barrow": ["barrow afc"],
    "stockport county": ["stockport"],
    "wrexham": ["wrexham fc"],
    "doncaster rovers": ["doncaster"],
    "crewe alexandra": ["crewe"],
    "grimsby town": ["grimsby"],
    "chesterfield": ["chesterfield fc"],
    "bromley": ["bromley fc"],
    "sutton united": ["sutton"],
    "forest green rovers": ["forest green"],
    "fleetwood town": ["fleetwood"],
    "port vale": ["port vale"],
    "bradford city": ["bradford"],
    "carlisle united": ["carlisle"],
    "morecambe": ["morecambe fc"],
    "afc wimbledon": ["wimbledon"],
    "mk dons": ["milton keynes dons"],
    "salford": ["salford city"],
    "derby": ["derby county"],
    "northampton town": ["northampton"],
    "peterborough united": ["peterborough"],
    "rotherham united": ["rotherham"],
    "wycombe wanderers": ["wycombe"],
    "barnsley": ["barnsley fc"],
    "reading": ["reading fc"],
    "huddersfield town": ["huddersfield"],
    "cambridge united": ["cambridge"],
    "ipswich town": ["ipswich"],
    "man utd": ["manchester united", "manchester utd"],
    "west brom": ["west bromwich albion"],
    "jagiellonia bialystok": ["jagiellonia"],
    "legia warsaw": ["legia warszawa", "legia"],
    "lech poznan": ["lech"],
    "rakow czestochowa": ["rakow"],
    "slask wroclaw": ["slask"],
    "pogon szczecin": ["pogon"],
    "wisla krakow": ["wisla", "wisla krakow"],
    "gornik zabrze": ["gornik"],
    "korona kielce": ["korona"],
    "piast gliwice": ["piast"],
    "stali mielec": ["stali"],
    "cracovia": ["cracovia krakow"],
    "zaglebie lubin": ["zaglebie"],
    "psv eindhoven": ["psv"],
    "ajax": ["ajax amsterdam"],
    "feyenoord": ["feyenoord rotterdam"],
    "az alkmaar": ["az"],
    "fc twente": ["twente"],
    "fc utrecht": ["utrecht"],
    "vitesse": ["sbv vitesse"],
    "heerenveen": ["sc heerenveen"],
    "groningen": ["fc groningen"],
    "go ahead eagles": ["go ahead"],
    "neitherland": ["nec", "nec nijmegen"],
    "nec nijmegen": ["nec"],
    "pec zwolle": ["zwolle"],
    "fortuna sittard": ["fortuna"],
    "sparta rotterdam": ["sparta"],
    "excelsior": ["sbv excelsior"],
    "almere city": ["almere"],
    "rkc waalwijk": ["rkc"],
    "heerlen": ["roda jc"],
    "sporting lisbon": ["sporting cp", "sporting"],
    "benfica": ["sl benfica"],
    "porto": ["fc porto"],
    "braga": ["sc braga"],
    "vitoria guimaraes": ["vitoria", "vitoria sc"],
    "boavista": ["boavista fc"],
    "gil vicente": ["gil vicente"],
    "famalicao": ["fc famalicao"],
    "maritimo": ["cs maritimo"],
    "arouca": ["fc arouca"],
    "estoril": ["gd estoril"],
    "portimonense": ["portimonense sc"],
    "rio ave": ["rio ave fc"],
    "santa clara": ["cd santa clara"],
    "alverca": ["fc alverca"],
    "academico viseu": ["academico de viseu"],
    "paços ferreira": ["pacos ferreira"],
    "chaves": ["gd chaves"],
    "vizela": ["fc vizela"],
    "covilha": ["sporting covilha"],
    "real sociedad": ["la real", "real sociedad"],
    "athletic club": ["athletic bilbao", "athletic"],
    "atl. madrid": ["atletico madrid", "atletico madrid"],
    "atletico madrid": ["atletico madrid"],
    "sevilla": ["sevilla fc"],
    "valencia": ["valencia cf"],
    "villarreal": ["villarreal cf"],
    "betis": ["real betis", "real betis"],
    "real betis": ["betis"],
    "osasuna": ["ca osasuna"],
    "celta vigo": ["celta"],
    "rayo vallecano": ["rayo"],
    "getafe": ["getafe cf"],
    "espanyol": ["rcd espanyol", "espanyol"],
    "girona": ["girona fc"],
    "granada": ["granada cf"],
    "mallorca": ["rcd mallorca", "mallorca"],
    "levante": ["levante ud"],
    "elche": ["elche cf"],
    "racing santander": ["racing", "racing santander"],
    "alaves": ["deportivo alaves"],
    "malaga": ["malaga cf"],
    "ayacucho": ["ayacucho fc"],
    "galatasaray": ["galatasaray sk"],
    "fenerbahce": ["fenerbahce sk"],
    "besiktas": ["besiktas jk"],
    "trabzonspor": ["trabzonspor"],
    "basaksehir": ["istanbul basaksehir"],
    "goztepe": ["goztepe sk"],
    "caykur rizespor": ["rize", "caykur rizespor"],
    "gaziantep": ["gaziantep", "gaziantep fk"],
    "antalyaspor": ["antalya"],
    "konyaspor": ["konya"],
    "kayserispor": ["kayseri"],
    "sivasspor": ["sivasspor"],
    "alanyaspor": ["alanya"],
    "kasimpasa": ["kasimpasa sk"],
    "keciorengucu": ["ankara keciorengucu"],
    "umraniyespor": ["umraniyespor"],
    "adana demirspor": ["adana demir"],
    "kocaelispor": ["kocaeli"],
    "panathinaikos": ["panathinaikos"],
    "olympiacos": ["olympiacos piraeus", "olympiakos"],
    "paok": ["paok thessaloniki"],
    "aek athens": ["aek"],
    "aris": ["aris thessaloniki"],
    "volos": ["volos nfc", "volos"],
    "iraklis": ["iraklis thessaloniki"],
    "kalamata": ["kalamata fc"],
    "panetolikos": ["panetolikos"],
    "asteras tripolis": ["asteras"],
    "lamia": ["lamia 1964"],
    "ofi crete": ["ofi"],
    "atromitos": ["atromitos athens"],
    "slovan bratislava": ["slovan"],
    "sparta prague": ["sparta praha"],
    "slavia prague": ["slavia praha"],
    "viktoria plzen": ["plzen"],
    "banik ostrava": ["banik"],
    "sigma olomouc": ["sigma"],
    "mlada boleslav": ["mlada"],
    "jablonec": ["fk jablonec"],
    "teplice": ["fk teplice"],
    "zlin": ["fc zlin", "fotbalovy klub zlin"],
    "zbrojovka": ["fc zbrojovka brno", "zbrojovka brno"],
    "budejovice": ["ceske budejovice"],
    "karvina": ["mfk karvina"],
    "pribram": ["1.fk pribram"],
    "dukla prague": ["dukla"],
    "bohemians prague": ["bohemians"],
    "olomouc": ["sigma"],
    "lask linz": ["lask"],
    "rheindorf altach": ["altach", "scr altach"],
    "wolfsberger": ["wolfsberger ac"],
    "sankt polten": ["st. polten"],
    "austria vienna": ["austria wien", "fk austria"],
    "rapid vienna": ["rapid wien", "sk rapid"],
    "red bull salzburg": ["salzburg", "rb salzburg", "a. salzburg"],
    "a. salzburg": ["salzburg", "red bull salzburg"],
    "tirol": ["swarovski tirol", "wsg tirol"],
    "wsg tirol": ["tirol"],
    "rw oberhausen": ["roda jc"],
    "horn": ["sv horn"],
    "adler tirol": ["tirol"],
    "klagenfurt": ["austria klagenfurt"],
    "hartberg": ["tsv hartberg"],
    "graz": ["sk sturm graz", "sturm graz"],
    "sturm graz": ["graz"],
    "liefering": ["fc liefering"],
    "voitsberg": ["ask voitsberg"],
    "kapfenberg": ["kapfenberger sv"],
    "parndorf": ["sc parndorf"],
    "gleisdorf": ["tsv gleisdorf"],
    "lafnitz": ["sv lafnitz"],
    "amstetten": ["skn st. polten"],
    "hertha wels": ["hertha wels"],
    "admira": ["admira wacker"],
    "wiener sport-club": ["wiener sport"],
    "marschall": ["marchfeld"],
    "sv donau": ["sv donau"],
    "traiskirchen": ["fcm traiskirchen"],
    "sk st. johann": ["st. johann"],
    "bw linz": ["blau-weiss linz", "blau weiss linz"],
    "first vienna": ["first vienna fc"],
    "warth": ["sc warth"],
    "kremser": ["kremser sc"],
    "urartu": ["fc urartu"],
    "alashkert": ["alashkert"],
    "prospect united": ["prospect"],
    "hurstville zagreb": ["hurstville"],
    "adelaide olympic": ["adelaide olymp"],
    "modbury jets": ["modbury"],
    "rochedale": ["rochedale u21", "rochedale u23"],
    "moreton city excelsior": ["moreton bay", "moreton city"],
    "interclube": ["gd interclube"],
    "fc luanda": ["1 de agosto angola"],
    "union de santa fe": ["union santa fe", "union"],
    "sarmiento junin": ["sarmiento"],
    "buenos aires city": ["buenos aires"],
    "barrancas": ["cd barrancas"],
    "estudiantes lp": ["estudiantes", "estudiantes la plata"],
    "barracas central": ["barracas"],
    "platense": ["ca platense"],
    "instituto": ["instituto cordoba"],
    "racing santander": ["racing santander"],
    "racing avellaneda": ["racing club"],
    "rosario central": ["rosario"],
    "gimnasia y esgrima": ["gimnasia", "gimnasia la plata"],
    "gimnasia la plata": ["gimnasia", "gimnasia y esgrima"],
    "colon": ["colon santa fe"],
    "talleres cordoba": ["talleres"],
    "independiente": ["ca independiente"],
    "river plate": ["river"],
    "boca juniors": ["boca"],
    "club atlético tucumán": ["atletico tucuman"],
    "defensa y justicia": ["defensa"],
    "argentinos juniors": ["argentinos"],
    "belgrano": ["belgrano cordoba"],
    "godoy cruz": ["godoy cruz"],
    "huracan": ["huracan"],
    "lanus": ["lanus"],
    "newell's old boys": ["newells", "newell's"],
    "san lorenzo": ["san lorenzo de almagro"],
    "velez": ["velez sarsfield"],
    "banfield": ["banfield"],
    "union": ["union santa fe"],
    "tigre": ["ca tigre"],
    "central cordoba": ["central cordoba sde"],
    "barracas central": ["barracas"],
    "chacarita": ["chacarita juniors"],
    "alvarado": ["club alvarado"],
    "dep. moron": ["deportivo moron"],
    "central norte": ["central norte"],
    "nueva chicago": ["nueva chicago"],
    "los andes": ["club los andes"],
    "sacachispas": ["sacachispas"],
    "flandria": ["csd flandria"],
    "gudibne": ["alvarado"],
    "studiantes": ["estudiantes"],
    "liniers": ["ca liniers"],
    "ferro": ["ferro carril oeste"],
    "almirante brown": ["almirante brown"],
    "tristan suarez": ["tristan suarez"],
    "deportivo espanol": ["deportivo espanol"],
    "villa san carlos": ["villa san carlos"],
    "sportivo barracas": ["sportivo barracas"],
    "ela": ["ca argentino de quilmes"],
    "quilmes": ["quilmes ac"],
    "arsenal sarandi": ["arsenal de sarandi", "arsenal"],
    "temperley": ["temperley"],
    "atlanta": ["ca atlanta"],
    "defensores de belgrano": ["defensores de belgrano"],
    "all boys": ["ca all boys"],
    "estudiantes de caseros": ["estudiantes caseros"],
    "tristan suarez": ["tristan suarez"],
    "doxa": ["doxa katakopias"],
    "apoel": ["apoel nicosia"],
    "omonia": ["omonia nicosia"],
    "anorthosis": ["anorthosis famagusta"],
    "apollon limassol": ["apollon"],
    "ael limassol": ["ael"],
    "aris limassol": ["aris"],
    "pafos": ["pafos fc"],
    "nea salamis": ["nea salamis"],
    "enosis paralimni": ["enosis"],
    "karmiotissa": ["karmiotissa"],
    "doxa katokopias": ["doxa"],
    "olympiakos nicosia": ["olympiakos nicosia"],
    "ael": ["ael limassol"],
    "kavala": ["kavala"],
    "liga mx": ["liga mx"],
    "america": ["club america"],
    "chivas": ["guadalajara", "cd guadalajara"],
    "guadalajara": ["chivas"],
    "cruz azul": ["cruz azul"],
    "rayados": ["monterrey"],
    "monterrey": ["rayados"],
    "tigres": ["tigres uanl"],
    "pumas": ["pumas unam"],
    "leon": ["club leon"],
    "toluca": ["deportivo toluca"],
    "pachuca": ["cf pachuca"],
    "santos laguna": ["santos"],
    "atlas": ["atlas fc"],
    "necaxa": ["club necaxa"],
    "juarez": ["fc juarez", "bravos"],
    "queretaro": ["queretaro fc"],
    "tijuana": ["xolos", "club tijuana"],
    "puebla": ["puebla fc"],
    "mazatlan": ["mazatlan fc"],
    "san luis": ["atletico san luis"],
    "atletico san luis": ["san luis"],
    "celaya": ["celaya fc"],
    "atletico morelia": ["morelia"],
    "venados": ["venados fc"],
    "cimarrones": ["cimarrones de sonora"],
    "zacatecas": ["mineros de zacatecas"],
    "tapatio": ["cd tapatio"],
    "cancun": ["cancun fc"],
    "atletico la paz": ["atletico la paz"],
    "dorados": ["dorados de sinaloa"],
    "correcaminos": ["correcaminos uat"],
    "tlaxcala": ["tlaxcala fc"],
    "aguacateros": ["aguacateros de periban"],
    "la paz fc": ["atletico la paz"],
    "tapatio": ["cd tapatio"],
    "zacatepec": ["zacatepec 1948"],
    "alacranes": ["alacranes de durango"],
    "dep. tapatio": ["cd tapatio"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_keys(name):
    n = norm(name)
    keys = {n}
    for canon, al in ALIASES.items():
        if n == norm(canon):
            keys.update(norm(a) for a in al)
    if n in keys:
        for canon, al in ALIASES.items():
            for a in al:
                if n == norm(a):
                    keys.add(norm(canon))
    toks = [t for t in n.split() if len(t) > 2]
    keys.update(toks)
    return keys


def fetch_recent_results(days=9, sleep_s=0.4, use_cache=True):
    now = time.time()
    if use_cache and _CACHE["index"] is not None and now - _CACHE["ts"] < _CACHE["ttl"]:
        return _CACHE["index"]
    index = {}
    failed = 0
    today = date.today()
    for d in range(0, -days, -1):
        url = f"https://www.flashscore.mobi/?d={d}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                html = r.read().decode("utf-8", "ignore")
        except Exception as exc:
            failed += 1
            print(f"[scores_flashscore] WARN fetch failed d={d}: {exc}", flush=True)
            continue
        date_key = (today + timedelta(days=d)).isoformat()
        for m in re.finditer(r'<h4>(.*?)</h4>(.*?)(?=<h4>|$)', html, re.S):
            chunk = m.group(2)
            for am in re.finditer(r'<a href="/match/([A-Za-z0-9]+)[^"]*"[^>]*class="fin">(\d+)-(\d+)', chunk):
                fsid, hg, ag = am.group(1), int(am.group(2)), int(am.group(3))
                start = chunk.rfind("</span>", 0, am.start())
                seg = chunk[start + 7:am.start()] if start != -1 else chunk[:am.start()]
                teams = re.sub(r"<[^>]+>", "", seg)
                parts = [p.strip() for p in teams.split(" - ")]
                if len(parts) >= 2:
                    key = (norm(parts[0]), norm(parts[1]))
                    index[key] = {"home": parts[0], "away": parts[1], "home_goals": hg,
                                  "away_goals": ag, "fs_id": fsid, "date_key": date_key}
        time.sleep(sleep_s)
    if failed:
        print(f"[scores_flashscore] WARN {failed}/{days} day-pages failed to fetch", flush=True)
    if not index and failed == days:
        print("[scores_flashscore] ERROR results feed empty — flashscore.mobi unreachable or blocked from this host", flush=True)
        return index
    _CACHE["ts"] = time.time()
    _CACHE["index"] = index
    return index


def build_lookup(index):
    lookup = {}
    for (hn, an), row in index.items():
        for hk in name_keys(row["home"]):
            for ak in name_keys(row["away"]):
                lookup.setdefault((hk, ak), []).append(row)
    return lookup


def find_result(home, away, lookup, allowed_dates=None):
    allowed_dates = set(allowed_dates or [])

    def preferred(rows):
        if allowed_dates:
            rows = [row for row in rows if row.get("date_key") in allowed_dates]
        return rows[0] if rows else None

    for h in name_keys(home):
        for a in name_keys(away):
            cands = lookup.get((h, a)) or []
            candidate = preferred(cands)
            if candidate:
                return candidate
    # fallback: token overlap scoring
    best = None
    best_score = 0.0
    htoks = set(t for t in norm(home).split() if len(t) > 2)
    atoks = set(t for t in norm(away).split() if len(t) > 2)
    for (ch, ca), rows in lookup.items():
        for row in rows:
            if allowed_dates and row.get("date_key") not in allowed_dates:
                continue
            sc = 0.0
            if htoks:
                inter_h = len(htoks & set(ch.split()))
                sc += inter_h / max(len(htoks), len(set(ch.split())))
            if atoks:
                inter_a = len(atoks & set(ca.split()))
                sc += inter_a / max(len(atoks), len(set(ca.split())))
            sc /= 2
            if sc > best_score:
                best_score = sc
                best = row
    if best and best_score >= 0.5:
        return best
    return None
