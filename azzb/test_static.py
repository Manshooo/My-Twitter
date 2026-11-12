from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from .storage import MinifiedStaticFilesStorage, minifier_for


class MinifierForTests(SimpleTestCase):
	def test_own_css_and_js(self):
		self.assertIsNotNone(minifier_for('css/azzb.css'))
		self.assertIsNotNone(minifier_for('js/azzb.js'))

	def test_skips_foreign_and_premin(self):
		self.assertIsNone(minifier_for('admin/css/base.css'))
		self.assertIsNone(minifier_for('vendor/htmx-2.0.4.min.js'))
		self.assertIsNone(minifier_for('js/lib.min.js'))
		self.assertIsNone(minifier_for('images/logo_quad.png'))


class StorageTests(SimpleTestCase):
	def test_save_minifies_even_after_read(self):
		import tempfile
		with tempfile.TemporaryDirectory() as root:
			storage = MinifiedStaticFilesStorage(location=root)
			content = ContentFile(b'/* note */\n.a {\n\tcolor: red;\n}\n')
			content.read()  # post_process отдаёт файл, прочитанный ради хеша
			storage._save('css/x.css', content)
			with storage.open('css/x.css') as f:
				self.assertEqual(f.read(), b'.a{color:red}')
