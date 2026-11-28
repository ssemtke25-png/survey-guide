# 전국 아파트 매매 실거래가 모으기 (국토교통부_아파트 매매 실거래가 상세 자료, 공공데이터포털)
#
# 사용법
#   python scripts/apt_fetch.py 36     ← 새로 모으기 시작 (최근 36개월). 하루에 다 못 하면 이어서 받을 목록을 남김
#   python scripts/apt_fetch.py auto   ← 매일 자동 실행용 : 남은 게 있으면 이어서, 없으면 매달 5일에만 최근 3개월 갱신
#
# 결과
#   data/apt/{시군구5}/{읍면동5}.json   ← 사이트는 누른 땅의 읍면동 파일 하나만 받음 (작고 빠름)
#   data/apt/index.json                 ← 시군구별 건수 (나중에 대시보드용)
#   data/apt/_progress.json             ← 이어 받기 목록 (다 끝나면 지워짐)
import os, sys, json, time, datetime, glob, urllib.request, urllib.parse, xml.etree.ElementTree as ET

KEY = os.environ.get('DATA_GO_KR_KEY', '').strip()
ARG = sys.argv[1] if len(sys.argv) > 1 else 'auto'
KEEP = 36                                              # 파일에 남겨 둘 개월 수
BUDGET = int(os.environ.get('APT_BUDGET', '9000'))      # 하루 호출 한도(10,000) 안에서 이번 실행에 쓸 양
URLS = ['https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',  # 상세판
        'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade']        # 일반판 (상세판이 안 될 때)
URL = URLS[0]
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'apt')
PROG = os.path.join(OUT, '_progress.json')
CODES = os.path.join(OUT, '_codes.json')

# 전국 시군구 코드 (법정동코드 앞 5자리, 2024.8 기준. 구가 있는 시는 구 단위, 출장소 제외)
SGG = [
    # 서울특별시
    '11110', '11140', '11170', '11200', '11215', '11230', '11260', '11290', '11305', '11320', '11350', '11380', '11410', '11440', '11470', '11500', '11530', '11545', '11560', '11590', '11620', '11650', '11680', '11710', '11740',
    # 부산광역시
    '26110', '26140', '26170', '26200', '26230', '26260', '26290', '26320', '26350', '26380', '26410', '26440', '26470', '26500', '26530', '26710',
    # 대구광역시
    '27110', '27140', '27170', '27200', '27230', '27260', '27290', '27710', '27720',
    # 인천광역시 (2026.7 개편 전 코드. 새 구 코드는 아래 찾기로 보탬)
    '28110', '28140', '28177', '28185', '28200', '28237', '28245', '28260', '28710', '28720',
    # 광주광역시
    '29110', '29140', '29155', '29170', '29200',
    # 대전광역시
    '30110', '30140', '30170', '30200', '30230',
    # 울산광역시
    '31110', '31140', '31170', '31200', '31710',
    # 세종특별자치시
    '36110',
    # 경기도 (화성시는 2026.2 구 설치 전 코드. 새 구 코드는 아래 찾기로 보탬)
    '41111', '41113', '41115', '41117', '41131', '41133', '41135', '41150', '41171', '41173', '41192', '41194', '41196', '41210', '41220', '41250', '41271', '41273', '41281', '41285', '41287', '41290', '41310', '41360', '41370', '41390', '41410', '41430', '41450', '41461', '41463', '41465', '41480', '41500', '41550', '41570', '41590', '41610', '41630', '41650', '41670', '41800', '41820', '41830',
    # 충청북도
    '43111', '43112', '43113', '43114', '43130', '43150', '43720', '43730', '43740', '43745', '43750', '43760', '43770', '43800',
    # 충청남도
    '44131', '44133', '44150', '44180', '44200', '44210', '44230', '44250', '44270', '44710', '44760', '44770', '44790', '44800', '44810', '44825',
    # 전라남도
    '46110', '46130', '46150', '46170', '46230', '46710', '46720', '46730', '46770', '46780', '46790', '46800', '46810', '46820', '46830', '46840', '46860', '46870', '46880', '46890', '46900', '46910',
    # 경상북도
    '47111', '47113', '47130', '47150', '47170', '47190', '47210', '47230', '47250', '47280', '47290', '47730', '47750', '47760', '47770', '47820', '47830', '47840', '47850', '47900', '47920', '47930', '47940',
    # 경상남도
    '48121', '48123', '48125', '48127', '48129', '48170', '48220', '48240', '48250', '48270', '48310', '48330', '48720', '48730', '48740', '48820', '48840', '48850', '48860', '48870', '48880', '48890',
    # 제주특별자치도
    '50110', '50130',
    # 강원특별자치도
    '51110', '51130', '51150', '51170', '51190', '51210', '51230', '51720', '51730', '51750', '51760', '51770', '51780', '51790', '51800', '51810', '51820', '51830',
    # 전북특별자치도
    '52111', '52113', '52130', '52140', '52180', '52190', '52210', '52710', '52720', '52730', '52740', '52750', '52770', '52790', '52800',
]
# 행정구역이 바뀐 곳의 새 코드 후보 (실제로 거래가 나오는 코드만 보탬)
CAND = [f'2{n}' for n in range(8101, 8300)] + [f'4159{d}' for d in range(1, 10)]

