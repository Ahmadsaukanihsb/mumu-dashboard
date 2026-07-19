const CACHE_NAME = 'roblox-dashboard-v1';
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/script.js',
  '/static/manifest.json'
];

const API_CACHE = 'roblox-dashboard-api-v1';
const API_ROUTES = ['/api/summary', '/api/inventory', '/api/item-thumbnails'];

// Install event
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// Activate event
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(cacheName => cacheName !== CACHE_NAME && cacheName !== API_CACHE)
          .map(cacheName => caches.delete(cacheName))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // API requests - network first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(API_CACHE).then(cache => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
    return;
  }

  // Static assets - cache first, fallback to network
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).then(response => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then(cache => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        });
      })
      .catch(() => {
        if (event.request.destination === 'document') {
          return caches.match('/');
        }
      })
  );
});

// Push notification
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Dashboard Roblox';
  const options = {
    body: data.body || 'New notification',
    icon: '/static/icons/icon-192x192.svg',
    badge: '/static/icons/icon-72x72.svg',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/'
    },
    actions: [
      { action: 'open', title: 'Buka Dashboard' },
      { action: 'dismiss', title: 'Tutup' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.openWindow(event.notification.data.url)
    );
  }
});

// Background sync for offline actions
self.addEventListener('sync', event => {
  if (event.tag === 'sync-inventory') {
    event.waitUntil(syncInventory());
  }
});

async function syncInventory() {
  const cache = await caches.open(API_CACHE);
  const requests = await cache.keys();
  
  for (const request of requests) {
    if (request.url.includes('/api/inventory')) {
      try {
        await fetch(request);
      } catch (e) {
        console.log('Sync failed:', e);
      }
    }
  }
}
