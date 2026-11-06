from allauth.account.adapter import DefaultAccountAdapter

from azzb.ratelimit import client_ip

# Тосты «Вы вошли как …» / «Вы вышли» ничего не сообщают: человек и так видит, что вошёл.
SILENT_MESSAGES = {
	'account/messages/logged_in.txt',
	'account/messages/logged_out.txt',
}


class AccountAdapter(DefaultAccountAdapter):
	def add_message(self, request, level, message_template=None, message_context=None, extra_tags='', message=None):
		if message_template in SILENT_MESSAGES:
			return
		super().add_message(request, level, message_template, message_context, extra_tags, message=message)

	def get_client_ip(self, request):
		# Тот же IP, что и у остальных лимитов сайта: за nginx — из X-Real-IP.
		return client_ip(request)
