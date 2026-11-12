from django.test import SimpleTestCase, TestCase

from azzb.templatetags.azzb_ui import count, count_plural


class CountFilterTests(SimpleTestCase):
	def test_short_forms(self):
		cases = {0: '', 7: '7', 999: '999', 1000: '1 тыс.', 1299: '1,2 тыс.', 9999: '9,9 тыс.',
			12345: '12 тыс.', 999_999: '999 тыс.', 1_200_000: '1,2 млн', 15_000_000: '15 млн'}
		for number, text in cases.items():
			with self.subTest(number=number):
				self.assertEqual(count(number), text)

	def test_plural_after_short_form(self):
		forms = 'репост,репоста,репостов'
		self.assertEqual(count_plural(2, forms), 'репоста')
		self.assertEqual(count_plural(21, forms), 'репост')
		self.assertEqual(count_plural(12_344, forms), 'репостов')  # «12 тыс. репостов»
		self.assertEqual(count_plural(1_001, forms), 'репостов')


class EmptyComponentTests(TestCase):
	"""<c-empty> собирает cotton-загрузчик: проверяем на настоящей странице, а не на Template из строки."""

	def test_feed_empty_state(self):
		html = self.client.get('/').content.decode()
		self.assertIn('class="empty"', html)
		self.assertIn('class="empty-icon" aria-hidden="true"><svg class="icon"><use href="#i-people">', html)
		self.assertIn('data-feed-empty', html)
		self.assertIn('<h2>Постов пока нет</h2>', html)
