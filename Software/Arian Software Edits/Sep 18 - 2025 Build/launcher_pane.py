import time
from datetime import datetime
# main.py
import sys
import os
import time
import inspect
import requests
import psutil
from datetime import datetime
import threading, queue
import cv2
import pycoral
#import tflite-runtime
#import tflite_runtime.interpreter as tflite
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets

from pane_base import Pane
assets_directory = os.path.join(os.getcwd(), "VisionAriesAssets")
logo_path = os.path.join(assets_directory, "VisionAriesLogo.png")

WIDTH, HEIGHT = 640, 400
FPS = 30
BUILD_STR = "Pandora - Sep 19 2025 Build"

APPS = [
    ("camera.png",      "Camera"),
    ("gps.png",         "Maps"),
    ("gpt.png",         "Assistant"),
    ("settings.png",    "Settings"),
    ("bluetooth.png",   "Tether"),
    ("photo.png",       "Photos"),
    ("video.png",       "Video"),
    ("translate.png",   "Translate"),
    ("nav.png",         "Nav"),
    ("music.png",       "Music"),
    ("call.png",        "Call"),
    ("draw.png",        "Draw"),
    ("person.png",      "Track"),
    ("gesture.png",     "Gesture"),
    ("llm.png",         "LLM"),
    ("theme.png",       "Theme"),
    ("sharear.png",     "ShareAR"),
    ("spatialaudio.png","SpatialAudio"),
    ("livestream.png",  "LiveStream"),
]

class LauncherPane(Pane):
    id = "launcher"
    def __init__(self):
        super().__init__()
        self.apps = []


