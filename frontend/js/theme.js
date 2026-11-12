// ---------- Тема ----------
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
function isDark() {
	const chosen = document.documentElement.dataset.theme;
	return chosen ? chosen === 'dark' : darkQuery.matches;
}
export function syncThemeToggles() {
	const dark = String(isDark());
	document.querySelectorAll('[data-theme-toggle]').forEach((el) => el.setAttribute('aria-checked', dark));
}
export function applyTheme(theme) {
	if (theme) document.documentElement.dataset.theme = theme;
	else delete document.documentElement.dataset.theme; // как в системе
	syncThemeToggles();
}
export function toggleTheme() {
	const next = isDark() ? 'light' : 'dark';
	applyTheme(next);
	// Cookie нужна серверу, чтобы сразу отдать страницу в нужной теме, без мигания.
	document.cookie = 'theme=' + next + '; path=/; max-age=31536000; SameSite=Lax';
	// Вошедшим — ещё и в аккаунт, чтобы выбор был на всех устройствах.
	const url = document.body.dataset.themeUrl;
	if (url && window.htmx) htmx.ajax('POST', url, { source: document.body, values: { theme: next }, swap: 'none' });
}
darkQuery.addEventListener('change', syncThemeToggles);
