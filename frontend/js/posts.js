import { bumpReplyCount, composerOf, setRepostCount } from './composer.js';
import { closeMenus } from './menu.js';
import { toast } from './toast.js';
import { errorsOf } from './util.js';

// ---------- Посты ----------
// Лайк, удаление и «Показать ещё» — атрибуты hx-* в шаблонах. Сервер дополняет их
// событиями в заголовке HX-Trigger: azzb:toast и azzb:post-deleted.
document.addEventListener('azzb:toast', (event) => toast(event.detail.value));
document.addEventListener('azzb:reposts', (event) => setRepostCount(event.detail.id, event.detail.count));

document.addEventListener('azzb:post-deleted', (event) => {
	const { id, replyOf } = event.detail;
	document.querySelectorAll('[data-post-id="' + id + '"]').forEach((card) => card.remove());
	// Ответы под удалённым постом остаются в ветке (там он теперь заглушка) и в счётчиках выше.
	if (replyOf) bumpReplyCount(replyOf, -1);
});

// Ошибка запроса не из composer (у него свой блок ошибок) — короткий тост.
function requestFailed(event) {
	if (composerOf(event)) return;
	const elt = event.detail.elt;
	if (elt && elt.hasAttribute('data-silent')) return;
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

export async function copyLink(btn) {
	closeMenus();
	const url = new URL(btn.dataset.copy, window.location.origin).href;
	try {
		await navigator.clipboard.writeText(url);
		toast('Ссылка скопирована');
	} catch (e) {
		window.prompt('Скопируйте ссылку', url);
	}
}

// Ответ из середины ветки: посты выше по ветке стоят над ним, и без прокрутки открытый пост
// оказывается где-то внизу страницы. Прокручиваем к нему — кроме «Назад» и перезагрузки
// (браузер сам вернёт прежнее место) и ссылки с #якорем.
export function scrollToMainPost() {
	const main = document.querySelector('[data-main-post]');
	if (!main || !document.querySelector('.thread') || window.location.hash) return;
	const nav = performance.getEntriesByType ? performance.getEntriesByType('navigation')[0] : null;
	if (nav && (nav.type === 'back_forward' || nav.type === 'reload')) return;
	main.scrollIntoView({ block: 'start' });
}
