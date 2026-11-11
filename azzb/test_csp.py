from django.test import TestCase, override_settings

from .csp import ContentSecurityPolicyMiddleware


class ContentSecurityPolicyTests(TestCase):
	def test_pages_forbid_inline_scripts_and_eval(self):
		response = self.client.get('/')
		policy = response['Content-Security-Policy']
		script_src = next(part for part in policy.split('; ') if part.startswith('script-src'))
		self.assertNotIn('unsafe-inline', script_src)
		self.assertNotIn('unsafe-eval', policy)
		self.assertIn("frame-ancestors 'none'", policy)
		self.assertIn('wss://testserver', policy)
		# Фильтры [...] в hx-trigger htmx исполняет через eval — их быть не должно.
		self.assertContains(response, '"allowEval": false')

	def test_only_html_gets_policy(self):
		self.assertNotIn('Content-Security-Policy', self.client.get('/robots.txt'))

	@override_settings(DEBUG=True)
	def test_debug_only_reports(self):
		middleware = ContentSecurityPolicyMiddleware(lambda request: None)
		self.assertEqual(middleware.header, 'Content-Security-Policy-Report-Only')
