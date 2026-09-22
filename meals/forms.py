from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory

from .models import DetectedFoodItem, Meal


class MealUploadForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ["image", "meal_type"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "id": "id_image",
            }),
            "meal_type": forms.Select(attrs={"class": "form-select"}),
        }


class PortionGramsField(forms.FloatField):
    """Float field that enforces the 1–2000g sanity range."""

    def validate(self, value):
        super().validate(value)
        if value is not None:
            if value <= 0:
                raise ValidationError("Portion size must be greater than 0 g.")
            if value > 2000:
                raise ValidationError("Portion size cannot exceed 2000 g.")


class PortionItemForm(forms.ModelForm):
    estimated_grams = PortionGramsField(
        min_value=1,
        max_value=2000,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
        label="Grams",
    )

    class Meta:
        model = DetectedFoodItem
        fields = ["estimated_grams"]


# Factory creates a formset where each form represents one DetectedFoodItem.
# extra=0 means no blank forms are added; can_delete=False keeps the formset
# focused purely on portion-size editing.
PortionAdjustFormSet = modelformset_factory(
    DetectedFoodItem,
    form=PortionItemForm,
    extra=0,
    can_delete=False,
)


class AddManualItemForm(forms.Form):
    food = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_manual_food"}),
        label="Select Food Item",
    )
    estimated_grams = PortionGramsField(
        min_value=1,
        max_value=2000,
        initial=100,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1", "id": "id_manual_grams"}),
        label="Portion (Grams)",
    )

    def __init__(self, *args, **kwargs):
        from nutrition.models import FoodNutrition
        super().__init__(*args, **kwargs)
        self.fields["food"].queryset = FoodNutrition.objects.all().order_by("name")

