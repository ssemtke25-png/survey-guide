# 전국 관광지 모으기 (한국관광공사_국문 관광정보 서비스_GW, 공공데이터포털)
#
# 사용법
#   python scripts/tour_fetch.py        ← 목록이 오래됐으면(25일) 다시 받고, 소개글은 하루 한도 안에서 조금씩 채움 (경북 먼저)
#   python scripts/tour_fetch.py list   ← 목록을 지금 다시 받기
#
# 결과
#   data/tour/all.json        ← 전체 목록 + 소개글 (다음 실행이 이어서 씀)
#   data/tour/g/{위도}_{경도}.json ← 사이트용 : 0.1도 칸마다 나눈 작은 파일. 누른 땅 주변 칸만 받음
import os, sys, json, time, datetime, glob, re, urllib.request, urllib.parse

KEY = os.environ.get('DATA_GO_KR_KEY', '').strip()
ARG = sys.argv[1] if len(sys.argv) > 1 else 'auto'
BUDGET = int(os.environ.get('TOUR_BUDGET', '900'))     # 이번 실행에서 쓸 호출 수 (개발계정 하루 한도 안쪽)
TYPES = {'12': '관광지', '14': '문화시설', '28': '레포츠', '39': '음식점'}
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'tour')
ALL = os.path.join(OUT, 'all.json')
# 관광정보 서비스 판 : 새 판(KorService2) → 안 되면 예전 판(KorService1)
VERS = [('https://apis.data.go.kr/B551011/KorService2', '2'), ('https://apis.data.go.kr/B551011/KorService1', '1')]
VER = 0
calls = 0

class OutOfBudget(Exception): pass

def call(op, **params):
    global calls, VER
    if calls >= BUDGET: raise OutOfBudget()
    base, n = VERS[VER]
    q = {'serviceKey': KEY, 'MobileOS': 'ETC', 'MobileApp': 'naeddang', '_type': 'json'}
    q.update(params)
    if n == '1' and op == 'detailCommon': q.update({'defaultYN': 'Y', 'overviewYN': 'Y'})
    url = f'{base}/{op}{n}?' + urllib.parse.urlencode(q)
    for t in range(4):
        try:
            calls += 1
            with urllib.request.urlopen(url, timeout=30) as r: txt = r.read().decode('utf-8', 'replace'); break
        except Exception as e:
            if getattr(e, 'code', None) == 429: print('오늘 호출 한도(429 Too Many Requests)에 닿았어요.'); raise OutOfBudget()
            print('  재시도', op, e); time.sleep(3 + 5 * t)
    else:
        print(f'{op} 응답이 계속 없어서 오늘은 여기까지 받고 저장해요'); raise OutOfBudget()
    if call.first: print('첫 응답 예시:', txt[:500]); call.first = False
    if 'LIMITED' in txt or 'EXCEEDS' in txt: print('오늘 호출 한도에 닿았어요.'); raise OutOfBudget()
    try: d = json.loads(txt)
    except ValueError:
        if VER == 0 and op == 'areaBasedList':
            print('새 판 응답이 이상해서 예전 판으로 바꿔요:', txt[:200].replace('\n', ' ')); VER = 1; return call(op, **params)
        if op == 'detailCommon': print('소개글 응답이 이상해서 오늘은 여기까지:', txt[:300]); raise OutOfBudget()
        raise SystemExit(f'{op} 응답이 JSON이 아니에요 (인증키·활용신청 확인): {txt[:400]}')
    h = d.get('response', {}).get('header', {})
    if h.get('resultCode') not in ('0000', '00'):
        if h.get('resultCode') == '22': raise OutOfBudget()
        if op == 'detailCommon': print('소개글 오류로 오늘은 여기까지:', h); raise OutOfBudget()
        raise SystemExit(f'{op} 오류 {h.get("resultCode")} {h.get("resultMsg")}')
    b = d['response'].get('body', {}); it = (b.get('items') or {})
    it = it.get('item', []) if isinstance(it, dict) else []
    return (it if isinstance(it, list) else [it]), int(b.get('totalCount') or 0)
call.first = True

def https(u): return re.sub(r'^http://', 'https://', u or '')

