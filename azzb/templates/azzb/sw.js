'use strict';
// Сервис-воркер AzzB (PWA). Кэширует только статику и офлайн-страницу: в страницах и ответах API — личное,
// им место только в сети. Новая версия статики (другие хеши в именах) — новый воркер и новый кэш.
const CACHE = 'azzb-{{ version|escapejs }}';
const OFFLINE_URL = '{{ offline_url|escapejs }}';
const PRECACHE = {% autoescape off %}{{ precache }}{% endautoescape %};  // JSON-список адресов
const HASHED = /\.[0-9a-f]{12}\.[a-z0-9]+$/;

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches.open(CACHE)
			.then((cache) => cache.addAll([OFFLINE_URL, ...PRECACHE]))
			.then(() => self.skipWaiting()),
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		// Navigation preload: браузер шлёт запрос страницы, не дожидаясь запуска воркера, —
		// иначе после простоя (воркер останавливается через ~30 с) навигация ждёт его старта.
		(self.registration.navigationPreload ? self.registration.navigationPreload.enable() : Promise.resolve())
			.then(() => caches.keys())
			.then((keys) => Promise.all(keys.filter((key) => key.startsWith('azzb-') && key !== CACHE).map((key) => caches.delete(key))))
			.then(() => self.clients.claim()),
	);
});

async function cacheFirst(request) {
	const cache = await caches.open(CACHE);
	const hit = await cache.match(request);
	if (hit) return hit;
	const response = await fetch(request);
	if (response.ok) cache.put(request, response.clone());
	return response;
}

// Страница — из сети: ответ, уже начатый браузером (navigation preload), или свой запрос; без связи — офлайн-страница.
async function navigate(event) {
	try {
		return (await event.preloadResponse) || await fetch(event.request);
	} catch (error) {
		return caches.match(OFFLINE_URL);
	}
}

self.addEventListener('fetch', (event) => {
	const request = event.request;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;
	if (request.mode === 'navigate') {
		event.respondWith(navigate(event));
	} else if (url.pathname.startsWith('{{ static_prefix|escapejs }}')) {
		// Файл с хешем в имени не меняется никогда; без хеша (разработка) — сначала сеть.
		event.respondWith(HASHED.test(url.pathname)
			? cacheFirst(request)
			: fetch(request).catch(() => caches.match(request)));
	}
});
