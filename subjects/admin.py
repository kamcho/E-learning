from django.contrib import admin
from .models import (
    GradeLevel,
    Discipline,
    Pathway,
    PathwayDiscipline,
    Subject,
    Strand,
    SubStrand,
    StrandObjective,
    TeacherSubject,
    SubStrandObjective,
)


@admin.register(GradeLevel)
class GradeLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


class PathwayDisciplineInline(admin.TabularInline):
    model = PathwayDiscipline
    extra = 0
    autocomplete_fields = ('discipline',)


@admin.register(Pathway)
class PathwayAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'emoji', 'order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (PathwayDisciplineInline,)


@admin.register(PathwayDiscipline)
class PathwayDisciplineAdmin(admin.ModelAdmin):
    list_display = ('pathway', 'discipline', 'weight')
    list_filter = ('pathway', 'discipline')
    search_fields = ('pathway__name', 'discipline__name')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade_level', 'discipline', 'is_active', 'created_at')
    list_filter = ('is_active', 'grade_level', 'discipline')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Strand)
class StrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'order', 'is_active')
    list_filter = ('is_active', 'subject')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SubStrand)
class SubStrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'strand', 'order', 'is_active')
    list_filter = ('is_active', 'strand')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StrandObjective)
class StrandObjectiveAdmin(admin.ModelAdmin):
    list_display = ('name', 'strand', 'order', 'is_active')
    list_filter = ('is_active', 'strand')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SubStrandObjective)
class SubStrandObjectiveAdmin(admin.ModelAdmin):
    list_display = ('name', 'sub_strand', 'order', 'is_active')
    list_filter = ('is_active', 'sub_strand')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TeacherSubject)
class TeacherSubjectAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'subject', 'assigned_at')
    list_filter = ('subject__grade_level', 'subject__discipline')
    search_fields = ('teacher__first_name', 'teacher__last_name', 'teacher__phone', 'subject__name')
    autocomplete_fields = ('teacher', 'subject')
