from django import forms
from django.core.exceptions import ValidationError

from core.models import Option, Question, Quiz
from core.validators import validate_option_image, validate_question_audio, validate_question_image
from core.svg_sanitizer import sanitize_question_svg
from subjects.models import SubStrand, Subject, Strand


class QuestionCreateForm(forms.Form):
    """
    Create a Question (+ Option rows for quiz types that require them).

    This form is intentionally "thin": the view decides which options to create
    based on `quiz_type`.
    """

    difficulty = forms.ChoiceField(
        choices=Question.DIFFICULTY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quiz_type = forms.ChoiceField(
        choices=Question.QUIZ_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_quiz_type"}),
    )
    quiz = forms.CharField(
        label="Question (Prompt)",
        widget=forms.Textarea(attrs={
            "class": "form-textarea",
            "rows": 4,
            "placeholder": "Use $x^2$ for inline math and $$\\frac{a}{b}$$ for display math.",
        }),
        help_text="Supports LaTeX math: $inline$ and $$display$$. Line breaks are preserved.",
    )
    prompt_image = forms.ImageField(
        label="Question image (optional)",
        required=False,
        validators=[validate_question_image],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    prompt_svg = forms.CharField(
        label='SVG illustration (optional)',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 5,
            'spellcheck': 'false',
            'placeholder': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">...</svg>',
        }),
        help_text='Inline SVG only. Scripts, links, and unsupported elements are rejected.',
    )
    prompt_audio = forms.FileField(
        label="Question audio (optional)",
        required=False,
        validators=[validate_question_audio],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "audio/*"}),
    )
    image_alt_text = forms.CharField(
        label="Image description (accessibility)",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g. Triangle ABC with sides labeled 3 cm, 4 cm, 5 cm",
        }),
    )
    sub_strand = forms.ModelChoiceField(
        queryset=SubStrand.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_prompt_svg(self):
        try:
            return sanitize_question_svg(self.cleaned_data.get('prompt_svg', ''))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    # Fixed option inputs (used for Multiple Choice / True-False)
    option_1 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    option_1_image = forms.ImageField(
        required=False,
        validators=[validate_option_image],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    correct_1 = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}))

    option_2 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    option_2_image = forms.ImageField(
        required=False,
        validators=[validate_option_image],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    correct_2 = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}))

    option_3 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    option_3_image = forms.ImageField(
        required=False,
        validators=[validate_option_image],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    correct_3 = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}))

    option_4 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-input"}))
    option_4_image = forms.ImageField(
        required=False,
        validators=[validate_option_image],
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    correct_4 = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}))

    def __init__(self, *args, subject_id=None, sub_strand_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subject_id is not None:
            self.fields["sub_strand"].queryset = SubStrand.objects.filter(
                strand__subject_id=subject_id
            ).order_by("order", "name")
            self.fields["sub_strand"].empty_label = "Select a sub-strand"
        if sub_strand_id is not None:
            self.fields["sub_strand"].initial = sub_strand_id

    def clean(self):
        cleaned_data = super().clean()

        quiz_type = cleaned_data.get("quiz_type")
        option_texts = []
        correct_indices = []

        for idx in range(1, 5):
            txt = (cleaned_data.get(f"option_{idx}") or "").strip()
            option_texts.append(txt)
            correct = cleaned_data.get(f"correct_{idx}") is True
            if correct and not txt:
                raise ValidationError({f"correct_{idx}": "Marking correct requires an option text."})
            if correct:
                correct_indices.append(idx)

        provided_options = [t for t in option_texts if t]

        # Multiple Choice: require >=2 options and at least 1 marked correct.
        if quiz_type == "Multiple Choice":
            if len(provided_options) < 2:
                raise ValidationError("Provide at least 2 options for Multiple Choice questions.")
            if not correct_indices:
                raise ValidationError("Mark at least one correct option for Multiple Choice questions.")

        # True/False: we only use option_1/option_2. Require exactly 1 marked correct.
        if quiz_type == "True or False":
            opt1 = option_texts[0] or "True"
            opt2 = option_texts[1] or "False"

            # Normalize defaults back into cleaned_data for the view.
            cleaned_data["option_1"] = opt1
            cleaned_data["option_2"] = opt2
            cleaned_data["option_3"] = ""
            cleaned_data["option_4"] = ""

            correct_on_1_2 = [
                idx for idx in (1, 2) if (cleaned_data.get(f"correct_{idx}") is True)
            ]
            if len(correct_on_1_2) != 1:
                raise ValidationError("Select exactly one correct answer (True or False).")

            # Avoid confusing UX: for True/False we only honor Option 1/2.
            if cleaned_data.get("correct_3") is True or cleaned_data.get("correct_4") is True:
                raise ValidationError("For True/False, only mark Option 1 or Option 2 as correct.")

        return cleaned_data


class QuizForm(forms.ModelForm):
    """Create or update a Quiz (metadata only — questions are managed separately)."""

    class Meta:
        model = Quiz
        fields = [
            'title', 'description', 'difficulty',
            'subject', 'strand', 'sub_strand',
            'test_size', 'time_limit_minutes', 'is_active',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Grade 4 Fractions Quiz'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Brief description of this quiz…'}),
            'difficulty': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select', 'id': 'id_subject'}),
            'strand': forms.Select(attrs={'class': 'form-select', 'id': 'id_strand'}),
            'sub_strand': forms.Select(attrs={'class': 'form-select', 'id': 'id_sub_strand'}),
            'test_size': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'placeholder': '0 = all questions'}),
            'time_limit_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': '0 = no limit',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        labels = {
            'test_size': 'Question Limit (0 = use all)',
            'time_limit_minutes': 'Time Limit (minutes)',
            'is_active': 'Published (visible to learners)',
        }
        help_texts = {
            'time_limit_minutes': '0 means learners have unlimited time.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subject'].queryset = Subject.objects.filter(is_active=True).select_related('grade_level').order_by('grade_level__name', 'name')
        self.fields['subject'].empty_label = 'Select a subject'
        self.fields['strand'].queryset = Strand.objects.all().select_related('subject').order_by('subject__name', 'name')
        self.fields['strand'].empty_label = 'Select a strand (optional)'
        self.fields['strand'].required = False
        self.fields['sub_strand'].queryset = SubStrand.objects.all().select_related('strand__subject').order_by('name')
        self.fields['sub_strand'].empty_label = 'All sub-strands (optional)'
        self.fields['sub_strand'].required = False


