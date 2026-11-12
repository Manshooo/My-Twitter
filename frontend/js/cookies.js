import { toast } from './toast.js';

// ---------- Cookie и Яндекс Метрика ----------
// Выбор хранится в cookie cookie_consent (формат и версия — azzb/cookies.py). Метрику грузим,
// только если её номер задан на сервере (<meta name="azzb-metrika">) и аналитика разрешена.
const CONSENT_COOKIE = 'cookie_consent';
const CONSENT_VERSION = 'v1';
const METRIKA_COOKIES = ['_ym_uid', '_ym_d', '_ym_isad', '_ym_visorc', '_ym_hostIndex'];
let metrikaLoaded = false;

function loadMetrika() {
	const meta = document.querySelector('meta[name="azzb-metrika"]');
	if (!meta || metrikaLoaded) return;
	metrikaLoaded = true;
	const id = Number(meta.content);
	window.ym = window.ym || function () { (window.ym.a = window.ym.a || []).push(arguments); };
	window.ym.l = Date.now();
	const script = document.createElement('script');
	script.async = true;
	script.src = 'https://mc.yandex.ru/metrika/tag.js?id=' + id;
	document.head.append(script);
	// Как в коде счётчика из Метрики, но без <noscript>-пикселя (он считал бы и тех, кто не давал согласия),
	// без trackHash (на сайте нет навигации по #) и ecommerce. Вебвизор выключен: запись экрана — лишнее для соцсети.
	window.ym(id, 'init', { ssr: true, clickmap: true, trackLinks: true, accurateTrackBounce: true, webvisor: false });
}

function dropMetrikaCookies() {
	const host = window.location.hostname;
	const domains = ['', host, '.' + host, '.' + host.split('.').slice(-2).join('.')];
	METRIKA_COOKIES.forEach((name) => domains.forEach((domain) => {
		document.cookie = name + '=; path=/; max-age=0' + (domain ? '; domain=' + domain : '');
	}));
}

export function cookieBanner() {
	return document.querySelector('[data-cookie-banner]');
}

export function saveCookieChoice(kind) {
	const banner = cookieBanner();
	let analytics = kind === 'all';
	if (kind === 'custom' && banner) analytics = banner.querySelector('[data-cookie-category="analytics"]').checked;
	const value = CONSENT_VERSION + ':' + (analytics ? 'analytics' : 'necessary');
	document.cookie = CONSENT_COOKIE + '=' + value + '; path=/; max-age=31536000; SameSite=Lax'
		+ (window.location.protocol === 'https:' ? '; Secure' : '');
	if (banner) {
		banner.querySelector('[data-cookie-category="analytics"]').checked = analytics;
		banner.hidden = true;
	}
	if (analytics) {
		loadMetrika();
	} else {
		dropMetrikaCookies();
		// Уже загруженный счётчик из страницы не выгрузить — перестанет грузиться со следующей.
	}
	toast(analytics ? 'Аналитика разрешена' : 'Используем только необходимые cookie');
}

export function openCookieSettings() {
	const banner = cookieBanner();
	if (!banner) return;
	banner.hidden = false;
	showCookieOptions(banner);
	banner.querySelector('[data-cookie-category="analytics"]').focus();
}

export function showCookieOptions(banner) {
	banner.querySelector('[data-cookie-options]').hidden = false;
	banner.querySelector('[data-cookie-customize]').hidden = true;
	banner.querySelector('[data-cookie-accept="custom"]').hidden = false;
}

document.addEventListener('DOMContentLoaded', () => {
	const meta = document.querySelector('meta[name="azzb-metrika"]');
	if (meta && meta.hasAttribute('data-allowed')) loadMetrika();
});
