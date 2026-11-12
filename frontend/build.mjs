// Сборка фронтенда: frontend/ → azzb/static/{css,js}/azzb.* (в .gitignore; collectstatic берёт оттуда).
import * as esbuild from 'esbuild';

const watch = process.argv.includes('--watch');
const options = {
	entryPoints: { 'js/azzb': 'frontend/js/main.js', 'css/azzb': 'frontend/css/main.css' },
	outdir: 'azzb/static',
	bundle: true,
	format: 'iife',
	target: 'es2020',
	// Шрифты уже лежат в azzb/static/fonts: путь '../fonts/…' верен и для собранного CSS.
	external: ['*.woff2'],
	minify: !watch,
	sourcemap: watch ? 'linked' : false,
	logLevel: 'info',
};

if (watch) await (await esbuild.context(options)).watch();
else await esbuild.build(options);
