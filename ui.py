from concurrent.futures.thread import ThreadPoolExecutor
from multiprocessing import Process

import PySide2
import zmq
from PySide2.QtCore import QThread, Slot, Signal, QUrl
from PySide2.QtMultimedia import QMediaPlayer
from threading import Thread

from converter import Converter, ConverterController

import sys
from PySide2.QtWidgets import QApplication, QLabel, QMainWindow, QTextEdit, QGridLayout, QPlainTextEdit, QWidget, \
    QPushButton, QGroupBox, QComboBox, QVBoxLayout, QFileDialog, QMessageBox, QCheckBox
from PySide2.QtGui import QFont, QTextCursor, QDesktopServices, QIcon


class LogWidget(QPlainTextEdit):
    def log_message(self, msg):
        self.moveCursor(QTextCursor.End)
        self.insertPlainText(msg)
        self.moveCursor(QTextCursor.End)
        if self.verticalScrollBar().value() >= self.verticalScrollBar().maximum() - 5: # scrollbar at bottom, autoscroll
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class Main(QMainWindow):
    new_log = Signal(str)
    new_input = Signal(str)
    new_download = Signal(str)
    conversion_status = Signal()

    def msg_listener(self):
        if not self.sub_socket:
            self.sub_socket = zmq.Context().socket(zmq.SUB)
            self.sub_socket.connect("tcp://127.0.0.1:10290")
            self.sub_socket.setsockopt(zmq.SUBSCRIBE, b"")

        while True:
            msg = self.sub_socket.recv_string()
            cmd, data = msg.split("|", maxsplit=1)
            # print("Got converter msg", cmd, data)
            if cmd == "[file-content]":
                self.emit_input(data)
            elif cmd == "[log]":
                self.emit_log(data, end="")
            elif cmd == "[download]":
                self.emit_log(data)
                self.new_download.emit(data)
            elif cmd == "[conversion-done]":
                self.conversion_status.emit()
            elif cmd == "[crash]":
                self.emit_log(f"Converter crashed, exiting... ({data})")
            else:
                print("Unknown message:", msg)
                continue
            # QApplication.processEvents()

    def emit_log(self, msg, end="\n"):
        self.new_log.emit(msg + end)

    def emit_input(self, s):
        self.new_input.emit(s)

    @Slot(str)
    def log(self, msg):
        self.status_output.log_message(msg)

    @Slot(str)
    def update_text_input(self, s):
        self.text_input.setPlainText(s)
        self.text_input.setPlaceholderText("Paste in text you want to hear, or select a file to see its content here.")
        self.from_file = True

    @Slot(str)
    def show_download_dialog(self, s):
        reply = QMessageBox.information(self, "Download Calibre", s, QMessageBox.Ok | QMessageBox.Cancel)
        if reply == QMessageBox.Ok:
            QDesktopServices.openUrl(QUrl("https://calibre-ebook.com/download"))
        # msgBox.setIcon(QMessageBox.Information)
        # msgBox.setText(s)
        # msgBox.setWindowTitle("Download Calibre")
        # msgBox.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        # downBtn = msgBox.button(QMessageBox.Ok)
        # downBtn.setText("Download")

    @Slot()
    def conversion_done(self):
        self.result_btn.setEnabled(True)

    def log_with_end(self, msg, end="\n"):
        self.log(msg + end)

    def msg_sender(self, cmd, msg):
        try:
            self.pub_socket.send_string(cmd + "|" + msg, zmq.NOBLOCK)
        except zmq.error.Again:
            print("No subscriber. Send again later:", cmd, msg)

    def start_convert(self):
        print("Starting conversion...")
        self.msg_sender("[lang]", self.language_dropdown.currentData())
        self.msg_sender("[esp-model]", self.esp_model_dropdown.currentData())
        self.msg_sender("[vocoder-model]", self.vocoder_model_dropdown.currentData())
        # self.msg_sender("[calibre]", "1" if self.calibre_checkbox.isChecked() else "0")
        self.msg_sender("[convert]", ("" if self.from_file else self.text_input.toPlainText()))
        if 'main' not in self.cfg.sections():
            self.cfg.add_section('main')
        self.cfg.set('main', 'lang', str(self.language_dropdown.currentIndex()))
        self.cfg.set('main', 'esp', str(self.esp_model_dropdown.currentIndex()))
        self.cfg.set('main', 'vocoder', str(self.vocoder_model_dropdown.currentIndex()))
        self.cfg.set('main', 'calibre', str(self.calibre_checkbox.isChecked()))
        with open('./config.ini', encoding="utf-8", mode="w") as f:
            self.cfg.write(f)
        # self.converter_executor.submit(self.converter.convert)

    def select_file(self):
        fileName, _ = QFileDialog.getOpenFileName(self,"Select a file",
                                                  "","All Files (*);;Documents (*.txt *.pdf *.doc *.docx *.rtf *.htm *.html);;")
        if fileName.isspace(): return
        self.log_with_end("Reading from " + fileName)
        self.msg_sender("[file]", fileName)
        self.text_input.setPlaceholderText("Loading file...")

    def text_changed(self):
        self.from_file = False
        if self.text_input.document().isEmpty() or self.text_input.toPlainText().isspace():
            self.convert_btn.setEnabled(False)
        else:
            self.convert_btn.setEnabled(True)

    def open_result(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile("./out.wav"))

    def change_lang(self, idx):
        lang = self.language_dropdown.itemData(idx)
        self.msg_sender("[lang]", lang)

    def change_esp_model(self, idx):
        model = self.esp_model_dropdown.itemData(idx)
        self.msg_sender("[esp-model]", model)

    def change_vocoder_model(self, idx):
        model = self.vocoder_model_dropdown.itemData(idx)
        self.msg_sender("[vocoder-model]", model)

    def calibre_change(self, checked):
        self.msg_sender("[calibre]", "1" if checked else "0")

    def create_control_group(self):
        group = QVBoxLayout()
        self.language_dropdown = QComboBox()
        self.language_dropdown.addItem("Auto detect", "")
        self.language_dropdown.addItem("English", "en")
        self.language_dropdown.addItem("中文", "zh")
        self.language_dropdown.setCurrentIndex(int(self.cfg.get("main", "lang", fallback='0')))
        # self.language_dropdown.currentIndexChanged.connect(self.change_lang)

        self.esp_model_dropdown = QComboBox()
        self.esp_model_dropdown.addItem("conformer+fastspeech2", "conformer_fastspeech2")
        self.esp_model_dropdown.addItem("tacotron2", "tacotron2")
        self.esp_model_dropdown.addItem("fastspeech2", "fastspeech2")
        self.esp_model_dropdown.addItem("fastspeech", "fastspeech")
        self.esp_model_dropdown.setCurrentIndex(int(self.cfg.get("main", "esp", fallback='0')))
        # self.esp_model_dropdown.currentIndexChanged.connect(self.change_esp_model)

        self.vocoder_model_dropdown = QComboBox()
        self.vocoder_model_dropdown.addItem("parallel wavegan", "parallel_wavegan")
        self.vocoder_model_dropdown.addItem("multi-band melgan", "multi_band_melgan")
        self.vocoder_model_dropdown.addItem("full-band melgan", "full_band_melgan")
        self.vocoder_model_dropdown.setCurrentIndex(int(self.cfg.get("main", "vocoder", fallback='0')))
        # self.vocoder_model_dropdown.currentIndexChanged.connect(self.change_vocoder_model)

        self.calibre_checkbox = QCheckBox("Always use Calibre")
        self.calibre_checkbox.setChecked(self.cfg.get("main", "calibre", fallback='False') == "True")
        self.calibre_checkbox.stateChanged.connect(self.calibre_change)

        self.file_btn = QPushButton("Open File")
        self.file_btn.clicked.connect(self.select_file)

        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self.start_convert)

        self.result_btn = QPushButton("Open Result")
        self.result_btn.setEnabled(False)
        self.result_btn.clicked.connect(self.open_result)

        group.addWidget(self.language_dropdown)
        group.addWidget(self.esp_model_dropdown)
        group.addWidget(self.vocoder_model_dropdown)
        group.addWidget(self.calibre_checkbox)
        group.addWidget(self.file_btn)
        group.addWidget(self.convert_btn)
        group.addSpacing(100)
        group.addWidget(self.result_btn)
        group.addStretch(1)
        return group

    def init_converter(self):
        self.converter_process = Process(target=ConverterController)
        self.converter_process.daemon = True
        self.converter_process.start()
        ctx = zmq.Context()
        self.pub_socket = ctx.socket(zmq.PUB)
        self.pub_socket.bind("tcp://127.0.0.1:10289")
        self.sub_socket = None
        # self.converter = Converter(comm=self.log)

    def resizeEvent(self, event:PySide2.QtGui.QResizeEvent) -> None:
        QMainWindow.resizeEvent(self, event)
        print("New size:", event.size())

    def __init__(self):
        QMainWindow.__init__(self)
        self.new_log.connect(self.log)
        self.new_input.connect(self.update_text_input)
        self.new_download.connect(self.show_download_dialog)
        self.conversion_status.connect(self.conversion_done)

        from configparser import ConfigParser
        self.cfg = ConfigParser()
        self.cfg.read("./config.ini")

        screen_rect = QApplication.primaryScreen().geometry()
        print("Screen size:", screen_rect.width(), screen_rect.height())
        self.resize(screen_rect.width() * 0.45, screen_rect.height() * 0.67)
        self.setWindowTitle("Speech Synthesizer")
        self.setWindowIcon(QIcon('speech_synthesizer.svg'))
        self.setCentralWidget(QWidget())
        self.main_layout = QGridLayout()
        self.centralWidget().setLayout(self.main_layout)

        self.text_input = QPlainTextEdit()
        self.text_input.resize(70,100)
        self.text_input.setPlaceholderText("Paste in text you want to hear, or select a file to see its content here.")
        font = self.text_input.font()
        font.setPointSize(12)
        self.text_input.setFont(font)
        self.text_input.textChanged.connect(self.text_changed)

        self.status_output = LogWidget()
        font = self.status_output.font()
        font.setPointSize(10)
        self.status_output.setFont(font)
        self.status_output.setReadOnly(True)

        self.control_group = self.create_control_group()

        self.audio_player = QMediaPlayer()

        self.main_layout.addWidget(self.text_input, 0, 0)
        self.main_layout.addWidget(self.status_output, 2, 0, 1, 3)
        self.main_layout.addLayout(self.control_group, 0, 1)
        self.main_layout.setRowStretch(0, 2)
        self.main_layout.setRowStretch(2, 1)
        self.main_layout.setColumnStretch(0, 5)
        self.main_layout.setColumnStretch(1, 1)

        self.show()

        self.log_with_end("Initializing converter")
        self.init_converter()
        self.msg_thread = Thread(target=self.msg_listener)
        self.msg_thread.setDaemon(True)
        self.msg_thread.start()
        # self.converter_executor = ThreadPoolExecutor(max_workers=1)
        # self.converter_executor.submit(self.init_converter)

    def closeEvent(self, event:PySide2.QtGui.QCloseEvent) -> None:
        self.__del__()
        event.accept()

    def terminate(self):
        if self.pub_socket:
            self.pub_socket.send_string("[exit]")
            self.pub_socket.close()
        if self.sub_socket:
            self.sub_socket.close()
        if self.converter_process and self.converter_process.is_alive():
            self.converter_process.terminate()
            self.converter_process.join(timeout=2)
            if self.converter_process.is_alive():
                self.converter_process.kill()
        # if self.msg_thread:
            # self.msg_thread.join(timeout=2)
        # print("Exiting")

    def __del__(self):
        self.terminate()

import os

if __name__ == '__main__':

    if os.name == "nt": # Windows quirks
        import ctypes
        myappid = u'com.jackz314.speech_synthesizer'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    main = Main()
    sys.exit(app.exec_())