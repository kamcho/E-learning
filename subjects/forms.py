from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import (
    GradeLevel, Discipline, Subject, Strand, 
    SubStrand, StrandObjective, SubStrandObjective
)

class SlugifyMixin:
    """Helper to auto-generate slug from name if not provided."""
    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        
        if name and not slug:
            cleaned_data['slug'] = slugify(name)
            # Ensure slug uniqueness (simple increment if duplicate)
            model_class = self.Meta.model
            base_slug = cleaned_data['slug']
            counter = 1
            while model_class.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data

class GradeLevelForm(forms.ModelForm):
    class Meta:
        model = GradeLevel
        fields = ['name', 'slug', 'level']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Grade 1'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
            }),
            'level': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            cleaned_data['slug'] = slugify(name)
        return cleaned_data

class DisciplineForm(forms.ModelForm):
    class Meta:
        model = Discipline
        fields = ['name', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Mathematics'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            cleaned_data['slug'] = slugify(name)
        return cleaned_data

class SubjectForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank to auto-generate',
        }),
    )

    class Meta:
        model = Subject
        fields = ['name', 'slug', 'grade_level', 'discipline', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Environmental Activities'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
            }),
            'grade_level': forms.Select(attrs={
                'class': 'form-select'
            }),
            'discipline': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        grade_level = cleaned_data.get('grade_level')
        if name and grade_level:
            duplicate_qs = Subject.objects.filter(name=name, grade_level=grade_level)
            if self.instance.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                raise ValidationError({
                    'name': 'A subject with this name already exists for this grade.',
                })
        if name and not slug:
            base_slug = slugify(name)
            if grade_level:
                base_slug = f"{base_slug}-{slugify(grade_level.name)}"[:45]
            cleaned_data['slug'] = base_slug
            counter = 1
            slug_qs = Subject.objects.filter(slug=cleaned_data['slug'])
            if self.instance.pk:
                slug_qs = slug_qs.exclude(pk=self.instance.pk)
            while slug_qs.exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                slug_qs = Subject.objects.filter(slug=cleaned_data['slug'])
                if self.instance.pk:
                    slug_qs = slug_qs.exclude(pk=self.instance.pk)
                counter += 1
        elif slug and self.instance.pk:
            if Subject.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
                raise ValidationError({'slug': 'This slug is already in use.'})
        return cleaned_data


class SubjectNameForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Subject name',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data['name']
        if Subject.objects.filter(
            grade_level=self.instance.grade_level,
            name=name,
        ).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A subject with this name already exists for this grade.')
        return name


class StrandForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank to auto-generate',
        }),
    )

    class Meta:
        model = Strand
        fields = ['name', 'slug', 'order', 'subject', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Human Body'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-input', 
                'min': '0'
            }),
            'subject': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            # We want to slugify name, but Strand slug needs to be unique.
            # Let's make it unique relative to subject name.
            subject = cleaned_data.get('subject')
            subj_slug = slugify(subject.name) if subject else ''
            base_slug = f"{slugify(name)}-{subj_slug}"[:40]
            cleaned_data['slug'] = base_slug
            
            counter = 1
            while Strand.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data


class StrandNameForm(forms.ModelForm):
    class Meta:
        model = Strand
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Strand name',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data['name']
        if Strand.objects.filter(
            subject=self.instance.subject,
            name=name,
        ).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A strand with this name already exists for this subject.')
        return name


class SubStrandForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank to auto-generate',
        }),
    )

    class Meta:
        model = SubStrand
        fields = ['name', 'slug', 'order', 'strand', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Digestive System'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-input', 
                'min': '0'
            }),
            'strand': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            strand = cleaned_data.get('strand')
            strand_slug = slugify(strand.name) if strand else ''
            base_slug = f"{slugify(name)}-{strand_slug}"[:40]
            cleaned_data['slug'] = base_slug
            
            counter = 1
            while SubStrand.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data


class SubStrandNameForm(forms.ModelForm):
    class Meta:
        model = SubStrand
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Sub-strand name',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data['name']
        if SubStrand.objects.filter(
            strand=self.instance.strand,
            name=name,
        ).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A sub-strand with this name already exists for this strand.')
        return name


class StrandObjectiveForm(forms.ModelForm):
    class Meta:
        model = StrandObjective
        fields = ['name', 'slug', 'order', 'strand', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Identify parts of the body'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-input', 
                'min': '0'
            }),
            'strand': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            strand = cleaned_data.get('strand')
            strand_slug = slugify(strand.name) if strand else ''
            base_slug = f"{slugify(name)}-{strand_slug}"[:40]
            cleaned_data['slug'] = base_slug
            
            counter = 1
            while StrandObjective.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data

class SubStrandObjectiveForm(forms.ModelForm):
    class Meta:
        model = SubStrandObjective
        fields = ['name', 'slug', 'order', 'sub_strand', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Describe digestive processes'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-input', 
                'min': '0'
            }),
            'sub_strand': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if name and not slug:
            sub_strand = cleaned_data.get('sub_strand')
            ss_slug = slugify(sub_strand.name) if sub_strand else ''
            base_slug = f"{slugify(name)}-{ss_slug}"[:40]
            cleaned_data['slug'] = base_slug
            
            counter = 1
            while SubStrandObjective.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data
