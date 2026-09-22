import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import (
    get_daily_report,
    get_macro_breakdown,
    get_monthly_report,
    get_weekly_series,
)


@login_required
def dashboard_view(request):
    # Gracefully handle users who haven't completed their profile yet.
    # `profile` always exists (created by signal), but its fields may be null.
    profile = request.user.profile
    if not all([profile.height_cm, profile.weight_kg, profile.age, profile.gender]):
        messages.info(
            request,
            "Complete your profile to see your personalised calorie target and BMI. "
            "Your meal data is still tracked."
        )

    daily = get_daily_report(request.user)
    monthly = get_monthly_report(request.user)
    labels, calorie_series = get_weekly_series(request.user, weeks=1)
    macros = get_macro_breakdown(request.user, days=7)

    context = {
        "profile": profile,
        "daily": daily,
        "monthly": monthly,
        "calorie_target": profile.daily_calorie_target,
        "week_labels": json.dumps(labels),
        "week_calories": json.dumps(calorie_series),
        "macros_json": json.dumps(macros),
    }
    return render(request, "dashboard_app/dashboard.html", context)
