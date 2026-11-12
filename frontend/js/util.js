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
