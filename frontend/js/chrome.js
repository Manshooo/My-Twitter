// ---------- Шапка и вкладки на телефоне ----------
// Прокрутка вниз прячет липкие шапку и вкладки (класс chrome-hidden на <body>, CSS в layout.css),
// прокрутка вверх возвращает: на телефоне они занимали около пятой части экрана.
const PHONE = window.matchMedia('(max-width: 760px)');
const THRESHOLD = 8;
let lastY = window.scrollY;

window.addEventListener('scroll', () => {
	const y = window.scrollY;
	if (Math.abs(y - lastY) < THRESHOLD) return;
	// Не прячем у самого верха и пока открыто меню: его кнопка может быть в шапке.
	const hide = PHONE.matches && y > lastY && y > 120 && !document.querySelector('[data-menu-toggle][aria-expanded="true"]');
	document.body.classList.toggle('chrome-hidden', hide);
	lastY = y;
}, { passive: true });
