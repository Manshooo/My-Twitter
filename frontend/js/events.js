import { addFiles, autosize, closeComposer, composer, composerMode, imageFiles, openComposer, openEdit, openQuote, openReply, removeAttachment, saveDraftSoon, trapFocus, updateCounter } from './composer.js';
import { cookieBanner, openCookieSettings, saveCookieChoice, showCookieOptions } from './cookies.js';
import { applyCrop, closeCropper, crop, cropperEl, drawCrop, moveCropDrag, openCropper, setCropZoom, startCropDrag } from './cropper.js';
import { closeLightbox, lightboxEl, openLightbox, stepLightbox } from './lightbox.js';
import { mentionKeydown, suggestMentions } from './mentions.js';
import { closeMenus, toggleMenu } from './menu.js';
import { addPollOption, pollActive, removePollOption, setPoll } from './poll.js';
import { copyLink } from './posts.js';
import { applyTheme, toggleTheme } from './theme.js';

// ---------- Делегирование событий ----------
document.addEventListener('click', (event) => {
	const target = event.target.closest('button, a');
	if (!target) {
		if (!event.target.closest('[role="menu"]')) closeMenus();
		const modal = composer();
		if (modal && event.target === modal) closeComposer();
		// Клик мимо картинки в просмотрщике закрывает его.
		if (event.target.closest('#lightbox') && !event.target.closest('img')) closeLightbox();
		return;
	}
	if (target.matches('[data-menu-toggle]')) { event.preventDefault(); toggleMenu(target); return; }
	if (target.matches('[data-theme-toggle]')) { event.preventDefault(); toggleTheme(); return; }
	if (target.matches('[data-composer-open]')) { event.preventDefault(); openComposer({ kind: 'new' }); return; }
	if (target.matches('[data-poll-toggle]')) { event.preventDefault(); setPoll(target.form, !pollActive(target.form)); return; }
	if (target.matches('[data-poll-add]')) { event.preventDefault(); addPollOption(target.form); return; }
	if (target.matches('[data-poll-remove]')) { event.preventDefault(); removePollOption(target); return; }
	if (target.matches('[data-cookie-accept]')) { event.preventDefault(); saveCookieChoice(target.dataset.cookieAccept); return; }
	if (target.matches('[data-cookie-customize]')) { event.preventDefault(); showCookieOptions(cookieBanner()); return; }
	if (target.matches('[data-cookie-settings]')) { event.preventDefault(); openCookieSettings(); return; }
	if (target.matches('[data-reply]')) { event.preventDefault(); openReply(target); return; }
	if (target.matches('[data-quote]')) { event.preventDefault(); openQuote(target); return; }
	if (target.matches('[data-edit]')) { event.preventDefault(); openEdit(target); return; }
	if (target.matches('[data-composer-close]')) { event.preventDefault(); closeComposer(); return; }
	if (target.matches('[data-composer-attach]')) { event.preventDefault(); target.form.querySelector('[data-composer-file]').click(); return; }
	if (target.matches('[data-attachment-remove]')) { event.preventDefault(); removeAttachment(target.form, Number(target.dataset.index)); return; }
	if (target.matches('[data-lightbox]')) {
		// Ctrl/⌘/Shift+клик — открыть картинку в новой вкладке, как обычную ссылку.
		if (event.ctrlKey || event.metaKey || event.shiftKey) return;
		if (openLightbox(target)) event.preventDefault();
		return;
	}
	if (target.matches('[data-lightbox-close]')) { event.preventDefault(); closeLightbox(); return; }
	if (target.matches('[data-lightbox-step]')) { event.preventDefault(); stepLightbox(Number(target.dataset.lightboxStep)); return; }
	if (target.matches('[data-crop-cancel]')) { event.preventDefault(); closeCropper(true); return; }
	if (target.matches('[data-crop-apply]')) { event.preventDefault(); applyCrop(); return; }
	if (target.matches('[data-copy]')) { event.preventDefault(); copyLink(target); return; }
	// «Назад» возвращает туда, откуда пришли с этого же сайта (с той же позицией в ленте);
	// если пришли по внешней ссылке — обычный переход на главную.
	if (target.matches('[data-back]') && document.referrer.startsWith(window.location.origin + '/') && window.history.length > 1) {
		event.preventDefault();
		window.history.back();
		return;
	}
	if (!target.closest('[role="menu"]')) closeMenus();
});

