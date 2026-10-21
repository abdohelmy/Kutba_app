// Only the public app shell and immutable assets are cached. Never cache API/auth data.
const CACHE = "khutba-shell-v1";
self.addEventListener("message",event=>{
 if(event.data?.type!=="CACHE_SHELL_ASSETS"||!Array.isArray(event.data.urls))return;
 const urls=event.data.urls.filter(value=>{try{const url=new URL(value);return url.origin===self.location.origin&&/^\/(assets\/|_next\/static\/)/.test(url.pathname);}catch{return false;}}).slice(0,100);
 event.waitUntil(caches.open(CACHE).then(async cache=>{await Promise.all(urls.map(async url=>{try{const response=await fetch(url);if(response.ok&&!response.redirected)await cache.put(url,response);}catch{}}));}));
});
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      for (const path of [
        "/",
        "/app-icon.png",
        "/favicon.svg",
        "/manifest.webmanifest",
      ]) {
        try {
          const response = await fetch(path, { cache: "reload" });
          if (response.ok && !response.redirected)
            await cache.put(path, response);
        } catch {}
      }
    })(),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys())
        if (key.startsWith("khutba-shell-") && key !== CACHE)
          await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});
self.addEventListener("fetch", (event) => {
  const request = event.request,
    url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname.includes("auth")
  )
    return;
  if (request.mode === "navigate" && url.pathname === "/") {
    event.respondWith(
      fetch(request)
        .then(async (response) => {
          if (response.ok && !response.redirected) {
            const cache = await caches.open(CACHE);
            await cache.put("/", response.clone());
          }
          return response;
        })
        .catch(async () => (await caches.match("/")) || Response.error()),
    );
    return;
  }
  if (/^\/(assets\/|_next\/static\/)/.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then(async (response) => {
            if (response.ok) {
              const cache = await caches.open(CACHE);
              await cache.put(request, response.clone());
            }
            return response;
          }),
      ),
    );
  }
});
