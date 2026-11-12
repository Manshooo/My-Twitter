import { rememberFocus, syncModalOpen } from './modal.js';
import { toast } from './toast.js';

// ---------- Кадрирование аватара и баннера ----------
// Сам файл уходит на сервер как есть, а вместе с ним — выбранная область в долях
// (x, y, ширина, высота). Обрезает и сжимает сервер; без JS он берёт центр.
export const crop = { input: null, name: '', natural: [1, 1], zoom: 1, ox: 0, oy: 0, drag: null, url: null };
export const cropperEl = () => document.getElementById('cropper');
const CROP_PREVIEW = { avatar: [192, 192], banner: [900, 300] };

function cropMetrics() {
	const frame = cropperEl().querySelector('[data-crop-frame]');
	const W = frame.clientWidth;
	const H = frame.clientHeight;
	const [w, h] = crop.natural;
	return { W: W, H: H, w: w, h: h, scale: Math.max(W / w, H / h) * crop.zoom };
}

export function drawCrop() {
	const m = cropMetrics();
	crop.ox = Math.min(0, Math.max(m.W - m.w * m.scale, crop.ox));
	crop.oy = Math.min(0, Math.max(m.H - m.h * m.scale, crop.oy));
	const img = cropperEl().querySelector('[data-crop-img]');
	img.style.width = m.w + 'px';
	img.style.height = m.h + 'px';
	img.style.transform = 'translate(' + crop.ox + 'px, ' + crop.oy + 'px) scale(' + m.scale + ')';
}

export function setCropZoom(zoom) {
	const before = cropMetrics();
	// Приближаем относительно центра кадра, а не левого верхнего угла.
	const cx = (before.W / 2 - crop.ox) / before.scale;
	const cy = (before.H / 2 - crop.oy) / before.scale;
	crop.zoom = Math.min(4, Math.max(1, zoom));
	const after = cropMetrics();
	crop.ox = after.W / 2 - cx * after.scale;
	crop.oy = after.H / 2 - cy * after.scale;
	cropperEl().querySelector('[data-crop-zoom]').value = String(crop.zoom);
	drawCrop();
}

export function openCropper(input) {
	const modal = cropperEl();
	const file = input.files && input.files[0];
	if (!modal || !file) return;
	const limit = input.closest('[data-max-mb]');
	const maxMb = Number(limit ? limit.dataset.maxMb : 10);
	if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type) || file.size > maxMb * 1024 * 1024) {
		input.value = '';
		toast('Нужна картинка JPEG, PNG, WebP или GIF до ' + maxMb + ' МБ');
		return;
	}
	crop.input = input;
	crop.name = input.dataset.cropInput;
	if (crop.url) URL.revokeObjectURL(crop.url);
	crop.url = URL.createObjectURL(file);
	const img = modal.querySelector('[data-crop-img]');
	const frame = modal.querySelector('[data-crop-frame]');
	frame.dataset.shape = crop.name;
	modal.querySelector('[data-crop-title]').textContent = crop.name === 'avatar' ? 'Аватар' : 'Баннер';
	img.onload = () => {
		crop.natural = [img.naturalWidth, img.naturalHeight];
		crop.zoom = 1;
		modal.querySelector('[data-crop-zoom]').value = '1';
		const m = cropMetrics();
		crop.ox = (m.W - m.w * m.scale) / 2;
		crop.oy = (m.H - m.h * m.scale) / 2;
		drawCrop();
	};
	img.onerror = () => { closeCropper(true); toast('Не удалось открыть картинку'); };
	rememberFocus();
	modal.hidden = false;
	syncModalOpen();
	img.src = crop.url;
	frame.focus();
}

export function closeCropper(cancel) {
	const modal = cropperEl();
	if (!modal || modal.hidden) return false;
	if (cancel && crop.input) {
		crop.input.value = '';
		crop.input.form.querySelector('[name="' + crop.name + '_crop"]').value = '';
	}
	modal.hidden = true;
	syncModalOpen();
	if (crop.input) crop.input.focus();
	return true;
}

export function applyCrop() {
	const m = cropMetrics();
	const box = {
		x: -crop.ox / (m.w * m.scale),
		y: -crop.oy / (m.h * m.scale),
		w: m.W / (m.w * m.scale),
		h: m.H / (m.h * m.scale),
	};
	const form = crop.input.form;
	form.querySelector('[name="' + crop.name + '_crop"]').value =
		[box.x, box.y, box.w, box.h].map((v) => Math.min(1, Math.max(0, v)).toFixed(5)).join(',');
	// Превью: как будет выглядеть после сохранения.
	const [pw, ph] = CROP_PREVIEW[crop.name];
	const canvas = document.createElement('canvas');
	canvas.width = pw;
	canvas.height = ph;
	const img = cropperEl().querySelector('[data-crop-img]');
	canvas.getContext('2d').drawImage(img, box.x * m.w, box.y * m.h, box.w * m.w, box.h * m.h, 0, 0, pw, ph);
	const preview = form.querySelector('[data-crop-preview="' + crop.name + '"]');
	const shot = document.createElement('img');
	shot.src = canvas.toDataURL('image/jpeg', 0.9);
	shot.alt = '';
	if (crop.name === 'avatar') shot.className = 'avatar avatar-xl';
	preview.classList.remove('ph');
	preview.replaceChildren(shot);
	const clear = form.querySelector('[name="' + crop.name + '_clear"]');
	if (clear) clear.checked = false;
	closeCropper(false);
}

export function startCropDrag(event) {
	const frame = event.target.closest('[data-crop-frame]');
	if (!frame || event.button !== 0) return;
	crop.drag = { x: event.clientX, y: event.clientY, ox: crop.ox, oy: crop.oy };
	frame.setPointerCapture(event.pointerId);
}

export function moveCropDrag(event) {
	if (!crop.drag) return;
	crop.ox = crop.drag.ox + event.clientX - crop.drag.x;
	crop.oy = crop.drag.oy + event.clientY - crop.drag.y;
	drawCrop();
}