calls = 0

def months(n, start=None):
    d = (start or datetime.date.today()).replace(day=1); out = []
    for _ in range(n):
        out.append(d.strftime('%Y%m')); d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out

def g(it, *names):
    for n in names:
        e = it.find(n)
        if e is not None and e.text and e.text.strip(): return e.text.strip()
    return ''

class OutOfBudget(Exception): pass

def call(sgg, ym, page, rows=1000):
    global URL, calls
    if calls >= BUDGET: raise OutOfBudget()
    q = urllib.parse.urlencode({'serviceKey': KEY, 'LAWD_CD': sgg, 'DEAL_YMD': ym, 'numOfRows': rows, 'pageNo': page})
    for t in range(4):
        try:
            calls += 1
            with urllib.request.urlopen(URL + '?' + q, timeout=30) as r: x = r.read(); break
        except Exception as e:
            print('  재시도', sgg, ym, e); time.sleep(3 + 5 * t)
    else: raise SystemExit(f'{sgg} {ym} 받기 실패')
    txt = x.decode('utf-8', 'replace')
    try: root = ET.fromstring(x)
    except ET.ParseError: raise SystemExit(f'{sgg} {ym} 응답이 XML이 아니에요: {txt[:300]}')
    code = g(root, './/resultCode')
    if not code and call.first and URL != URLS[-1] and '<returnReasonCode>' in txt:
        print('상세판 응답 이상 → 일반판으로 바꿔서 다시 받아요:', txt[:200].replace('\n', ' '))
        URL = URLS[URLS.index(URL) + 1]; return call(sgg, ym, page, rows)
    if not code:  # 인증키 오류·호출 한도 초과 등은 resultCode 없이 다른 모양으로 옴
        if 'LIMITED' in txt or 'EXCEEDS' in txt:
            print('오늘 호출 한도에 닿았어요. 내일 이어서 받아요.'); raise OutOfBudget()
        raise SystemExit(f'{sgg} {ym} 응답 이상 (인증키·활용신청 확인): {txt[:400]}')
    if call.first: print('첫 응답 예시:', txt[:400]); call.first = False
    if code not in ('00', '000'):
        if code == '22': print('오늘 호출 한도 초과(22). 내일 이어서 받아요.'); raise OutOfBudget()
        raise SystemExit(f'{sgg} {ym} 오류 {code} {g(root, ".//resultMsg")}')
    return root
call.first = True

def fetch(sgg, ym):
    rows, page = [], 1
    while True:
        root = call(sgg, ym, page); items = root.findall('.//item'); rows += items
        total = int(g(root, './/totalCount') or 0)
        if page * 1000 >= total or not items: return rows
        page += 1; time.sleep(0.2)

def norm_jb(s):
    s = (s or '').replace(' ', '')
    if '-' in s:
        a, b = s.split('-', 1); b = b.lstrip('0') or '0'
        s = (a.lstrip('0') or '0') + ('' if b == '0' else '-' + b)
    else: s = s.lstrip('0') or s
    return s

def rec(it, ym):
    amt = g(it, 'dealAmount', '거래금액').replace(',', '')
    y, m, d = g(it, 'dealYear', '년'), g(it, 'dealMonth', '월'), g(it, 'dealDay', '일')
    jb = g(it, 'jibun', '지번')
    if not jb:
        bo, bu = g(it, 'bonbun', '법정동본번코드'), g(it, 'bubun', '법정동부번코드')
        if bo: jb = f'{int(bo)}' + (f'-{int(bu)}' if bu and int(bu) else '')
    return {
        'ym': ym, 'umdCd': g(it, 'umdCd', '법정동읍면동코드'), 'umd': g(it, 'umdNm', '법정동').split(' ')[-1], 'jb': norm_jb(jb),
        'n': g(it, 'aptNm', '아파트'), 'by': g(it, 'buildYear', '건축년도'),
        'd': f'{y}{int(m or 0):02d}{int(d or 0):02d}' if y else '',
        'f': g(it, 'floor', '층'), 'a': g(it, 'excluUseAr', '전용면적'),
        'p': int(amt) if amt.isdigit() else 0,
        'c': 1 if g(it, 'cdealType', '해제여부') in ('O', 'o') else 0,
        'k': g(it, 'dealingGbn', '거래유형'),
    }

