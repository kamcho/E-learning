from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import AchievementForm
from .models import Achievement


def admin_required(view_func):
    @login_required(login_url='accounts:signin')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_admin_role or user.is_staff):
            messages.error(request, "You don't have permission to manage achievements.")
            if user.is_guardian:
                return redirect('accounts:guardian_dashboard')
            return redirect('core:landing')
        return view_func(request, *args, **kwargs)

    return wrapper


@admin_required
def achievement_list(request):
    achievements = (
        Achievement.objects
        .annotate(earned_count=Count('student_awards'))
        .order_by('order', 'title')
    )
    active_count = achievements.filter(is_active=True).count()

    return render(request, 'achievements/achievement_list.html', {
        'achievements': achievements,
        'stats': {
            'total': achievements.count(),
            'active': active_count,
            'inactive': achievements.count() - active_count,
        },
        'django_admin_url': reverse('admin:achievements_achievement_changelist'),
    })


@admin_required
def achievement_create(request):
    if request.method == 'POST':
        form = AchievementForm(request.POST)
        if form.is_valid():
            achievement = form.save()
            messages.success(request, f"Achievement “{achievement.title}” created.")
            return redirect('achievements:achievement_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        next_order = (
            Achievement.objects.order_by('-order').values_list('order', flat=True).first() or 0
        )
        form = AchievementForm(initial={'order': next_order + 10, 'is_active': True})

    return render(request, 'achievements/achievement_create.html', {
        'form': form,
    })
