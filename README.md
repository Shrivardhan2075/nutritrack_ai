# NutriTrack AI
### AI-Powered Food Detection and Nutrition Analysis using YOLO

A Django web application that detects multiple food items in a meal photo
using YOLO object detection, estimates portion sizes, calculates calories
and macronutrients, and gives users daily/weekly/monthly dashboards and
personalized recommendations.

This README covers setup, architecture, the database design, how to train
your own food-detection model, what's tested, and known limitations —
everything you need for the report, the viva, and to actually run it.

---

## 1. Quick Start

```bash
cd nutritrack_ai
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

python manage.py migrate
python manage.py load_nutrition_data     # seeds 30 food items with real nutrition data
python manage.py createsuperuser          # optional, for /admin/

python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. Sign up, upload a meal photo, and it will
run through YOLO detection → nutrition matching → dashboard automatically.

**First run note:** the first time you upload an image, Ultralytics will
auto-download the pretrained `yolov8n.pt` checkpoint (~6MB) if you haven't
supplied your own trained weights. This requires internet access once.

---

## 2. Project Structure (Modular Architecture)

```
nutritrack_ai/
├── nutritrack_project/     # Django project settings, root urls
├── core/                   # Landing page
├── accounts/                # Signup, login, profile, BMI/calorie-target logic
├── nutrition/               # FoodNutrition model + seed data + admin
├── meals/                   # Meal upload, detection pipeline, history
│   └── services/
│       ├── detector.py          # YOLO wrapper (isolates all ML code)
│       └── nutrition_engine.py  # Matches detections → nutrition, recommendations
├── dashboard_app/           # Daily/weekly/monthly aggregation + charts
├── templates/                # All HTML (Bootstrap 5 + Chart.js via CDN)
├── static/css/style.css
├── ml_models/                # Put your trained YOLO weights here (yolo_food.pt)
└── requirements.txt
```

**Why this structure:** each app has one responsibility (single-responsibility
principle). `meals/services/` isolates the AI logic from Django views —
so the detection code can be unit-tested or swapped without touching HTTP
handling, and the view functions stay thin and readable.

---

## 3. Database Design (Phase 4)

**Entities:**

| Model | Purpose |
|---|---|
| `User` (Django built-in) | Authentication |
| `Profile` (1:1 with User) | Height, weight, age, gender, activity level, goal → derives BMI & daily calorie target |
| `FoodNutrition` | Master nutrition table, per-100g values |
| `Meal` | One uploaded photo; FK to User; cached totals |
| `DetectedFoodItem` | One YOLO bounding box; FK to Meal and FoodNutrition; snapshotted nutrition values |

**Relationships:**
- `User 1—1 Profile`
- `User 1—N Meal`
- `Meal 1—N DetectedFoodItem`
- `DetectedFoodItem N—1 FoodNutrition` (nullable — a detection might not match any known food)

**Why snapshot nutrition values on `DetectedFoodItem` instead of just
joining to `FoodNutrition` at display time?** If you later correct a
nutrition value in the master table, historical meals shouldn't silently
change — that would corrupt a user's calorie history. This is a standard
"point-in-time snapshot" pattern used in any system with historical
records tied to a mutable reference table (e.g. order line items vs. a
product catalog).

**Normalization:** the schema is in 3NF — nutrition data lives once in
`FoodNutrition`, not repeated per meal; `DetectedFoodItem` stores only the
scaled snapshot + a reference, avoiding update anomalies while preserving
history.

ER diagram (textual — draw this in draw.io / dbdiagram.io for your report):

```
User ──1:1── Profile
User ──1:N── Meal ──1:N── DetectedFoodItem ──N:1── FoodNutrition
```

---

## 4. How Detection Works (Phase 8)

`meals/services/detector.py`:
1. Lazy-loads a YOLO model once (cached at module level — reloading a
   checkpoint on every request would be far too slow).
2. Runs inference on the uploaded image with a confidence threshold
   (default 0.35, configurable in `settings.YOLO_CONFIDENCE_THRESHOLD`).
3. Returns a list of `Detection` objects: label, confidence, bounding box.

`meals/services/nutrition_engine.py`:
1. Matches each detected label to a `FoodNutrition` row (case-insensitive,
   matches either the display name or the `yolo_class_name`).
2. Estimates portion size in grams from the bounding-box area relative to
   the image (`estimate_grams` in `detector.py`) — a simple heuristic,
   documented as a limitation below.
3. Scales the matched food's per-100g values to the estimated portion and
   saves a `DetectedFoodItem`.
4. Recomputes cached totals on the `Meal`.

---

## 5. Training Your Own Food-Detection Model (Phases 5–7)

The app ships with a **pretrained COCO YOLOv8n fallback**, which already
detects: pizza, banana, apple, sandwich, orange, broccoli, carrot, hot dog,
donut, cake. That's enough to demo the entire pipeline today.

To hit the project's target (mAP50 > 95%) on a broader set of food classes,
train your own model — this needs a GPU (a free Google Colab GPU is enough
for a small model) and a labeled dataset. This sandbox environment doesn't
have GPU access or the network access to download multi-GB datasets, so
this step is meant to be run on your own machine or Colab.

**5.1 Recommended datasets to combine:**
| Dataset | Content | Why |
|---|---|---|
| Open Images V7 (food subset) | Large, diverse, has bounding boxes already | Real-world variety, saves annotation time |
| Food-101 (re-annotated) | 101 food categories | Broad class coverage (originally classification-only, needs bbox annotation) |
| Roboflow Universe "food detection" public datasets | Pre-annotated YOLO-format food datasets | Ready-to-train, various plate/multi-item scenes |
| Your own photos | Meals you actually eat | Domain-matches your real use case, boosts real-world accuracy |

Combine 2–3 of these rather than relying on one — this is the "dataset
comparison and recommendation" step from Phase 5, and you should document
*why* you chose your specific combination in your report (class coverage,
image diversity, annotation quality).

**5.2 Folder structure (YOLO format):**
```
dataset/
├── images/
│   ├── train/
│   ├── val/
│   └── test/
├── labels/
│   ├── train/    # one .txt per image: class x_center y_center width height (normalized 0-1)
│   ├── val/
│   └── test/
└── data.yaml     # class names + paths
```

**5.3 `data.yaml` example:**
```yaml
train: ../dataset/images/train
val: ../dataset/images/val
test: ../dataset/images/test
nc: 12
names: ['pizza','banana','apple','sandwich','rice','chicken','salad','fries','burger','egg','bread','pasta']
```

**5.4 Training script (run on Colab/local GPU, not in this sandbox):**
```python
from ultralytics import YOLO

