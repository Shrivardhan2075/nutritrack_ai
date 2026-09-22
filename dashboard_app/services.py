"""
Report aggregation logic for Phase 10 (Meal History) and Phase 11 (Dashboard).
Pure data-crunching functions, kept separate from views so they're easy
to unit test independently of HTTP requests.
"""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from meals.models import Meal


def _aggregate(meals):
    return meals.aggregate(
        calories=Sum("total_calories"),
        protein=Sum("total_protein_g"),
        carbs=Sum("total_carbs_g"),
        fat=Sum("total_fat_g"),
        fiber=Sum("total_fiber_g"),
    )


def get_daily_report(user, date=None):
    date = date or timezone.localdate()
    meals = Meal.objects.filter(user=user, uploaded_at__date=date)
    return {"date": date, "meal_count": meals.count(), **_aggregate(meals)}


def get_weekly_series(user, weeks=1):
    """Returns per-day calorie totals for the last `weeks` weeks (for Chart.js)."""
    today = timezone.localdate()
    start = today - timedelta(days=7 * weeks - 1)
    labels, calories = [], []
    for i in range(7 * weeks):
        day = start + timedelta(days=i)
        total = Meal.objects.filter(user=user, uploaded_at__date=day).aggregate(
            c=Sum("total_calories")
        )["c"] or 0
        labels.append(day.strftime("%b %d"))
        calories.append(round(total, 1))
    return labels, calories


def get_monthly_report(user, year=None, month=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    meals = Meal.objects.filter(
        user=user, uploaded_at__year=year, uploaded_at__month=month
    )
    return {"year": year, "month": month, "meal_count": meals.count(), **_aggregate(meals)}


def get_macro_breakdown(user, days=7):
    """Protein/Carbs/Fat totals over the last N days -- feeds the pie chart."""
    start = timezone.localdate() - timedelta(days=days - 1)
    meals = Meal.objects.filter(user=user, uploaded_at__date__gte=start)
    agg = _aggregate(meals)
    return {
        "protein": round(agg["protein"] or 0, 1),
        "carbs": round(agg["carbs"] or 0, 1),
        "fat": round(agg["fat"] or 0, 1),
    }