def fetch_list(db):
    seen = set()
    for ty in TYPES:
        page = 1; got = 0
        while True:
            items, total = call('areaBasedList', contentTypeId=ty, numOfRows=1000, pageNo=page, arrange='C')
            for x in items:
                cid = str(x.get('contentid'))
                try: lon, lat = float(x.get('mapx') or 0), float(x.get('mapy') or 0)
                except ValueError: continue
                if not (124 < lon < 132 and 33 < lat < 39): continue
                old = db.get(cid, {})
                db[cid] = {'t': x.get('title', '').strip(), 'ty': ty, 'a': (x.get('addr1') or '').strip(),
                           'x': round(lon, 6), 'y': round(lat, 6), 'img': https(x.get('firstimage2') or x.get('firstimage')),
                           'tel': (x.get('tel') or '').strip(), 'm': x.get('modifiedtime', ''),
                           # 분류 : 새 분류체계(lclsSystm1~3)와 예전 서비스분류(cat1~3) 둘 다 남김 → MBTI·테마 코스 고를 때 씀
                           'c': '/'.join(filter(None, [x.get('lclsSystm1'), x.get('lclsSystm2'), x.get('lclsSystm3')])),
                           'c0': '/'.join(filter(None, [x.get('cat1'), x.get('cat2'), x.get('cat3')])),
                           'o': old.get('o', '') if old.get('m') == x.get('modifiedtime', '') else '',
                           'hp': old.get('hp', '') if old.get('m') == x.get('modifiedtime', '') else '',
                           'od': old.get('od', 0) if old.get('m') == x.get('modifiedtime', '') else 0}
                seen.add(cid)
            got += len(items); print(TYPES[ty], page, '쪽', len(items), '건 · 누적', got, '/ 전체', total)
            if got >= total or not items: break
            page += 1; time.sleep(0.2)
    for cid in [c for c in db if c not in seen]: del db[cid]   # 없어진 곳 지우기

def homepage(h):
    # 관광공사 homepage 칸은 '<a href="http://...">www...</a>' 같은 HTML이라 첫 주소만 꺼냄
    h = h or ''
    m = re.search(r'href=["\']?(https?://[^"\'\s>]+)', h, re.I) or re.search(r'(https?://[^\s<"\']+)', h)
    if m: return m.group(1).strip()
    m = re.search(r'\b(www\.[^\s<"\']+)', h)
    return ('http://' + m.group(1).strip()) if m else ''

def clean(s):
    s = re.sub(r'<br\s*/?>', ' ', s or '', flags=re.I); s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def fill_overview(db):
    # 소개글은 한 곳에 한 번씩 불러야 해서, 경북·사진 있는 곳부터 조금씩 채움
    todo = [c for c, v in db.items() if not v.get('od')]
    # 경북 → 사진 있는 곳 → 관광지 → 문화시설·레포츠 → 음식점 순
    rank = {'12': 0, '14': 1, '28': 1, '39': 2}
    todo.sort(key=lambda c: (not db[c]['a'].startswith('경상북도'), not db[c]['img'], rank.get(db[c]['ty'], 3)))
    n = 0
    for cid in todo:
        items, _ = call('detailCommon', contentId=cid)
        o = clean(items[0].get('overview', '')) if items else ''
        db[cid]['hp'] = homepage(items[0].get('homepage', '')) if items else ''
        db[cid]['o'] = o[:160] + ('…' if len(o) > 160 else ''); db[cid]['od'] = 1; n += 1; fill_overview.n = n
        time.sleep(0.1)
    return n

def write_grid(db):
    gdir = os.path.join(OUT, 'g'); os.makedirs(gdir, exist_ok=True)
    for f in glob.glob(os.path.join(gdir, '*.json')): os.remove(f)
    cells = {}
    for cid, v in db.items():
        k = f'{int(v["y"] * 10)}_{int(v["x"] * 10)}'
        cells.setdefault(k, []).append([cid, v['t'], v['ty'], v['x'], v['y'], v['img'], v['a'], v.get('o', ''), v.get('hp', ''), v.get('c') or v.get('c0', '')])
    for k, rows in cells.items():
        json.dump(rows, open(os.path.join(gdir, f'{k}.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return len(cells)

def main():
    if not KEY: raise SystemExit('DATA_GO_KR_KEY 가 없어요')
    os.makedirs(OUT, exist_ok=True)
    st = json.load(open(ALL, encoding='utf-8')) if os.path.exists(ALL) else {'listed': '', 'items': {}}
    db = st['items']; filled = 0
    try:
        stale = not st.get('listed') or (datetime.date.today() - datetime.date.fromisoformat(st['listed'])).days >= 25
        # 받는 종류(음식점)나 칸(분류)이 늘었으면 목록을 다시 받음
        stale = stale or any(ty not in {v.get('ty') for v in db.values()} for ty in TYPES) or any('c' not in v for v in db.values())
        if ARG == 'list' or stale:
            fetch_list(db); st['listed'] = datetime.date.today().isoformat()
        filled = fill_overview(db)
    except OutOfBudget:
        filled = getattr(fill_overview, 'n', 0); print(f'이번엔 여기까지 (호출 {calls}번).')
    st['updated'] = datetime.date.today().isoformat()
    json.dump(st, open(ALL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    cells = write_grid(db)
    left = sum(1 for v in db.values() if not v.get('od'))
    print(f'관광지 {len(db)}곳 · 이번에 소개글 {filled}곳 채움 · 남은 소개글 {left}곳 · 칸 파일 {cells}개 · 호출 {calls}번')
    if not db: raise SystemExit('받은 관광지가 0곳이에요. 위의 첫 응답 예시를 확인해 주세요.')

main()
