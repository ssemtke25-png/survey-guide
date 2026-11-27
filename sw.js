// 홈 화면 앱용 : 우리 파일만 잠깐 저장 (지도·브이월드 자료는 항상 새로 받음)
const V='sg-v15',FILES=['./','index.html','config.js','contacts.js','lx.js','manifest.webmanifest','icon-192.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(FILES)).catch(()=>{}));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))));self.clients.claim()});
// 새 버전이 먼저 : 인터넷이 되면 항상 새 파일, 안 되면 저장해 둔 파일
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==location.origin)return;
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(V).then(x=>x.put(e.request,c));return r}).catch(()=>caches.match(e.request)))});
