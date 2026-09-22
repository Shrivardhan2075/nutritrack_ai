import json
from pathlib import Path

from django.core.management.base import BaseCommand

from nutrition.models import FoodNutrition

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "food_nutrition_seed.json"


class Command(BaseCommand):
    help = "Seeds the FoodNutrition table from data/food_nutrition_seed.json"

    def handle(self, *args, **options):
        with open(DATA_FILE) as f:
            records = json.load(f)

        created, updated = 0, 0
        for r in records:
            obj, was_created = FoodNutrition.objects.update_or_create(
                name=r["name"],
                defaults={
                    "yolo_class_name": r.get("yolo_class_name", r["name"]),
                    "calories_per_100g": r["calories_per_100g"],
                    "protein_g": r["protein_g"],
                    "carbs_g": r["carbs_g"],
                    "fat_g": r["fat_g"],
                    "fiber_g": r["fiber_g"],
                    "sugar_g": r.get("sugar_g", 0),
                    "sodium_mg": r.get("sodium_mg", 0),
                    "is_healthy_flag": r.get("is_healthy_flag", True),
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"Nutrition data loaded: {created} created, {updated} updated."
        ))
