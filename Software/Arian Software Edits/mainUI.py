import os, sys, time, threading, queue
import cv2
import pycoral
#import tflite-runtime
#import tflite_runtime.interpreter as tflite
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
WIDTH, HEIGHT = 600, 400
FPS = 30
