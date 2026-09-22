"""
YOLO food detection wrapper.

This module isolates all Ultralytics/YOLO-specific code behind a single
`detect_foods()` function, so the rest of the app (views, nutrition
engine) never has to know which YOLO version or weight file is in use.
Swap YOLO_WEIGHTS_PATH in settings.py once you've trained your own
food-detection model (Phase 5-7) and nothing else in the codebase changes.

Design note (why lazy-load the model):
Loading a YOLO checkpoint takes real time and memory. We load it once,
the first time it's needed, and cache it at module level -- not on
every request.
"""
from dataclasses import dataclass

from django.conf import settings

_model_cache = None

# COCO class names that correspond to food items.
# The pretrained yolov8n.pt only detects these food-related classes;
# all other COCO classes (person, car, chair, etc.) are deliberately
# excluded so non-food bounding boxes never enter the nutrition pipeline.
COCO_FOOD_CLASSES = {
    "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake",
}


class DetectionError(Exception):
    """
    Raised when the YOLO model cannot be loaded or inference fails.
    Views catch this specifically to show a helpful user-facing message
    rather than an unhandled 500 error.
    """


@dataclass
class Detection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def box_area(self):
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


def _get_model():
    global _model_cache
    if _model_cache is None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectionError(
                "The 'ultralytics' package is not installed. "
                "Run: pip install ultralytics"
            ) from exc

        weights_path = settings.YOLO_WEIGHTS_PATH
        try:
            if weights_path.exists():
                _model_cache = YOLO(str(weights_path))
            else:
                # Fallback: pretrained COCO checkpoint downloaded automatically
                # by Ultralytics on first use. Covers the 10 food classes listed
                # in COCO_FOOD_CLASSES above -- enough to demo the full pipeline
                # before you train a custom food-detection model.
                _model_cache = YOLO("yolov8n.pt")
        except Exception as exc:
            raise DetectionError(
                f"Failed to load YOLO model ({type(exc).__name__}: {exc}). "
                "Check YOLO_WEIGHTS_PATH in settings.py."
            ) from exc

    return _model_cache


def detect_foods(image_path: str, confidence_threshold: float = None) -> list[Detection]:
    """
    Run YOLO inference on a single image and return a list of Detections.

    Only detections whose class name is in COCO_FOOD_CLASSES are kept:
    - When using the pretrained COCO fallback model this filters out the
      many non-food categories (person, car, chair, etc.).
    - When using a custom food-only model, all returned classes are food
      by definition and this filter is a harmless no-op (add your class
      names to COCO_FOOD_CLASSES or override the filter in subclasses).

    Raises DetectionError if the model cannot be loaded or inference fails.
    """
    threshold = confidence_threshold or settings.YOLO_CONFIDENCE_THRESHOLD
    model = _get_model()

    try:
        results = model.predict(source=str(image_path), conf=threshold, verbose=False)
    except Exception as exc:
        raise DetectionError(
            f"YOLO inference failed ({type(exc).__name__}: {exc})."
        ) from exc

    detections = []
    for result in results:
        names = result.names
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = names[cls_id]
            # --- Food-class gate ---
            # If a custom model is loaded (YOLO_WEIGHTS_PATH exists), skip
            # this filter because the custom model only has food classes.
            # For the COCO fallback, only pass known food class names.
            if not settings.YOLO_WEIGHTS_PATH.exists() and label not in COCO_FOOD_CLASSES:
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            detections.append(Detection(label, conf, x1, y1, x2, y2))
    return detections


def estimate_grams(detection: Detection, image_width: int, image_height: int) -> float:
    """
    Portion-size heuristic (Phase 8): estimate grams from how much of the
    frame a bounding box occupies, relative to a typical reference plate
    area. This is intentionally simple -- a real volumetric/depth model
    is future work (see README 'Limitations & Future Work').

    Calibration: a food item filling ~15% of the frame is treated as a
    ~150g 'typical' serving; scaled roughly linearly from there, clamped
    to [20g, 600g] to reject absurd values from extreme bounding boxes.
    """
    image_area = image_width * image_height
    if image_area == 0:
        return 100.0
    area_ratio = detection.box_area / image_area
    grams = 150 * (area_ratio / 0.15)
    return round(min(max(grams, 20), 600), 1)
