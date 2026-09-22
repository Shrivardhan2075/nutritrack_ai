"""
Unit tests for the accounts app.

Tests cover:
- BMI calculation and category boundaries
- Mifflin-St Jeor calorie-target formula for both genders + goal adjustments
- Profile auto-creation via signal
"""
from django.contrib.auth.models import User
from django.test import TestCase


def make_user(username="testuser", password="testpass123"):
    return User.objects.create_user(username=username, password=password)


class ProfileAutoCreateTest(TestCase):
    def test_profile_created_with_user(self):
        user = make_user()
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.user, user)


class BMITest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = self.user.profile

    def _set_stats(self, height_cm, weight_kg):
        self.profile.height_cm = height_cm
        self.profile.weight_kg = weight_kg

    def test_bmi_none_when_stats_missing(self):
        self.assertIsNone(self.profile.bmi)

    def test_bmi_calculation(self):
        # 70 kg, 175 cm → BMI = 70 / (1.75²) ≈ 22.9
        self._set_stats(175, 70)
        self.assertAlmostEqual(self.profile.bmi, 22.9, places=1)

    def test_bmi_category_underweight(self):
        self._set_stats(175, 50)  # BMI ≈ 16.3
        self.assertEqual(self.profile.bmi_category, "Underweight")

    def test_bmi_category_normal(self):
        self._set_stats(175, 70)  # BMI ≈ 22.9
        self.assertEqual(self.profile.bmi_category, "Normal")

    def test_bmi_category_overweight(self):
        self._set_stats(175, 85)  # BMI ≈ 27.8
        self.assertEqual(self.profile.bmi_category, "Overweight")

    def test_bmi_category_obese(self):
        self._set_stats(175, 105)  # BMI ≈ 34.3
        self.assertEqual(self.profile.bmi_category, "Obese")


class CalorieTargetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = self.user.profile
        # Set required fields
        self.profile.height_cm = 175
        self.profile.weight_kg = 70
        self.profile.age = 30
        self.profile.activity_level = "moderate"  # multiplier 1.55
        self.profile.goal = "maintain"

    def test_default_when_profile_incomplete(self):
        """Returns 2000 kcal default when profile fields are missing."""
        # profile has no height/weight/age set by default
        new_user = make_user("incomplete_user")
        self.assertEqual(new_user.profile.daily_calorie_target, 2000)

    def test_male_maintain(self):
        """
        Male, 30y, 70kg, 175cm, moderate activity, maintain weight.
        BMR = 10*70 + 6.25*175 - 5*30 + 5 = 700+1093.75-150+5 = 1648.75
        TDEE = 1648.75 * 1.55 ≈ 2555.56 → rounded to 2556
        """
        self.profile.gender = "M"
        expected_bmr = 10 * 70 + 6.25 * 175 - 5 * 30 + 5
        expected_tdee = round(expected_bmr * 1.55)
        self.assertEqual(self.profile.daily_calorie_target, expected_tdee)

    def test_female_maintain(self):
        """
        Female, 30y, 70kg, 175cm, moderate.
        BMR = 10*70 + 6.25*175 - 5*30 - 161 = 1482.75
        TDEE = 1482.75 * 1.55 ≈ 2298.26 → rounded to 2298
        """
        self.profile.gender = "F"
        expected_bmr = 10 * 70 + 6.25 * 175 - 5 * 30 - 161
        expected_tdee = round(expected_bmr * 1.55)
        self.assertEqual(self.profile.daily_calorie_target, expected_tdee)

    def test_lose_weight_adjustment(self):
        """Goal 'lose' subtracts 500 kcal from TDEE."""
        self.profile.gender = "M"
        self.profile.goal = "maintain"
        maintain = self.profile.daily_calorie_target
        self.profile.goal = "lose"
        self.assertEqual(self.profile.daily_calorie_target, maintain - 500)

    def test_gain_weight_adjustment(self):
        """Goal 'gain' adds 500 kcal to TDEE."""
        self.profile.gender = "M"
        self.profile.goal = "maintain"
        maintain = self.profile.daily_calorie_target
        self.profile.goal = "gain"
        self.assertEqual(self.profile.daily_calorie_target, maintain + 500)

    def test_sedentary_activity(self):
        self.profile.gender = "M"
        self.profile.activity_level = "sedentary"
        bmr = 10 * 70 + 6.25 * 175 - 5 * 30 + 5
        self.assertEqual(self.profile.daily_calorie_target, round(bmr * 1.2))
