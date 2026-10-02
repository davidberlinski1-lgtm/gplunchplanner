# Builds gp-lunch-planner/supabase/seed-referrals.sql from the Recent Referral Sources export.
# Usage: python build_seed.py "<path to export .xlsx>"
import sys, os, re, json, collections, unicodedata, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xl
sys.stdout.reconfigure(encoding='utf-8')
SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\david\Downloads\Recent Referral Sources (1).xlsx"
rows = list(xl.load(SRC).values())[0][1:]


def key(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().replace('&', ' and ').replace("'", '')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


# Spelling variants of the same practice (beyond case, accents and punctuation, which key() handles).
ALIAS = {
    'Carnegie Central Medical Centre': 'Carnegie Central Medical Clinic',
    'Carnegie Centre Medical Clinic': 'Carnegie Central Medical Clinic',
    'Carnegie Malvern': 'Carnegie Malvern Medical Centre',
    'Carnegie Malvern Medical Practice': 'Carnegie Malvern Medical Centre',
    'Comprehensive Family Health Care Oakleigh East': 'Comprehensive Family Healthcare Oakleigh East',
    'Comprehensive Family Healthcare': 'Comprehensive Family Healthcare Oakleigh East',
    'Eastbound Clinic': 'Eastbound Medical Clinic',
    'Keys Health Service': 'Keys Medical Centre',
    'Jasper Medical Bentleigh': 'Jasper Medical',
    'Jasper Medical Life Long Care': 'Jasper Medical',
    'My Clinic Prahran': 'MyClinic Prahran',
    'Qualitas Medical Pracitce': 'Qualitas Medical Practice',
    'Qualitas Medical Centre': 'Qualitas Medical Practice',
    'Revita Medical Clinic': 'Revita Medical and Skin Clinic',
}
ALIASK = {key(k): key(v) for k, v in ALIAS.items()}
CANON = {key(v): v for v in ALIAS.values()}

# Postcodes around each Toolbox practice; anything else with an address is "Other".
BENT = {'3204', '3165', '3163', '3189', '3186', '3187', '3188', '3162', '3185', '3166', '3190', '3192', '3161', '3167'}
HAW = {'3122', '3123', '3124', '3146', '3147', '3101', '3102', '3103', '3126', '3127', '3144', '3145', '3125', '3121'}


def iso(d):
    if not d:
        return None
    a, b, c = d.split('/')
    return f"{int(c):04d}-{int(b):02d}-{int(a):02d}"


def slug(s):
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', s.lower()))[:60]


def best(vals):
    c = collections.Counter(v for v in vals if v)
    return c.most_common(1)[0][0] if c else ''


def docs(pairs):
    by = collections.defaultdict(list)
    for d, dt in pairs:
        if d:
            by[d].append(dt)
    out = [{'name': n, 'refs': len(v),
            'years': dict(sorted(collections.Counter(x[:4] for x in v if x).items())),
            'last': max([x for x in v if x], default=None), 'source': 'Referrals', 'web': False}
           for n, v in by.items()]
    return sorted(out, key=lambda x: (-x['refs'], x['name']))


G = collections.defaultdict(list)
unassigned = collections.defaultdict(list)
merged = collections.defaultdict(set)
yt = collections.Counter()
dates = []
for r in rows:
    p = (r.get('E') or '').strip()
    d = re.sub(r'^dr\.?\s+', '', (r.get('D') or '').strip(), flags=re.I)
    dt = iso(r.get('F'))
    if dt:
        yt[dt[:4]] += 1
        dates.append(dt)
    if not p:
        if d:
            unassigned[d].append(dt)
        continue
    k = key(p)
    k = ALIASK.get(k, k)
    G[k].append((p, d, dt, r))
    merged[k].add(p)

clinics = {}
names_by_key = {}
for k, items in G.items():
    names = collections.Counter(p for p, _, _, _ in items)
    name = CANON.get(k)
    if not name:
        cands = [n for n, _ in names.most_common() if not n.isupper() and not n.islower()]
        name = cands[0] if cands else names.most_common(1)[0][0].title()
    names_by_key[k] = name
    addr = best(re.sub(r'\s+', ' ', (r.get('I') or '').strip()) for *_, r in items)
    pc = re.search(r'(\d{4})\s*$', addr)
    pc = pc.group(1) if pc else ''
    region = 'Bentleigh' if pc in BENT else 'Hawthorn East' if pc in HAW else 'Other' if pc else ''
    ds = [dt for _, _, dt, _ in items if dt]
    i = slug(name)
    while i in clinics:
        i += '-2'
    clinics[i] = {
        'id': i, 'name': name, 'address': addr, 'suburb': '', 'region': region,
        'phone': best((r.get('J') or '').strip() for *_, r in items),
        'email': best((r.get('K') or '').strip().lower() for *_, r in items),
        'website': '', 'contact': '',
        'refTotal': len(items), 'refYears': dict(sorted(collections.Counter(x[:4] for x in ds).items())),
        'lastReferral': max(ds, default=None), 'doctors': docs([(d, dt) for _, d, dt, _ in items]),
        'visits': [], 'flyerNeeded': False, 'flyerDone': False, 'flyerReason': '', 'noLunches': False,
        'notes': '', 'outreachNotes': '', 'sources': ['Recent Referral Sources export'], 'isNew': False,
        'noteLog': [], 'tierOverride': '', 'contacted': False}


def nice(s):
    return datetime.date.fromisoformat(s).strftime('%d %b %Y').lstrip('0')


settings = {
    'refYearTotals': dict(sorted(yt.items())),
    'referralPeriod': f"{len(rows)} referrals, {nice(min(dates))} – {nice(max(dates))} (Recent Referral Sources export)",
    'unassigned': docs([(d, dt) for d, v in unassigned.items() for dt in v]),
    'practiceHigh': 15, 'practiceMedium': 5, 'doctorHigh': 6, 'doctorMedium': 3,
    'travelMinutes': 60, 'lunchMinutes': 60, 'outlookHost': 'office'}


def q(o):
    s = json.dumps(o, ensure_ascii=False)
    assert '$j$' not in s
    return "$j$" + s + "$j$::jsonb"


L = ["-- Referral data for the planner, built from the Recent Referral Sources export.",
     "-- Run in the Supabase SQL Editor after schema.sql. Safe to re-run: existing clinics keep their",
     "-- visits, notes and contact edits; only the referral figures and doctor lists are refreshed.",
     "-- Holds practice and doctor names and practice contact details only - no client details.", "",
     "insert into public.docs (collection, id, data) values",
     ",\n".join(f"('clinics', '{i}', {q(c)})" for i, c in sorted(clinics.items())),
     "on conflict (collection, id) do update set updated_at = now(), data = public.docs.data || jsonb_build_object(",
     "  'refTotal', excluded.data->'refTotal', 'refYears', excluded.data->'refYears',",
     "  'lastReferral', excluded.data->'lastReferral', 'doctors', excluded.data->'doctors');", "",
     f"insert into public.docs (collection, id, data) values ('settings', 'main', {q(settings)})",
     "on conflict (collection, id) do update set updated_at = now(), data = public.docs.data || jsonb_build_object(",
     "  'refYearTotals', excluded.data->'refYearTotals', 'referralPeriod', excluded.data->'referralPeriod',",
     "  'unassigned', excluded.data->'unassigned');", ""]
out = os.path.join(HERE, '..', 'supabase', 'seed-referrals.sql')
open(out, 'w', encoding='utf-8', newline='\n').write("\n".join(L))

tier = lambda n: 'High' if n >= 15 else 'Medium' if n >= 5 else 'Low'
print('rows', len(rows), '| clinics', len(clinics), '| refs in clinics', sum(c['refTotal'] for c in clinics.values()),
      '| no-practice refs', sum(d['refs'] for d in settings['unassigned']),
      '| blank-practice rows', sum(1 for r in rows if not (r.get('E') or '').strip()))
print(settings['referralPeriod'], settings['refYearTotals'])
print('regions', dict(collections.Counter(c['region'] or 'not set' for c in clinics.values())))
print('tiers', dict(collections.Counter(tier(c['refTotal']) for c in clinics.values())))
print('with address', sum(1 for c in clinics.values() if c['address']), 'phone', sum(1 for c in clinics.values() if c['phone']), 'email', sum(1 for c in clinics.values() if c['email']))
print('merged spellings:')
for k, v in sorted(merged.items()):
    if len(v) > 1:
        print('  ', names_by_key[k], '<=', sorted(v))
print('top:', [(c['name'], c['refTotal']) for c in sorted(clinics.values(), key=lambda c: -c['refTotal'])[:8]])
