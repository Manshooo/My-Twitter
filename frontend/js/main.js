// Точка входа esbuild. Порядок импортов = порядок, в котором модули вешают обработчики.
// Запросы к серверу (лайк, удаление, публикация, подгрузка) делает htmx — см. атрибуты hx-* в шаблонах.
import './util.js';
import './toast.js';
import './realtime.js';
import './menu.js';
import './theme.js';
import './modal.js';
import './composer.js';
import './poll.js';
import './lightbox.js';
import './cropper.js';
import './posts.js';
import './mentions.js';
import './cookies.js';
import './dm.js';
import './events.js';
import './pwa.js';
