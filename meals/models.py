from django.contrib.auth.models import User
from django.db import models

from nutrition.models import FoodNutrition


class Meal(models.Model):
    MEAL_TYPE_CHOICES = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meals")
    image = models.ImageField(upload_to="meal_images/%Y/%m/%d/")
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPE_CHOICES, default="lunch")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Cached totals, recomputed whenever DetectedFoodItems change.
    # Storing these avoids recalculating on every dashboard/report query.
    total_calories = models.FloatField(default=0)
    total_protein_g = models.FloatField(default=0)
    total_carbs_g = models.FloatField(default=0)
    total_fat_g = models.FloatField(default=0)
    total_fiber_g = models.FloatField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.user.username} - {self.meal_type} - {self.uploaded_at:%Y-%m-%d}"

    def recompute_totals(self):
        items = self.detected_items.all()
        self.total_calories = sum(i.calories for i in items)
        self.total_protein_g = sum(i.protein_g for i in items)
        self.total_carbs_g = sum(i.carbs_g for i in items)
        self.total_fat_g = sum(i.fat_g for i in items)
        self.total_fiber_g = sum(i.fiber_g for i in items)
        self.save(update_fields=[
            "total_calories", "total_protein_g", "total_carbs_g",
            "total_fat_g", "total_fiber_g",
        ])


class DetectedFoodItem(models.Model):
    """One detected bounding box from YOLO, linked to a nutrition record."""

    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="detected_items")
    food = models.ForeignKey(FoodNutrition, on_delete=models.SET_NULL, null=True, blank=True)

    # Raw label YOLO returned, kept even if it didn't match a FoodNutrition row
    detected_label = models.CharField(max_length=100)
    confidence = models.FloatField()

    # Bounding box in pixel coordinates on the original image
    bbox_x1 = models.FloatField()
    bbox_y1 = models.FloatField()
    bbox_x2 = models.FloatField()
    bbox_y2 = models.FloatField()

    # Portion estimate in grams. Phase 8 uses a simple heuristic
    # (bounding-box area ratio); can be replaced with a depth/volume
    # model later for more accuracy.
    estimated_grams = models.FloatField(default=100)

    # Snapshot of scaled nutrition at detection time, so historical
    # meals stay accurate even if the FoodNutrition table is edited later.
    calories = models.FloatField(default=0)
    protein_g = models.FloatField(default=0)
    carbs_g = models.FloatField(default=0)
    fat_g = models.FloatField(default=0)
    fiber_g = models.FloatField(default=0)
    sugar_g = models.FloatField(default=0)
    sodium_mg = models.FloatField(default=0)

    def __str__(self):
        return f"{self.detected_label} ({self.confidence:.2f})"

    def recalculate(self, new_grams: float):
        """
        Rescale the snapshotted nutrition values to a user-provided portion
        size and persist. If no FoodNutrition record is linked (detection
        label didn't match the DB), only the gram estimate is updated.

        Validation (must be 1–2000g) is enforced at the form layer; this
        method trusts that the caller has already validated.
        """
        self.estimated_grams = new_grams
        if self.food:
            scaled = self.food.scaled(new_grams)
            self.calories = scaled["calories"]
            self.protein_g = scaled["protein_g"]
            self.carbs_g = scaled["carbs_g"]
            self.fat_g = scaled["fat_g"]
            self.fiber_g = scaled["fiber_g"]
            self.sugar_g = scaled["sugar_g"]
            self.sodium_mg = scaled["sodium_mg"]
        self.save()
