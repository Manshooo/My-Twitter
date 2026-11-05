from rest_framework import serializers
from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
	# Явный список полей: "__all__" отдавал наружу всё, что появится в модели.
	login = serializers.CharField(source='user.username', read_only=True)

	class Meta:
		model = Profile
		fields = ['id', 'user', 'login', 'username', 'avatar', 'bio']
		read_only_fields = ['id', 'user', 'login']
