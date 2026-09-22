"""
Tests for the meals app.

Tests cover:
- Full upload → detection → result pipeline via Django test client
- "No detections" edge case
- Portion recalculate() math
- Adjust-portions view validation
"""
import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from PIL import Image as PILImage

from meals.models import Meal, DetectedFoodItem
from nutrition.models import FoodNutrition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username="mealuser", password="pass1234"):
    return User.objects.create_user(username=username, password=password)


def make_food():
    return FoodNutrition.objects.create(
        name="Apple",
        yolo_class_name="apple",
        calories_per_100g=52.0,
        protein_g=0.3,
        carbs_g=14.0,
        fat_g=0.2,
        fiber_g=2.4,
        sugar_g=10.0,
        sodium_mg=1.0,
        is_healthy_flag=True,
    )


def make_png_image_file(filename="test.png", size=(200, 200)):
    """Return an in-memory PNG file object usable as a Django upload."""
    img = PILImage.new("RGB", size, color=(100, 200, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = filename
    return buf


def make_meal(user):
    return Meal.objects.create(user=user, meal_type="lunch")


def make_detected_item(meal, food, grams=150.0):
    scaled = food.scaled(grams)
    return DetectedFoodItem.objects.create(
        meal=meal,
        food=food,
        detected_label=food.yolo_class_name,
        confidence=0.90,
        bbox_x1=10, bbox_y1=10, bbox_x2=100, bbox_y2=100,
        estimated_grams=grams,
        calories=scaled["calories"],
        protein_g=scaled["protein_g"],
        carbs_g=scaled["carbs_g"],
        fat_g=scaled["fat_g"],
        fiber_g=scaled["fiber_g"],
        sugar_g=scaled["sugar_g"],
        sodium_mg=scaled["sodium_mg"],
    )


# ---------------------------------------------------------------------------
# Detection-pipeline tests (upload view with mocked YOLO)
# ---------------------------------------------------------------------------

from meals.services.detector import Detection as YOLODetection


FAKE_DETECTION = YOLODetection(
    label="apple", confidence=0.88,
    x1=10.0, y1=10.0, x2=110.0, y2=110.0,
)


class UploadFlowTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="mealuser", password="pass1234")
        self.food = make_food()
        self.url = reverse("meals:upload")

    @patch("meals.views.detect_foods", return_value=[FAKE_DETECTION])
    def test_upload_creates_meal_and_detected_items(self, mock_detect):
        img_file = make_png_image_file()
        response = self.client.post(self.url, {
            "image": img_file,
            "meal_type": "lunch",
        })
        self.assertEqual(Meal.objects.filter(user=self.user).count(), 1)
        meal = Meal.objects.get(user=self.user)
        self.assertGreater(meal.detected_items.count(), 0)
        # Should redirect to result page
        self.assertRedirects(response, reverse("meals:result", args=[meal.id]))

    @patch("meals.views.detect_foods", return_value=[FAKE_DETECTION])
    def test_upload_sets_calorie_total(self, mock_detect):
        self.client.post(self.url, {
            "image": make_png_image_file(),
            "meal_type": "breakfast",
        })
        meal = Meal.objects.get(user=self.user)
        # Apple at some grams → calories > 0
        self.assertGreater(meal.total_calories, 0)

    def test_upload_requires_login(self):
        self.client.logout()
        response = self.client.post(self.url, {
            "image": make_png_image_file(),
            "meal_type": "lunch",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class NoDetectionsTest(TestCase):
    def setUp(self):
        self.user = make_user("nodetect_user")
        self.client.login(username="nodetect_user", password="pass1234")
        self.url = reverse("meals:upload")

    @patch("meals.views.detect_foods", return_value=[])
    def test_no_detections_redirects_to_result(self, mock_detect):
        """Empty detection list → warning message + redirect to result (no crash)."""
        response = self.client.post(self.url, {
            "image": make_png_image_file(),
            "meal_type": "snack",
        })
        meal = Meal.objects.get(user=self.user)
        self.assertRedirects(response, reverse("meals:result", args=[meal.id]))

    @patch("meals.views.detect_foods", return_value=[])
    def test_no_detections_result_page_renders(self, mock_detect):
        """Result page must render without crashing even with 0 detected items."""
        self.client.post(self.url, {
            "image": make_png_image_file(),
            "meal_type": "snack",
        })
        meal = Meal.objects.get(user=self.user)
        response = self.client.get(reverse("meals:result", args=[meal.id]))
        self.assertEqual(response.status_code, 200)
        # Zero calorie total is shown
        self.assertContains(response, "0")


# ---------------------------------------------------------------------------
# Portion recalculate() tests
# ---------------------------------------------------------------------------

class PortionRecalculateTest(TestCase):
    def setUp(self):
        self.user = make_user("portionuser")
        self.food = make_food()
        meal = make_meal(self.user)
        self.item = make_detected_item(meal, self.food, grams=100.0)

    def test_recalculate_updates_grams(self):
        self.item.recalculate(200.0)
        self.assertEqual(self.item.estimated_grams, 200.0)

    def test_recalculate_scales_calories(self):
        # At 100g: 52 kcal; at 200g: 104 kcal
        self.item.recalculate(200.0)
        self.assertAlmostEqual(self.item.calories, 104.0, places=0)

    def test_recalculate_scales_protein(self):
        # 0.3g/100g → 0.6g/200g
        self.item.recalculate(200.0)
        self.assertAlmostEqual(self.item.protein_g, 0.6, places=1)

    def test_recalculate_persists_to_db(self):
        self.item.recalculate(300.0)
        refreshed = DetectedFoodItem.objects.get(pk=self.item.pk)
        self.assertAlmostEqual(refreshed.estimated_grams, 300.0)


# ---------------------------------------------------------------------------
# Adjust-portions view tests
# ---------------------------------------------------------------------------

class AdjustPortionsViewTest(TestCase):
    def setUp(self):
        self.user = make_user("adjustuser")
        self.client.login(username="adjustuser", password="pass1234")
        self.food = make_food()
        self.meal = make_meal(self.user)
        self.item = make_detected_item(self.meal, self.food, grams=100.0)
        self.url = reverse("meals:adjust_portions", args=[self.meal.id])

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adjust Portions")

    def test_post_valid_updates_grams(self):
        mgmt = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            f"form-0-id": str(self.item.pk),
            f"form-0-estimated_grams": "250",
        }
        response = self.client.post(self.url, mgmt)
        self.item.refresh_from_db()
        self.assertAlmostEqual(self.item.estimated_grams, 250.0)
        self.assertRedirects(response, reverse("meals:result", args=[self.meal.id]))

    def test_post_negative_grams_rejected(self):
        mgmt = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            f"form-0-id": str(self.item.pk),
            f"form-0-estimated_grams": "-50",
        }
        response = self.client.post(self.url, mgmt)
        # Should re-render with errors, not redirect
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertAlmostEqual(self.item.estimated_grams, 100.0)  # unchanged

    def test_post_over_2000g_rejected(self):
        mgmt = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            f"form-0-id": str(self.item.pk),
            f"form-0-estimated_grams": "9999",
        }
        response = self.client.post(self.url, mgmt)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertAlmostEqual(self.item.estimated_grams, 100.0)  # unchanged
