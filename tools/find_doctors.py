# Finds each clinic's website (via Google Maps) and the doctors listed on it, then writes
# supabase/seed-doctors.sql. Results are cached in tools/doctors.json so it can be re-run.
# Usage: python find_doctors.py [--refresh]
import sys, os, re, json, html, time, urllib.request, urllib.parse, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
CACHE = os.path.join(HERE, 'doctors.json')


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-AU,en', 'Accept': 'text/html,*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if 'html' not in (r.headers.get('Content-Type') or 'html') and 'json' not in (r.headers.get('Content-Type') or ''):
            return '', r.geturl()
        return r.read(3_000_000).decode('utf-8', 'replace'), r.geturl()


def gm(q):
    u = ('https://www.google.com/search?tbm=map&hl=en&gl=au&q=' + urllib.parse.quote(q) +
         '&pb=!4m12!1m3!1d120000!2d145.03!3d-37.88!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!7i20!10b1')
    t, _ = get(u)
    d = json.loads(t[t.index('\n') + 1:] if t.startswith(")]}'") else t)
    out = []

    def walk(x, dep):
        if not isinstance(x, list) or dep > 6 or len(out) >= 3:
            return
        if len(x) > 39 and isinstance(x[11], str) and isinstance(x[2], list) and isinstance(x[10], str) and x[10].startswith('0x'):
            web = x[7][0] if isinstance(x[7], list) and x[7] else ''
            if web.startswith('/url?'):
                web = urllib.parse.parse_qs(urllib.parse.urlparse(web).query).get('q', [''])[0]
            out.append({'n': x[11], 'a': x[39] or ', '.join(x[2]), 'w': web})
            return
        for y in x:
            walk(y, dep + 1)
    walk(d, 0)
    return out


def nk(s):
    s = re.sub(r'&', ' and ', s.lower())
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return [w for w in s.split() if w not in {'the', 'medical', 'centre', 'center', 'clinic', 'practice', 'family', 'general',
                                              'health', 'care', 'group', 'and', 'dr', 'doctors', 'healthcare'}]


# ---------- clinics ----------
def load_clinics():
    by = {}
    for f in ['seed-referrals.sql', 'seed-lunches.sql']:
        s = open(os.path.join(HERE, '..', 'supabase', f), encoding='utf-8').read()
        for m in re.finditer(r"\('clinics', '([^']+)', \$j\$(.*?)\$j\$::jsonb\)", s):
            by.setdefault(m.group(1), json.loads(m.group(2)))
        for m in re.finditer(r"data = data \|\| \$j\$(.*?)\$j\$::jsonb where collection = 'clinics' and id = '([^']+)'", s):
            by[m.group(2)].update(json.loads(m.group(1)))
    for line in open(os.path.join(HERE, 'addresses.tsv'), encoding='utf-8'):
        if line.strip():
            i, a, p = line.strip().split('|')
            if i in by and not by[i].get('address'):
                by[i]['address'] = a
    return by


# ---------- doctor names ----------
STOP = set('''MBBS FRACGP MB BS MD BMed BSc BMedSc BMBS DRANZCOG DCH FRACP PhD MPH General Practitioner GP GPs Is Has Was Will Can
Graduated Special Interests Interest Book Booking Appointment Appointments View Profile Read More Female Male Speaks Languages
Monday Tuesday Wednesday Thursday Friday Saturday Sunday Available Clinic Medical Centre Our The And Bio Qualifications
Completed Joined Works Enjoys Dr Doctor Doctors Mon Tue Wed Thu Fri Sat Sun Practice Principal Director Owner Founder Also
Speaks English Mandarin Cantonese Hindi Greek Italian Russian Hebrew Arabic Vietnamese Online Now Call Us Team Staff Meet
In At On For With From To Of By She He Her His They Who After Since Before A An Welcome Welcomes New Patients Patient
Not Currently Taking Accepting Bulk Billing Skin Cancer Women Womens Men Mens Health Children Family Mental Care Learn
Click Here Contact Home About Services Location Hours Telehealth Consults Consulting Days Day Paediatrician Psychologist
Dentist Physiotherapist Registrar Associate Professor Background Education Experience Areas Location Locations'''.split())
NAME = re.compile(r"\bDr\.?\s+((?:[A-Z][A-Za-z'’\-]+|[A-Z]\.)(?:[  ]+(?:[A-Z][A-Za-z'’\-]+|de|van|von|der|le|la|di|bin|[A-Z]\.)){0,3})")


