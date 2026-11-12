import { readSavedDrafts } from './composer.js';
import { scrollToMainPost } from './posts.js';
import { syncThemeToggles } from './theme.js';
import { toast } from './toast.js';

// ---------- Приложение (PWA) ----------
// Воркер кэширует только статику и офлайн-страницу (/sw.js). Кнопка «Установить приложение»
// появляется, только если браузер предложил установку (Chrome, Edge, Яндекс Браузер).
const swMeta = document.querySelector('meta[name="azzb-sw"]');
if (swMeta && 'serviceWorker' in navigator) {
	window.addEventListener('load', () => navigator.serviceWorker.register(swMeta.content).catch(() => {}));
}

let installPrompt = null;
window.addEventListener('beforeinstallprompt', (event) => {
	event.preventDefault();
	installPrompt = event;
	document.querySelectorAll('[data-install-app]').forEach((el) => { el.hidden = false; });
});
window.addEventListener('appinstalled', () => {
	installPrompt = null;
	document.querySelectorAll('[data-install-app]').forEach((el) => { el.hidden = true; });
});
document.addEventListener('click', async (event) => {
	if (event.target.closest('[data-reload]')) { window.location.reload(); return; }
	if (!event.target.closest('[data-install-app]') || !installPrompt) return;
	installPrompt.prompt();
	await installPrompt.userChoice;
	installPrompt = null;
});
if (document.querySelector('[data-offline]')) window.addEventListener('online', () => window.location.reload());

document.addEventListener('DOMContentLoaded', () => {
	syncThemeToggles();
	scrollToMainPost();
	// Сообщения Django (например, «Почта подтверждена» после перехода по ссылке из письма).
	const flash = document.getElementById('toast');
	if (flash && flash.dataset.flash) toast(flash.dataset.flash);
	// Недописанный пост из прошлого визита ждёт в composer.
	const form = document.querySelector('#composer [data-composer-form]');
	if (form) {
		const saved = readSavedDrafts(form)[''];
		if (saved) form.querySelector('textarea').value = saved.text;
	}
});
