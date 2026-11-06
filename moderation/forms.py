from django import forms

from .models import Reason
from .services import BAN_TERMS


class ReportForm(forms.Form):
	reason = forms.ChoiceField(label='Что не так?', choices=Reason.choices, widget=forms.RadioSelect)
	comment = forms.CharField(
		label='Подробности', required=False, max_length=500,
		help_text='Необязательно. Например, ссылка на оригинал, если аккаунт выдаёт себя за другого.',
		widget=forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
	)


class ActionForm(forms.Form):
	"""Решение модератора по карточке очереди."""
	ACTIONS = ('dismiss', 'hide', 'ban')
	action = forms.ChoiceField(choices=[(a, a) for a in ACTIONS])
	post = forms.UUIDField(required=False)
	profile = forms.IntegerField()
	reason = forms.CharField(required=False, max_length=200)
	term = forms.ChoiceField(required=False, choices=[(key, label) for key, (label, _) in BAN_TERMS.items()])

	def clean(self):
		cleaned = super().clean()
		action = cleaned.get('action')
		if action in ('hide', 'ban') and not cleaned.get('reason', '').strip():
			self.add_error('reason', 'Укажите причину — её увидит автор.')
		if action == 'hide' and not cleaned.get('post'):
			self.add_error('post', 'Не указан пост.')
		if action == 'ban' and not cleaned.get('term'):
			self.add_error('term', 'Выберите срок.')
		return cleaned
