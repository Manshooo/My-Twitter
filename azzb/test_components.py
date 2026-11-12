from django.test import SimpleTestCase, TestCase

from azzb.templatetags.azzb_ui import count


class CountFilterTests(SimpleTestCase):
	def test_short_forms(self):
		cases = {0: '', 7: '7', 999: '999', 1000: '1 тыс.', 1299: '1,2 тыс.', 9999: '9,9 тыс.',
			12345: '12 тыс.', 999_999: '999 тыс.', 1_200_000: '1,2 млн', 15_000_000: '15 млн'}
		for number, text in cases.items():
			with self.subTest(number=number):
				self.assertEqual(count(number), text)


class EmptyComponentTests(TestCase):
	"""<c-empty> собирает cotton-загрузчик: проверяем на настоящей странице, а не на Template из строки."""

	def test_feed_empty_state(self):
		from accounts.models import CustomUser
		from azzb.testing import ACTIVE
		self.client.force_login(CustomUser.objects.create_user('ann', 'ann@example.com', 'pass-12345', **ACTIVE))
		html = self.client.get('/following/').content.decode()
		self.assertIn('class="empty"', html)
		self.assertIn('class="empty-icon" aria-hidden="true"><svg class="icon"><use href="#i-people">', html)
		self.assertIn('data-feed-empty', html)
		self.assertIn('<h2>Здесь пока тихо</h2>', html)
