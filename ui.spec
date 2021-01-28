# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import langdetect
langdetect_path = langdetect.__path__[0]

import espnet
esp_path = espnet.__path__[0]

import librosa
librosa_path = librosa.__path__[0]

a = Analysis(['ui.py'],
             pathex=['C:\\Users\\zhang\\OneDrive\\Desktop\\Projects\\ML\\file-to-speech'],
             binaries=[],
             datas=[('./synthesizer_data', 'synthesizer_data'),
             (langdetect_path + '/utils', 'langdetect/utils'),  # for messages.properties file
             (langdetect_path + '/profiles', 'langdetect/profiles'), # don't forget if you load langdetect as a submodule of your app, change the second string to the relative path from your parent module. The first argument is the relative path inside the pyinstaller bundle.
             (esp_path + "/version.txt", 'espnet'),
             (librosa_path + "/util/example_data", "librosa/util/example_data")
                ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='ui',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          icon='synthesizer_data/resources/speech_synthesizer.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='ui')
