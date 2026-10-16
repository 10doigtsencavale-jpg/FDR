const C="fdr-v4";
self.addEventListener("install",e=>{self.skipWaiting()});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener("fetch",e=>{
  const r=e.request;if(r.method!=="GET")return;
  const u=new URL(r.url);
  if(u.origin!==location.origin&&!u.hostname.endsWith("cdnjs.cloudflare.com")&&!u.hostname.endsWith("gstatic.com")&&!u.hostname.endsWith("googleapis.com"))return;
  // network first (fresh data), cache fallback (offline at the venue)
  e.respondWith(fetch(r).then(res=>{if(res.ok){const cp=res.clone();caches.open(C).then(c=>c.put(r,cp))}return res}).catch(()=>caches.match(r)));
});
