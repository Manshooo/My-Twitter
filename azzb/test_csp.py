import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .csp import ContentSecurityPolicyMiddleware


def directive(policy, name):
	return next(part for part in policy.split('; ') if part.startswith(name + ' '))


class ContentSecurityPolicyTests(TestCase):
	def test_pages_forbid_inline_scripts_and_eval(self):
		response = self.client.get('/')
		policy = response['Content-Security-Policy']
		self.assertNotIn('unsafe-inline', directive(policy, 'script-src'))
		self.assertNotIn('unsafe-eval', policy)
		self.assertIn("frame-ancestors 'none'", policy)
		self.assertIn('wss://testserver', policy)
		# Фильтры [...] в hx-trigger htmx исполняет через eval — их быть не должно;
		# <script> из подгруженного HTML с 'strict-dynamic' запустился бы — htmx их не исполняет.
		self.assertContains(response, '"allowEval": false, "allowScriptTags": false')

	def test_scripts_carry_the_header_nonce(self):
		response = self.client.get('/')
		script_src = directive(response['Content-Security-Policy'], 'script-src')
		self.assertIn("'strict-dynamic'", script_src)
		nonce = re.search(r"'nonce-([^']+)'", script_src).group(1)
		# JSON-LD — данные, а не код: CSP его не касается.
		tags = [tag for tag in re.findall(r'<script\b[^>]*>', response.content.decode()) if 'application/ld+json' not in tag]
		self.assertTrue(tags)
		for tag in tags:
			self.assertIn(f'nonce="{nonce}"', tag)

	def test_nonce_is_new_for_each_response(self):
		first = directive(self.client.get('/')['Content-Security-Policy'], 'script-src')
		second = directive(self.client.get('/')['Content-Security-Policy'], 'script-src')
		self.assertNotEqual(first, second)

	def test_pages_without_nonce_keep_host_allowlist(self):
		# Админка Django: её <script> без nonce, 'strict-dynamic' их бы заблокировал.
		admin = get_user_model().objects.create_superuser('root', 'root@example.com', 'pass')
		self.client.force_login(admin)
		script_src = directive(self.client.get('/admin/')['Content-Security-Policy'], 'script-src')
		self.assertNotIn('nonce-', script_src)
		self.assertNotIn('strict-dynamic', script_src)
		self.assertIn("'self'", script_src)

	def test_only_html_gets_policy(self):
		self.assertNotIn('Content-Security-Policy', self.client.get('/robots.txt'))

	@override_settings(DEBUG=True)
	def test_debug_only_reports(self):
		middleware = ContentSecurityPolicyMiddleware(lambda request: None)
		self.assertEqual(middleware.header, 'Content-Security-Policy-Report-Only')
