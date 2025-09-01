# gesture_tracker.py

import cv2
try:
    from pycoral.utils.edgetpu import make_interpreter
    from pycoral.adapters import common, classify
    EDGE_SUPPORTED = True
except ImportError:
    EDGE_SUPPORTED = False

class GestureTracker:
    """
    Runs a small palm-vs-fist or gesture classifier on the Edge TPU
    every few frames, otherwise skips.
    """
    def __init__(self,
                 model_path: str = "models/gesture_edgetpu.tflite",
                 resolution=(128,128),
                 threshold: float = 0.6):
        self.resolution = resolution
        self.threshold = threshold
        self.use_tpu = False

        if EDGE_SUPPORTED:
            try:
                self.interpreter = make_interpreter(model_path)
                self.interpreter.allocate_tensors()
                self.use_tpu = True
            except Exception as e:
                print(f"⚠️ GestureTracker failed to load {model_path}: {e}")

        # map TFLite class IDs → gesture names
        self.gesture_map = {
            0: "fist",
            1: "palm",
            2: "swipe_right",
            3: "swipe_left"
        }

    def detect(self, frame):
        """
        frame: BGR numpy array (we'll center-crop & resize internally)
        Returns one of the gestures or None.
        """
        if not self.use_tpu:
            return None

        # Center-crop
        h, w, _ = frame.shape
        size = min(h, w)
        y0 = (h - size)//2
        x0 = (w - size)//2
        crop = frame[y0:y0+size, x0:x0+size]

        img = cv2.resize(crop, self.resolution)
        common.set_input(self.interpreter, img)
        self.interpreter.invoke()
        classes = classify.get_classes(self.interpreter, top_k=1)
        if classes and classes[0].score >= self.threshold:
            return self.gesture_map.get(classes[0].id)
        return None
