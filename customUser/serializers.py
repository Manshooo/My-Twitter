from rest_framework import serializers
from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
	# Явный список полей: "__all__" отдавал наружу всё, что появится в модели.
	login = serializers.CharField(source='user.username', read_only=True)

	class Meta:
		model = Profile
		fields = ['id', 'user', 'login', 'username', 'avatar', 'bio']
		# Аватар меняется только через форму профиля: там картинка обрезается и чистится от EXIF.
		read_only_fields = ['id', 'user', 'login', 'avatar']
