// ---------- Модальные окна ----------
export function syncModalOpen() {
	const anyOpen = Array.from(document.querySelectorAll('.modal, .lightbox')).some((el) => !el.hidden);
	document.body.classList.toggle('modal-open', anyOpen);
}

// Куда вернуть фокус, когда окно закроется.
let lastFocus = null;
export function rememberFocus() {
	lastFocus = document.activeElement;
}
export function restoreFocus() {
	if (lastFocus) lastFocus.focus();
}
