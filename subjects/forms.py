from django import forms
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
        if name and not slug:
            base_slug = slugify(name)
            if grade_level:
                base_slug = f"{base_slug}-{slugify(grade_level.name)}"[:45]
            cleaned_data['slug'] = base_slug
            counter = 1
            while Subject.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data

class StrandForm(forms.ModelForm):
    class Meta:
        model = Strand
        fields = ['name', 'slug', 'order', 'subject', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Human Body'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'Leave blank to auto-generate'
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

class SubStrandForm(forms.ModelForm):
    class Meta:
        model = SubStrand
        fields = ['name', 'slug', 'order', 'strand', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input', 
                'placeholder': 'e.g. Digestive System'
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
            while SubStrand.objects.filter(slug=cleaned_data['slug']).exists():
                cleaned_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return cleaned_data

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