class QuestionMediaForm(forms.ModelForm):
    """Upload or replace narration files on an existing question."""

    class Meta:
        model = Question
        fields = ('prompt_audio', 'explanation_audio')
        widgets = {
            'prompt_audio': forms.ClearableFileInput(attrs={
                'class': 'form-input',
                'accept': 'audio/*',
            }),
            'explanation_audio': forms.ClearableFileInput(attrs={
                'class': 'form-input',
                'accept': 'audio/*',
            }),
        }
        labels = {
            'prompt_audio': 'Question prompt audio',
            'explanation_audio': 'Explanation audio',
        }
        help_texts = {
            'prompt_audio': 'Played when learners tap “Listen to question”.',
            'explanation_audio': 'Played when learners tap “Listen to explanation” (before TTS).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('prompt_audio', 'explanation_audio'):
            self.fields[field_name].required = False
            self.fields[field_name].validators = [validate_question_audio]

    def clean_prompt_audio(self):
        upload = self.cleaned_data.get('prompt_audio')
        if upload is False:
            return None
        if upload:
            validate_question_audio(upload)
        return upload

    def clean_explanation_audio(self):
        upload = self.cleaned_data.get('explanation_audio')
        if upload is False:
            return None
        if upload:
            validate_question_audio(upload)
        return upload


class OptionMediaForm(forms.ModelForm):
    class Meta:
        model = Option
        fields = ('option_audio',)
        widgets = {
            'option_audio': forms.ClearableFileInput(attrs={
                'class': 'form-input',
                'accept': 'audio/*',
            }),
        }
        labels = {
            'option_audio': 'Answer choice audio',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['option_audio'].required = False
        self.fields['option_audio'].validators = [validate_question_audio]

    def clean_option_audio(self):
        upload = self.cleaned_data.get('option_audio')
        if upload is False:
            return None
        if upload:
            validate_question_audio(upload)
        return upload


class QuizEditForm(forms.ModelForm):
    """Edit quiz metadata only — curriculum scope is fixed after creation."""

    class Meta:
        model = Quiz
        fields = ['title', 'description', 'difficulty', 'test_size', 'time_limit_minutes']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Grade 6 Mathematics Quiz'}),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Brief description of this quiz…',
            }),
            'difficulty': forms.Select(attrs={'class': 'form-select'}),
            'test_size': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'placeholder': '0'}),
            'time_limit_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': '0',
            }),
        }
        labels = {
            'test_size': 'Question Limit (0 = use all)',
            'time_limit_minutes': 'Time Limit (minutes)',
        }
        help_texts = {
            'time_limit_minutes': '0 means learners have unlimited time.',
        }