document.addEventListener('keydown', (event) => {
	if (mentionKeydown(event)) return;
	if (event.key === 'Tab') { trapFocus(event); return; }
	// Ctrl+Enter (⌘+Enter на Mac) — отправить из composer.
	if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.target.closest('[data-composer-form]')) {
		const form = event.target.closest('[data-composer-form]');
		event.preventDefault();
		if (!form.querySelector('[type="submit"]').disabled) form.requestSubmit();
		return;
	}
	const box = lightboxEl();
	if (box && !box.hidden) {
		if (event.key === 'ArrowLeft') { event.preventDefault(); stepLightbox(-1); return; }
		if (event.key === 'ArrowRight') { event.preventDefault(); stepLightbox(1); return; }
		if (event.key === 'Escape') { closeLightbox(); return; }
	}
	const cropper = cropperEl();
	if (cropper && !cropper.hidden) {
		if (event.key === 'Escape') { closeCropper(true); return; }
		if (!event.target.matches('[data-crop-frame]')) return;
		const moves = { ArrowLeft: [10, 0], ArrowRight: [-10, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] };
		if (moves[event.key]) {
			event.preventDefault();
			crop.ox += moves[event.key][0];
			crop.oy += moves[event.key][1];
			drawCrop();
		} else if (event.key === '+' || event.key === '=') {
			setCropZoom(crop.zoom + 0.1);
		} else if (event.key === '-') {
			setCropZoom(crop.zoom - 0.1);
		}
		return;
	}
	if (event.key !== 'Escape') return;
	closeMenus();
	closeComposer();
});

document.addEventListener('input', (event) => {
	if (event.target.matches('[data-composer-text]')) {
		updateCounter(event.target.form);
		autosize(event.target);
		saveDraftSoon(event.target.form);
		suggestMentions(event.target);
	}
	if (event.target.matches('[data-poll-input]')) updateCounter(event.target.form);
	if (event.target.matches('[data-crop-zoom]')) setCropZoom(Number(event.target.value));
});

document.addEventListener('pointerdown', startCropDrag);
document.addEventListener('pointermove', moveCropDrag);
document.addEventListener('pointerup', () => { crop.drag = null; });
document.addEventListener('pointercancel', () => { crop.drag = null; });
document.addEventListener('wheel', (event) => {
	if (!event.target.closest('[data-crop-frame]')) return;
	event.preventDefault();
	setCropZoom(crop.zoom - Math.sign(event.deltaY) * 0.1);
}, { passive: false });

document.addEventListener('change', (event) => {
	if (event.target.matches('[data-crop-input]')) { openCropper(event.target); return; }
	// В настройках тема меняется сразу, для примерки; сохранится вместе с формой.
	if (event.target.matches('[data-theme-choice] input')) { applyTheme(event.target.value); return; }
	if (event.target.matches('[data-composer-file]')) {
		addFiles(event.target.form, event.target.files);
		event.target.value = ''; // чтобы тот же файл можно было выбрать снова
	}
});

// Картинку можно вставить из буфера (Ctrl+V) или перетащить в окно composer.
document.addEventListener('paste', (event) => {
	const form = event.target.closest && event.target.closest('[data-composer-form]');
	if (!form || composerMode.kind === 'edit') return;
	const files = imageFiles(event.clipboardData && event.clipboardData.files);
	if (!files.length) return;
	event.preventDefault();
	addFiles(form, files);
});

function dropTarget(event) {
	const modal = composer();
	if (!modal || modal.hidden || composerMode.kind === 'edit') return null;
	if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return null;
	return modal.querySelector('[data-composer-form]');
}
document.addEventListener('dragover', (event) => {
	const form = dropTarget(event);
	if (!form) return;
	event.preventDefault();
	form.classList.add('dragging');
});
document.addEventListener('dragleave', (event) => {
	if (event.relatedTarget === null) document.querySelectorAll('.dragging').forEach((el) => el.classList.remove('dragging'));
});
document.addEventListener('drop', (event) => {
	const form = dropTarget(event);
	if (!form) return;
	event.preventDefault();
	form.classList.remove('dragging');
	addFiles(form, imageFiles(event.dataTransfer.files));
});

// Обычные формы с подтверждением: <form data-confirm="Точно?"> (htmx-кнопкам хватает hx-confirm).
document.addEventListener('submit', (event) => {
	const form = event.target.closest('form[data-confirm]');
	if (form && !window.confirm(form.dataset.confirm)) event.preventDefault();
});
