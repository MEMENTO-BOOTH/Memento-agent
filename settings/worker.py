"""Worker thread générique pour appels réseau sans bloquer l'UI."""
from PyQt5.QtCore import QThread, pyqtSignal


class ApiWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args):
        super().__init__()
        self._func = func
        self._args = args

    def run(self):
        try:
            result = self._func(*self._args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
