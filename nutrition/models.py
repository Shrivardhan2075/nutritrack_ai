from django.db import models


class FoodNutrition(models.Model):
    """
    Master nutrition table. One row per food item, values normalised
    to "per 100 grams" so we can scale them to any detected portion size.

    This is the 'Nutrition Engine' data source referenced in Phase 9
    of the roadmap. In production this table would be seeded from a
    verified source (USDA FoodData Central / IFCT for Indian foods)
    via the load_nutrition_data management command.
    """

    name = models.CharField(max_length=100, unique=True, db_index=True)
    # Matches the class name YOLO was trained to detect. Kept separate
    # from `name` so display names can differ from model class names.
    yolo_class_name = models.CharField(max_length=100, blank=True, db_index=True)

    calories_per_100g = models.FloatField(help_text="kcal per 100g")
    protein_g = models.FloatField(default=0)
    carbs_g = models.FloatField(default=0)
    fat_g = models.FloatField(default=0)
    fiber_g = models.FloatField(default=0)
    sugar_g = models.FloatField(default=0)
    sodium_mg = models.FloatField(default=0)

    # Used by the Recommendation Engine (Phase 12) to flag healthier swaps
    is_healthy_flag = models.BooleanField(default=True)
    healthier_alternative = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Food Nutrition Record"

    def __str__(self):
        return self.name

    def scaled(self, grams: float) -> dict:
        """Scale this food's per-100g values to an arbitrary portion size."""
        factor = grams / 100.0
        return {
            "calories": round(self.calories_per_100g * factor, 1),
            "protein_g": round(self.protein_g * factor, 1),
            "carbs_g": round(self.carbs_g * factor, 1),
            "fat_g": round(self.fat_g * factor, 1),
            "fiber_g": round(self.fiber_g * factor, 1),
            "sugar_g": round(self.sugar_g * factor, 1),
            "sodium_mg": round(self.sodium_mg * factor, 1),
        }