def text_of(page):
    page = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', page)
    page = re.sub(r'(?i)<br\s*/?>|</(p|div|h\d|li|td|span|a|strong|b)>', ' \n ', page)
    page = re.sub(r'<[^>]+>', ' ', page)
    return html.unescape(page)


def names_in(page):
    found = []
    for m in NAME.finditer(text_of(page)):
        toks = []
        for t in m.group(1).replace(' ', ' ').split():
            t = re.sub(r"['’]s$", '', t)
            if t in STOP or (t.isupper() and len(t) > 3):
                break
            toks.append(t.rstrip('.') if len(t) == 2 and t.endswith('.') else t)
        while toks and toks[-1].lower() in {'de', 'van', 'von', 'der', 'le', 'la', 'di', 'bin'}:
            toks.pop()
        if toks and len(toks[-1]) > 1:
            n = ' '.join(toks)
            n = ' '.join(w.capitalize() if w.isupper() and len(w) > 2 else w for w in n.split())
            found.append(n)
    # prefer full names: drop "Smith" when "John Smith" is present, and exact duplicates
    out = []
    for n in found:
        k = n.lower()
        if any(k == o.lower() for o in out):
            continue
        out.append(n)
    full = [n for n in out if ' ' in n]
    lasts = {n.split()[-1].lower() for n in full}
    firsts = {n.split()[0].lower() for n in full}
    return full if full else out   # bare first names or surnames are only kept when the page has no full names


LINK = re.compile(r'(?is)<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>')
WANT = re.compile(r'doctor|our[\s\-_]*team|team|practitioner|\bgps?\b|our[\s\-_]*people|staff|meet|about', re.I)
BEST = re.compile(r'doctor|practitioner|\bgps?\b', re.I)


def scrape(site):
    """Returns (names, url of the page with the most doctors)."""
    try:
        home, base = get(site)
    except Exception as e:
        return [], '', f'home: {type(e).__name__}'
    pages = {base: home}
    host = urllib.parse.urlparse(base).netloc.replace('www.', '')
    cands = []
    for href, txt in LINK.findall(home):
        label = re.sub(r'<[^>]+>', ' ', txt)
        if not (WANT.search(href) or WANT.search(label)):
            continue
        u = urllib.parse.urljoin(base, href.strip())
        if urllib.parse.urlparse(u).netloc.replace('www.', '') != host or re.search(r'\.(pdf|jpg|png)$|mailto:|tel:', u, re.I):
            continue
        score = (2 if BEST.search(href + ' ' + label) else 0) + (1 if re.search(r'team|staff|people', href + ' ' + label, re.I) else 0)
        if u not in pages and u not in [c[1] for c in cands]:
            cands.append((score, u))
    cands.sort(key=lambda c: -c[0])
    for _, u in cands[:5]:
        try:
            pages[u] = get(u)[0]
        except Exception:
            pass
    best, best_url, allnames = [], base, []
    for u, p in pages.items():
        n = names_in(p)
        if len(n) > len(best):
            best, best_url = n, u
    return best[:45], best_url, ''


