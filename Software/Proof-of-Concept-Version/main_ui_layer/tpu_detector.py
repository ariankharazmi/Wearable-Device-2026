# tpu_detector.py

import numpy as np
try:
    from pycoral.utils.edgetpu import make_interpreter
    from pycoral.adapters import common, detect
    EDGE_SUPPORTED = True
except ImportError:
    EDGE_SUPPORTED = False

class TPUDetector:
    """
    Runs an 8-bit TFLite model on Edge TPU when available,
    otherwise returns empty detections.
    """
    def __init__(self,
                 model_path: str = "models/yolo_nano_edgetpu.tflite",
                 resolution=(320,240),
                 threshold: float = 0.5):
        self.resolution = resolution
        self.threshold = threshold
        self.use_tpu = False

        if EDGE_SUPPORTED:
            try:
                self.interpreter = make_interpreter(model_path)
                self.interpreter.allocate_tensors()
                self.use_tpu = True
            except Exception as e:
                print(f"⚠️ TPUDetector failed to load {model_path}: {e}")

    def detect(self, frame: np.ndarray):
        """
        frame: BGR numpy array at full camera size.
        Returns list of (xmin, ymin, xmax, ymax, class_id, score).
        """
        if not self.use_tpu:
            return []

        # Resize & feed input
        common.set_resized_input(
            self.interpreter, frame, self.resolution, keep_aspect_ratio=True)
        self.interpreter.invoke()

        # Parse detections
        objs = detect.get_objects(self.interpreter, self.threshold)
        results = []
        for o in objs:
            bbox = o.bbox
            results.append((
                bbox.xmin, bbox.ymin,
                bbox.xmax, bbox.ymax,
                o.id, o.score
            ))
        return results
