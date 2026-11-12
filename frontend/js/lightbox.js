import { syncModalOpen } from './modal.js';

// ---------- Просмотр картинок ----------
const lightbox = { items: [], index: 0, opener: null };
export const lightboxEl = () => document.getElementById('lightbox');

function showLightboxItem() {
	const box = lightboxEl();
	const item = lightbox.items[lightbox.index];
	const img = box.querySelector('[data-lightbox-img]');
	img.src = item.src;
	img.alt = item.alt;
	const caption = box.querySelector('[data-lightbox-caption]');
	caption.textContent = item.described ? item.alt : '';
	caption.hidden = !item.described;
	const many = lightbox.items.length > 1;
	box.querySelectorAll('[data-lightbox-step]').forEach((btn) => { btn.hidden = !many; });
	box.querySelector('[data-lightbox-count]').textContent = many ? (lightbox.index + 1) + ' / ' + lightbox.items.length : '';
}

export function openLightbox(link) {
	const box = lightboxEl();
	const gallery = link.closest('[data-gallery]');
	if (!box || !gallery) return false;
	lightbox.items = Array.from(gallery.querySelectorAll('[data-lightbox]')).map((a) => ({
		src: a.href,
		alt: a.querySelector('img').alt,
		described: Boolean(a.querySelector('.alt-badge')),
	}));
	lightbox.index = Number(link.dataset.lightbox) || 0;
	lightbox.opener = link;
	showLightboxItem();
	box.hidden = false;
	syncModalOpen();
	box.querySelector('[data-lightbox-close]').focus();
	return true;
}

export function stepLightbox(delta) {
	const n = lightbox.items.length;
	if (n < 2) return;
	lightbox.index = (lightbox.index + delta + n) % n;
	showLightboxItem();
}

export function closeLightbox() {
	const box = lightboxEl();
	if (!box || box.hidden) return false;
	box.hidden = true;
	box.querySelector('[data-lightbox-img]').removeAttribute('src');
	syncModalOpen();
	if (lightbox.opener) lightbox.opener.focus();
	return true;
}
