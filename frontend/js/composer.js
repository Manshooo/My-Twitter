import { checkMentionLinks, closeMentions } from './mentions.js';
import { closeMenus } from './menu.js';
import { rememberFocus, restoreFocus, syncModalOpen } from './modal.js';
import { filledPollOptions, pollActive, setPoll } from './poll.js';
import { toast } from './toast.js';
import { POST_MAX, errorsOf, formatCount } from './util.js';

// ---------- Composer ----------
export const composer = () => document.getElementById('composer');
// Выбранные картинки по формам: [{file, url, alt}]. Порядок = порядок в посте.
const attachments = new WeakMap();

function filesOf(form) {
	if (!attachments.has(form)) attachments.set(form, []);
	return attachments.get(form);
}

// Composer один на страницу, а пишут в нём новый пост, ответ на любой пост или правку своего.
// Режим: {kind: 'new'} | {kind: 'reply', id, name} | {kind: 'quote', id, name} | {kind: 'edit', id, hasImages}.
// Черновик у каждого режима свой: начатый пост не уедет ответом и наоборот.
const COMPOSER_TEXT = {
	new: { title: 'Новый пост', submit: 'Опубликовать', busy: 'Публикуем…', done: 'Пост опубликован' },
	reply: { title: 'Ответ', submit: 'Ответить', busy: 'Отправляем…', done: 'Ответ опубликован' },
	quote: { title: 'Цитата', submit: 'Опубликовать', busy: 'Публикуем…', done: 'Цитата опубликована' },
	edit: { title: 'Редактирование', submit: 'Сохранить', busy: 'Сохраняем…', done: 'Изменения сохранены' },
};
const drafts = new Map();
export let composerMode = { kind: 'new' };

function modeKey(mode) {
	return mode.kind === 'new' ? '' : mode.kind + ':' + mode.id;
}

// Тексты черновиков переживают перезагрузку и закрытую вкладку: лежат в localStorage
// (ключ свой у каждого пользователя). Картинки браузер так сохранить не даёт.
const DRAFT_MAX_AGE = 14 * 24 * 3600 * 1000;
const DRAFT_MAX_COUNT = 30;

