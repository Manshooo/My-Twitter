from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .cookies import CONSENT_COOKIE, cookie_choice


class CookieChoiceTests(SimpleTestCase):
	def choice(self, value=None):
		request = RequestFactory().get('/')
		if value is not None:
			request.COOKIES[CONSENT_COOKIE] = value
		return cookie_choice(request)

	def test_parsing(self):
		self.assertIsNone(self.choice())
		self.assertEqual(self.choice('v1:analytics'), {'analytics'})
		self.assertEqual(self.choice('v1:necessary'), set())
		# Старая версия, мусор и неизвестные категории — выбора нет, баннер спросит снова.
		for raw in ('v0:analytics', 'v1:', 'v1:ads', 'garbage'):
			self.assertIsNone(self.choice(raw), raw)


class CookieBannerTests(TestCase):
	def test_banner_until_choice(self):
		self.assertContains(self.client.get(reverse('index')), 'data-cookie-banner>')
		self.client.cookies[CONSENT_COOKIE] = 'v1:necessary'
		self.assertContains(self.client.get(reverse('index')), 'data-cookie-banner hidden')
		# На страницах входа баннер тоже есть.
		self.client.cookies.pop(CONSENT_COOKIE)
		self.assertContains(self.client.get(reverse('account_login')), 'data-cookie-banner>')

	def test_banner_names_no_services(self):
		# Конкретные сервисы — в политике cookie; в баннере — только что и зачем.
		html = self.client.get(reverse('index')).content.decode()
		banner = html[html.index('data-cookie-banner'):html.index('</section>', html.index('data-cookie-banner'))]
		self.assertNotIn('Яндекс', banner)
		self.assertNotIn('Метрик', banner)
		self.assertIn('просмотры и переходы', banner)

	@override_settings(YANDEX_METRIKA_ID='12345')
	def test_metrika_only_with_consent(self):
		self.assertContains(self.client.get(reverse('index')), '<meta name="azzb-metrika" content="12345">')
		self.client.cookies[CONSENT_COOKIE] = 'v1:analytics'
		self.assertContains(self.client.get(reverse('index')), '<meta name="azzb-metrika" content="12345" data-allowed>')

	@override_settings(YANDEX_METRIKA_ID='')
	def test_no_metrika_without_id(self):
		self.client.cookies[CONSENT_COOKIE] = 'v1:analytics'
		self.assertNotContains(self.client.get(reverse('index')), 'azzb-metrika')

	def test_policy_page(self):
		response = self.client.get(reverse('cookies'))
		self.assertContains(response, 'Политика в отношении файлов cookie')
		self.assertContains(response, 'cookie_consent')
		self.assertContains(self.client.get(reverse('privacy')), reverse('cookies'))
