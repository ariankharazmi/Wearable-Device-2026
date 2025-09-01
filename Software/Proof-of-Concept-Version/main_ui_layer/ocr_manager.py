# ocr_manager.py

import cv2
import pytesseract

class OCRManager:
    """
    Runs Tesseract OCR on a small ROI only when requested.
    """
    def __init__(self, tesseract_cmd: str = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def read_text(self, frame):
        """
        frame: BGR numpy array
        returns: a cleaned string
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray, config='--psm 6').strip()
        return text
