// Поведенческие события для ленты «Для вас» (docs/data-collection.md, раздел 6).
// Включается, только если сервер отдал data-events-url: человек вошёл и принял текущее согласие.
const url = document.body.dataset.eventsUrl;
const surface = document.body.dataset.surface || 'other';
// Порция ленты: повторный показ поста в ней не считается (сервер отбрасывает тоже).
const feed = crypto.randomUUID ? crypto.randomUUID() : null;

const VISIBLE = 0.5;
const IMPRESSION_MS = 1000;
const FLUSH_MS = 12000;
const BATCH = 50;
const DWELL_MAX = 600;

const queue = [];
const shown = new Set();
// Карточка → { since: когда стала видна, timer: до засчитанного показа }.
const onScreen = new Map();

function csrfToken() {
	try {
		return JSON.parse(document.body.getAttribute('hx-headers'))['X-CSRFToken'];
	} catch (e) {
		return '';
	}
}

function flush() {
	if (!queue.length) return;
	const batch = queue.splice(0, BATCH);
	// keepalive: запрос переживает закрытие вкладки, как sendBeacon, но с заголовком CSRF.
	fetch(url, {
		method: 'POST',
		keepalive: true,
		credentials: 'same-origin',
		headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
		body: JSON.stringify(batch),
	}).catch(() => { /* событие не критично — потеряли и ладно */ });
	if (queue.length) flush();
}

function push(event) {
	queue.push({ surface, ...event });
	if (queue.length >= BATCH) flush();
}

function postOf(card) {
	return card.dataset.postId;
}

function position(card) {
	return Array.prototype.indexOf.call(document.querySelectorAll('[data-post-id]'), card);
}

function leave(card) {
	const state = onScreen.get(card);
	if (!state) return;
	clearTimeout(state.timer);
	onScreen.delete(card);
	const seconds = Math.min(DWELL_MAX, Math.round((Date.now() - state.since) / 1000));
	if (seconds >= 1) push({ kind: 'dwell', post: postOf(card), feed, seconds });
}

function enter(card) {
	if (onScreen.has(card)) return;
	const state = { since: Date.now(), timer: null };
	state.timer = setTimeout(() => {
		const post = postOf(card);
		if (shown.has(post)) return;
		shown.add(post);
		push({ kind: 'impression', post, feed, position: position(card) });
	}, IMPRESSION_MS);
	onScreen.set(card, state);
}

const observer = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
	entries.forEach((entry) => {
		if (entry.isIntersecting && entry.intersectionRatio >= VISIBLE && document.visibilityState === 'visible') enter(entry.target);
		else leave(entry.target);
	});
}, { threshold: [0, VISIBLE] }) : null;

function observe(root) {
	if (!observer) return;
	if (root.matches && root.matches('article[data-post-id]')) observer.observe(root);
	root.querySelectorAll('article[data-post-id]').forEach((card) => observer.observe(card));
}

function clickEvent(event) {
	const link = event.target.closest('a, [data-lightbox]');
	if (!link) return null;
	const card = link.closest('[data-post-id]');
	if (surface === 'search' && !card) {
		if (link.classList.contains('who-row')) return { kind: 'search_click', result: 'person' };
		if (link.classList.contains('tag-row')) return { kind: 'search_click', result: 'tag' };
		return null;
	}
	if (!card) return null;
	const post = postOf(card);
	if (link.hasAttribute('data-lightbox')) return { kind: 'media_open', post, index: Number(link.dataset.lightbox) || 0 };
	if (link.classList.contains('tag-link')) return { kind: 'tag_click', post, tag: link.textContent.replace(/^#/, '').toLowerCase() };
	const href = link.getAttribute('href') || '';
	if (href.startsWith('/users/')) return { kind: 'profile_click', post };
	if (link.host && link.host !== location.host) return { kind: 'link_click', post, domain: link.hostname };
	if (surface === 'search' && href.startsWith('/p/')) return { kind: 'search_click', result: 'post', post, position: position(card) };
	return null;
}

if (url) {
	observe(document);
	document.addEventListener('htmx:load', (event) => observe(event.target));
	document.addEventListener('click', (event) => {
		const tracked = clickEvent(event);
		if (tracked) push(tracked);
	}, { capture: true });
	setInterval(flush, FLUSH_MS);
	document.addEventListener('visibilitychange', () => {
		if (document.visibilityState === 'hidden') {
			Array.from(onScreen.keys()).forEach(leave);
			flush();
		} else if (observer) {
			// Видимые карточки снова считаем видимыми: наблюдатель сам не перешлёт их состояние.
			observer.takeRecords();
			document.querySelectorAll('article[data-post-id]').forEach((card) => { observer.unobserve(card); observer.observe(card); });
		}
	});
	window.addEventListener('pagehide', () => {
		Array.from(onScreen.keys()).forEach(leave);
		flush();
	});
}
