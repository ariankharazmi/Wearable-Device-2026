from PyQt5.QtCore import QObject, pyqtSignal

class FeedbackOverlay(QObject):
    suggestionReady = pyqtSignal(str)
    def __init__(self, ctx_assistant, parent=None):
        super().__init__(parent)
        # on objectDetected, emit suggestion
        ctx_assistant.objectDetected.connect(self._suggest)

    def _suggest(self, label):
        # basic feedback
        suggestions = {
            'person': 'It is safe to proceed.',
            'cell phone': 'You can answer calls.',
            'knife': 'Handle with care!'
        }
        msg = suggestions.get(label.lower(), '')
        if msg:
            self.suggestionReady.emit(msg)


# ----- assistant_pane.py enhancement -----
# inside AssistantPane class, add:
#   def handleAssistantCommand(self, cmd):
#       # forward voice to GPT
#       response = openai.ChatCompletion.create(...)
#       self.displayResponse(response.choices[0].message.content)