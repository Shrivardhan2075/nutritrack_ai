from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    GENDER_CHOICES = [("M", "Male"), ("F", "Female"), ("O", "Other")]
    GOAL_CHOICES = [
        ("lose", "Lose Weight"),
        ("maintain", "Maintain Weight"),
        ("gain", "Gain Weight"),
    ]
    ACTIVITY_CHOICES = [
        ("sedentary", "Sedentary (little/no exercise)"),
        ("light", "Lightly active"),
        ("moderate", "Moderately active"),
        ("active", "Very active"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    activity_level = models.CharField(
        max_length=20, choices=ACTIVITY_CHOICES, default="moderate"
    )
    goal = models.CharField(max_length=10, choices=GOAL_CHOICES, default="maintain")

    def __str__(self):
        return f"{self.user.username}'s profile"

    @property
    def bmi(self):
        if not self.height_cm or not self.weight_kg:
            return None
        h_m = self.height_cm / 100
        return round(self.weight_kg / (h_m * h_m), 1)

    @property
    def bmi_category(self):
        bmi = self.bmi
        if bmi is None:
            return "Unknown"
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25:
            return "Normal"
        if bmi < 30:
            return "Overweight"
        return "Obese"

    @property
    def daily_calorie_target(self):
        """
        Mifflin-St Jeor BMR formula + activity multiplier + goal adjustment.
        Standard, widely-cited estimation used by most fitness apps.
        """
        if not all([self.height_cm, self.weight_kg, self.age, self.gender]):
            return 2000  # sensible default until profile is complete

        if self.gender == "M":
            bmr = 10 * self.weight_kg + 6.25 * self.height_cm - 5 * self.age + 5
        else:
            bmr = 10 * self.weight_kg + 6.25 * self.height_cm - 5 * self.age - 161

        multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "active": 1.725,
        }
        tdee = bmr * multipliers.get(self.activity_level, 1.55)

        if self.goal == "lose":
            tdee -= 500
        elif self.goal == "gain":
            tdee += 500
        return round(tdee)
