import js from '@eslint/js';
import globals from 'globals';

export default [
	js.configs.recommended,
	{
		files: ['frontend/**/*.{js,mjs}'],
		languageOptions: {
			ecmaVersion: 2022,
			sourceType: 'module',
			globals: { ...globals.browser, htmx: 'readonly', ym: 'readonly' },
		},
		rules: {
			'no-unused-vars': ['error', { caughtErrors: 'none' }],
		},
	},
	{
		files: ['frontend/build.mjs'],
		languageOptions: { globals: globals.node },
	},
];
