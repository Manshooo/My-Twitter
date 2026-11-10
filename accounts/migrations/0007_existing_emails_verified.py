"""E1: перенос почты существующих пользователей в allauth.

С обязательным подтверждением почты allauth пускает только тех, у кого есть подтверждённая
запись EmailAddress. Аккаунты, заведённые до allauth, считаем подтверждёнными: это ранние
пользователи, и запирать их до прихода письма незачем. Если один адрес указан у нескольких
аккаунтов, подтверждённым он становится только у самого старого — allauth требует, чтобы
подтверждённый адрес был уникальным. Остальным придётся подтвердить почту при входе.
"""
from django.db import migrations


def forwards(apps, schema_editor):
	User = apps.get_model('customUser', 'CustomUser')
	EmailAddress = apps.get_model('account', 'EmailAddress')
	taken = {email.lower() for email in EmailAddress.objects.filter(verified=True).values_list('email', flat=True)}
	have_address = set(EmailAddress.objects.values_list('user_id', flat=True))
	new = []
	for user in User.objects.exclude(email='').order_by('date_joined', 'pk').only('pk', 'email'):
		if user.pk in have_address:
			continue
		email = user.email.strip().lower()
		verified = email not in taken
		taken.add(email)
		new.append(EmailAddress(user_id=user.pk, email=email, verified=verified, primary=True))
	EmailAddress.objects.bulk_create(new)


class Migration(migrations.Migration):

	dependencies = [
		('customUser', '0006_user_theme'),
		('account', '0009_emailaddress_unique_primary_email'),
	]

	operations = [
		migrations.RunPython(forwards, migrations.RunPython.noop),
	]
