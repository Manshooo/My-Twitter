// ---------- Плашка «Присоединяйтесь» на гостевых страницах ----------
// Показываем, когда человек начал читать (прокрутил страницу), — не сразу поверх поста.
// Закрытая плашка не возвращается до конца сеанса вкладки.
const CLOSED_KEY = 'azzb-guest-cta-closed';
const SHOW_AFTER = 240;

function wasClosed() {
	try { return window.sessionStorage.getItem(CLOSED_KEY) === '1'; } catch (e) { return false; }
}

const cta = document.querySelector('[data-guest-cta]');
if (cta && !wasClosed()) {
	const reveal = () => {
		if (window.scrollY < SHOW_AFTER) return;
		cta.hidden = false;
		window.removeEventListener('scroll', reveal);
	};
	window.addEventListener('scroll', reveal, { passive: true });
	reveal();
}

document.addEventListener('click', (event) => {
	if (!cta || !event.target.closest('[data-guest-cta-close]')) return;
	cta.hidden = true;
	try { window.sessionStorage.setItem(CLOSED_KEY, '1'); } catch (e) { /* приватный режим: просто скрываем */ }
});
