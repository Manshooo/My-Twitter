// ---------- Реальное время (F1) ----------
// Сокет приносит только сигналы ({event: 'badges'}, {event: 'dm', ...}), данные забирает htmx.
// Каждый сигнал становится событием документа azzb:ws:<event>. Пока сокета нет, работает опрос
// (события azzb:poll-5 и azzb:poll-30 ниже), а после (пере)подключения всё обновляется один раз:
// сигналы, пришедшие без нас, потеряны.
window.azzbLive = false;

// Условие опроса — здесь, а не фильтром [...] в hx-trigger: фильтры htmx исполняются через eval, его запрещает CSP.
let pollSeconds = 0;
setInterval(() => {
	pollSeconds += 5;
	if (document.visibilityState !== 'visible' || window.azzbLive) return;
	document.dispatchEvent(new CustomEvent('azzb:poll-5'));
	if (pollSeconds % 30 === 0) document.dispatchEvent(new CustomEvent('azzb:poll-30'));
}, 5000);
const wsPath = document.body.dataset.wsPath;
let socket = null;
let wsAttempt = 0;
let badgesTimer = null;

function wsConnect() {
	socket = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + wsPath);
	socket.addEventListener('open', () => {
		wsAttempt = 0;
		window.azzbLive = true;
		document.dispatchEvent(new CustomEvent('azzb:ws:open'));
		refreshBadges();
	});
	socket.addEventListener('message', (event) => {
		let data;
		try { data = JSON.parse(event.data); } catch (e) { return; }
		if (data && typeof data.event === 'string') {
			document.dispatchEvent(new CustomEvent('azzb:ws:' + data.event, {detail: data}));
		}
	});
	socket.addEventListener('close', (event) => {
		socket = null;
		window.azzbLive = false;
		document.dispatchEvent(new CustomEvent('azzb:ws:close'));
		if (event.code === 4401) return;  // вышли или забанены — переподключаться незачем
		// 1, 2, 4… до 60 с, вразброс: после перезапуска сервера вкладки не придут все разом.
		const delay = Math.min(60000, 1000 * 2 ** wsAttempt++) * (0.5 + Math.random());
		setTimeout(wsConnect, delay);
	});
}

window.azzbSend = (data) => {
	if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data));
};

// Лайки сыплются пачкой — пачку сигналов превращаем в один запрос счётчиков.
export function refreshBadges() {
	clearTimeout(badgesTimer);
	badgesTimer = setTimeout(() => {
		const poller = document.querySelector('[data-badges]');
		if (poller && window.htmx) htmx.trigger(poller, 'azzb:refresh-badges');
	}, 300);
}
document.addEventListener('azzb:ws:badges', refreshBadges);
document.addEventListener('azzb:ws:notifications', () => {
	refreshBadges();
	const pill = document.querySelector('[data-new-notifications]');
	if (pill) pill.hidden = false;
});

if (wsPath && 'WebSocket' in window) wsConnect();
