"""
Nutrition Engine (Phase 9) + Recommendation Engine (Phase 12).

Takes raw YOLO detections, matches each to a FoodNutrition record,
scales it to the estimated portion size, and persists DetectedFoodItem
rows. Also generates simple rule-based recommendations for the meal.
"""
from django.db.models import Q

from nutrition.models import FoodNutrition
from .detector import Detection, estimate_grams


def match_food(label: str) -> FoodNutrition | None:
    """Match a raw YOLO label to a FoodNutrition row, case-insensitively."""
    return FoodNutrition.objects.filter(
        Q(yolo_class_name__iexact=label) | Q(name__iexact=label)
    ).first()


def process_detections(meal, detections: list[Detection], image_width: int, image_height: int):
    """
    Convert raw Detections into saved DetectedFoodItem rows on `meal`,
    then recompute the meal's cached totals.
    """
    from meals.models import DetectedFoodItem

    created_items = []
    for det in detections:
        food = match_food(det.label)
        grams = estimate_grams(det, image_width, image_height)

        item = DetectedFoodItem(
            meal=meal,
            food=food,
            detected_label=det.label,
            confidence=det.confidence,
            bbox_x1=det.x1, bbox_y1=det.y1, bbox_x2=det.x2, bbox_y2=det.y2,
            estimated_grams=grams,
        )
        if food:
            scaled = food.scaled(grams)
            item.calories = scaled["calories"]
            item.protein_g = scaled["protein_g"]
            item.carbs_g = scaled["carbs_g"]
            item.fat_g = scaled["fat_g"]
            item.fiber_g = scaled["fiber_g"]
            item.sugar_g = scaled["sugar_g"]
            item.sodium_mg = scaled["sodium_mg"]
        item.save()
        created_items.append(item)

    meal.recompute_totals()
    return created_items


def generate_recommendations(meal) -> list[str]:
    """
    Rule-based recommendation engine (Phase 12).
    Deliberately simple and explainable -- each rule states WHY it fired,
    which matters for a viva ("explain your recommendation logic").
    """
    tips = []
    items = meal.detected_items.select_related("food").all()

    unhealthy_items = [i for i in items if i.food and not i.food.is_healthy_flag]
    for item in unhealthy_items:
        alt = (
            FoodNutrition.objects.filter(is_healthy_flag=True)
            .order_by("calories_per_100g")
            .exclude(id=item.food.id)
            .first()
        )
        if alt:
            tips.append(
                f"{item.food.name} is high in calories/fat. Consider {alt.name} "
                f"(~{alt.calories_per_100g:.0f} kcal/100g) as a lighter alternative."
            )

    if meal.total_protein_g < 15:
        tips.append(
            "This meal is relatively low in protein "
            f"({meal.total_protein_g:.0f}g). Adding eggs, grilled chicken, "
            "or yogurt would help you hit your daily target."
        )

    if meal.total_fiber_g < 5:
        tips.append(
            "Low fiber content detected. Adding a side of salad, broccoli, "
            "or whole grains would improve digestion and satiety."
        )

    if meal.total_calories > 800:
        tips.append(
            f"This meal is calorie-dense (~{meal.total_calories:.0f} kcal). "
            "If weight loss is your goal, consider reducing portion size."
        )

    if not tips:
        tips.append("This meal looks well balanced. Keep it up!")

    return tips
