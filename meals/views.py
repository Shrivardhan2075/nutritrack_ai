import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from PIL import Image, UnidentifiedImageError

from .forms import AddManualItemForm, MealUploadForm, PortionAdjustFormSet
from .models import DetectedFoodItem, Meal
from .services.detector import DetectionError, detect_foods
from .services.nutrition_engine import generate_recommendations, process_detections

logger = logging.getLogger(__name__)


@login_required
def dashboard_redirect(request):
    """Sends users straight to the upload page right after login."""
    return redirect("meals:upload")


@login_required
def upload_view(request):
    if request.method == "POST":
        form = MealUploadForm(request.POST, request.FILES)
        if form.is_valid():
            meal = form.save(commit=False)
            meal.user = request.user
            meal.save()

            # --- Validate image can actually be opened ---
            try:
                with Image.open(meal.image.path) as img:
                    img.verify()  # raises for corrupted files
                # Re-open after verify (verify() closes the file pointer)
                with Image.open(meal.image.path) as img:
                    width, height = img.size
            except UnidentifiedImageError:
                meal.delete()
                messages.error(
                    request,
                    "The file you uploaded doesn't appear to be a valid image. "
                    "Please try a JPEG or PNG photo."
                )
                return render(request, "meals/upload.html", {"form": form})
            except Exception as exc:
                logger.exception("Image open failed: %s", exc)
                meal.delete()
                messages.error(request, "Could not read the uploaded image. Please try another file.")
                return render(request, "meals/upload.html", {"form": form})

            # --- Phase 8: Food Detection ---
            try:
                raw_detections = detect_foods(meal.image.path)
            except DetectionError as exc:
                logger.error("YOLO detection failed: %s", exc)
                messages.error(
                    request,
                    f"Food detection failed: {exc} "
                    "Your meal image was saved, but no items could be detected."
                )
                return redirect("meals:result", meal_id=meal.id)
            except Exception as exc:
                logger.exception("Unexpected detection error: %s", exc)
                messages.error(request, "An unexpected error occurred during food detection.")
                return redirect("meals:result", meal_id=meal.id)

            # --- Handle "nothing detected" gracefully ---
            if not raw_detections:
                messages.warning(
                    request,
                    "No food items were detected in this photo. "
                    "Tips: standard AI model recognizes standard COCO classes (pizza, banana, sandwich, etc.). "
                    "You can easily add items like Rice, Bread, Curry, etc. manually below to calculate calories!"
                )
                return redirect("meals:result", meal_id=meal.id)

            # --- Phase 9: Nutrition Engine ---
            process_detections(meal, raw_detections, width, height)

            return redirect("meals:result", meal_id=meal.id)
    else:
        form = MealUploadForm()
    return render(request, "meals/upload.html", {"form": form})


@login_required
def result_view(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, user=request.user)
    items = meal.detected_items.select_related("food").all()
    recommendations = generate_recommendations(meal)
    add_form = AddManualItemForm()
    return render(request, "meals/result.html", {
        "meal": meal,
        "items": items,
        "recommendations": recommendations,
        "add_form": add_form,
    })


@login_required
def add_item_view(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, user=request.user)
    if request.method == "POST":
        form = AddManualItemForm(request.POST)
        if form.is_valid():
            food = form.cleaned_data["food"]
            grams = form.cleaned_data["estimated_grams"]
            scaled = food.scaled(grams)
            DetectedFoodItem.objects.create(
                meal=meal,
                food=food,
                detected_label=food.name,
                confidence=1.0,
                bbox_x1=0, bbox_y1=0, bbox_x2=0, bbox_y2=0,
                estimated_grams=grams,
                calories=scaled["calories"],
                protein_g=scaled["protein_g"],
                carbs_g=scaled["carbs_g"],
                fat_g=scaled["fat_g"],
                fiber_g=scaled["fiber_g"],
                sugar_g=scaled["sugar_g"],
                sodium_mg=scaled["sodium_mg"],
            )
            meal.recompute_totals()
            messages.success(request, f"Added {food.name} ({grams}g) — {scaled['calories']:.0f} kcal added!")
    return redirect("meals:result", meal_id=meal.id)


@login_required
def delete_item_view(request, meal_id, item_id):
    meal = get_object_or_404(Meal, id=meal_id, user=request.user)
    item = get_object_or_404(DetectedFoodItem, id=item_id, meal=meal)
    if request.method == "POST":
        item.delete()
        meal.recompute_totals()
        messages.info(request, "Item removed from meal.")
    return redirect("meals:result", meal_id=meal.id)


@login_required
def adjust_portions_view(request, meal_id):
    """
    GET: Render a form with one editable gram field per detected item.
    POST: Validate portions (1–2000g each), call item.recalculate(),
          recompute meal totals, redirect to result page.
    """
    meal = get_object_or_404(Meal, id=meal_id, user=request.user)
    queryset = meal.detected_items.select_related("food").all()
    add_form = AddManualItemForm()

    if request.method == "POST":
        formset = PortionAdjustFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            for form in formset:
                item = form.instance
                new_grams = form.cleaned_data.get("estimated_grams")
                if new_grams is not None:
                    item.recalculate(new_grams)
            meal.recompute_totals()
            messages.success(request, "Portion sizes updated — nutrition totals recalculated.")
            return redirect("meals:result", meal_id=meal.id)
        # Fall through to re-render with errors
    else:
        formset = PortionAdjustFormSet(queryset=queryset)

    return render(request, "meals/adjust_portions.html", {
        "meal": meal,
        "formset": formset,
        "items_and_forms": zip(queryset, formset.forms),
        "add_form": add_form,
    })


@login_required
def history_view(request):
    meal_list = Meal.objects.filter(user=request.user)
    paginator = Paginator(meal_list, 12)  # 12 cards per page (3×4 grid)
    page_number = request.GET.get("page")
    meals = paginator.get_page(page_number)
    return render(request, "meals/history.html", {"meals": meals})
