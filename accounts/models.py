import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models


class Role(models.TextChoices):
    """User roles within the Soma Smart platform."""
    GUARDIAN = 'guardian', 'Guardian'
    TEACHER = 'teacher', 'Teacher'
    PARTNER = 'partner', 'Partner'
    REFERRAL = 'referral', 'Referral'
    ADMIN = 'admin', 'Admin'


class MyUserManager(BaseUserManager):
    """Custom manager for MyUser — creates users with phone + 4-digit PIN."""

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone number is required.')
        if not password:
            raise ValueError('A 4-digit PIN (password) is required.')
        if not str(password).isdigit() or len(str(password)) != 4:
            raise ValueError('PIN must be exactly 4 digits.')

        user = self.model(phone=phone, **extra_fields)
        user.set_password(str(password))  # hash the PIN like a regular password
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)


# Validators
phone_validator = RegexValidator(
    regex=r'^(?:\+254|0)\d{9}$',
    message='Enter a valid Kenyan phone number (e.g. 0712345678 or +254712345678).',
)

pin_validator = RegexValidator(
    regex=r'^\d{4}$',
    message='PIN must be exactly 4 digits.',
)


class MyUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for Soma Smart.

    - Login via **phone** + 4-digit **PIN** (no username).
    - Role determines dashboard & permissions.
    """

    phone = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        validators=[phone_validator],
        help_text='Kenyan phone number used for PIN login.',
    )
    google_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text='Google account subject ID for OAuth sign-in.',
    )
    email = models.EmailField(blank=True, null=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.GUARDIAN,
    )
    referral_code = models.CharField(
        max_length=16,
        unique=True,
        null=True,
        blank=True,
        help_text='Shareable code for referral agents.',
    )
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_users',
        help_text='Referral agent who referred this account.',
    )
    referral_points = models.PositiveIntegerField(
        default=0,
        help_text='Reward points earned from successful referral subscriptions.',
    )

    # Django auth flags
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MyUserManager()

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['first_name', 'last_name']  # prompted by createsuperuser

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        identifier = self.phone or self.email or f'google:{self.google_id}'
        return f'{self.first_name} {self.last_name} ({identifier})'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def is_guardian(self):
        return self.role == Role.GUARDIAN

    @property
    def is_teacher(self):
        return self.role == Role.TEACHER

    @property
    def is_partner(self):
        return self.role == Role.PARTNER

    @property
    def is_referral(self):
        return self.role == Role.REFERRAL

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN


class Student(models.Model):
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade_level = models.ForeignKey('subjects.GradeLevel', on_delete=models.SET_NULL, null=True, blank=True)
    gender = models.CharField(max_length=10,choices=[('Male','Male'),('Female','Female')],default='Male')
    dob=models.DateField(null=True,blank=True)
    
    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.uuid})'

    
class LinkedStudents(models.Model):
    user=models.ForeignKey(MyUser, on_delete=models.CASCADE, related_name='linked_students')
    students = models.ManyToManyField(Student, related_name='linked_students')

    def __str__(self):
        return f'{self.user.phone} linked to {self.students.count()} students'


class ReferralPointLog(models.Model):
    """Audit log for referral rewards — one row per successful referred payment."""

    referrer = models.ForeignKey(
        MyUser,
        on_delete=models.CASCADE,
        related_name='referral_point_logs',
    )
    referred_user = models.ForeignKey(
        MyUser,
        on_delete=models.CASCADE,
        related_name='referral_rewards_generated',
    )
    payment = models.OneToOneField(
        'subscriptions.Payment',
        on_delete=models.CASCADE,
        related_name='referral_reward',
    )
    points = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.referrer} +{self.points} from {self.referred_user}'
