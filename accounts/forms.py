from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.exceptions import ValidationError
from .models import MyUser, Role, Student

class SignUpForm(forms.ModelForm):
    role_choices = [
        (Role.GUARDIAN, 'Guardian (Parent/Sponsor)'),
        (Role.TEACHER, 'Teacher (Educator)'),
        (Role.PARTNER, 'School/Institutional Partner'),
        (Role.REFERRAL, 'Referral Agent'),
    ]

    full_name = forms.CharField(
        label='Full name',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. Jane Doe',
            'autocomplete': 'name',
        }),
    )

    role = forms.ChoiceField(
        choices=role_choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    password = forms.CharField(
        label='4-Digit PIN',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter 4-digit PIN',
            'maxlength': '4',
            'pattern': '[0-9]*',
            'inputmode': 'numeric'
        }),
        help_text='Use a 4-digit numeric code as your PIN password.'
    )
    referral_code = forms.CharField(
        label='Referral code (optional)',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. SKA1B2C3D4',
        }),
    )

    class Meta:
        model = MyUser
        fields = ['phone', 'role']
        widgets = {
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 0712345678',
                'type': 'tel'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['phone', 'full_name', 'role', 'password', 'referral_code'])

    def clean_full_name(self):
        full_name = (self.cleaned_data.get('full_name') or '').strip()
        if not full_name:
            raise ValidationError('Full name is required.')
        parts = full_name.split()
        if len(parts) < 2:
            raise ValidationError('Enter at least your first and last name.')
        return full_name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        # Simple cleanup/validation
        if not phone:
            raise ValidationError('Phone number is required.')
        
        # Strip whitespaces
        phone = phone.strip()
        
        # Check uniqueness manually to display a clean error
        if MyUser.objects.filter(phone=phone).exists():
            raise ValidationError('A user with this phone number already exists.')
            
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            raise ValidationError('PIN is required.')
        if not password.isdigit() or len(password) != 4:
            raise ValidationError('PIN must be exactly 4 digits.')
        return password

    def clean_referral_code(self):
        from .referrals import resolve_referrer
        code = (self.cleaned_data.get('referral_code') or '').strip().upper()
        if not code:
            return ''
        if not resolve_referrer(code):
            raise ValidationError('Referral code is invalid or inactive.')
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        first_name, last_name = self.cleaned_data['full_name'].split(None, 1)
        user.first_name = first_name
        user.last_name = last_name
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class StudentForm(forms.ModelForm):
    """Form for a guardian to create and link a new learner."""

    class Meta:
        model = Student
        fields = ['first_name', 'middle_name', 'last_name', 'grade_level', 'gender', 'dob']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'First Name',
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Middle Name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Last Name',
            }),
            'grade_level': forms.Select(attrs={'class': 'form-select'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'dob': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date',
            }),
        }
        labels = {
            'dob': 'Date of Birth',
            'grade_level': 'Grade Level',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['grade_level'].empty_label = 'Select grade level'
        self.fields['grade_level'].required = True


class PinPasswordResetForm(PasswordResetForm):
    """Request a PIN reset link by email (Django default password reset flow)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Email address on your account',
        })
        self.fields['email'].label = 'Email address'


class PinSetPasswordForm(SetPasswordForm):
    """Set a new 4-digit PIN after following the reset link."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pin_attrs = {
            'class': 'form-input',
            'placeholder': 'Enter 4-digit PIN',
            'maxlength': '4',
            'pattern': '[0-9]*',
            'inputmode': 'numeric',
        }
        self.fields['new_password1'].label = 'New 4-Digit PIN'
        self.fields['new_password1'].widget = forms.PasswordInput(attrs=pin_attrs)
        self.fields['new_password1'].help_text = 'Use a 4-digit numeric code as your PIN.'
        self.fields['new_password2'].label = 'Confirm New PIN'
        self.fields['new_password2'].widget = forms.PasswordInput(attrs={
            **pin_attrs,
            'placeholder': 'Re-enter 4-digit PIN',
        })

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if not password:
            raise ValidationError('PIN is required.')
        if not password.isdigit() or len(password) != 4:
            raise ValidationError('PIN must be exactly 4 digits.')
        return password

    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('PINs do not match.')
        return password2


class CompleteProfileForm(forms.Form):
    """Link a Kenyan phone number and PIN after Google sign-in."""

    phone = forms.CharField(
        label='Phone Number',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. 0712345678',
            'type': 'tel',
        }),
    )
    password = forms.CharField(
        label='4-Digit PIN',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Choose a 4-digit PIN',
            'maxlength': '4',
            'pattern': '[0-9]*',
            'inputmode': 'numeric',
        }),
        help_text='You can use this PIN with your phone number to sign in without Google.',
    )
    confirm_password = forms.CharField(
        label='Confirm PIN',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Re-enter 4-digit PIN',
            'maxlength': '4',
            'pattern': '[0-9]*',
            'inputmode': 'numeric',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if not phone:
            raise ValidationError('Phone number is required.')
        qs = MyUser.objects.filter(phone=phone)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise ValidationError('This phone number is already registered.')
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            raise ValidationError('PIN is required.')
        if not password.isdigit() or len(password) != 4:
            raise ValidationError('PIN must be exactly 4 digits.')
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('confirm_password')
        if password and confirm and password != confirm:
            self.add_error('confirm_password', 'PINs do not match.')
        return cleaned


class SignInForm(forms.Form):
    phone = forms.CharField(
        label='Phone Number',
        widget=forms.TextInput(attrs={
            'class': 'form-input', 
            'placeholder': 'e.g. 0712345678',
            'type': 'tel'
        })
    )
    password = forms.CharField(
        label='4-Digit PIN',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input', 
            'placeholder': 'Enter 4-digit PIN',
            'maxlength': '4',
            'pattern': '[0-9]*',
            'inputmode': 'numeric'
        })
    )
