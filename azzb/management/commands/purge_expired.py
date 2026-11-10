from django.core.management.base import BaseCommand

from azzb.retention import purge_expired


class Command(BaseCommand):
	help = 'Стирает удалённые посты и аккаунты старше полугода и журнал действий старше года (сроки — azzb/retention.py).'

	def handle(self, *args, **options):
		done = purge_expired()
		self.stdout.write(
			f"Стёрто: аккаунтов {done['accounts']}, постов {done['posts']}, записей журнала {done['activity']}."
		)
