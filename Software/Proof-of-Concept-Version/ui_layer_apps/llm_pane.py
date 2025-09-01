import os
import openai
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton
from PyQt5.QtGui import QFont

class LLMPane(QWidget):
    """
    Pane for interacting with an on-device or API-backed LLM.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        font = QFont("Helvetica Neue", 12)
        if not font.exactMatch(): font = QFont("Arial", 12)

        self.input = QTextEdit(self)
        self.input.setFont(font)
        self.input.setPlaceholderText("Ask a question…")
        layout.addWidget(self.input)

        self.send_btn = QPushButton("Send", self)
        self.send_btn.setFont(font)
        layout.addWidget(self.send_btn)

        self.output = QTextEdit(self)
        self.output.setFont(font)
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.send_btn.clicked.connect(self._query)
        openai.api_key = os.getenv("OPENAI_API_KEY", "")

    def _query(self):
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return
        # call OpenAI ChatCompletion (or local LLM)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"user","content":prompt}]
            )
            text = response.choices[0].message.content
        except Exception as e:
            text = f"Error: {e}"
        self.output.append(f"> {prompt}\n{text}\n")
        self.input.clear()
        self.output.moveCursor(self.output.textCursor().End)
