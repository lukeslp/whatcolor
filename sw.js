const CACHE_NAME = 'whatcolor-v3';
const SHARE_CACHE = 'whatcolor-shares';
const PRECACHE = ['/', '/index.html', '/manifest.json', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(PRECACHE)));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME && k !== SHARE_CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // Handle share_target POST: cache the shared image, redirect to app
    if (url.pathname === '/' && url.searchParams.get('share') === 'true' && e.request.method === 'POST') {
        e.respondWith((async () => {
            const formData = await e.request.formData();
            const image = formData.get('image');
            if (image) {
                const cache = await caches.open(SHARE_CACHE);
                await cache.put('shared-image', new Response(image));
            }
            return Response.redirect('/?share=true', 303);
        })());
        return;
    }

    // Always go to network for API calls
    if (url.pathname.includes('/api/')) return;

    e.respondWith(
        fetch(e.request).then(r => {
            if (r.ok) {
                const clone = r.clone();
                caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
            }
            return r;
        }).catch(() => caches.match(e.request))
    );
});
