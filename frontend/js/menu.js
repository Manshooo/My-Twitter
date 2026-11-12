// ---------- Меню ----------
// Меню открывается в верхнем слое страницы (Popover API), поэтому его не обрезает overflow
// карточки и не перекрывает чужой z-index — где бы в разметке оно ни стояло. Место считаем сами:
// под кнопкой, по умолчанию правым краем к правому краю кнопки (раскрывается влево), с .menu-start —
// левым краем к левому (раскрывается вправо). Не помещается — пробуем другую сторону, а в конце
// прижимаем к краям экрана: меню никогда не уходит за экран.
const MENU_GAP = 4;
const VIEWPORT_PAD = 8;
const canPopover = typeof HTMLElement.prototype.showPopover === 'function';
let openMenu = null; // { btn, menu }

function placeMenu(btn, menu) {
	if (!canPopover) return; // старые браузеры: меню остаётся absolute внутри .menu-wrap
	const b = btn.getBoundingClientRect();
	const width = menu.offsetWidth;
	const height = menu.offsetHeight;
	const vw = document.documentElement.clientWidth;
	const vh = window.innerHeight;
	const fits = (left) => left >= VIEWPORT_PAD && left + width <= vw - VIEWPORT_PAD;
	const start = b.left;
	const end = b.right - width;
	let left = menu.classList.contains('menu-start') ? start : end;
	if (!fits(left)) left = left === start ? end : start;
	left = Math.max(VIEWPORT_PAD, Math.min(left, vw - VIEWPORT_PAD - width));

	let top = b.bottom + MENU_GAP;
	const above = b.top - MENU_GAP - height;
	if (top + height > vh - VIEWPORT_PAD && above >= VIEWPORT_PAD) top = above;
	top = Math.max(VIEWPORT_PAD, Math.min(top, vh - VIEWPORT_PAD - height));

	menu.style.left = `${Math.round(left)}px`;
	menu.style.top = `${Math.round(top)}px`;
}

function hideMenu(btn, menu) {
	btn.setAttribute('aria-expanded', 'false');
	if (!menu) return;
	if (canPopover && menu.matches(':popover-open')) menu.hidePopover();
	menu.hidden = true;
	if (openMenu && openMenu.menu === menu) openMenu = null;
}

export function closeMenus(except) {
	document.querySelectorAll('[data-menu-toggle][aria-expanded="true"]').forEach((btn) => {
		if (btn === except) return;
		hideMenu(btn, document.getElementById(btn.getAttribute('aria-controls')));
	});
}

export function toggleMenu(btn) {
	const menu = document.getElementById(btn.getAttribute('aria-controls'));
	if (!menu) return;
	const open = btn.getAttribute('aria-expanded') !== 'true';
	closeMenus(btn);
	if (!open) { hideMenu(btn, menu); return; }
	btn.setAttribute('aria-expanded', 'true');
	menu.hidden = false;
	if (canPopover) {
		// manual: закрытием по клику мимо и Esc по-прежнему управляет код ниже.
		if (!menu.hasAttribute('popover')) menu.setAttribute('popover', 'manual');
		menu.showPopover();
		placeMenu(btn, menu);
	}
	openMenu = { btn, menu };
	const first = menu.querySelector('[role^="menuitem"]');
	if (first) first.focus({ preventScroll: true });
}

// Меню в верхнем слое не едет вместе со страницей — двигаем его за кнопкой.
function followOpenMenu() {
	if (!openMenu) return;
	if (!openMenu.btn.isConnected) { hideMenu(openMenu.btn, openMenu.menu); return; }
	placeMenu(openMenu.btn, openMenu.menu);
}
window.addEventListener('resize', followOpenMenu);
document.addEventListener('scroll', followOpenMenu, { capture: true, passive: true });
