// ---------- @упоминания ----------
// Ссылки на @логин сервер ставит по виду, не проверяя, есть ли такой человек (лента без
// лишних запросов). Здесь одним запросом на страницу узнаём, какие логины есть, а ссылки
// на несуществующие превращаем в обычный текст. Гостям проверка не нужна: профили открываются после входа.
const knownLogins = new Map();
let mentionCheckTimer = null;

export function checkMentionLinks() {
	clearTimeout(mentionCheckTimer);
	mentionCheckTimer = setTimeout(runMentionCheck, 50);
}

async function runMentionCheck() {
	const url = document.body.dataset.usersExistUrl;
	if (!url) return;
	const links = Array.from(document.querySelectorAll('a.mention-link:not([data-checked])'));
	const loginOf = (link) => link.textContent.slice(1);
	const unknown = Array.from(new Set(links.map(loginOf).filter((login) => !knownLogins.has(login))));
	for (let i = 0; i < unknown.length; i += 50) {
		const batch = unknown.slice(i, i + 50);
		try {
			const response = await fetch(url + '?names=' + encodeURIComponent(batch.join(',')), { headers: { Accept: 'application/json' } });
			if (!response.ok) return;
			const existing = new Set((await response.json()).existing);
			batch.forEach((login) => knownLogins.set(login, existing.has(login)));
		} catch (e) {
			return; // сеть подвела — оставляем ссылки как есть
		}
	}
	links.forEach((link) => {
		if (!knownLogins.has(loginOf(link))) return;
		if (knownLogins.get(loginOf(link))) link.dataset.checked = '1';
		else link.replaceWith(document.createTextNode(link.textContent));
	});
}

document.addEventListener('DOMContentLoaded', checkMentionLinks);
document.addEventListener('htmx:afterSettle', checkMentionLinks);

// Подсказки при наборе @ в composer: стрелки — выбор, Enter или Tab — вставить, Esc — закрыть.
const MENTION_BEFORE_CARET = /(?:^|[^\w@])@([a-zA-Z0-9_.-]{1,30})$/;
const mention = { start: -1, items: [], active: 0, timer: null, controller: null };

function mentionList() {
	return document.querySelector('[data-mention-list]');
}

export function closeMentions() {
	const list = mentionList();
	clearTimeout(mention.timer);
	if (mention.controller) mention.controller.abort();
	mention.start = -1;
	mention.items = [];
	if (!list) return;
	list.hidden = true;
	list.replaceChildren();
	const textarea = document.querySelector('[data-composer-text]');
	textarea.setAttribute('aria-expanded', 'false');
	textarea.removeAttribute('aria-activedescendant');
}

export function suggestMentions(textarea) {
	const url = document.body.dataset.mentionUrl;
	if (!url || !mentionList()) return;
	const before = textarea.value.slice(0, textarea.selectionStart);
	const match = textarea.selectionStart === textarea.selectionEnd && before.match(MENTION_BEFORE_CARET);
	if (!match) { closeMentions(); return; }
	const query = match[1];
	const start = textarea.selectionStart - query.length - 1;
	clearTimeout(mention.timer);
	mention.timer = setTimeout(async () => {
		if (mention.controller) mention.controller.abort();
		mention.controller = new AbortController();
		try {
			const response = await fetch(url + '?q=' + encodeURIComponent(query), {
				headers: { Accept: 'application/json' }, signal: mention.controller.signal,
			});
			if (!response.ok) { closeMentions(); return; }
			const results = (await response.json()).results;
			results.forEach((person) => knownLogins.set(person.username, true));
			showMentions(textarea, start, results);
		} catch (e) { /* запрос отменён следующим нажатием или нет сети */ }
	}, 150);
}

function avatarNode(person) {
	if (person.avatar) {
		const img = document.createElement('img');
		img.className = 'avatar avatar-xs';
		img.src = person.avatar;
		img.alt = '';
		return img;
	}
	const span = document.createElement('span');
	span.className = 'avatar avatar-xs tone-' + person.tone;
	span.setAttribute('aria-hidden', 'true');
	span.textContent = person.initial;
	return span;
}

function showMentions(textarea, start, results) {
	const list = mentionList();
	if (!results.length) { closeMentions(); return; }
	mention.start = start;
	mention.items = results;
	mention.active = 0;
	list.replaceChildren(...results.map((person, index) => {
		const item = document.createElement('li');
		item.id = 'mention-option-' + index;
		item.className = 'mention-option';
		item.setAttribute('role', 'option');
		item.dataset.index = String(index);
		const who = document.createElement('span');
		who.className = 'who';
		const name = document.createElement('b');
		name.className = 'clip1';
		name.textContent = person.name;
		const login = document.createElement('span');
		login.className = 'muted clip1';
		login.textContent = '@' + person.username;
		who.append(name, login);
		item.append(avatarNode(person), who);
		return item;
	}));
	list.hidden = false;
	textarea.setAttribute('aria-expanded', 'true');
	highlightMention(0);
}

function highlightMention(index) {
	const list = mentionList();
	mention.active = (index + mention.items.length) % mention.items.length;
	list.querySelectorAll('[role="option"]').forEach((item) => {
		item.setAttribute('aria-selected', String(Number(item.dataset.index) === mention.active));
	});
	document.querySelector('[data-composer-text]').setAttribute('aria-activedescendant', 'mention-option-' + mention.active);
}

function insertMention(index) {
	const textarea = document.querySelector('[data-composer-text]');
	const person = mention.items[index];
	if (!person || mention.start < 0) return;
	const caret = textarea.selectionStart;
	const value = textarea.value;
	const inserted = '@' + person.username + ' ';
	textarea.value = value.slice(0, mention.start) + inserted + value.slice(caret).replace(/^\s/, '');
	const position = mention.start + inserted.length;
	textarea.setSelectionRange(position, position);
	closeMentions();
	textarea.dispatchEvent(new Event('input', { bubbles: true }));
	textarea.focus();
}

export function mentionKeydown(event) {
	const list = mentionList();
	if (!list || list.hidden || !event.target.matches('[data-composer-text]')) return false;
	if (event.ctrlKey || event.metaKey || event.altKey) return false;
	if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
		event.preventDefault();
		highlightMention(mention.active + (event.key === 'ArrowDown' ? 1 : -1));
		return true;
	}
	if (event.key === 'Enter' || event.key === 'Tab') {
		event.preventDefault();
		insertMention(mention.active);
		return true;
	}
	if (event.key === 'Escape') {
		// Закрываем только подсказки, сам composer остаётся открытым.
		event.preventDefault();
		closeMentions();
		return true;
	}
	return false;
}

// mousedown, а не click: иначе поле потеряет фокус раньше, чем мы вставим логин.
document.addEventListener('mousedown', (event) => {
	const option = event.target.closest('.mention-option');
	if (!option) return;
	event.preventDefault();
	insertMention(Number(option.dataset.index));
});
document.addEventListener('focusout', (event) => {
	if (event.target.matches('[data-composer-text]')) setTimeout(() => {
		if (document.activeElement !== event.target) closeMentions();
	}, 0);
});
document.addEventListener('click', (event) => {
	if (event.target.matches('[data-composer-text]')) suggestMentions(event.target);
});
