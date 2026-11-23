from django.test import TestCase, override_settings
from django.urls import reverse

from .cookies import CONSENT_COOKIE


class CookieBannerTests(TestCase):
	@override_settings(YANDEX_METRIKA_ID='12345')
	def test_metrika_only_with_consent(self):
		self.assertContains(self.client.get(reverse('index')), '<meta name="azzb-metrika" content="12345">')
		self.client.cookies[CONSENT_COOKIE] = 'v1:analytics'
		self.assertContains(self.client.get(reverse('index')), '<meta name="azzb-metrika" content="12345" data-allowed>')