export function readSavedDrafts(form) {
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
export function saveDraftSoon(form) {
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

export function openComposer(mode, text) {
	const modal = composer();
	if (!modal) return;
	const form = modal.querySelector('form');
	switchComposerMode(form, mode, text);
	const labels = COMPOSER_TEXT[mode.kind];
	form.querySelector('[data-composer-reply-to]').value = mode.kind === 'reply' ? mode.id : '';
	form.querySelector('[data-composer-edit]').value = mode.kind === 'edit' ? mode.id : '';
	form.querySelector('[data-composer-replying]').hidden = mode.kind !== 'reply';
	form.querySelector('[data-composer-replying-name]').textContent = mode.name || '';
	form.querySelector('[data-composer-quote-of]').value = mode.kind === 'quote' ? mode.id : '';
	form.querySelector('[data-composer-quoting]').hidden = mode.kind !== 'quote';
	form.querySelector('[data-composer-quoting-name]').textContent = mode.name || '';
	// У правки картинки не меняются — прячем всё, что про вложения.
	form.querySelector('.composer-tools').hidden = mode.kind === 'edit';
	if (mode.kind === 'edit' && pollActive(form)) setPoll(form, false);
	form.querySelector('[data-composer-edit-note]').hidden = !(mode.kind === 'edit' && mode.hasImages);
	modal.querySelector('[data-composer-title]').textContent = labels.title;
	const textarea = form.querySelector('textarea');
	textarea.placeholder = mode.kind === 'reply' ? 'Ваш ответ' : mode.kind === 'quote' ? 'Ваш комментарий' : textarea.dataset.placeholder;
	form.querySelector('[type="submit"]').textContent = labels.submit;
	rememberFocus();
	modal.hidden = false;
	syncModalOpen();
	closeMenus();
	updateCounter(form);
	autosize(textarea);
	textarea.focus();
	textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}

// Поле растёт вместе с текстом (до половины экрана, дальше — прокрутка внутри).
export function autosize(textarea) {
	textarea.style.height = 'auto';
	textarea.style.height = Math.min(textarea.scrollHeight + 2, window.innerHeight * 0.5) + 'px';
}

// Tab и Shift+Tab не выходят из открытого окна на страницу под ним.
export function trapFocus(event) {
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

export function imageFiles(list) {
	return Array.from(list || []).filter((file) => file.type.startsWith('image/'));
}

export function openReply(btn) {
	const card = btn.closest('[data-post-id]');
	const id = btn.dataset.replyTo || (card && card.dataset.postId);
	if (id) openComposer({ kind: 'reply', id: id, name: btn.dataset.replyName || '' });
}

export function openQuote(btn) {
	openComposer({ kind: 'quote', id: btn.dataset.quote, name: btn.dataset.quoteName || '' });
}

// Число на экране сокращено («1,2 тыс.»), точное — в data-n.
function setCount(el, n) {
	el.dataset.n = String(n);
	el.textContent = formatCount(n);
}

// Число репостов у всех карточек поста на странице: пост и его репосты — разные карточки.
export function setRepostCount(postId, count) {
	document.querySelectorAll('[data-post-id="' + postId + '"] [data-repost-count]').forEach((el) => {
		setCount(el, count);
	});
}

function bumpRepostCount(postId, delta) {
	const el = document.querySelector('[data-post-id="' + postId + '"] [data-repost-count]');
	if (el) setRepostCount(postId, (Number(el.dataset.n) || 0) + delta);
}

export function openEdit(btn) {
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
			// В шапке отметка «изменено».
			card.querySelector('.post-header').replaceWith(fresh.querySelector('.post-header').cloneNode(true));
			const body = fresh.querySelector('.post-body').cloneNode(true);
			// Кнопки действий оставляем прежние: у главного поста «Ответить» открывает composer,
			// а в свежей карточке (вид ленты) это ссылка на страницу поста.
			const actions = card.querySelector('.actions');
			if (actions) body.querySelector('.actions').replaceWith(actions);
			card.querySelector('.post-body').replaceWith(body);
			htmx.process(body);
			checkMentionLinks();
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
	else if (position === 'after') anchor.after(page.content);
	else if (position === 'prepend') anchor.prepend(page.content);
	else anchor.append(page.content);
	nodes.forEach((node) => htmx.process(node));
	checkMentionLinks();
}

// Счётчик ответов считает всю ветку, поэтому меняем его у поста и у всех постов выше
// по ветке, что есть на странице (идём вверх по data-reply-of).
export function bumpReplyCount(postId, delta) {
	const seen = new Set();
	while (postId && !seen.has(postId)) {
		seen.add(postId);
		const cards = Array.from(document.querySelectorAll('[data-post-id="' + postId + '"]'));
		cards.forEach((card) => card.querySelectorAll('[data-reply-count]').forEach((el) => {
			setCount(el, Math.max(0, (Number(el.dataset.n) || 0) + delta));
		}));
		const child = cards.find((card) => card.dataset.replyOf);
		postId = child ? child.dataset.replyOf : null;
	}
}

export function closeComposer() {
	const modal = composer();
	if (!modal || modal.hidden) return;
	closeMentions();
	modal.hidden = true;
	syncModalOpen();
	restoreFocus();
}

function showComposerError(form, messages) {
	const error = form.querySelector('[data-composer-error]');
	const text = form.querySelector('[data-composer-error-text]');
	if (!messages || !messages.length) { error.hidden = true; return; }
	text.textContent = messages.join(' ');
	error.hidden = false;
}

export function updateCounter(form) {
	const textarea = form.querySelector('textarea');
	const max = Number(form.dataset.maxLength) || POST_MAX;
	const n = textarea.value.length;
	const counter = form.querySelector('[data-counter]');
	counter.textContent = n + ' / ' + max;
	counter.classList.toggle('warn', n > max - 50 && n <= max);
	counter.classList.toggle('over', n > max);
	const keepsImages = composerMode.kind === 'edit' && composerMode.hasImages;
	const hasContent = textarea.value.trim() || filesOf(form).length || keepsImages;
	// Опрос: нужен вопрос (текст) и хотя бы два варианта. Картинки и опрос — не вместе.
	const poll = pollActive(form);
	const pollReady = !poll || (textarea.value.trim() && filledPollOptions(form) >= 2);
	form.querySelector('[type="submit"]').disabled = Boolean(form.dataset.busy) || !hasContent || !pollReady || n > max;
	const attach = form.querySelector('[data-composer-attach]');
	if (attach) attach.disabled = poll || filesOf(form).length >= Number(form.dataset.maxImages || 4);
	const pollButton = form.querySelector('.composer-tools [data-poll-toggle]');
	if (pollButton) pollButton.disabled = filesOf(form).length > 0;
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

export function addFiles(form, fileList) {
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

export function removeAttachment(form, index) {
	collectAlts(form);
	const [removed] = filesOf(form).splice(index, 1);
	if (removed) URL.revokeObjectURL(removed.url);
	renderAttachments(form);
	const attach = form.querySelector('[data-composer-attach]');
	if (attach) attach.focus();
}

function resetComposer(form) {
	setPoll(form, false);
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
		if (mode.kind === 'quote') bumpRepostCount(mode.id, 1);
		const feed = document.querySelector('[data-feed-prepend]');
		if (feed) {
			const empty = feed.querySelector('[data-feed-empty]');
			if (empty) empty.remove();
			// Закреплённый пост в профиле остаётся первым — новый встаёт под ним.
			const pinned = feed.querySelector(':scope > .post-pinned');
			if (pinned) insertCards(pinned, 'after', html);
			else insertCards(feed, 'prepend', html);
		}
	}
}

// Отправляет composer htmx (hx-post на форме). Здесь только то, чего htmx сам не знает.
export function composerOf(event) {
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
