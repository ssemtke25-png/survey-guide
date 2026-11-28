# 경북 아파트 매매 실거래가 모으기 (국토교통부_아파트 매매 실거래가 상세 자료, 공공데이터포털)
# 사용 : DATA_GO_KR_KEY=키 python scripts/apt_fetch.py 3   ← 최근 3개월 다시 받기 (처음엔 36)
import os, sys, json, time, datetime, urllib.request, urllib.parse, xml.etree.ElementTree as ET

KEY = os.environ.get('DATA_GO_KR_KEY', '').strip()
MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
KEEP = 36  # 파일에 남겨 둘 개월 수
URLS = ['https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',  # 상세판
        'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade']        # 일반판 (상세판이 안 될 때)
URL = URLS[0]
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'apt')
# 경북 시군구 (직제순)
SGG = ['47111','47113','47130','47150','47170','47190','47210','47230','47250','47280','47290',
       '47730','47750','47760','47770','47820','47830','47840','47850','47900','47920','47930','47940']

def months(n):
    d = datetime.date.today().replace(day=1); out = []
    for _ in range(n):
        out.append(d.strftime('%Y%m')); d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out

def g(it, *names):
    for n in names:
        e = it.find(n)
        if e is not None and e.text and e.text.strip(): return e.text.strip()
    return ''

def switch():
    global URL
    URL = URLS[URLS.index(URL) + 1]

def fetch(sgg, ym):
    global URL
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({'serviceKey': KEY, 'LAWD_CD': sgg, 'DEAL_YMD': ym, 'numOfRows': 1000, 'pageNo': page})
        for t in range(3):
            try:
                with urllib.request.urlopen(URL + '?' + q, timeout=30) as r: x = r.read(); break
            except Exception as e:
                print('  재시도', sgg, ym, e); time.sleep(3)
        else: raise SystemExit(f'{sgg} {ym} 받기 실패')
        txt = x.decode('utf-8', 'replace')
        try: root = ET.fromstring(x)
        except ET.ParseError: raise SystemExit(f'{sgg} {ym} 응답이 XML이 아니에요: {txt[:300]}')
        code = g(root, './/resultCode')
        if not code and fetch.first and URL != URLS[-1] and '<returnReasonCode>' in txt:
            print('상세판 응답 이상 → 일반판으로 바꿔서 다시 받아요:', txt[:200].replace('\n', ' '))
            switch(); continue
        if not code:  # 인증키 오류 등은 resultCode 없이 다른 모양으로 옴
            raise SystemExit(f'{sgg} {ym} 응답 이상 (인증키·활용신청 확인): {txt[:400]}')
        if fetch.first:
            print('첫 응답 예시:', txt[:600]); fetch.first = False
        if code not in ('00', '000'):
            raise SystemExit(f'{sgg} {ym} 오류 {code} {g(root, ".//resultMsg")}')
        items = root.findall('.//item'); rows += items
        total = int(g(root, './/totalCount') or 0)
        if page * 1000 >= total or not items: return rows
        page += 1; time.sleep(0.3)

def norm_jb(s):
    s = (s or '').replace(' ', '')
    if '-' in s:
        a, b = s.split('-', 1); b = b.lstrip('0') or '0'
        s = (a.lstrip('0') or '0') + ('' if b == '0' else '-' + b)
    else: s = s.lstrip('0') or s
    return s

fetch.first = True

def rec(it, ym):
    amt = g(it, 'dealAmount', '거래금액').replace(',', '')
    y, m, d = g(it, 'dealYear', '년'), g(it, 'dealMonth', '월'), g(it, 'dealDay', '일')
    umd_cd = g(it, 'umdCd', '법정동읍면동코드')
    umd_nm = g(it, 'umdNm', '법정동').split(' ')[-1]
    jb = g(it, 'jibun', '지번')
    if not jb:
        bo, bu = g(it, 'bonbun', '법정동본번코드'), g(it, 'bubun', '법정동부번코드')
        if bo: jb = f'{int(bo)}' + (f'-{int(bu)}' if bu and int(bu) else '')
    return {
        'ym': ym, 'umdCd': umd_cd, 'umd': umd_nm, 'jb': norm_jb(jb),
        'n': g(it, 'aptNm', '아파트'), 'by': g(it, 'buildYear', '건축년도'),
        'd': f'{y}{int(m or 0):02d}{int(d or 0):02d}' if y else '',
        'f': g(it, 'floor', '층'), 'a': g(it, 'excluUseAr', '전용면적'),
        'p': int(amt) if amt.isdigit() else 0,
        'c': 1 if g(it, 'cdealType', '해제여부') in ('O', 'o') else 0,
        'k': g(it, 'dealingGbn', '거래유형'),
    }

def main():
    if not KEY: raise SystemExit('DATA_GO_KR_KEY 가 없어요')
    os.makedirs(OUT, exist_ok=True)
    yms = months(MONTHS); keep = set(months(KEEP)); calls = 0; summary = {}
    for sgg in SGG:
        path = os.path.join(OUT, f'{sgg}.json')
        old = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {'rows': []}
        rows = [r for r in old.get('rows', []) if r['ym'] in keep and r['ym'] not in yms]
        for ym in yms:
            items = fetch(sgg, ym); calls += 1
            rows += [rec(it, ym) for it in items]
            time.sleep(0.2)
        rows.sort(key=lambda r: r['d'], reverse=True)
        json.dump({'sgg': sgg, 'updated': datetime.date.today().isoformat(), 'rows': rows},
                  open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        summary[sgg] = len(rows); print(sgg, len(rows), '건')
    json.dump({'updated': datetime.date.today().isoformat(), 'count': summary},
              open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('API 호출', calls, '번')
    if not sum(summary.values()):
        raise SystemExit('받은 거래가 0건이에요. 위의 첫 응답 예시를 확인해 주세요.')

main()