def work(c):
    q = c['name'] + ' ' + (c.get('address') or 'VIC')
    res = {'website': '', 'match': '', 'names': [], 'doctorsUrl': '', 'note': ''}
    try:
        hits = gm(q)
    except Exception as e:
        res['note'] = f'maps: {type(e).__name__}'
        return c['id'], res
    want = nk(c['name'])
    hit = next((h for h in hits if want and all(w in nk(h['n']) for w in want)), None)
    if not hit and c.get('address') and hits:
        # Google sometimes shows a different trading name at the same street address
        num = re.match(r'[^,]*?(\d+[A-Za-z]?)\s+([A-Za-z]+)', c['address'])
        hit = next((h for h in hits if num and num.group(1) in h['a'] and num.group(2) in h['a']), None)
    if not hit:
        res['note'] = 'no confident Google Maps match'
        return c['id'], res
    res['match'], res['website'] = hit['n'], re.sub(r'[?&]utm_[^#]*', '', hit['w'])
    if not hit['w']:
        res['note'] = 'no website on Google Maps'
        return c['id'], res
    if re.search(r'facebook\.com|instagram\.com|hotdoc\.com|healthengine\.com', hit['w']):
        res['note'] = 'listing is a booking/social page, not a clinic website'
        return c['id'], res
    res['names'], res['doctorsUrl'], res['note'] = scrape(hit['w'])
    if not res['names'] and not res['note']:
        res['note'] = 'no doctor names found on the site'
    return c['id'], res


def same(a, b):
    """'John Smith' vs 'J Smith' / 'Smith' / 'John A Smith'."""
    a, b = a.lower().replace('.', '').split(), b.lower().replace('.', '').split()
    if a[-1] != b[-1]:
        return False
    if len(a) == 1 or len(b) == 1:
        return True
    return a[0] == b[0] or a[0][0] == b[0] or b[0][0] == a[0] or (len(a[0]) == 1 or len(b[0]) == 1) and a[0][0] == b[0][0]


if __name__ == '__main__':
    clinics = load_clinics()
    cache = {} if '--refresh' in sys.argv or not os.path.exists(CACHE) else json.load(open(CACHE, encoding='utf-8'))
    todo = [c for i, c in clinics.items() if i not in cache]
    print(len(clinics), 'clinics;', len(todo), 'to look up')
    with cf.ThreadPoolExecutor(6) as ex:
        for n, (i, res) in enumerate(ex.map(work, todo), 1):
            cache[i] = res
            if n % 20 == 0:
                print(' ', n, 'done')
                json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    def q(o):
        s = json.dumps(o, ensure_ascii=False)
        assert '$j$' not in s
        return "$j$" + s + "$j$::jsonb"

    L = ["-- Websites and doctor lists collected from each practice's own website.",
         "-- Adds doctors that are not already listed for the clinic; never removes or changes existing ones.", ""]
    stats = {'site': 0, 'docs': 0, 'clinics_with_docs': 0}
    for i, c in sorted(clinics.items()):
        r = cache.get(i) or {}
        if not r.get('website'):
            continue
        stats['site'] += 1
        have = [d['name'] for d in c.get('doctors') or []]
        new = [{'name': n, 'refs': 0, 'years': {}, 'last': None, 'source': 'Clinic website', 'web': True}
               for n in r.get('names', []) if not any(same(n, h) for h in have)]
        stats['docs'] += len(new)
        stats['clinics_with_docs'] += bool(r.get('names'))
        L.append(
            f"update public.docs set updated_at = now(), data = data"
            f" || jsonb_build_object('website', coalesce(nullif(data->>'website', ''), $a${r['website']}$a$))"
            + (f" || jsonb_build_object('doctorsUrl', $a${r['doctorsUrl']}$a$, 'doctors', coalesce(data->'doctors', '[]'::jsonb) || coalesce(("
               f"select jsonb_agg(n) from jsonb_array_elements({q(new)}) n where not exists ("
               f"select 1 from jsonb_array_elements(coalesce(data->'doctors', '[]'::jsonb)) e where lower(e->>'name') = lower(n->>'name'))), '[]'::jsonb))"
               if new else '')
            + f" where collection = 'clinics' and id = '{i}';")
    open(os.path.join(HERE, '..', 'supabase', 'seed-doctors.sql'), 'w', encoding='utf-8', newline='\n').write("\n".join(L) + "\n")
    print(stats)
    notes = {}
    for i, r in cache.items():
        if r.get('note'):
            notes.setdefault(r['note'].split(':')[0], []).append(clinics[i]['name'] if i in clinics else i)
    for k, v in notes.items():
        print(f"{k} ({len(v)}):", '; '.join(sorted(v)))
