'use strict';
// Общий JS AzzB: меню, тема, composer, картинки, лайки, удаление, тосты. Без зависимостей.

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

	// Сообщения об ошибке из ответа сервера: {"errors": [...]} или запасной текст.
	async function errorsOf(response, fallback) {
		if (response.status === 413) return ['Файлы слишком тяжёлые для отправки.'];
		try {
			const data = await response.json();
			if (Array.isArray(data.errors) && data.errors.length) return data.errors;
		} catch (e) { /* не JSON */ }
		return [fallback];
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

	// ---------- Модальные окна ----------
	function syncModalOpen() {
		const anyOpen = Array.from(document.querySelectorAll('.modal, .lightbox')).some((el) => !el.hidden);
		document.body.classList.toggle('modal-open', anyOpen);
	}

	// ---------- Composer ----------
	const composer = () => document.getElementById('composer');
	let lastFocus = null;
	// Выбранные картинки по формам: [{file, url, alt}]. Порядок = порядок в посте.
	const attachments = new WeakMap();

	function filesOf(form) {
		if (!attachments.has(form)) attachments.set(form, []);
		return attachments.get(form);
	}

	// Composer один на страницу, а писать можно новый пост или ответ на любой пост.
	// Черновик у каждой цели свой: начатый пост не уедет ответом и наоборот.
	// Ключ: '' — новый пост, иначе id поста, на который отвечаем.
	const drafts = new Map();
	let composerTarget = '';

	function switchComposerTarget(form, target) {
		if (target === composerTarget) return;
		collectAlts(form);
		const textarea = form.querySelector('textarea');
		drafts.set(composerTarget, { text: textarea.value, files: filesOf(form) });
		const next = drafts.get(target) || { text: '', files: [] };
		drafts.delete(target);
		textarea.value = next.text;
		attachments.set(form, next.files);
		composerTarget = target;
		renderAttachments(form);
		showComposerError(form, null);
	}

	function openComposer(reply) {
		const modal = composer();
		if (!modal) return;
		const form = modal.querySelector('form');
		const target = reply ? reply.id : '';
		switchComposerTarget(form, target);
		form.querySelector('[data-composer-reply-to]').value = target;
		const replying = form.querySelector('[data-composer-replying]');
		replying.hidden = !reply;
		form.querySelector('[data-composer-replying-name]').textContent = reply ? reply.name : '';
		modal.querySelector('[data-composer-title]').textContent = reply ? 'Ответ' : 'Новый пост';
		const textarea = form.querySelector('textarea');
		textarea.placeholder = reply ? 'Ваш ответ' : textarea.dataset.placeholder || textarea.placeholder;
		form.querySelector('[type="submit"]').textContent = reply ? 'Ответить' : 'Опубликовать';
		lastFocus = document.activeElement;
		modal.hidden = false;
		syncModalOpen();
		closeMenus();
		updateCounter(form);
		textarea.focus();
	}

	function openReply(btn) {
		const card = btn.closest('[data-post-id]');
		const id = btn.dataset.replyTo || (card && card.dataset.postId);
		if (id) openComposer({ id: id, name: btn.dataset.replyName || '' });
	}

	function bumpReplyCount(postId, delta) {
		document.querySelectorAll('[data-post-id="' + postId + '"] [data-reply-count]').forEach((el) => {
			const n = Math.max(0, (Number(el.textContent) || 0) + delta);
			el.textContent = n ? String(n) : '';
		});
	}

	function closeComposer() {
		const modal = composer();
		if (!modal || modal.hidden) return;
		modal.hidden = true;
		syncModalOpen();
		if (lastFocus) lastFocus.focus();
	}

	function showComposerError(form, messages) {
		const error = form.querySelector('[data-composer-error]');
		const text = form.querySelector('[data-composer-error-text]');
		if (!messages || !messages.length) { error.hidden = true; return; }
		text.textContent = messages.join(' ');
		error.hidden = false;
	}

	function updateCounter(form) {
		const textarea = form.querySelector('textarea');
		const max = Number(form.dataset.maxLength) || POST_MAX;
		const n = textarea.value.length;
		const counter = form.querySelector('[data-counter]');
		counter.textContent = n + ' / ' + max;
		counter.classList.toggle('warn', n > max - 50 && n <= max);
		counter.classList.toggle('over', n > max);
		const hasContent = textarea.value.trim() || filesOf(form).length;
		form.querySelector('[type="submit"]').disabled = Boolean(form.dataset.busy) || !hasContent || n > max;
		const attach = form.querySelector('[data-composer-attach]');
		if (attach) attach.disabled = filesOf(form).length >= Number(form.dataset.maxImages || 4);
	}

	// Описания, которые уже ввели, переносим из полей в список перед перерисовкой и отправкой.
	function collectAlts(form) {
		const files = filesOf(form);
		form.querySelectorAll('[data-attachment-alt]').forEach((input, i) => {
			if (files[i]) files[i].alt = input.value;
		});
	}

	function renderAttachments(form) {
		const list = form.querySelector('[data-attachments]');
		const template = form.querySelector('[data-attachment-template]');
		if (!list || !template) return;
		const files = filesOf(form);
		list.replaceChildren();
		files.forEach((item, i) => {
			const node = template.content.firstElementChild.cloneNode(true);
			node.querySelector('[data-attachment-preview]').src = item.url;
			const remove = node.querySelector('[data-attachment-remove]');
			remove.dataset.index = String(i);
			remove.setAttribute('aria-label', 'Убрать картинку ' + (i + 1));
			const alt = node.querySelector('[data-attachment-alt]');
			const label = node.querySelector('[data-attachment-alt-label]');
			alt.id = form.id + '-alt-' + i;
			alt.value = item.alt || '';
			label.htmlFor = alt.id;
			label.textContent = 'Описание картинки ' + (i + 1);
			list.appendChild(node);
		});
		list.hidden = files.length === 0;
		updateCounter(form);
	}

	function addFiles(form, fileList) {
		collectAlts(form);
		const files = filesOf(form);
		const maxImages = Number(form.dataset.maxImages || 4);
		const maxBytes = Number(form.dataset.maxMb || 10) * 1024 * 1024;
		const problems = [];
		Array.from(fileList).forEach((file) => {
			if (files.length >= maxImages) {
				problems.push('Не больше ' + maxImages + ' картинок.');
			} else if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type)) {
				problems.push('«' + file.name + '»: поддерживаются JPEG, PNG, WebP и GIF.');
			} else if (file.size > maxBytes) {
				problems.push('«' + file.name + '» больше ' + form.dataset.maxMb + ' МБ.');
			} else {
				files.push({ file: file, url: URL.createObjectURL(file), alt: '' });
			}
		});
		showComposerError(form, Array.from(new Set(problems)));
		renderAttachments(form);
	}

	function removeAttachment(form, index) {
		collectAlts(form);
		const [removed] = filesOf(form).splice(index, 1);
		if (removed) URL.revokeObjectURL(removed.url);
		renderAttachments(form);
		const attach = form.querySelector('[data-composer-attach]');
		if (attach) attach.focus();
	}

	function resetComposer(form) {
		form.querySelector('textarea').value = '';
		filesOf(form).forEach((item) => URL.revokeObjectURL(item.url));
		attachments.set(form, []);
		renderAttachments(form);
		showComposerError(form, null);
	}

	async function submitComposer(form) {
		const textarea = form.querySelector('textarea');
		collectAlts(form);
		const target = composerTarget;
		const body = new FormData();
		body.append('text', textarea.value);
		if (target) body.append('reply_to', target);
		filesOf(form).forEach((item) => {
			body.append('images', item.file, item.file.name);
			body.append('alt', item.alt || '');
		});
		form.dataset.busy = '1';
		updateCounter(form);
		showComposerError(form, null);
		const button = form.querySelector('[type="submit"]');
		const label = button.textContent;
		button.textContent = 'Публикуем…';
		try {
			let response;
			try {
				response = await fetch(form.action, {
					method: 'POST',
					headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
					body: body,
					credentials: 'same-origin',
				});
			} catch (e) {
				throw ['Нет связи с сервером. Попробуйте ещё раз.'];
			}
			if (!response.ok) throw await errorsOf(response, 'Пост не отправлен. Попробуйте ещё раз.');
			const html = await response.text();
			if (target) {
				// Ответ: в конец ветки, если она открыта, и +1 к счётчику на карточках родителя.
				const thread = document.querySelector('[data-replies="' + target + '"]');
				if (thread) {
					const empty = thread.querySelector('[data-feed-empty]');
					if (empty) empty.remove();
					const more = thread.querySelector('[data-load-more]');
					if (more) more.insertAdjacentHTML('beforebegin', html);
					else thread.insertAdjacentHTML('beforeend', html);
				}
				bumpReplyCount(target, 1);
			} else {
				const feed = document.querySelector('[data-feed-prepend]');
				if (feed) {
					const empty = feed.querySelector('[data-feed-empty]');
					if (empty) empty.remove();
					feed.insertAdjacentHTML('afterbegin', html);
				}
			}
			resetComposer(form);
			closeComposer();
			toast(target ? 'Ответ опубликован' : 'Пост опубликован');
		} catch (messages) {
			showComposerError(form, Array.isArray(messages) ? messages : ['Пост не отправлен. Попробуйте ещё раз.']);
		} finally {
			delete form.dataset.busy;
			button.textContent = label;
			updateCounter(form);
		}
	}

	// ---------- Просмотр картинок ----------
	const lightbox = { items: [], index: 0, opener: null };
	const lightboxEl = () => document.getElementById('lightbox');

	function showLightboxItem() {
		const box = lightboxEl();
		const item = lightbox.items[lightbox.index];
		const img = box.querySelector('[data-lightbox-img]');
		img.src = item.src;
		img.alt = item.alt;
		const caption = box.querySelector('[data-lightbox-caption]');
		caption.textContent = item.described ? item.alt : '';
		caption.hidden = !item.described;
		const many = lightbox.items.length > 1;
		box.querySelectorAll('[data-lightbox-step]').forEach((btn) => { btn.hidden = !many; });
		box.querySelector('[data-lightbox-count]').textContent = many ? (lightbox.index + 1) + ' / ' + lightbox.items.length : '';
	}

	function openLightbox(link) {
		const box = lightboxEl();
		const gallery = link.closest('[data-gallery]');
		if (!box || !gallery) return false;
		lightbox.items = Array.from(gallery.querySelectorAll('[data-lightbox]')).map((a) => ({
			src: a.href,
			alt: a.querySelector('img').alt,
			described: Boolean(a.querySelector('.alt-badge')),
		}));
		lightbox.index = Number(link.dataset.lightbox) || 0;
		lightbox.opener = link;
		showLightboxItem();
		box.hidden = false;
		syncModalOpen();
		box.querySelector('[data-lightbox-close]').focus();
		return true;
	}

	function stepLightbox(delta) {
		const n = lightbox.items.length;
		if (n < 2) return;
		lightbox.index = (lightbox.index + delta + n) % n;
		showLightboxItem();
	}

	function closeLightbox() {
		const box = lightboxEl();
		if (!box || box.hidden) return false;
		box.hidden = true;
		box.querySelector('[data-lightbox-img]').removeAttribute('src');
		syncModalOpen();
		if (lightbox.opener) lightbox.opener.focus();
		return true;
	}

	// ---------- Кадрирование аватара и баннера ----------
	// Сам файл уходит на сервер как есть, а вместе с ним — выбранная область в долях
	// (x, y, ширина, высота). Обрезает и сжимает сервер; без JS он берёт центр.
	const crop = { input: null, name: '', natural: [1, 1], zoom: 1, ox: 0, oy: 0, drag: null, url: null };
	const cropperEl = () => document.getElementById('cropper');
	const CROP_PREVIEW = { avatar: [192, 192], banner: [900, 300] };

	function cropMetrics() {
		const frame = cropperEl().querySelector('[data-crop-frame]');
		const W = frame.clientWidth;
		const H = frame.clientHeight;
		const [w, h] = crop.natural;
		return { W: W, H: H, w: w, h: h, scale: Math.max(W / w, H / h) * crop.zoom };
	}

	function drawCrop() {
		const m = cropMetrics();
		crop.ox = Math.min(0, Math.max(m.W - m.w * m.scale, crop.ox));
		crop.oy = Math.min(0, Math.max(m.H - m.h * m.scale, crop.oy));
		const img = cropperEl().querySelector('[data-crop-img]');
		img.style.width = m.w + 'px';
		img.style.height = m.h + 'px';
		img.style.transform = 'translate(' + crop.ox + 'px, ' + crop.oy + 'px) scale(' + m.scale + ')';
	}

	function setCropZoom(zoom) {
		const before = cropMetrics();
		// Приближаем относительно центра кадра, а не левого верхнего угла.
		const cx = (before.W / 2 - crop.ox) / before.scale;
		const cy = (before.H / 2 - crop.oy) / before.scale;
		crop.zoom = Math.min(4, Math.max(1, zoom));
		const after = cropMetrics();
		crop.ox = after.W / 2 - cx * after.scale;
		crop.oy = after.H / 2 - cy * after.scale;
		cropperEl().querySelector('[data-crop-zoom]').value = String(crop.zoom);
		drawCrop();
	}

	function openCropper(input) {
		const modal = cropperEl();
		const file = input.files && input.files[0];
		if (!modal || !file) return;
		const limit = input.closest('[data-max-mb]');
		const maxMb = Number(limit ? limit.dataset.maxMb : 10);
		if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type) || file.size > maxMb * 1024 * 1024) {
			input.value = '';
			toast('Нужна картинка JPEG, PNG, WebP или GIF до ' + maxMb + ' МБ');
			return;
		}
		crop.input = input;
		crop.name = input.dataset.cropInput;
		if (crop.url) URL.revokeObjectURL(crop.url);
		crop.url = URL.createObjectURL(file);
		const img = modal.querySelector('[data-crop-img]');
		const frame = modal.querySelector('[data-crop-frame]');
		frame.dataset.shape = crop.name;
		modal.querySelector('[data-crop-title]').textContent = crop.name === 'avatar' ? 'Аватар' : 'Баннер';
		img.onload = () => {
			crop.natural = [img.naturalWidth, img.naturalHeight];
			crop.zoom = 1;
			modal.querySelector('[data-crop-zoom]').value = '1';
			const m = cropMetrics();
			crop.ox = (m.W - m.w * m.scale) / 2;
			crop.oy = (m.H - m.h * m.scale) / 2;
			drawCrop();
		};
		img.onerror = () => { closeCropper(true); toast('Не удалось открыть картинку'); };
		lastFocus = document.activeElement;
		modal.hidden = false;
		syncModalOpen();
		img.src = crop.url;
		frame.focus();
	}

	function closeCropper(cancel) {
		const modal = cropperEl();
		if (!modal || modal.hidden) return false;
		if (cancel && crop.input) {
			crop.input.value = '';
			crop.input.form.querySelector('[name="' + crop.name + '_crop"]').value = '';
		}
		modal.hidden = true;
		syncModalOpen();
		if (crop.input) crop.input.focus();
		return true;
	}

	function applyCrop() {
		const m = cropMetrics();
		const box = {
			x: -crop.ox / (m.w * m.scale),
			y: -crop.oy / (m.h * m.scale),
			w: m.W / (m.w * m.scale),
			h: m.H / (m.h * m.scale),
		};
		const form = crop.input.form;
		form.querySelector('[name="' + crop.name + '_crop"]').value =
			[box.x, box.y, box.w, box.h].map((v) => Math.min(1, Math.max(0, v)).toFixed(5)).join(',');
		// Превью: как будет выглядеть после сохранения.
		const [pw, ph] = CROP_PREVIEW[crop.name];
		const canvas = document.createElement('canvas');
		canvas.width = pw;
		canvas.height = ph;
		const img = cropperEl().querySelector('[data-crop-img]');
		canvas.getContext('2d').drawImage(img, box.x * m.w, box.y * m.h, box.w * m.w, box.h * m.h, 0, 0, pw, ph);
		const preview = form.querySelector('[data-crop-preview="' + crop.name + '"]');
		const shot = document.createElement('img');
		shot.src = canvas.toDataURL('image/jpeg', 0.9);
		shot.alt = '';
		if (crop.name === 'avatar') shot.className = 'avatar avatar-xl';
		preview.classList.remove('ph');
		preview.replaceChildren(shot);
		const clear = form.querySelector('[name="' + crop.name + '_clear"]');
		if (clear) clear.checked = false;
		closeCropper(false);
	}

	function startCropDrag(event) {
		const frame = event.target.closest('[data-crop-frame]');
		if (!frame || event.button !== 0) return;
		crop.drag = { x: event.clientX, y: event.clientY, ox: crop.ox, oy: crop.oy };
		frame.setPointerCapture(event.pointerId);
	}

	function moveCropDrag(event) {
		if (!crop.drag) return;
		crop.ox = crop.drag.ox + event.clientX - crop.drag.x;
		crop.oy = crop.drag.oy + event.clientY - crop.drag.y;
		drawCrop();
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
			// На странице самого поста после удаления смотреть не на что — уводим на главную.
			if (post.matches('[data-main-post]')) {
				window.location.href = '/';
				return;
			}
			document.querySelectorAll('[data-post-id="' + post.dataset.postId + '"]').forEach((el) => el.remove());
			if (post.dataset.replyOf) bumpReplyCount(post.dataset.replyOf, -1);
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
			const page = document.createElement('template');
			page.innerHTML = await response.text();
			// Свой свежий ответ мог уже попасть на страницу — не показываем его дважды.
			page.content.querySelectorAll('[data-post-id]').forEach((card) => {
				if (document.querySelector('[data-post-id="' + card.dataset.postId + '"]')) card.remove();
			});
			link.before(page.content);
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
			// Клик мимо картинки в просмотрщике закрывает его.
			if (event.target.closest('#lightbox') && !event.target.closest('img')) closeLightbox();
			return;
		}
		if (target.matches('[data-menu-toggle]')) { event.preventDefault(); toggleMenu(target); return; }
		if (target.matches('[data-theme-toggle]')) { event.preventDefault(); toggleTheme(); return; }
		if (target.matches('[data-composer-open]')) { event.preventDefault(); openComposer(null); return; }
		if (target.matches('[data-reply]')) { event.preventDefault(); openReply(target); return; }
		if (target.matches('[data-composer-close]')) { event.preventDefault(); closeComposer(); return; }
		if (target.matches('[data-composer-attach]')) { event.preventDefault(); target.form.querySelector('[data-composer-file]').click(); return; }
		if (target.matches('[data-attachment-remove]')) { event.preventDefault(); removeAttachment(target.form, Number(target.dataset.index)); return; }
		if (target.matches('[data-lightbox]')) {
			// Ctrl/⌘/Shift+клик — открыть картинку в новой вкладке, как обычную ссылку.
			if (event.ctrlKey || event.metaKey || event.shiftKey) return;
			if (openLightbox(target)) event.preventDefault();
			return;
		}
		if (target.matches('[data-lightbox-close]')) { event.preventDefault(); closeLightbox(); return; }
		if (target.matches('[data-lightbox-step]')) { event.preventDefault(); stepLightbox(Number(target.dataset.lightboxStep)); return; }
		if (target.matches('[data-crop-cancel]')) { event.preventDefault(); closeCropper(true); return; }
		if (target.matches('[data-crop-apply]')) { event.preventDefault(); applyCrop(); return; }
		if (target.matches('[data-like]')) { event.preventDefault(); like(target); return; }
		if (target.matches('[data-delete]')) { event.preventDefault(); removePost(target); return; }
		if (target.matches('[data-copy]')) { event.preventDefault(); copyLink(target); return; }
		if (target.matches('[data-load-more]')) { event.preventDefault(); loadMore(target); return; }
		// «Назад» возвращает туда, откуда пришли с этого же сайта (с той же позицией в ленте);
		// если пришли по внешней ссылке — обычный переход на главную.
		if (target.matches('[data-back]') && document.referrer.startsWith(window.location.origin + '/') && window.history.length > 1) {
			event.preventDefault();
			window.history.back();
			return;
		}
		if (!target.closest('[role="menu"]')) closeMenus();
	});

	document.addEventListener('keydown', (event) => {
		const box = lightboxEl();
		if (box && !box.hidden) {
			if (event.key === 'ArrowLeft') { event.preventDefault(); stepLightbox(-1); return; }
			if (event.key === 'ArrowRight') { event.preventDefault(); stepLightbox(1); return; }
			if (event.key === 'Escape') { closeLightbox(); return; }
		}
		const cropper = cropperEl();
		if (cropper && !cropper.hidden) {
			if (event.key === 'Escape') { closeCropper(true); return; }
			if (!event.target.matches('[data-crop-frame]')) return;
			const moves = { ArrowLeft: [10, 0], ArrowRight: [-10, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] };
			if (moves[event.key]) {
				event.preventDefault();
				crop.ox += moves[event.key][0];
				crop.oy += moves[event.key][1];
				drawCrop();
			} else if (event.key === '+' || event.key === '=') {
				setCropZoom(crop.zoom + 0.1);
			} else if (event.key === '-') {
				setCropZoom(crop.zoom - 0.1);
			}
			return;
		}
		if (event.key !== 'Escape') return;
		closeMenus();
		closeComposer();
	});

	document.addEventListener('input', (event) => {
		if (event.target.matches('[data-composer-text]')) updateCounter(event.target.form);
		if (event.target.matches('[data-crop-zoom]')) setCropZoom(Number(event.target.value));
	});

	document.addEventListener('pointerdown', startCropDrag);
	document.addEventListener('pointermove', moveCropDrag);
	document.addEventListener('pointerup', () => { crop.drag = null; });
	document.addEventListener('pointercancel', () => { crop.drag = null; });
	document.addEventListener('wheel', (event) => {
		if (!event.target.closest('[data-crop-frame]')) return;
		event.preventDefault();
		setCropZoom(crop.zoom - Math.sign(event.deltaY) * 0.1);
	}, { passive: false });

	document.addEventListener('change', (event) => {
		if (event.target.matches('[data-crop-input]')) { openCropper(event.target); return; }
		if (event.target.matches('[data-composer-file]')) {
			addFiles(event.target.form, event.target.files);
			event.target.value = ''; // чтобы тот же файл можно было выбрать снова
		}
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
