'use strict';
// Общий JS AzzB: меню, тема, composer, лайки, удаление, тосты. Без зависимостей.

(function () {
	const POST_MAX = 500;

	function getCookie(name) {
		const match = document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith(name + '='));
		return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
	}

	async function api(url, data) {
		const response = await fetch(url, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
			body: JSON.stringify(data),
			credentials: 'same-origin',
		});
		return response;
	}

	// ---------- Тосты ----------
	let toastTimer = null;
	function toast(message) {
		let el = document.getElementById('toast');
		if (!el) return;
		el.textContent = message;
		el.hidden = false;
		clearTimeout(toastTimer);
		toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
	}
	window.azzbToast = toast;

	// ---------- Меню ----------
	function closeMenus(except) {
		document.querySelectorAll('[data-menu-toggle][aria-expanded="true"]').forEach((btn) => {
			if (btn === except) return;
			btn.setAttribute('aria-expanded', 'false');
			const menu = document.getElementById(btn.getAttribute('aria-controls'));
			if (menu) menu.hidden = true;
		});
	}

	function toggleMenu(btn) {
		const menu = document.getElementById(btn.getAttribute('aria-controls'));
		if (!menu) return;
		const open = btn.getAttribute('aria-expanded') !== 'true';
		closeMenus(btn);
		btn.setAttribute('aria-expanded', String(open));
		menu.hidden = !open;
		if (open) {
			const first = menu.querySelector('[role^="menuitem"]');
			if (first) first.focus();
		}
	}

	// ---------- Тема ----------
	const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
	function isDark() {
		const chosen = document.documentElement.dataset.theme;
		return chosen ? chosen === 'dark' : darkQuery.matches;
	}
	function syncThemeToggles() {
		const dark = String(isDark());
		document.querySelectorAll('[data-theme-toggle]').forEach((el) => el.setAttribute('aria-checked', dark));
	}
	function toggleTheme() {
		const next = isDark() ? 'light' : 'dark';
		document.documentElement.dataset.theme = next;
		// Cookie нужна серверу, чтобы сразу отдать страницу в нужной теме, без мигания.
		document.cookie = 'theme=' + next + '; path=/; max-age=31536000; SameSite=Lax';
		syncThemeToggles();
	}
	darkQuery.addEventListener('change', syncThemeToggles);

	// ---------- Composer ----------
	const composer = () => document.getElementById('composer');
	let lastFocus = null;

	function openComposer() {
		const modal = composer();
		if (!modal) return;
		lastFocus = document.activeElement;
		modal.hidden = false;
		document.body.classList.add('modal-open');
		closeMenus();
		const textarea = modal.querySelector('textarea');
		updateCounter(textarea);
		textarea.focus();
	}

	function closeComposer() {
		const modal = composer();
		if (!modal || modal.hidden) return;
		modal.hidden = true;
		document.body.classList.remove('modal-open');
		if (lastFocus) lastFocus.focus();
	}

	function updateCounter(textarea) {
		const form = textarea.closest('form');
		const n = textarea.value.length;
		const counter = form.querySelector('[data-counter]');
		counter.textContent = n + ' / ' + POST_MAX;
		counter.classList.toggle('warn', n > POST_MAX - 50 && n <= POST_MAX);
		counter.classList.toggle('over', n > POST_MAX);
		form.querySelector('[type="submit"]').disabled = !textarea.value.trim() || n > POST_MAX;
	}

	async function submitComposer(form) {
		const textarea = form.querySelector('textarea');
		const button = form.querySelector('[type="submit"]');
		const error = form.querySelector('[data-composer-error]');
		button.disabled = true;
		error.hidden = true;
		try {
			const response = await api(form.action, { text: textarea.value });
			if (!response.ok) throw new Error('status ' + response.status);
			const html = await response.text();
			const feed = document.querySelector('[data-feed-prepend]');
			if (feed) {
				const empty = feed.querySelector('[data-feed-empty]');
				if (empty) empty.remove();
				feed.insertAdjacentHTML('afterbegin', html);
			}
			textarea.value = '';
			closeComposer();
			toast('Пост опубликован');
		} catch (e) {
			error.hidden = false;
		} finally {
			updateCounter(textarea);
		}
	}

	// ---------- Посты ----------
	async function like(btn) {
		const post = btn.closest('[data-post-id]');
		btn.disabled = true;
		try {
			const response = await api('/api/like-post/', { id: post.dataset.postId });
			if (!response.ok) throw new Error('status ' + response.status);
			const data = await response.json();
			btn.classList.toggle('liked', data.liked);
			btn.setAttribute('aria-pressed', String(data.liked));
			btn.querySelector('[data-like-count]').textContent = data.likes_count || '';
		} catch (e) {
			toast('Не удалось поставить лайк');
		} finally {
			btn.disabled = false;
		}
	}

	async function removePost(btn) {
		const post = btn.closest('[data-post-id]');
		closeMenus();
		if (!window.confirm('Удалить пост? Это нельзя отменить.')) return;
		try {
			const response = await api('/api/delete-post/', { id: post.dataset.postId });
			if (!response.ok) throw new Error('status ' + response.status);
			post.remove();
			toast('Пост удалён');
		} catch (e) {
			toast('Не удалось удалить пост');
		}
	}

	async function copyLink(btn) {
		closeMenus();
		const url = new URL(btn.dataset.copy, window.location.origin).href;
		try {
			await navigator.clipboard.writeText(url);
			toast('Ссылка скопирована');
		} catch (e) {
			window.prompt('Скопируйте ссылку', url);
		}
	}

	// ---------- «Показать ещё» и бесконечная прокрутка ----------
	// Кнопка — обычная ссылка на следующую страницу: без JS она просто открывает её.
	// С JS подгружаем только порцию карточек и подменяем кнопку на неё.
	async function loadMore(link) {
		if (link.dataset.loading) return;
		link.dataset.loading = '1';
		link.setAttribute('aria-busy', 'true');
		link.textContent = 'Загрузка…';
		try {
			const response = await fetch(link.href, {
				headers: { 'X-Requested-With': 'azzb-load-more' },
				credentials: 'same-origin',
			});
			if (!response.ok) throw new Error('status ' + response.status);
			const html = await response.text();
			link.insertAdjacentHTML('beforebegin', html);
			if (loadMoreObserver) loadMoreObserver.unobserve(link);
			link.remove();
			observeLoadMore();
		} catch (e) {
			delete link.dataset.loading;
			link.removeAttribute('aria-busy');
			link.textContent = 'Показать ещё';
			toast('Не удалось загрузить посты');
		}
	}

	const loadMoreObserver = 'IntersectionObserver' in window
		? new IntersectionObserver((entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) loadMore(entry.target);
			});
		}, { rootMargin: '600px 0px' })
		: null;

	function observeLoadMore() {
		if (!loadMoreObserver) return;
		document.querySelectorAll('[data-load-more]:not([data-observed])').forEach((link) => {
			link.dataset.observed = '1';
			loadMoreObserver.observe(link);
		});
	}

	// ---------- Делегирование событий ----------
	document.addEventListener('click', (event) => {
		const target = event.target.closest('button, a');
		if (!target) {
			if (!event.target.closest('[role="menu"]')) closeMenus();
			const modal = composer();
			if (modal && event.target === modal) closeComposer();
			return;
		}
		if (target.matches('[data-menu-toggle]')) { event.preventDefault(); toggleMenu(target); return; }
		if (target.matches('[data-theme-toggle]')) { event.preventDefault(); toggleTheme(); return; }
		if (target.matches('[data-composer-open]')) { event.preventDefault(); openComposer(); return; }
		if (target.matches('[data-composer-close]')) { event.preventDefault(); closeComposer(); return; }
		if (target.matches('[data-like]')) { event.preventDefault(); like(target); return; }
		if (target.matches('[data-delete]')) { event.preventDefault(); removePost(target); return; }
		if (target.matches('[data-copy]')) { event.preventDefault(); copyLink(target); return; }
		if (target.matches('[data-load-more]')) { event.preventDefault(); loadMore(target); return; }
		if (!target.closest('[role="menu"]')) closeMenus();
	});

	document.addEventListener('keydown', (event) => {
		if (event.key !== 'Escape') return;
		closeMenus();
		closeComposer();
	});

	document.addEventListener('input', (event) => {
		if (event.target.matches('[data-composer-text]')) updateCounter(event.target);
	});

	document.addEventListener('submit', (event) => {
		if (event.target.matches('[data-composer-form]')) {
			event.preventDefault();
			submitComposer(event.target);
		}
	});

	document.addEventListener('DOMContentLoaded', () => {
		syncThemeToggles();
		observeLoadMore();
	});
})();
