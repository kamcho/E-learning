from django.conf import settings
from django.db import models

# Create your models here.

class GradeLevel(models.Model):
    choices=(
        ("ECDE","ECDE"),
        ("Lower Primary","Lower Primary"),
        ("Upper Primary","Upper Primary"),
        ("Junior Secondary","Junior Secondary"),
        ("Senior Secondary","Senior Secondary"),
    )
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    level = models.CharField(max_length=50,choices=choices)

    class Meta:
        verbose_name = "Grade Level"
        verbose_name_plural = "Grade Levels"
        unique_together = ('name', 'level')
        ordering = ('name',)
        
    def __str__(self):
        return self.name

class Discipline(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = "Discipline"
        verbose_name_plural = "Disciplines"
        unique_together = ('name', 'slug')
        ordering = ('name',)
        
    def __str__(self):
        return self.name


class Pathway(models.Model):
    """CBC Senior School pathway (STEM, Social Sciences, Arts and Sports Science)."""
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    emoji = models.CharField(max_length=8, default='🎓')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "CBC Pathway"
        verbose_name_plural = "CBC Pathways"
        ordering = ('order', 'name')

    def __str__(self):
        return self.name


class PathwayDiscipline(models.Model):
    """How strongly a discipline signals fit for a pathway (0–1 weight)."""
    pathway = models.ForeignKey(Pathway, on_delete=models.CASCADE, related_name='discipline_weights')
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='pathway_weights')
    weight = models.DecimalField(max_digits=3, decimal_places=2, default=1.0)

    class Meta:
        verbose_name = "Pathway discipline weight"
        verbose_name_plural = "Pathway discipline weights"
        unique_together = ('pathway', 'discipline')
        ordering = ('pathway', '-weight')

    def __str__(self):
        return f"{self.pathway.name} ← {self.discipline.name} ({self.weight})"

class Subject(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.CASCADE, related_name='subjects')
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='subjects')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        unique_together = ('name','grade_level')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.grade_level.name})"
    
class Strand(models.Model):
    name = models.CharField(max_length=50)
    order = models.IntegerField(default=0)
    slug = models.SlugField(unique=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='strands')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # test_count = models.IntegerField(default=2)
    class Meta:
        verbose_name = "Strand"
        verbose_name_plural = "Strands"
        unique_together = ('name','subject')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.subject.name})"

class SubStrand(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    order = models.IntegerField(default=0)
    strand = models.ForeignKey(Strand, on_delete=models.CASCADE, related_name='sub_strands')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    test_count = models.IntegerField(default=2)
    class Meta:
        verbose_name = "Sub Strand"
        verbose_name_plural = "Sub Strands"
        unique_together = ('name','strand')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.strand.name})"

class StrandObjective(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    order = models.IntegerField(default=0)
    strand = models.ForeignKey(Strand, on_delete=models.CASCADE, related_name='strand_objectives')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Strand Objective"
        verbose_name_plural = "Strand Objectives"
        unique_together = ('name','strand')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.strand.name})"

class SubStrandObjective(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    order = models.IntegerField(default=0)
    sub_strand = models.ForeignKey(SubStrand, on_delete=models.CASCADE, related_name='sub_strand_objectives')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sub Strand Objective"
        verbose_name_plural = "Sub Strand Objectives"
        unique_together = ('name','sub_strand')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.sub_strand.name})"


class TeacherSubject(models.Model):
    """Explicit assignment of a teacher to a subject they teach."""
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teacher_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Teacher subject'
        verbose_name_plural = 'Teacher subjects'
        unique_together = ('teacher', 'subject')
        ordering = ('subject__name',)

    def __str__(self):
        return f'{self.teacher} → {self.subject}'


class TeacherSubject(models.Model):
    """Explicit assignment of a teacher to a subject they teach."""
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teacher_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Teacher subject'
        verbose_name_plural = 'Teacher subjects'
        unique_together = ('teacher', 'subject')
        ordering = ('subject__name',)

    def __str__(self):
        return f'{self.teacher} → {self.subject}'