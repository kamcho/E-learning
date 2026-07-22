from django.contrib.auth.backends import ModelBackend
from .models import MyUser


class PhonePinBackend(ModelBackend):
    """
    Authenticate users by phone number and 4-digit PIN.

    Works with Django's built-in ``authenticate()`` — simply pass
    ``phone`` and ``password`` (the PIN) as keyword arguments.
    """

    def authenticate(self, request, phone=None, password=None, **kwargs):
        if phone is None or password is None:
            return None

        try:
            user = MyUser.objects.get(phone=phone)
        except MyUser.DoesNotExist:
            # Run the password hasher to mitigate timing attacks
            MyUser().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
