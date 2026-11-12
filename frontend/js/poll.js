import { updateCounter } from './composer.js';

// ---------- Опрос в composer (B7) ----------
function pollEditor(form) {
	return form.querySelector('[data-poll-editor]');
}

export function pollActive(form) {
	const editor = pollEditor(form);
	return Boolean(editor && !editor.hidden);
}

export function filledPollOptions(form) {
	return Array.from(form.querySelectorAll('[data-poll-input]')).filter((input) => input.value.trim()).length;
}

export function setPoll(form, on) {
	const editor = pollEditor(form);
	if (!editor) return;
	editor.hidden = !on;
	editor.disabled = !on; // выключенный fieldset не попадает в отправку формы
	form.querySelector('.composer-tools [data-poll-toggle]').setAttribute('aria-pressed', String(on));
	if (!on) {
		editor.querySelectorAll('[data-poll-input]').forEach((input) => { input.value = ''; });
		editor.querySelectorAll('[data-poll-row]').forEach((row, index) => { row.hidden = index >= 2; });
	}
	syncPollAdd(form);
	updateCounter(form);
	if (on) editor.querySelector('[data-poll-input]').focus();
}

function syncPollAdd(form) {
	const add = form.querySelector('[data-poll-add]');
	if (add) add.hidden = !form.querySelector('[data-poll-row][hidden]');
}

export function addPollOption(form) {
	const row = form.querySelector('[data-poll-row][hidden]');
	if (!row) return;
	row.hidden = false;
	row.querySelector('input').focus();
	syncPollAdd(form);
}

export function removePollOption(btn) {
	const row = btn.closest('[data-poll-row]');
	const form = btn.form;
	row.querySelector('input').value = '';
	row.hidden = true;
	syncPollAdd(form);
	updateCounter(form);
}