model = YOLO('yolo11n.pt')  # transfer learning from COCO-pretrained weights

results = model.train(
    data='dataset/data.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    optimizer='AdamW',
    lr0=0.001,
    patience=20,          # early stopping
    augment=True,          # mosaic, flip, HSV augmentation
)

metrics = model.val()
print(metrics.box.map50)   # mAP@0.5 — your headline accuracy metric
print(metrics.box.map)     # mAP@0.5:0.95 — stricter metric
```

**5.5 Interpreting results:**
- **mAP50**: average precision at 50% IoU overlap threshold — the standard
  headline metric for detection accuracy. >90% is strong for a
  well-annotated food dataset.
- **Precision**: of all boxes the model drew, what fraction were correct
  (low precision = false positives — the model sees food that isn't there).
- **Recall**: of all actual food items, what fraction did the model find
  (low recall = missed detections).
- **F1**: harmonic mean of precision/recall — use it when you need one
  number balancing both.
- **Confusion matrix**: shows which classes get confused with each other
  (e.g. burger vs. sandwich) — read it to decide which classes need more
  training images.

If mAP is low: check for (1) mislabeled boxes, (2) class imbalance —
oversample rare classes or collect more images, (3) too few epochs —
Ultralytics' `patience` early-stopping will tell you if it plateaued,
(4) images too small/blurry — verify `imgsz` matches your image quality.

**5.6 After training:** copy `runs/detect/train/weights/best.pt` into this
project's `ml_models/yolo_food.pt`, and update `data.yaml`'s class names to
match rows in `nutrition/data/food_nutrition_seed.json` (`yolo_class_name`
field) so detections map to nutrition data automatically.

---

## 6. Testing (Phase 13)

What's been verified in this build:
- Django system checks (`manage.py check`) — pass, no issues
- Migrations apply cleanly on a fresh SQLite DB
- Full HTTP flow via Django's test client: landing → signup → profile →
  upload → **real YOLO inference** → result page → dashboard → history —
  all return correct status codes
- Nutrition seed data loads and matches YOLO class names correctly

**Recommended additional tests for your report** (write these as Django
`TestCase` classes in each app's `tests.py`):
- Unit: `FoodNutrition.scaled()` returns correct math for arbitrary grams
- Unit: `Profile.daily_calorie_target` against known Mifflin-St Jeor values
- Integration: upload → detection → DB rows created → totals recomputed
- Model: run `model.val()` on a held-out test split, record mAP/P/R/F1
- Performance: measure inference time per image (should be well under 1s
  on GPU, a few seconds on CPU with yolov8n)

---

## 7. Known Limitations & Future Work

Be upfront about these in your report — reviewers respect honesty about
scope more than overselling:

1. **Portion-size estimation is a heuristic** (bounding-box area ratio),
   not true volumetric estimation. A depth-estimation model or reference-
   object calibration (e.g. detecting a standard-size plate) would improve
   accuracy — good "future work" section material.
2. **Pretrained fallback model** only recognizes ~10 COCO food classes
   until you train on a food-specific dataset (Section 5).
3. **Nutrition matching is exact-label matching**, not fuzzy/semantic —
   a class labeled "fried_rice" won't match a "Rice" row unless
   `yolo_class_name` is set correctly during data seeding.
4. **Single-image estimation** doesn't account for foods hidden under
   others in the same dish (e.g. sauce fully covering rice).

---

## 8. Sample Viva Questions

- Why YOLO instead of a CNN classifier for this problem?
- Walk through what happens between image upload and the result page.
- Why is nutrition data snapshotted per detection instead of always
  joined live from the master table?
- How is portion size estimated, and what's its main weakness?
- Explain precision vs. recall in the context of missing a food item
  vs. hallucinating one that isn't there.
- How would you extend this to depth-based portion estimation?
- Why Mifflin-St Jeor for calorie targets, and what are its limitations?

---

## 9. Tech Stack

Python · Django · SQLite (dev) / MySQL (prod-ready) · Ultralytics YOLO ·
PyTorch · OpenCV · Pillow · Bootstrap 5 · Chart.js
