'use strict';
// Общий JS AzzB: меню, тема, composer, картинки, кадрирование, тосты.
// Запросы к серверу (лайк, удаление, публикация, подгрузка) делает htmx — см. атрибуты hx-* в шаблонах.

(function () {
	const POST_MAX = 500;

	// Сообщения об ошибке из ответа сервера: {"errors": [...]} или запасной текст.
	function errorsOf(xhr, fallback) {
		if (!xhr || !xhr.status) return ['Нет связи с сервером. Попробуйте ещё раз.'];
		if (xhr.status === 413) return ['Файлы слишком тяжёлые для отправки.'];
		try {
			const data = JSON.parse(xhr.responseText);
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

	// Composer один на страницу, а пишут в нём новый пост, ответ на любой пост или правку своего.
	// Режим: {kind: 'new'} | {kind: 'reply', id, name} | {kind: 'edit', id, hasImages}.
	// Черновик у каждого режима свой: начатый пост не уедет ответом и наоборот.
	const COMPOSER_TEXT = {
		new: { title: 'Новый пост', submit: 'Опубликовать', busy: 'Публикуем…', done: 'Пост опубликован' },
		reply: { title: 'Ответ', submit: 'Ответить', busy: 'Отправляем…', done: 'Ответ опубликован' },
		edit: { title: 'Редактирование', submit: 'Сохранить', busy: 'Сохраняем…', done: 'Изменения сохранены' },
	};
	const drafts = new Map();
	let composerMode = { kind: 'new' };

	function modeKey(mode) {
		return mode.kind === 'new' ? '' : mode.kind + ':' + mode.id;
	}

	// Тексты черновиков переживают перезагрузку и закрытую вкладку: лежат в localStorage
	// (ключ свой у каждого пользователя). Картинки браузер так сохранить не даёт.
	const DRAFT_MAX_AGE = 14 * 24 * 3600 * 1000;
	const DRAFT_MAX_COUNT = 30;

	function readSavedDrafts(form) {
		try {
			const data = JSON.parse(localStorage.getItem(form.dataset.draftKey) || '{}');
			return data && typeof data === 'object' ? data : {};
		} catch (e) {
			return {};
		}
	}

	function writeSavedDraft(form, key, text) {
		if (!form.dataset.draftKey) return;
		const data = readSavedDrafts(form);
		if (text.trim()) data[key] = { text: text, at: Date.now() };
		else delete data[key];
		// Старые и лишние черновики выбрасываем, чтобы хранилище не росло бесконечно.
		const fresh = Object.entries(data)
			.filter(([, item]) => item && typeof item.text === 'string' && Date.now() - item.at < DRAFT_MAX_AGE)
			.sort((a, b) => b[1].at - a[1].at)
			.slice(0, DRAFT_MAX_COUNT);
		try {
			if (fresh.length) localStorage.setItem(form.dataset.draftKey, JSON.stringify(Object.fromEntries(fresh)));
			else localStorage.removeItem(form.dataset.draftKey);
		} catch (e) { /* приватный режим или нет места — живём без сохранения */ }
	}

	let draftTimer = null;
	function saveDraftSoon(form) {
		if (composerMode.kind === 'edit') return;
		const key = modeKey(composerMode);
		const text = form.querySelector('textarea').value;
		clearTimeout(draftTimer);
		draftTimer = setTimeout(() => writeSavedDraft(form, key, text), 400);
	}

	function switchComposerMode(form, mode, text) {
		const textarea = form.querySelector('textarea');
		if (modeKey(mode) !== modeKey(composerMode)) {
			collectAlts(form);
			// Правку не храним: при следующем открытии берём свежий текст поста.
			if (composerMode.kind !== 'edit') drafts.set(modeKey(composerMode), { text: textarea.value, files: filesOf(form) });
			const saved = mode.kind === 'edit' ? null : readSavedDrafts(form)[modeKey(mode)];
			const next = drafts.get(modeKey(mode)) || { text: saved ? saved.text : '', files: [] };
			drafts.delete(modeKey(mode));
			textarea.value = next.text;
			attachments.set(form, next.files);
			composerMode = mode;
			renderAttachments(form);
			showComposerError(form, null);
		}
		if (mode.kind === 'edit') textarea.value = text;
	}

	function openComposer(mode, text) {
		const modal = composer();
		if (!modal) return;
		const form = modal.querySelector('form');
		switchComposerMode(form, mode, text);
		const labels = COMPOSER_TEXT[mode.kind];
		form.querySelector('[data-composer-reply-to]').value = mode.kind === 'reply' ? mode.id : '';
		form.querySelector('[data-composer-edit]').value = mode.kind === 'edit' ? mode.id : '';
		form.querySelector('[data-composer-replying]').hidden = mode.kind !== 'reply';
		form.querySelector('[data-composer-replying-name]').textContent = mode.name || '';
		// У правки картинки не меняются — прячем всё, что про вложения.
		form.querySelector('.composer-tools').hidden = mode.kind === 'edit';
		form.querySelector('[data-composer-edit-note]').hidden = !(mode.kind === 'edit' && mode.hasImages);
		modal.querySelector('[data-composer-title]').textContent = labels.title;
		const textarea = form.querySelector('textarea');
		textarea.placeholder = mode.kind === 'reply' ? 'Ваш ответ' : textarea.dataset.placeholder;
		form.querySelector('[type="submit"]').textContent = labels.submit;
		lastFocus = document.activeElement;
		modal.hidden = false;
		syncModalOpen();
		closeMenus();
		updateCounter(form);
		autosize(textarea);
		textarea.focus();
		textarea.setSelectionRange(textarea.value.length, textarea.value.length);
	}

	// Поле растёт вместе с текстом (до половины экрана, дальше — прокрутка внутри).
	function autosize(textarea) {
		textarea.style.height = 'auto';
		textarea.style.height = Math.min(textarea.scrollHeight + 2, window.innerHeight * 0.5) + 'px';
	}

	// Tab и Shift+Tab не выходят из открытого окна на страницу под ним.
	function trapFocus(event) {
		const dialog = Array.from(document.querySelectorAll('.modal, .lightbox')).find((el) => !el.hidden);
		if (!dialog) return;
		const focusable = Array.from(dialog.querySelectorAll(
			'button, [href], input:not([type="hidden"]), textarea, select, [tabindex]:not([tabindex="-1"])'
		)).filter((el) => !el.disabled && !el.closest('[hidden]') && !el.classList.contains('sr'));
		if (!focusable.length) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (!dialog.contains(document.activeElement)) {
			event.preventDefault();
			first.focus();
		} else if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}

	function imageFiles(list) {
		return Array.from(list || []).filter((file) => file.type.startsWith('image/'));
	}

	function openReply(btn) {
		const card = btn.closest('[data-post-id]');
		const id = btn.dataset.replyTo || (card && card.dataset.postId);
		if (id) openComposer({ kind: 'reply', id: id, name: btn.dataset.replyName || '' });
	}

	function openEdit(btn) {
		const card = btn.closest('[data-post-id]');
		const text = card.querySelector('.post-text');
		openComposer(
			{ kind: 'edit', id: card.dataset.postId, hasImages: btn.hasAttribute('data-has-images') },
			text ? text.textContent : '',
		);
	}

	// После правки меняем содержимое карточек, а не сами карточки: у главного поста
	// и постов выше по ветке свой вид, и он должен сохраниться.
	function replaceCardBodies(html) {
		const page = document.createElement('template');
		page.innerHTML = html;
		page.content.querySelectorAll('[data-post-id]').forEach((fresh) => {
			document.querySelectorAll('[data-post-id="' + fresh.dataset.postId + '"]').forEach((card) => {
				const body = fresh.querySelector('.post-body').cloneNode(true);
				card.querySelector('.post-body').replaceWith(body);
				htmx.process(body);
			});
		});
	}

	// Вставить карточки из ответа сервера. htmx сам обрабатывает только то, что вставил сам,
	// поэтому новые кнопки (лайк, удаление) подключаем к нему явно.
	function insertCards(anchor, position, html) {
		const page = document.createElement('template');
		page.innerHTML = html;
		const nodes = Array.from(page.content.children);
		if (position === 'before') anchor.before(page.content);
		else if (position === 'prepend') anchor.prepend(page.content);
		else anchor.append(page.content);
		nodes.forEach((node) => htmx.process(node));
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
		const keepsImages = composerMode.kind === 'edit' && composerMode.hasImages;
		const hasContent = textarea.value.trim() || filesOf(form).length || keepsImages;
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

	function showPublished(mode, html) {
		if (mode.kind === 'edit') {
			replaceCardBodies(html);
		} else if (mode.kind === 'reply') {
			// Ответ: в конец ветки, если она открыта, и +1 к счётчику на карточках родителя.
			const thread = document.querySelector('[data-replies="' + mode.id + '"]');
			if (thread) {
				const empty = thread.querySelector('[data-feed-empty]');
				if (empty) empty.remove();
				const more = thread.querySelector('.load-more');
				if (more) insertCards(more, 'before', html);
				else insertCards(thread, 'append', html);
			}
			bumpReplyCount(mode.id, 1);
		} else {
			const feed = document.querySelector('[data-feed-prepend]');
			if (feed) {
				const empty = feed.querySelector('[data-feed-empty]');
				if (empty) empty.remove();
				insertCards(feed, 'prepend', html);
			}
		}
	}

	// Отправляет composer htmx (hx-post на форме). Здесь только то, чего htmx сам не знает.
	function composerOf(event) {
		const elt = event.detail && event.detail.elt;
		return elt && elt.matches && elt.matches('[data-composer-form]') ? elt : null;
	}

	// Картинки живут в списке JS (их можно вставить, перетащить, убрать), поэтому
	// в запрос их кладём сами — вместе с описаниями, в том же порядке.
	document.addEventListener('htmx:configRequest', (event) => {
		const form = composerOf(event);
		if (!form) return;
		collectAlts(form);
		form._mode = composerMode;
		const data = event.detail.formData;
		data.delete('images');
		data.delete('alt');
		if (composerMode.kind !== 'edit') {
			filesOf(form).forEach((item) => {
				data.append('images', item.file, item.file.name);
				data.append('alt', item.alt || '');
			});
		}
	});

	document.addEventListener('htmx:beforeRequest', (event) => {
		closeMenus();
		const form = composerOf(event);
		if (!form) return;
		form.dataset.busy = '1';
		updateCounter(form); // кнопка неактивна, пока идёт запрос
		showComposerError(form, null);
		form.querySelector('[type="submit"]').textContent = COMPOSER_TEXT[composerMode.kind].busy;
	});

	document.addEventListener('htmx:afterRequest', (event) => {
		const form = composerOf(event);
		if (!form) return;
		const mode = form._mode || composerMode;
		const labels = COMPOSER_TEXT[mode.kind];
		delete form.dataset.busy;
		form.querySelector('[type="submit"]').textContent = labels.submit;
		if (event.detail.successful) {
			showPublished(mode, event.detail.xhr.responseText);
			clearTimeout(draftTimer);
			if (mode.kind !== 'edit') writeSavedDraft(form, modeKey(mode), '');
			resetComposer(form);
			closeComposer();
			toast(labels.done);
		} else {
			const fallback = mode.kind === 'edit' ? 'Изменения не сохранены. Попробуйте ещё раз.' : 'Пост не отправлен. Попробуйте ещё раз.';
			showComposerError(form, errorsOf(event.detail.xhr, fallback));
		}
		updateCounter(form);
	});

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
	// Лайк, удаление и «Показать ещё» — атрибуты hx-* в шаблонах. Сервер дополняет их
	// событиями в заголовке HX-Trigger: azzb:toast и azzb:post-deleted.
	document.addEventListener('azzb:toast', (event) => toast(event.detail.value));

	document.addEventListener('azzb:post-deleted', (event) => {
		const { id, replyOf } = event.detail;
		document.querySelectorAll('[data-post-id="' + id + '"]').forEach((card) => card.remove());
		if (replyOf) bumpReplyCount(replyOf, -1);
	});

	// Ошибка запроса не из composer (у него свой блок ошибок) — короткий тост.
	function requestFailed(event) {
		if (composerOf(event)) return;
		const elt = event.detail.elt;
		toast(errorsOf(event.detail.xhr, (elt && elt.dataset.error) || 'Что-то пошло не так. Попробуйте ещё раз.')[0]);
	}
	document.addEventListener('htmx:responseError', requestFailed);
	document.addEventListener('htmx:sendError', requestFailed);

	// Подгруженная порция могла принести карточку, которая уже есть на странице
	// (например, свой свежий ответ в ветке) — второй раз её не показываем.
	document.addEventListener('htmx:load', (event) => {
		const card = event.detail.elt;
		if (!card.matches || !card.matches('[data-post-id]') || !card.parentElement) return;
		const twins = card.parentElement.querySelectorAll(':scope > [data-post-id="' + card.dataset.postId + '"]');
		if (twins.length > 1 && twins[0] !== card) card.remove();
	});

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
		if (target.matches('[data-composer-open]')) { event.preventDefault(); openComposer({ kind: 'new' }); return; }
		if (target.matches('[data-reply]')) { event.preventDefault(); openReply(target); return; }
		if (target.matches('[data-edit]')) { event.preventDefault(); openEdit(target); return; }
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
		if (target.matches('[data-copy]')) { event.preventDefault(); copyLink(target); return; }
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
		if (event.key === 'Tab') { trapFocus(event); return; }
		// Ctrl+Enter (⌘+Enter на Mac) — отправить из composer.
		if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.target.closest('[data-composer-form]')) {
			const form = event.target.closest('[data-composer-form]');
			event.preventDefault();
			if (!form.querySelector('[type="submit"]').disabled) form.requestSubmit();
			return;
		}
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
		if (event.target.matches('[data-composer-text]')) {
			updateCounter(event.target.form);
			autosize(event.target);
			saveDraftSoon(event.target.form);
		}
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

	// Картинку можно вставить из буфера (Ctrl+V) или перетащить в окно composer.
	document.addEventListener('paste', (event) => {
		const form = event.target.closest && event.target.closest('[data-composer-form]');
		if (!form || composerMode.kind === 'edit') return;
		const files = imageFiles(event.clipboardData && event.clipboardData.files);
		if (!files.length) return;
		event.preventDefault();
		addFiles(form, files);
	});

	function dropTarget(event) {
		const modal = composer();
		if (!modal || modal.hidden || composerMode.kind === 'edit') return null;
		if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return null;
		return modal.querySelector('[data-composer-form]');
	}
	document.addEventListener('dragover', (event) => {
		const form = dropTarget(event);
		if (!form) return;
		event.preventDefault();
		form.classList.add('dragging');
	});
	document.addEventListener('dragleave', (event) => {
		if (event.relatedTarget === null) document.querySelectorAll('.dragging').forEach((el) => el.classList.remove('dragging'));
	});
	document.addEventListener('drop', (event) => {
		const form = dropTarget(event);
		if (!form) return;
		event.preventDefault();
		form.classList.remove('dragging');
		addFiles(form, imageFiles(event.dataTransfer.files));
	});

	document.addEventListener('DOMContentLoaded', () => {
		syncThemeToggles();
		// Недописанный пост из прошлого визита ждёт в composer.
		const form = document.querySelector('#composer [data-composer-form]');
		if (form) {
			const saved = readSavedDrafts(form)[''];
			if (saved) form.querySelector('textarea').value = saved.text;
		}
	});
})();
