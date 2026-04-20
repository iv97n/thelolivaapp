const CACHE_NAME = 'thelolivaapp-cache-v4';

// Assets to cache immediately on SW install
const PRECACHE_ASSETS = [
    '/',
    '/index.html',
    '/styles.css',
    '/app.js',
    '/manifest.json',
    '/icon.svg',
    '/world.svg'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(PRECACHE_ASSETS);
            })
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    // Clean up old caches if CACHE_NAME changes
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Network-first strategy with cache fallback
self.addEventListener('fetch', event => {
    // Only handle GET requests
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request)
            .then(networkResponse => {
                // Optionally update cache here
                const responseClone = networkResponse.clone();
                caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, responseClone);
                });
                return networkResponse;
            })
            .catch(() => {
                // Fallback to cache
                return caches.match(event.request);
            })
    );
});

self.addEventListener('push', event => {
    if (!event.data) return;
    const { title, body } = event.data.json();
    event.waitUntil(
        self.registration.showNotification(title, {
            body,
            icon:    '/logo.png',
            badge:   '/logo.png',
            vibrate: [200, 100, 200],
        })
    );
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil(clients.openWindow('/'));
});
