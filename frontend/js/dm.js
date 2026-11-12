import { imageFiles } from './composer.js';
import { refreshBadges } from './realtime.js';
import { toast } from './toast.js';

// ---------- Сообщения (F2) ----------
// Новые сообщения вставляет один запрос — dm/_updates.html после ?after=<последний id>: по сигналу
// из сокета, после своей отправки и опросом без сокета. Поэтому у вкладки один путь вставки.
const dmScroll = document.getElementById('dm-scroll');
const dmConversation = dmScroll ? Number(dmScroll.dataset.dmChat) || 0 : 0;
const dmNearBottom = () => !dmScroll || dmScroll.scrollHeight - dmScroll.scrollTop - dmScroll.clientHeight < 120;
const dmToBottom = () => { if (dmScroll) dmScroll.scrollTop = dmScroll.scrollHeight; };
let dmStick = true;
let dmForceStick = false;  // своё отправленное сообщение показываем, даже если листали вверх
const dmUpdate = () => document.dispatchEvent(new CustomEvent('azzb:dm-update'));

function dmLastId() {
	const items = dmScroll ? dmScroll.querySelectorAll('[data-message-id]') : [];
	return items.length ? items[items.length - 1].dataset.messageId : '0';
}

if (dmScroll) {
	dmToBottom();
	document.addEventListener('htmx:configRequest', (event) => {
		if (event.detail.elt.hasAttribute('data-dm-updates')) event.detail.parameters.after = dmLastId();
	});
	document.addEventListener('htmx:beforeSwap', (event) => {
		if (event.detail.target && event.detail.target.id === 'dm-messages') {
			dmStick = dmForceStick || dmNearBottom();
			dmForceStick = false;
		}
	});
	document.addEventListener('htmx:afterSwap', (event) => {
		if (!event.detail.target || event.detail.target.id !== 'dm-messages') return;
		// Сигнал и ответ на отправку могли принести одно и то же сообщение.
		const seen = new Set();
		dmScroll.querySelectorAll('[data-message-id]').forEach((item) => {
			if (seen.has(item.dataset.messageId)) item.remove();
			else seen.add(item.dataset.messageId);
		});
		if (seen.size) dmScroll.querySelectorAll('.dm-empty').forEach((hint) => { hint.hidden = true; });
		if (dmStick) dmToBottom();
	});
}

function dmMarkDeleted(id) {
	const item = document.getElementById('m' + id);
	if (!item) return;
	const bubble = item.querySelector('.msg-bubble');
	bubble.className = 'msg-bubble msg-gone';
	bubble.textContent = 'Сообщение удалено';
	const button = item.querySelector('.msg-delete');
	if (button) button.remove();
}

let dmListTimer = null;
document.addEventListener('azzb:ws:dm', (event) => {
	refreshBadges();
	const data = event.detail;
	if (data.deleted) dmMarkDeleted(data.deleted);
	if (data.conversation === dmConversation) dmUpdate();
	if (document.getElementById('dm-list')) {
		clearTimeout(dmListTimer);
		dmListTimer = setTimeout(() => document.dispatchEvent(new CustomEvent('azzb:dm-list')), 500);
	}
});
document.addEventListener('azzb:ws:dm-read', (event) => {
	if (event.detail.conversation === dmConversation) dmUpdate();
});
// После переподключения сигналы за время обрыва потеряны — догоняем.
document.addEventListener('azzb:ws:open', () => {
	if (dmConversation) dmUpdate();
	if (document.getElementById('dm-list')) document.dispatchEvent(new CustomEvent('azzb:dm-list'));
});

let typingTimer = null;
document.addEventListener('azzb:ws:typing', (event) => {
	const typing = document.getElementById('dm-typing');
	if (!typing || event.detail.conversation !== dmConversation) return;
	typing.hidden = false;
	clearTimeout(typingTimer);
	typingTimer = setTimeout(() => { typing.hidden = true; }, 5000);
});
// Пришло сообщение — значит, уже не печатает.
document.addEventListener('htmx:afterSwap', (event) => {
	const typing = document.getElementById('dm-typing');
	if (typing && event.detail.target && event.detail.target.id === 'dm-messages' && event.detail.target.children.length) typing.hidden = true;
});

