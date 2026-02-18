import abc

class Pane(abc.ABC):
    def __init__(self, services):
        self.services = services

    @abc.abstractmethod
    def draw(self, frame):
        """Draw the pane content onto the given frame."""
        pass

    @abc.abstractmethod
    def handle_input(self, input_data):
        """Handle user input for this specific pane."""
        pass