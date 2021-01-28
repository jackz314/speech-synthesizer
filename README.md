# Speech Synthesizer
A GUI application that does end-to-end human-realistic text to speech.

### Overview

The app uses [espnet](https://github.com/espnet/espnet) for most of the heavy lifting (text -> spectrogram generation -> wave generation), I added some text preprocessing steps that improves support for Chinese, as well as automatic language identification (with [langdetect](https://github.com/Mimino666/langdetect)) for ease of use. 

In addition, the app supports reading from files, including a wide range of formats thanks to the [Calibre](http://calibre-ebook.com/) integration. It also outputs a subtitle and lyrics file synced for each sentence.

The GUI is implemented with [PySide2](https://www.qt.io/qt-for-python) (Qt for Python), and the backend-frontend communication is implemented with [pyzmq](https://github.com/zeromq/pyzmq/).

### Installation

To run locally, clone the repository and install the requirements:
```bash
pip install -r requirements.txt
```
Then run `ui.py` to start the app (`python ./ui.py`).

Alternatively, download zip from [releases](https://github.com/jackz314/speech-synthesizer/releases), extract it and run `ui.exe`, currently only Windows has pre-built releases.

### OS Support

Everything I used is cross-platform, this has been roughly tested on both Windows and Ubuntu 20.10, but it should also work on other platforms.

### Deployment

Deployment of this app is done with [PyInstaller](https://github.com/pyinstaller/pyinstaller), it freezes the app and its dependencies into one huge (due to dependency on large libraries) directory.

To deploy, install pyinstaller (`pip install pyinstaller`) and run:
```bash
pyinstaller ui.spec
```