const dmForm = document.querySelector('[data-dm-form]');
if (dmForm) {
	const text = dmForm.querySelector('[data-dm-text]');
	const input = dmForm.querySelector('[data-dm-files]');
	const previews = dmForm.querySelector('[data-dm-previews]');
	const maxFiles = Number(input.dataset.max) || 4;
	const maxBytes = (Number(input.dataset.maxMb) || 10) * 1024 * 1024;
	let files = [];
	let lastTyping = 0;

	const grow = () => { text.style.height = 'auto'; text.style.height = text.scrollHeight + 'px'; };

	function syncFiles() {
		const transfer = new DataTransfer();
		files.forEach((file) => transfer.items.add(file));
		input.files = transfer.files;
		previews.querySelectorAll('img').forEach((img) => URL.revokeObjectURL(img.src));
		previews.replaceChildren(...files.map((file, index) => {
			const item = document.createElement('li');
			const img = document.createElement('img');
			img.src = URL.createObjectURL(file);
			img.alt = '';
			const remove = document.createElement('button');
			remove.type = 'button';
			remove.setAttribute('aria-label', 'Убрать картинку ' + (index + 1));
			remove.innerHTML = '<svg class="icon icon-xs" aria-hidden="true"><use href="#i-close"></use></svg>';
			remove.addEventListener('click', () => { files.splice(index, 1); syncFiles(); });
			item.append(img, remove);
			return item;
		}));
		previews.hidden = !files.length;
	}

	const attachFiles = (list) => {
		const picked = Array.from(list).filter((file) => {
			if (!input.accept.split(',').includes(file.type) || file.size > maxBytes) {
				toast('Нужна картинка JPEG, PNG, WebP или GIF до ' + input.dataset.maxMb + ' МБ');
				return false;
			}
			return true;
		});
		if (!picked.length) return;
		files = files.concat(picked);
		if (files.length > maxFiles) {
			toast('Не больше ' + maxFiles + ' картинок в сообщении');
			files = files.slice(0, maxFiles);
		}
		syncFiles();
	};
	input.addEventListener('change', () => attachFiles(input.files));
	// Картинка из буфера (Ctrl+V) или перетащенная в окно переписки — как выбранная кнопкой.
	dmForm.addEventListener('paste', (event) => {
		const pasted = imageFiles(event.clipboardData && event.clipboardData.files);
		if (!pasted.length) return;
		event.preventDefault();
		attachFiles(pasted);
	});
	const chat = dmForm.closest('.dm-chat');
	const draggingFiles = (event) => event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files');
	chat.addEventListener('dragover', (event) => {
		if (!draggingFiles(event)) return;
		event.preventDefault();
		chat.classList.add('dragging');
	});
	chat.addEventListener('dragleave', (event) => {
		if (!chat.contains(event.relatedTarget)) chat.classList.remove('dragging');
	});
	chat.addEventListener('drop', (event) => {
		if (!draggingFiles(event)) return;
		event.preventDefault();
		chat.classList.remove('dragging');
		attachFiles(event.dataTransfer.files);
	});

	text.addEventListener('input', () => {
		grow();
		const now = Date.now();
		if (dmConversation && text.value.trim() && now - lastTyping > 3000) {
			lastTyping = now;
			window.azzbSend({event: 'typing', conversation: dmConversation});
		}
	});
	// Enter — отправить, Shift+Enter — новая строка. На телефоне Enter — всегда новая строка.
	text.addEventListener('keydown', (event) => {
		if (event.key !== 'Enter' || event.shiftKey || event.isComposing || matchMedia('(pointer: coarse)').matches) return;
		event.preventDefault();
		dmForm.requestSubmit();
	});

	dmForm.addEventListener('htmx:beforeRequest', (event) => {
		if (event.detail.elt === dmForm && !text.value.trim() && !files.length) event.preventDefault();
	});
	dmForm.addEventListener('htmx:afterRequest', (event) => {
		if (event.detail.elt !== dmForm || !event.detail.successful) return;
		dmForm.reset();
		files = [];
		syncFiles();
		grow();
		lastTyping = 0;
		dmForceStick = true;
		dmUpdate();
		text.focus();
	});
}