def codes():
    # 바뀐 행정구역의 새 코드를 한 번 찾아 _codes.json에 저장 (지난달 거래가 1건이라도 있으면 사용)
    if os.path.exists(CODES):
        return json.load(open(CODES, encoding='utf-8'))['codes']
    found = []; ym = months(2)[1]
    for c in CAND:
        if c in SGG: continue
        root = call(c, ym, 1, rows=1)
        if int(g(root, './/totalCount') or 0) > 0: found.append(c); print('새 시군구 코드 발견', c)
        time.sleep(0.1)
    out = SGG + found
    json.dump({'checked': datetime.date.today().isoformat(), 'added': found, 'codes': out}, open(CODES, 'w', encoding='utf-8'), ensure_ascii=False)
    return out

def save_sgg(sgg, new_rows, yms):
    # 읍면동별 파일로 나눠 저장. 이번에 받은 달은 갈아 끼우고, 36개월보다 오래된 건 버림
    keep = set(months(KEEP)); d = os.path.join(OUT, sgg); os.makedirs(d, exist_ok=True)
    old = []
    for f in glob.glob(os.path.join(d, '*.json')):
        old += json.load(open(f, encoding='utf-8')).get('rows', []); os.remove(f)
    legacy = os.path.join(OUT, f'{sgg}.json')   # 예전 경북용 한 파일짜리
    if os.path.exists(legacy):
        old += json.load(open(legacy, encoding='utf-8')).get('rows', []); os.remove(legacy)
    rows = [r for r in old if r['ym'] in keep and r['ym'] not in yms] + new_rows
    by = {}
    for r in rows: by.setdefault(r['umdCd'] or '00000', []).append(r)
    today = datetime.date.today().isoformat()
    for umd, rs in by.items():
        rs.sort(key=lambda r: r['d'], reverse=True)
        json.dump({'sgg': sgg, 'umd': umd, 'updated': today, 'rows': rs},
                  open(os.path.join(d, f'{umd}.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return len(rows)

def write_index():
    cnt = {}
    for d in sorted(glob.glob(os.path.join(OUT, '[0-9]' * 5))):
        n = 0
        for f in glob.glob(os.path.join(d, '*.json')): n += len(json.load(open(f, encoding='utf-8')).get('rows', []))
        cnt[os.path.basename(d)] = n
    json.dump({'updated': datetime.date.today().isoformat(), 'count': cnt},
              open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    return cnt

def main():
    if not KEY: raise SystemExit('DATA_GO_KR_KEY 가 없어요')
    os.makedirs(OUT, exist_ok=True)
    prog = json.load(open(PROG, encoding='utf-8')) if os.path.exists(PROG) else None
    if ARG == 'auto':
        if not prog:
            if datetime.date.today().day != 5: print('이어 받을 것도 없고 갱신일(5일)도 아니에요. 끝.'); return
            prog = {'months': months(3), 'done': []}
    else:
        prog = {'months': months(int(ARG)), 'done': []}   # 새로 시작
    yms = prog['months']
    try:
        todo = [c for c in codes() if c not in prog['done']]
        print(f'{len(yms)}개월 · 남은 시군구 {len(todo)}곳 · 이번 실행 호출 한도 {BUDGET}')
        for sgg in todo:
            if calls + len(yms) > BUDGET: raise OutOfBudget()
            rows = []
            for ym in yms:
                rows += [rec(it, ym) for it in fetch(sgg, ym)]; time.sleep(0.15)
            n = save_sgg(sgg, rows, set(yms)); prog['done'].append(sgg)
            json.dump(prog, open(PROG, 'w', encoding='utf-8'), ensure_ascii=False)
            print(sgg, '새로', len(rows), '건 · 보관', n, '건 · 누적 호출', calls)
    except OutOfBudget:
        json.dump(prog, open(PROG, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'이번엔 여기까지 (호출 {calls}번). 끝낸 시군구 {len(prog["done"])}곳. 다음 실행에서 이어서 받아요.')
        write_index(); return
    os.remove(PROG) if os.path.exists(PROG) else None
    cnt = write_index()
    print('다 받았어요. 시군구', len(cnt), '곳 · 거래', sum(cnt.values()), '건 · 호출', calls, '번')
    if not sum(cnt.values()): raise SystemExit('받은 거래가 0건이에요. 위의 첫 응답 예시를 확인해 주세요.')

main()
