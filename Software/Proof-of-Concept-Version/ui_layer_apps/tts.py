import pyttsx3
engine = pyttsx3.init()
engine.setProperty('rate', 150)
engine.say("Hello, this is a test of the Text-to-Speech capabilities of AriesOS")
engine.runAndWait()