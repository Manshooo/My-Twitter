from django.core.management.base import BaseCommand

from azzb.retention import purge_expired


class Command(BaseCommand):
	help = 'Стирает удалённые посты, сообщения и аккаунты старше полугода журнал действий старше года и истёкшие сеансы (сроки — azzb/retention.py).'

	def handle(self, *args, **options):
		done = purge_expired()
		self.stdout.write(
			f"Стёрто: аккаунтов {done['accounts']}, постов {done['posts']}, сообщений {done['messages']}, "
			f"записей журнала {done['activity']}, сеансов {done['sessions']}."
		)
