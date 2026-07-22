from django import forms
from django.utils.text import slugify

from .models import Achievement


class AchievementForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        help_text='Leave blank to auto-generate from the title.',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank to auto-generate',
        }),
    )

    class Meta:
        model = Achievement
        fields = [
            'title',
            'slug',
            'description',
            'icon',
            'criteria_type',
            'threshold',
            'min_attempts',
            'order',
            'is_active',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. First Steps',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'What must the learner do to earn this?',
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 🏅',
                'maxlength': 16,
            }),
            'criteria_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_criteria_type',
            }),
            'threshold': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 1,
                'id': 'id_threshold',
            }),
            'min_attempts': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
                'id': 'id_min_attempts',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def clean_slug(self):
        slug = (self.cleaned_data.get('slug') or '').strip()
        title = (self.cleaned_data.get('title') or '').strip()
        if not slug and title:
            slug = slugify(title)
        if not slug:
            raise forms.ValidationError('Enter a slug or title to generate one.')

        base_slug = slug
        counter = 1
        qs = Achievement.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        while qs.exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
            qs = Achievement.objects.filter(slug=slug)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
        return slug

    def clean(self):
        cleaned = super().clean()
        criteria_type = cleaned.get('criteria_type')
        threshold = cleaned.get('threshold')
        min_attempts = cleaned.get('min_attempts')

        if criteria_type == Achievement.CriteriaType.PERFECT_SCORE:
            cleaned['threshold'] = 100
            cleaned['min_attempts'] = 0
        elif criteria_type == Achievement.CriteriaType.EXAMS_COMPLETED:
            if threshold is not None and threshold < 1:
                self.add_error('threshold', 'Enter at least 1 completed exam.')
        elif criteria_type in (
            Achievement.CriteriaType.BEST_SCORE,
            Achievement.CriteriaType.AVG_SCORE,
        ):
            if threshold is not None and not 1 <= threshold <= 100:
                self.add_error('threshold', 'Enter a percentage between 1 and 100.')
            if criteria_type == Achievement.CriteriaType.AVG_SCORE:
                if min_attempts is not None and min_attempts < 1:
                    self.add_error(
                        'min_attempts',
                        'Average score achievements need at least 1 completed exam.',
                    )
            else:
                cleaned['min_attempts'] = 0

        return cleaned
