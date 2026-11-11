from django.contrib.auth import get_user_model
from django.test import TestCase
from azzb.testing import ACTIVE


class ProgressiveWebAppTests(TestCase):
	def test_service_worker_is_served_from_root(self):
		response = self.client.get('/sw.js')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'application/javascript; charset=utf-8')
		self.assertIn('no-cache', response['Cache-Control'])
		body = response.content.decode()
		self.assertIn("const OFFLINE_URL = '/offline/';", body)
		self.assertIn('"/static/css/azzb.css"', body)

	def test_pages_register_worker(self):
		self.assertContains(self.client.get('/'), '<meta name="azzb-sw" content="/sw.js">', html=True)

	def test_offline_page_has_nothing_personal(self):
		user = get_user_model().objects.create_user('ann', 'ann@example.com', 'pass-12345', **ACTIVE)
		user.theme = 'dark'
		user.save()
		self.client.force_login(user)
		response = self.client.get('/offline/')
		self.assertContains(response, 'Нет соединения')
		self.assertNotContains(response, 'data-theme="dark"')
		self.assertNotContains(response, 'ann')
