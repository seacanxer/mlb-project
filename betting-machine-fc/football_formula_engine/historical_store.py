"""Historical result store: multi-season results with explicit provenance.

The live scan uses per-league CSVs in betting-machine-fc/data/. This module
adds a *deeper* read-only layer that spans several seasons and competitions,
so a caller can answer "does this team have history, and how much?" without
inventing data.

Honesty contract
----------------
Every record carries a ``source`` and a ``join_status``. A team that has no
record in a season is simply absent - it is never given a synthesised row.
Callers must check ``coverage()`` before trusting any rating derived here.
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

HIST_DIRNAME = 'historical'

_JUNK_SUFFIXES = (' fc', ' cf', ' sc', ' afc', ' ac', ' us', ' as', ' rc')
_CATEGORY_TOKENS = frozenset({
    'ii', 'iii', 'iv', 'u17', 'u18', 'u19', 'u20', 'u21', 'u23',
    'b', 'c', 'res', 'reserves', 'reserve', 'youth', 'women', 'woman',
    'wfc', 'ladies', 'academy',
})

# Maps a live/common team name onto the label used by the historical store.
# The store keeps the raw source labels (football-data short names such as
# "Man City", "Nottm Forest", "M'gladbach"), which a live caller rarely uses.
# Only names that genuinely differ need an entry; everything else is resolved
# case-insensitively or by token overlap. Never alias two different clubs.
TEAM_ALIASES = {
    'manchester city': 'man city',
    'manchester united': 'man united',
    'man utd': 'man united',
    'manchester utd': 'man united',
    'tottenham hotspur': 'tottenham',
    'spurs': 'tottenham',
    'wolverhampton wanderers': 'wolves',
    'wolverhampton': 'wolves',
    'nottingham forest': 'nottm forest',
    'west ham united': 'west ham',
    'west bromwich albion': 'west brom',
    'brighton hove albion': 'brighton',
    'brighton and hove albion': 'brighton',
    'newcastle united': 'newcastle',
    'sheffield utd': 'sheffield united',
    'queen of south': 'queen of south',
    'queens of the south': 'queen of south',
    'borussia dortmund': 'dortmund',
    'bayer leverkusen': 'leverkusen',
    'bayer 04 leverkusen': 'leverkusen',
    'bayern munchen': 'bayern munich',
    'rasenballsport leipzig': 'rb leipzig',
    '1 fc koln': 'fc koln',
    'borussia monchengladbach': "m'gladbach",
    'mgladbach': "m'gladbach",
    'm gladbach': "m'gladbach",
    'fsv mainz 05': 'mainz',
    '1 fsv mainz 05': 'mainz',
    'vfl wolfsburg': 'wolfsburg',
    'vfb stuttgart': 'stuttgart',
    'sc freiburg': 'freiburg',
    'tsg hoffenheim': 'hoffenheim',
    'fc augsburg': 'augsburg',
    'vfl bochum': 'bochum',
    '1 fc union berlin': 'union berlin',
    'sv werder bremen': 'werder bremen',
    'fc st pauli': 'st pauli',
    '1 fc heidenheim': 'heidenheim',
    'internazionale milano': 'inter',
    'inter milan': 'inter',
    'fc internazionale milano': 'inter',
    'juventus fc': 'juventus',
    'atalanta bc': 'atalanta',
    'bologna fc': 'bologna',
    'ac monza': 'monza',
    'como 1907': 'como',
    'us lecce': 'lecce',
    'empoli fc': 'empoli',
    'parma calcio': 'parma',
    'torino fc': 'torino',
    'udinese calcio': 'udinese',
    'genoa cfc': 'genoa',
    'venezia fc': 'venezia',
    'us sassuolo': 'sassuolo',
    'frosinone calcio': 'frosinone',
    'cagliari calcio': 'cagliari',
    'hellas verona fc': 'verona',
    'real sociedad': 'sociedad',
    'real sociedad de futbol': 'sociedad',
    'athletic club bilbao': 'athletic club',
    'athletic bilbao': 'athletic club',
    'atletico de madrid': 'atletico madrid',
    'real betis balompie': 'betis',
    'fc barcelona': 'barcelona',
    'real madrid cf': 'real madrid',
    'sevilla fc': 'sevilla',
    'valencia cf': 'valencia',
    'villarreal cf': 'villarreal',
    'getafe cf': 'getafe',
    'ca osasuna': 'osasuna',
    'rc celta de vigo': 'celta',
    'celta vigo': 'celta',
    'rc celta': 'celta',
    'deportivo alaves': 'alaves',
    'cadiz cf': 'cadiz',
    'real valladolid': 'valladolid',
    'girona fc': 'girona',
    'rcd mallorca': 'mallorca',
    'rcd espanyol': 'espanyol',
    'cd leganes': 'leganes',
    'ud las palmas': 'las palmas',
    'levante ud': 'levante',
    'ud almeria': 'almeria',
    'paris saint germain': 'paris sg',
    'paris saint germain fc': 'paris sg',
    'psg': 'paris sg',
    'as monaco': 'monaco',
    'asm monaco': 'monaco',
    'olympique marseille': 'marseille',
    'olympique de marseille': 'marseille',
    'om': 'marseille',
    'olympique lyonnais': 'lyon',
    'olympique lyon': 'lyon',
    'fc metz': 'metz',
    'rc strasbourg alsace': 'strasbourg',
    'clermont foot': 'clermont',
    'toulouse fc': 'toulouse',
    'nimes olympique': 'nimes',
    'sc bastia': 'bastia',
    'es troyes ac': 'troyes',
    'estac troyes': 'troyes',
    'angers sco': 'angers',
    'sco angers': 'angers',
    'stade brestois 29': 'brest',
    'stade brestois': 'brest',
    'stade rennais': 'rennes',
    'racing club de lens': 'lens',
    'fc lorient': 'lorient',
    'fc nantes': 'nantes',
    'ogc nice': 'nice',
    'lille osc': 'lille',
    'losc': 'lille',
    'le havre ac': 'le havre',
    'havre ac': 'le havre',
    'aj auxerre': 'auxerre',
    'as saint etienne': 'st etienne',
    'saint etienne': 'st etienne',
    'usl dunkerque': 'dunkerque',
    'psv eindhoven': 'psv',
    'ajax amsterdam': 'ajax',
    'feyenoord rotterdam': 'feyenoord',
    'az alkmaar': 'az alkmaar',
    'fc twente': 'twente',
    'go ahead eagles': 'go ahead',
    'nec nijmegen': 'nijmegen',
    'n e c': 'nijmegen',
    'nec': 'nijmegen',
    'heracles almelo': 'heracles',
    'nac breda': 'nac breda',
    'fortuna sittard': 'for sittard',
    'fc utrecht': 'utrecht',
    'sparta rotterdam': 'sparta',
    'pec zwolle': 'zwolle',
    'vitoria guimaraes': 'v guimaraes',
    'vitoria de guimaraes': 'v guimaraes',
    'fc vitoria': 'v guimaraes',
    'fc porto': 'porto',
    'sl benfica': 'benfica',
    'sporting cp': 'sporting',
    'sporting clube de portugal': 'sporting',
    'sc braga': 'braga',
    'casa pia ac': 'casa pia',
    'estoril praia': 'estoril',
    'fc arouca': 'arouca',
    'rio ave fc': 'rio ave',
    'boavista fc': 'boavista',
    'cd santa clara': 'santa clara',
    'fc famalicao': 'famalicao',
    'gd chaves': 'chaves',
    'moreirense fc': 'moreirense',
    'fc vizela': 'vizela',
    'portimonense sc': 'portimonense',
    'sc farense': 'farense',
    'cd nacional': 'nacional',
    'gil vicente fc': 'gil vicente',
    'rsc anderlecht': 'anderlecht',
    'royal antwerp': 'antwerp',
    'krc genk': 'genk',
    'k aa gent': 'gent',
    'standard liege': 'standard',
    'st liege': 'standard',
    'kvc westerlo': 'westerlo',
    'cercle brugge': 'cercle brugge',
    'oh leuven': 'oud-heverlee leuven',
    'kas eupen': 'eupen',
    'zulte waregem': 'zulte-waregem',
    'kv mechelen': 'mechelen',
    'k sint truiden': 'st truiden',
    'sint truiden': 'st truiden',
    'sporting charleroi': 'charleroi',
    'gv beaton': 'beerschot',
    'k lommel sk': 'lommel',
    'galatasaray sk': 'galatasaray',
    'fenerbahce sk': 'fenerbahce',
    'besiktas jk': 'besiktas',
    'trabzon spor': 'trabzonspor',
    'istanbul basaksehir': 'basaksehir',
    'istanbasaksehir': 'basaksehir',
    'adana demirspor': 'ad. demirspor',
    'adem demirspor': 'ad. demirspor',
    'ankara gucu': 'ankaragucu',
    'adem demirspor fc': 'ad. demirspor',
    'fatih karagumruk': 'karagumruk',
    'yeni malatyaspor fc': 'yeni malatyaspor',
    'olympiakos': 'olympiacos',
    'paok thessaloniki': 'paok',
    'aris thessaloniki': 'aris',
    'asteras tripoli': 'asteras',
    'ofi crete': 'ofi',
    'apollon smyrnis': 'apollon',
    'pass giannina': 'giannina',
    'heart of midlothian': 'hearts',
    'glasgow celtic': 'celtic',
    'glasgow rangers': 'rangers',
    'dundee utd': 'dundee united',
    'inverness caledonian thistle': 'inverness c',
    'inverness ct': 'inverness c',
    'partick thistle': 'partick',
    'greenock morton': 'morton',
    'queen s park': 'queen park',
    'queens park': 'queen park',
    'airdrieonians': 'airdrie utd',
    'airdrie united': 'airdrie utd',
    'hamilton academical': 'hamilton',
    'st johnstone': 'st johnstone',
    'st mirren': 'st mirren',
    'ross county fc': 'ross county',
    'ayr united': 'ayr',
    'alloa athletic': 'alloa',
    'stirling albion': 'stirling',
    'forfar athletic': 'forfar',
    'brechin city': 'brechin',
    'elgin city': 'elgin',
    'buckie thistle': 'buckie',
    'banks o dee': 'banks o dee',
    'formartine united': 'formartine',
    'deveronvale fc': 'deveronvale',
    'clachnacuddin fc': 'clachnacuddin',
    'fort william fc': 'fort william',
    'nairn county': 'nairn',
    'victoria united': 'victoria utd',
    'afc wimbledon': 'afc wimbledon',
    'accrington': 'accrington stanley',
    'dover athletic': 'dover',
    'fc halifax town': 'halifax',
    'halifax town': 'halifax',
    'leyton orient': 'leyton orient',
    'macclesfield town': 'macclesfield',
    'maidstone united': 'maidstone',
    'milton keynes dons': 'mk dons',
    'newport county': 'newport',
    'notts county': 'notts county',
    'oldham athletic': 'oldham',
    'salford city': 'salford',
    'scunthorpe united': 'scunthorpe',
    'solihull moors': 'solihull',
    'southend united': 'southend',
    'sutton united': 'sutton',
    'torquay united': 'torquay',
    'afc fylde': 'fylde',
    'birmingham city': 'birmingham',
    'blackburn rovers': 'blackburn',
    'bolton wanderers': 'bolton',
    'bristol city': 'bristol city',
    'bristol rovers': 'bristol rovers',
    'burton albion': 'burton',
    'cambridge united': 'cambridge',
    'cardiff city': 'cardiff',
    'charlton athletic': 'charlton',
    'cheltenham town': 'cheltenham',
    'coventry city': 'coventry',
    'doncaster rovers': 'doncaster',
    'exeter city': 'exeter',
    'fleetwood town': 'fleetwood',
    'grimsby town': 'grimsby',
    'huddersfield town': 'huddersfield',
    'ipswich town': 'ipswich',
    'leeds united': 'leeds',
    'lincoln city': 'lincoln city',
    'luton town': 'luton',
    'mansfield town': 'mansfield',
    'northampton town': 'northampton',
    'norwich city': 'norwich',
    'oxford united': 'oxford',
    'peterborough united': 'peterborough',
    'plymouth argyle': 'plymouth',
    'port vale': 'port vale',
    'preston north end': 'preston',
    'queens park rangers': 'qpr',
    'rotherham united': 'rotherham',
    'shrewsbury town': 'shrewsbury',
    'stoke city': 'stoke',
    'swansea city': 'swansea',
    'swindon town': 'swindon',
    'wigan athletic': 'wigan',
    'wycombe wanderers': 'wycombe',
    'yeovil town': 'yeovil',
    'bradford city': 'bradford',
    'fc united of manchester': 'fc united',
    'kidderminster harriers': 'kidderminster',
    'stockport county': 'stockport',
    'afc telford': 'afc telford united',
    'telford united': 'afc telford united',
    'york city': 'york',
    'blyth spartans': 'blyth',
    'spennymoor town': 'spennymoor',
    'kettering town': 'kettering',
    'curzon ashton': 'curzon',
    'ashton united': 'ashton',
    'hyde united': 'hyde',
    'radcliffe borough': 'radcliffe',
    'skelmersdale united': 'skelmersdale',
    'warrington town': 'warrington',
    'witton albion': 'witton',
    'gainsborough trinity': 'gainsborough',
    'ilkeston town': 'ilkeston',
    'matlock town': 'matlock',
    'mickleover sports': 'mickleover',
    'frickley athletic': 'frickley',
    'stalybridge celtic': 'stalybridge',
    'scarborough athletic': 'scarborough athletic',
    'cleethorpes town': 'cleethorpes',
    'grimsby borough': 'grimsby borough',
    'lincoln united': 'lincoln united',
    'loughborough dynamo': 'loughborough',
    'shepshed dynamo': 'shepshed',
    'leicester road': 'leicester road',
    'coventry sphinx': 'coventry sphinx',
    'coventry copsewood': 'coventry copsewood',
    'stourbridge': 'stourbridge',
    'rushall olympic': 'rushall',
    'hednesford town': 'hednesford',
    'stafford rangers': 'stafford',
    'sporting khalsa': 'sporting khalsa',
    'walsall wood': 'walsall wood',
    'st neots town': 'st neots',
    'biggleswade town': 'biggleswade',
    'biggleswade united': 'biggleswade united',
    'bedford town': 'bedford',
    'kempston rovers': 'kempston',
    'potton united': 'potton',
    'rushden diamonds': 'rushden',
    'rushden and diamonds': 'rushden',
    'corby town': 'corby',
    'sleaford united': 'sleaford',
    'boston united': 'boston',
    'boston town': 'boston town',
    'spalding united': 'spalding',
    'holbeach united': 'holbeach',
    'pinchbeck united': 'pinchbeck',
    'stamford': 'stamford',
    'deeping rangers': 'deeping',
    'huntingdon town': 'huntingdon',
    'godmanchester rovers': 'godmanchester',
    'st ives town': 'st ives',
    'cambridge city': 'cambridge city',
    'royston town': 'royston',
    'hitchin town': 'hitchin',
    'baldock town': 'baldock',
    'ware fc': 'ware',
    'hertford town': 'hertford',
    'enfield town': 'enfield town',
    'edgware town': 'edgware',
    'wingate and finchley': 'wingate',
    'hampton and richmond borough': 'hampton',
    'hampton and richmond': 'hampton',
    'walton casuals': 'walton casuals',
    'walton and hersham': 'walton hersham',
    'metropolitan police': 'met police',
    'carshalton athletic': 'carshalton',
    'croydon athletic': 'croydon',
    'kingstonian': 'kingstonian',
    'corinthian casuals': 'corinthian',
    'merstham': 'merstham',
    'dorking wanderers': 'dorking',
    'horley town': 'horley',
    'redhill': 'redhill',
    'south park': 'south park',
    'east grinstead town': 'east grinstead',
    'horsham': 'horsham',
    'lancing': 'lancing',
    'bognor regis town': 'bognor',
    'bognor regis': 'bognor',
    'selsey': 'selsey',
    'chi united': 'chichester',
    'chichester city': 'chichester',
    'petersfield town': 'petersfield',
    'fareham town': 'fareham',
    'gosport borough': 'gosport',
    'sholing': 'sholing',
    'winchester city': 'winchester',
    'salisbury': 'salisbury',
    'salisbury city': 'salisbury',
    'bemerton heath': 'bemerton',
    'andover new street': 'andover',
    'andover town': 'andover',
    'blackfield and langley': 'blackfield',
    'fawley': 'fawley',
    'hythe and dibden': 'hythe',
    'marchwood united': 'marchwood',
    'newport fc iw': 'newport (iw)',
    'newport iow': 'newport (iw)',
    'swanage and herston': 'swanage',
    'bridport town': 'bridport',
    'dorchester town': 'dorchester',
    'weymouth': 'weymouth',
    'taunton town': 'taunton',
    'bath city': 'bath',
    'barnstaple town': 'barnstaple',
    'bideford': 'bideford',
    'tiverton town': 'tiverton',
    'exmouth town': 'exmouth',
    'axminster town': 'axminster',
    'crediton united': 'crediton',
    'willand rovers': 'willand',
    'cullompton rangers': 'cullompton',
    'bampton town': 'bampton',
    'wellington town': 'wellington',
    'elmore': 'elmore',
    'bradninch town': 'bradninch',
    'exeter united': 'exeter united',
    'topsham town': 'topsham',
    'south molton united': 'south molton',
    'ilfracombe town': 'ilfracombe',
    'combe martin': 'combe martin',
    'braunton': 'braunton',
    'lynton town': 'lynton',
    'porlock': 'porlock',
    'minehead town': 'minehead',
    'watchet town': 'watchet',
    'washford': 'washford',
    'dulverton': 'dulverton',
    'wiveliscombe town': 'wiveliscombe',
    'north petherton united': 'north petherton',
    'bridgwater united': 'bridgwater',
    'bridgwater town': 'bridgwater',
    'burnham on sea': 'burnham',
    'east harptree united': 'east harptree',
    'weston super mare': 'weston',
    'weston s mare': 'weston',
    'clevedon town': 'clevedon',
    'nailsea united': 'nailsea',
    'backwell united': 'backwell',
    'bristol manchester': 'bristol manchester',
    'saltdean united': 'saltdean',
    'rottingdean': 'rottingdean',
    'hove village': 'hove village',
    'southwick': 'southwick',
    'worthing united': 'worthing',
    'littlehampton town': 'littlehampton',
    'arundel': 'arundel',
    'chichester university': 'chichester',
    'portsmouth university': 'portsmouth',
    'portsmouth college': 'portsmouth',
    'havant and waterlooville': 'havant',
    'havant and waterlooville fc': 'havant',
    'waterlooville': 'havant',
    'horndean': 'horndean',
    'denmead': 'denmead',
    'widbrook united': 'widbrook',
    'burghfield': 'burghfield',
    'reading college': 'reading',
    'reading town': 'reading',
    'woodley town': 'woodley',
    'wokingham and embrook': 'wokingham',
    'wokingham town': 'wokingham',
    'bracknell town': 'bracknell',
    'binfield': 'binfield',
    'ascot united': 'ascot',
    'windsor and eton': 'windsor',
    'slough town': 'slough',
    'beaconsfield town': 'beaconsfield',
    'beaconsfield sycob': 'beaconsfield',
    'chalfont wasps': 'chalfont',
    'chalfont st peter': 'chalfont',
    'chalfont st peter athletic': 'chalfont',
    'marlow town': 'marlow',
    'high wycombe': 'high wycombe',
    'chesham united': 'chesham',
    'amersham town': 'amersham',
    'berkhamsted town': 'berkhamsted',
    'berkhamsted raiders': 'berkhamsted',
    'tring athletic': 'tring',
    'pitstone and ivers': 'pitstone',
    'kings langley': 'kings langley',
    'berkhampsted town': 'berkhamsted',
    'northwood town': 'northwood',
    'potters bar town': 'potters bar',
    'potters bar united': 'potters bar',
    'bishops stortford': 'bishops stortford',
    'bishop stortford': 'bishops stortford',
    'sawbridgeworth town': 'sawbridgeworth',
    'harlow town': 'harlow',
    'stansted mountfitchet': 'stansted',
    'saffron walden town': 'saffron walden',
    'saffron walden utd': 'saffron walden',
    'saffron walden city': 'saffron walden',
    'audley end': 'audley end',
    'great chesterford': 'great chesterford',
    'haverhill town': 'haverhill',
    'haverhill rovers': 'haverhill',
    'haverhill borough': 'haverhill',
    'kennett': 'kennett',
    'moulton': 'moulton',
    'newmarket town': 'newmarket',
    'newmarket utd': 'newmarket',
    'exning': 'exning',
    'burwell': 'burwell',
    'swaffham town': 'swaffham',
    'watton united': 'watton',
    'thetford town': 'thetford',
    'fakenham town': 'fakenham',
    'melksham town': 'melksham',
    'devizes town': 'devizes',
    'corsham town': 'corsham',
    'westbury united': 'westbury',
    'warminster town': 'warminster',
    'trowbridge town': 'trowbridge',
    'chippenham town': 'chippenham',
    'radstock town': 'radstock',
    'frome town': 'frome',
    'larkhall athletic': 'larkhall',
    'odd down': 'odd down',
    'peasedown athletic': 'peasedown',
    'shepton mallet': 'shepton mallet',
    'wells city': 'wells',
    'glastonbury town': 'glastonbury',
    'street town': 'street',
    'somerton town': 'somerton',
    'langport town': 'langport',
    'huish episcopi': 'huish episcopi',
    'martock town': 'martock',
    'westonzoyland town': 'westonzoyland',
    'norton fitzwarren town': 'norton fitzwarren',
    'kingston st mary': 'kingston st mary',
    'trispen': 'trispen',
    'probus': 'probus',
    'grampound road': 'grampound road',
    'st austell town': 'st austell',
    'st blazey town': 'st blazey',
    'bodmin town': 'bodmin',
    'liskeard athletic': 'liskeard',
    'saltash united': 'saltash',
    'torpoint athletic': 'torpoint',
    'parkway east': 'parkway',
    'parkway west': 'parkway',
    'launceston town': 'launceston',
    'wadebridge town': 'wadebridge',
    'camelford town': 'camelford',
    'newquay town': 'newquay',
    'penryn athletic': 'penryn',
    'falmouth town': 'falmouth',
    'penzance town': 'penzance',
    'mousehole': 'mousehole',
    'helston athletic': 'helston',
    'porthleven': 'porthleven',
    'mullion': 'mullion',
    'crowlas pigment': 'crowlas',
    'illogan rovers': 'illogan',
    'portreath': 'portreath',
    'st agnes': 'st agnes',
    'perranporth': 'perranporth',
    'goonhavern athletic': 'goonhavern',
    'st columb major': 'st columb',
    'newlyn': 'newlyn',
    'st just in penwith': 'st just',
    'sennen': 'sennen',
    'lands end': 'lands end',
    'st buryan': 'st buryan',
    'sancreed': 'sancreed',
    'drift': 'drift',
    'cerys bracken': 'cerys bracken',
    'bray wanderers': 'bray wanderers',
    'dalkey utd': 'dalkey',
    'dun laoghaire': 'dun laoghaire',
    'shelbourne fc': 'shelbourne',
    'shamrock rovers fc': 'shamrock rovers',
    'bohemian fc': 'bohemians',
    'bohemian': 'bohemians',
    'st patricks athletic': 'st patricks',
    'st pats': 'st patricks',
    'st patrick athletic': 'st patricks',
    'dundalk fc': 'dundalk',
    'drogheda united': 'drogheda',
    'derry city': 'derry city',
    'derry': 'derry city',
    'sligo rovers': 'sligo rovers',
    'galway united': 'galway',
    'finn harps': 'finn harps',
    'longford town': 'longford',
    'cobh ramblers': 'cobh ramblers',
    'cork city': 'cork city',
    'cork': 'cork city',
    'waterford fc': 'waterford',
    'waterford united': 'waterford',
    'limerick fc': 'limerick',
    'athlone town': 'athlone',
    'university college dublin': 'ucd',
    'ucd afc': 'ucd',
    'treaty united': 'treaty united',
    'treaty': 'treaty united',
    'wexford youths': 'wexford',
    'wexford fc': 'wexford',
    'cabinteely': 'cabinteely',
    'kerry fc': 'kerry',
    'kerry league': 'kerry',
    'shelbourne': 'shelbourne',
}


def _strip_accents(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value or '')
                   if not unicodedata.combining(char))


def _casefold(value):
    return ' '.join(_strip_accents(str(value or '')).casefold()
                    .replace('.', ' ').replace('-', ' ').replace("'", ' ').split())


def _short_name(folded):
    result = folded
    for junk in _JUNK_SUFFIXES:
        if result.endswith(junk):
            result = result[:-len(junk)].strip()
    return result


def _category_locked(candidate, probe):
    tokens = set(candidate.split()) | set(probe.split())
    return bool(tokens & _CATEGORY_TOKENS)


@dataclass(frozen=True)
class HistoricalResult:
    competition: str
    season: str
    date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    round_label: str
    is_neutral: bool
    source: str


class HistoricalStore:
    """Read-only view over data/historical/*.csv."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.hist_dir = os.path.join(data_dir, HIST_DIRNAME)
        self._results = None
        self._by_team = None
        self._by_comp = None
        self._by_fold = None

    # ------------------------------------------------------------------ load
    def _load(self):
        if self._results is not None:
            return
        results = []
        if not os.path.isdir(self.hist_dir):
            self._results = results
            self._by_team = {}
            self._by_comp = {}
            return
        for name in sorted(os.listdir(self.hist_dir)):
            if not name.endswith('.csv'):
                continue
            path = os.path.join(self.hist_dir, name)
            if name.startswith('facup'):
                results.extend(self._load_facup(path))
            else:
                results.extend(self._load_league(path, name))
        self._results = results
        by_team = defaultdict(list)
        by_comp = defaultdict(list)
        for result in results:
            by_comp[f'{result.competition}:{result.season}'].append(result)
            by_team[result.home_team].append(result)
            by_team[result.away_team].append(result)
        self._by_team = dict(by_team)
        self._by_comp = dict(by_comp)

    @staticmethod
    def _int(value):
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return number

    def _load_league(self, path, name):
        source = 'football-data.co.uk'
        league = name.split('_')[0]
        season = name[len(league) + 1:-len('.csv')]
        out = []
        with open(path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                home_goals = self._int(row.get('FTHG'))
                away_goals = self._int(row.get('FTAG'))
                if home_goals is None or away_goals is None:
                    continue
                home = (row.get('HomeTeam') or '').strip()
                away = (row.get('AwayTeam') or '').strip()
                if not home or not away or home == away:
                    continue
                out.append(HistoricalResult(
                    competition=league, season=season, date=(row.get('Date') or '').strip(),
                    home_team=home, away_team=away, home_goals=home_goals, away_goals=away_goals,
                    round_label='league', is_neutral=False, source=source))
        return out

    def _load_facup(self, path):
        source = 'engsoccerdata'
        out = []
        with open(path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                home_goals = self._int(row.get('FTHG'))
                away_goals = self._int(row.get('FTAG'))
                if home_goals is None or away_goals is None:
                    continue
                home = (row.get('HomeTeam') or '').strip()
                away = (row.get('AwayTeam') or '').strip()
                if not home or not away or home == away:
                    continue
                neutral = str(row.get('Neutral') or '').strip().lower() == 'yes'
                out.append(HistoricalResult(
                    competition='FACUP', season=(row.get('Season') or '').strip(),
                    date=(row.get('Date') or '').strip(), home_team=home, away_team=away,
                    home_goals=home_goals, away_goals=away_goals,
                    round_label=(row.get('Round') or '').strip(), is_neutral=neutral,
                    source=source))
        return out

    # --------------------------------------------------------------- resolve
    def resolve_team(self, name):
        """Map a live team name onto a stored label, or None if nothing matches.

        Resolution is explicit and never guesses across age/gender categories.
        Order: alias table, exact case-fold, stripped legal suffix, single
        distinctive token overlap, then a conservative similarity score. Any
        candidate that would cross a category boundary (women/youth/reserve) is
        rejected, because those are genuinely different teams.
        """
        self._load()
        if not name:
            return None
        probe = _casefold(name)
        by_fold = self._by_fold
        if by_fold is None:
            by_fold = {_casefold(team): team for team in (self._by_team or {})}
            self._by_fold = by_fold
        alias = TEAM_ALIASES.get(probe)
        if alias is not None:
            # Alias targets are stored labels written in the source's own case,
            # so fold them back to the canonical stored label.
            return by_fold.get(alias, alias)
        if probe in by_fold:
            return by_fold[probe]
        stripped = _short_name(probe)
        if stripped != probe and stripped in by_fold:
            return by_fold[stripped]
        for token in probe.split():
            if len(token) < 5:
                continue
            hits = [team for fold, team in by_fold.items()
                    if token in fold.split() and not _category_locked(fold, probe)]
            if len(hits) == 1:
                return hits[0]
        import difflib
        ranked = []
        for fold, team in by_fold.items():
            if _category_locked(fold, probe):
                continue
            ranked.append((difflib.SequenceMatcher(None, probe, fold).ratio(), team))
        ranked.sort(reverse=True)
        if ranked and ranked[0][0] >= 0.88 and \
                (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.10):
            return ranked[0][1]
        return None

    # --------------------------------------------------------------- queries
    @property
    def results(self):
        self._load()
        return list(self._results or [])

    def team_history(self, team):
        self._load()
        return list((self._by_team or {}).get(team, []))

    def team_matches(self, team, competition=None, seasons=None):
        rows = self.team_history(team)
        if competition is not None:
            rows = [r for r in rows if r.competition == competition]
        if seasons is not None:
            allowed = set(seasons)
            rows = [r for r in rows if r.season in allowed]
        return rows

    def coverage(self, team):
        """How much history exists for a team, split by competition."""
        self._load()
        rows = (self._by_team or {}).get(team, [])
        per_comp = defaultdict(lambda: {'matches': 0, 'seasons': set()})
        for result in rows:
            entry = per_comp[result.competition]
            entry['matches'] += 1
            entry['seasons'].add(result.season)
        return {
            competition: {'matches': entry['matches'], 'seasons': sorted(entry['seasons'])}
            for competition, entry in sorted(per_comp.items())
        }

    def seasons_available(self, competition):
        self._load()
        return sorted({r.season for r in (self._results or []) if r.competition == competition})

    def competition_summary(self):
        self._load()
        per = defaultdict(lambda: {'matches': 0, 'seasons': set(), 'teams': set()})
        for result in (self._results or []):
            entry = per[f'{result.competition}']
            entry['matches'] += 1
            entry['seasons'].add(result.season)
            entry['teams'].add(result.home_team)
            entry['teams'].add(result.away_team)
        return {
            key: {'matches': entry['matches'], 'seasons': sorted(entry['seasons']),
                  'teams': len(entry['teams'])}
            for key, entry in sorted(per.items())
        }

    def matches_as_of(self, cutoff_season=None):
        """All results, optionally restricted to seasons at or before a cutoff."""
        self._load()
        rows = self._results or []
        if cutoff_season is None:
            return list(rows)
        return [r for r in rows if r.season <= cutoff_season]
