from django import forms

from .mpesa import normalize_mpesa_phone


class SubscribeForm(forms.Form):
    phone_number = forms.CharField(
        max_length=20,
        label='M-Pesa phone number',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '0712345678',
            'autocomplete': 'tel',
        }),
    )

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        try:
            return normalize_mpesa_phone(phone)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
