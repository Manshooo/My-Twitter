// ---------- Тосты ----------
let toastTimer = null;
export function toast(message) {
	let el = document.getElementById('toast');
	if (!el) return;
	el.textContent = message;
	el.hidden = false;
	clearTimeout(toastTimer);
	toastTimer = setTimeout(() => { el.hidden = true; }, 3000);
}
window.azzbToast = toast;
