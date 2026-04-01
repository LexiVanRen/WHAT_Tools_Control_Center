import sys
from PySide6 import QtWidgets

from ui.main_window import MainWindow


def run_app():
    app = QtWidgets.QApplication(sys.argv)

    w = MainWindow()

    w.showMaximized()

    sys.exit(app.exec())
