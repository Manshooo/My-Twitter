export const POST_MAX = 500;

// Сообщения об ошибке из ответа сервера: {"errors": [...]} или запасной текст.
export function errorsOf(xhr, fallback) {
	if (!xhr || !xhr.status) return ['Нет связи с сервером. Попробуйте ещё раз.'];
	if (xhr.status === 413) return ['Файлы слишком тяжёлые для отправки.'];
	try {
		const data = JSON.parse(xhr.responseText);
		if (Array.isArray(data.errors) && data.errors.length) return data.errors;
	} catch (e) { /* не JSON */ }
	return [fallback];
}

// Счётчик под постом, как фильтр count в azzb_ui.py: 0 → «», 1234 → «1,2 тыс.», 12345 → «12 тыс.».
export function formatCount(n) {
	for (const [size, unit] of [[1e6, 'млн'], [1e3, 'тыс.']]) {
		if (n >= size) {
			const tenths = Math.floor((n * 10) / size);
			const whole = Math.floor(tenths / 10);
			const text = tenths < 100 && tenths % 10 ? whole + ',' + (tenths % 10) : String(whole);
			return text + ' ' + unit;
		}
	}
	return n > 0 ? String(n) : '';
}
