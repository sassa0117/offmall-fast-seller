const CACHE_NAME = 'fast-seller-v1';
const APP_SHELL = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];

// インストール時にApp Shellをキャッシュ
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

// 古いキャッシュを削除
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// ネットワークファースト戦略（APIはキャッシュしない）
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // APIリクエストはネットワークのみ
    if (url.pathname.startsWith('/api/')) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // 成功したらキャッシュを更新
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            })
            .catch(() => {
                // オフライン時はキャッシュから返す
                return caches.match(event.request);
            })
    );
});
