"""
Unit tests for the nutrition app.

Tests cover:
- FoodNutrition.scaled() math for arbitrary portion sizes
- match_food() case-insensitive lookup by yolo_class_name and name
"""
from django.test import TestCase

from nutrition.models import FoodNutrition
from meals.services.nutrition_engine import match_food


def make_food(**kwargs):
    defaults = {
        "name": "Test Food",
        "yolo_class_name": "test_food",
        "calories_per_100g": 200.0,
        "protein_g": 10.0,
        "carbs_g": 30.0,
        "fat_g": 5.0,
        "fiber_g": 2.0,
        "sugar_g": 8.0,
        "sodium_mg": 100.0,
        "is_healthy_flag": True,
    }
    defaults.update(kwargs)
    return FoodNutrition.objects.create(**defaults)


class NutritionScalingTest(TestCase):
    def setUp(self):
        self.food = make_food()

    def test_scale_to_100g_is_identity(self):
        scaled = self.food.scaled(100)
        self.assertAlmostEqual(scaled["calories"], 200.0)
        self.assertAlmostEqual(scaled["protein_g"], 10.0)
        self.assertAlmostEqual(scaled["carbs_g"], 30.0)
        self.assertAlmostEqual(scaled["fat_g"], 5.0)

    def test_scale_to_200g_doubles(self):
        scaled = self.food.scaled(200)
        self.assertAlmostEqual(scaled["calories"], 400.0, places=1)
        self.assertAlmostEqual(scaled["protein_g"], 20.0, places=1)

    def test_scale_to_50g_halves(self):
        scaled = self.food.scaled(50)
        self.assertAlmostEqual(scaled["calories"], 100.0, places=1)
        self.assertAlmostEqual(scaled["fat_g"], 2.5, places=1)

    def test_scale_includes_sugar_and_sodium(self):
        scaled = self.food.scaled(150)
        self.assertAlmostEqual(scaled["sugar_g"], 12.0, places=1)
        self.assertAlmostEqual(scaled["sodium_mg"], 150.0, places=1)

    def test_scale_zero_grams_returns_zeros(self):
        scaled = self.food.scaled(0)
        self.assertAlmostEqual(scaled["calories"], 0.0)


class MatchFoodTest(TestCase):
    def setUp(self):
        self.banana = make_food(name="Banana", yolo_class_name="banana")
        self.pizza = make_food(name="Pizza", yolo_class_name="pizza")

    def test_match_by_yolo_class_name_exact(self):
        result = match_food("banana")
        self.assertEqual(result, self.banana)

    def test_match_by_yolo_class_name_case_insensitive(self):
        result = match_food("BANANA")
        self.assertEqual(result, self.banana)

    def test_match_by_name_case_insensitive(self):
        result = match_food("Pizza")
        self.assertEqual(result, self.pizza)

    def test_no_match_returns_none(self):
        result = match_food("unicorn_food_xyz")
        self.assertIsNone(result)
