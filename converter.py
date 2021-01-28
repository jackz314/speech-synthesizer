import concurrent
import os
import time
import shutil
from concurrent.futures.thread import ThreadPoolExecutor

from util import parse_lrc_time, parse_srt_time, get_cn_num, cn_sent_tokenize, process_cn_text, get_full_esp_model_tag, \
    get_full_vocoder_model_tag

import zmq

import locale
sys_lang = locale.getdefaultlocale()[0]
if "en" in sys_lang: sys_lang = "en"
else: sys_lang = "zh"
calibre_link = f"https://calibre-ebook.com{'' if sys_lang == 'en' else '/zh_CN'}/download"

DATA_DIR = "./synthesizer_data"
MODEL_DIR =DATA_DIR + "/models/"

class HandledException(Exception):
    pass

# noinspection PyAttributeOutsideInit
class Converter:
    def comm(self, cmd, msg=""):
        try:
            self.socket.send_string(cmd + "|" + msg, zmq.NOBLOCK)
        except zmq.error.Again:
            print("No subscriber. Send again later:", cmd, msg)

    def log(self, msg):
        self.comm("[log]", msg)

    def __init__(self, out_dir=".", out_name="out", comm=None, lang="zh", background=True):
        print("CONVERTER RUNNING!")
        self.custom_esp = None
        self.custom_vocoder = None
        self.tag = None
        self.vocoder_tag = None
        self.model_reload_needed = False
        self.socket = zmq.Context().socket(zmq.PUB)
        self.socket.bind("tcp://127.0.0.1:10290")
        self.socket.setsockopt(zmq.LINGER, 0)
        self.convert_executor = ThreadPoolExecutor(max_workers=1)
        if background: self.convert_executor.submit(self._initialize, out_dir, out_name, comm, lang)
        else: self._initialize(out_dir, out_name, comm, lang)
        # print("Converter exited init")

    def _initialize(self, out_dir, out_name, comm, lang):
        try:
            # self.comm = comm
            self.calibre_supported = shutil.which("ebook-convert") is not None
            self.txt = ""
            self.out_dir = out_dir
            self.out_name = out_name
            self.force_calibre = False
            self.autoDetectLang = True
            if lang:
                self.language = lang
                self.setup_model_config()
                self.setup_model()
            self.save_executor = ThreadPoolExecutor(max_workers=1)
            self.save_tasks = []
            self.output_status("Converter initialized.")
        except HandledException:
            raise
        except Exception as e:
            print("INIT ERROR:", e)
            self.output_err("Initialization error", e)

    def output_status(self, s: str, end="\n"):
        print(s, end=end)
        self.log(s + end)

    def use_calibre(self, file):
        if self.calibre_supported:
            self.comm("[download]", f"You need to install calibre to convert this type of file to text at {calibre_link}")
            return ""
        self.output_status("Converting file via Calibre...")
        calibre_cmd = 'ebook-convert "' + file + f'" "{self.out_dir}/calibre_convert_{self.out_name}.txt" --enable-heuristics --unsmarten-punctuation'
        self.output_status(calibre_cmd)
        import subprocess
        try:
            subprocess.check_call(calibre_cmd, shell=True)
        except subprocess.CalledProcessError as e:
            self.output_err("Calibre error", e)
            return ""
        with open(f'{self.out_dir}/calibre_convert_{self.out_name}.txt', encoding="utf-8", mode="r") as f:
            return f.read()

    def set_text_from_file(self, file):
        if self.force_calibre:
            self.txt = self.use_calibre(file)
        else:
            try:
                with open(file, encoding="utf-8", mode="r") as f:
                    self.txt = f.read()
            except UnicodeDecodeError: # non-binary
                self.txt = self.use_calibre(file)
        if not self.txt or self.txt.isspace():
            self.output_status(f"[ERROR] couldn't get any text from file {file}, make sure it's valid and supported by Calibre")
        else:
            self.comm("[file-content]", self.txt)

    def set_text(self, txt):
        if self.force_calibre:
            with open("/temp.txt", encoding="utf-8", mode="w") as tmp:
                tmp.write(txt)
            self.txt = self.use_calibre("/temp.txt")
            os.remove("/temp.txt")
        else: self.txt = txt

    def preprocess_text(self):
        import re
        self.txt = self.txt.strip().replace("\n\n","\n")
        self.txt = re.sub(r'\n+','\n\n',self.txt)

        if len(self.txt) == 0:
            self.output_status("Input is empty/invalid")
            return

        if self.autoDetectLang: self.detect_language(executor=False)

        self.output_status(f"Got text (characters: {len(self.txt)})")

    def set_language(self, lang, executor=True):
        if not self.language or self.language != lang:
            self.language = lang
            self.setup_model_config()
            # self.change_model(lang, executor=executor)

    def detect_language(self, executor=True):
        self.output_status("Detecting language...", end=" ")
        # from textblob import TextBlob

        # b = TextBlob(self.txt[:1000])
        # lang = b.detect_language()
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0 # enforcing consistent output
        lang = detect(self.txt[:1000])

        if "zh" in lang: lang = "zh"
        self.output_status("English" if lang == 'en' else "中文（普通话）")
        self.set_language(lang, executor)

    def set_custom_model(self, esp_tag=None, vocoder_tag=None):
        if esp_tag: self.custom_esp = esp_tag
        if vocoder_tag: self.custom_vocoder = vocoder_tag
        self.setup_model_config()
        print("Custom model set", self.tag, self.vocoder_tag, self.model_reload_needed)

    def change_model(self, lang=None, esp_tag=None, vocoder_tag=None, executor=True):
        self.output_status(f"Changing model: {lang} {esp_tag} {vocoder_tag}")
        if lang:
            self.language = lang
            self.sample_rate = 22050 if lang == 'en' else 24000
            if not esp_tag or not vocoder_tag:
                self.setup_model_config()
        elif esp_tag or vocoder_tag:
            if esp_tag == self.tag and vocoder_tag == self.vocoder_tag: return
            if esp_tag: self.tag = esp_tag
            if vocoder_tag: self.vocoder_tag = vocoder_tag
        else: return # nothing's changed
        if self.model_reload_needed:
            if executor: self.convert_executor.submit(self.setup_model)
            else: self.setup_model()

    def setup_model_config(self):
        old_tag = self.tag
        old_vocoder_tag = self.vocoder_tag
        self.sample_rate, self.lang, self.tag, self.vocoder_tag = None, None, None, None
        if self.language == 'en':
            ###################################
            #          ENGLISH MODELS         #
            ###################################
            self.sample_rate, self.lang = 22050, "English"
            corpus = "ljspeech"
            speech_model = "conformer_fastspeech2"
            # speech_model = "fastspeech2"
            # speech_model = "tacotron2"
            self.tag = "kan-bayashi/" + corpus + "_" + speech_model
            # tag = "kan-bayashi/ljspeech_tacotron2"
            # tag = "kan-bayashi/jsut_tacotron2"
            # tag = "kan-bayashi/ljspeech_fastspeech"
            # tag = "kan-bayashi/ljspeech_fastspeech2"
            # tag = "kan-bayashi/ljspeech_conformer_fastspeech2"

            self.vocoder_tag = "ljspeech_parallel_wavegan.v3"
            # vocoder_tag = "ljspeech_full_band_melgan.v2"
            # vocoder_tag = "ljspeech_multi_band_melgan.v2"
        elif 'zh' in self.language:
            self.language = 'zh'

            ###################################
            #         MANDARIN MODELS         #
            ###################################
            self.sample_rate, self.lang = 24000, "Mandarin"
            # tag = "kan-bayashi/csmsc_tacotron2"
            # tag = "kan-bayashi/csmsc_transformer"
            # tag = "kan-bayashi/csmsc_fastspeech"
            # tag = "kan-bayashi/csmsc_fastspeech2"
            self.tag = "kan-bayashi/csmsc_conformer_fastspeech2"
            self.vocoder_tag = "csmsc_parallel_wavegan.v1"
            # vocoder_tag = "csmsc_multi_band_melgan.v2"
        if self.custom_esp:
            self.tag = get_full_esp_model_tag(self.custom_esp, self.language)
        if self.custom_vocoder:
            self.vocoder_tag = get_full_vocoder_model_tag(self.custom_vocoder, self.language)
        if old_tag != self.tag or old_vocoder_tag != self.vocoder_tag:
            self.model_reload_needed = True

    def setup_model(self):
        try:
            self.model_reload_needed = False
            self.output_status("Loading nltk...")

            # setup nltk
            import nltk
            nltk.data.path.append(MODEL_DIR + '/nltk_models')
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt', download_dir=MODEL_DIR + "/nltk_models")

            self.output_status("Loading torch...", end=" ")

            # setup model
            import torch
            from espnet_model_zoo.downloader import ModelDownloader
            from espnet2.bin.tts_inference import Text2Speech
            from parallel_wavegan.utils import download_pretrained_model
            from parallel_wavegan.utils import load_model

            self.mlDevice = "cuda" if torch.cuda.is_available() else "cpu"
            self.output_status("Running on " + self.mlDevice)

            self.output_status("Loading espnet...")

            d = ModelDownloader(MODEL_DIR + "/espnet_models")
            self.text2speech = Text2Speech(
                **d.download_and_unpack(self.tag),
                device=self.mlDevice,
                # Only for Tacotron 2
                threshold=0.5,
                minlenratio=0.0,
                maxlenratio=10.0,
                use_att_constraint=False,
                backward_window=1,
                forward_window=3,
                # Only for FastSpeech & FastSpeech2
                speed_control_alpha=1.0,
            )
            self.text2speech.spc2wav = None  # Disable griffin-lim
            # NOTE: Sometimes download is failed due to "Permission denied". That is
            #   the limitation of google drive. Please retry after serveral hours.

            self.output_status("Loading vocoder models...")

            self.vocoder = load_model(download_pretrained_model(self.vocoder_tag, download_dir=MODEL_DIR + "/vocoder_models")).to(self.mlDevice).eval()
            self.vocoder.remove_weight_norm()
            self.output_status("Model setup completed.")
        except Exception as e:
            self.output_err("Model error", e)
            raise HandledException()

    def pre_convert(self):
        self.preprocess_text()
        if self.model_reload_needed: self.setup_model()
        if os.path.isfile(self.out_name + ".wav"): os.remove(self.out_name + ".wav")

    def save_wav(self, wav, overwrite=False):
        out_arr = wav.view(-1).cpu().numpy()
        fname = self.out_dir + "/" + self.out_name + ".wav"
        import soundfile
        from soundfile import SoundFile
        if overwrite:
            soundfile.write(fname, out_arr, samplerate=self.sample_rate, format="WAV")
        else:
            try:
                with SoundFile(fname, mode="r+") as wav_file:
                    wav_file.seek(0, soundfile.SEEK_END)
                    wav_file.write(out_arr)
            except Exception as e:
                soundfile.write(fname, out_arr, samplerate=self.sample_rate, format="WAV")
        # if self.mlDevice == "cuda":
        #     torch.cuda.empty_cache()

    def simple_convert(self, t):
        import torch
        with torch.no_grad():
            start = time.time()
            wav, c, *_ = self.text2speech(t)
            wav = self.vocoder.inference(c)
        rtf = (len(wav) / self.sample_rate) / (time.time() - start)
        self.output_status(f"Speed: {rtf:5f}x")
        # save_wav(wav, count)
        self.save_tasks.append(self.save_executor.submit(self.save_wav, wav))
        return len(wav)

    def _convert(self):
        try:
            self.pre_convert()
            txt = self.txt
            if len(txt) <= 30:
                if self.language == 'zh':
                    txt = process_cn_text(txt)
                self.simple_convert(txt)
            else:
                import re
                txt = txt.replace("\n", " ")
                if self.language == 'zh':
                    # txt = txt.replace(" ", "").replace("　", "")
                    txt = re.sub("\\s+", "", txt)
                    sentence_list = cn_sent_tokenize(txt)
                else:
                    from nltk import tokenize
                    sentence_list = tokenize.sent_tokenize(txt)

                # heavy dependency, might be more accurate, also supports more languages
                # import stanza
                # nlp = None
                # try:
                #     nlp = stanza.Pipeline(lang=language, processors='tokenize', dir=MODEL_DIR + "/stanza_models")
                # except:
                #     stanza.download(lang=language, dir=MODEL_DIR + "/stanza_models")
                #     nlp = stanza.Pipeline(lang=language, processors='tokenize', dir=MODEL_DIR + "/stanza_models")
                # doc = nlp(txt)
                # sentence_list = [s.text for s in doc.sentences]
                # end of stanza usage

                # if not os.path.exists(MODEL_DIR + "/tmp"): os.mkdir(MODEL_DIR + "/tmp")

                srt = ""
                lrc = ""
                srt_time = 0

                for i, t in enumerate(sentence_list, 1):
                    t_preview = t
                    self.output_status(
                        f"Converting part {i} out of {len(sentence_list)}: "
                        f"{t_preview if len(t) < 30 else (t_preview[:30] + f'... ({len(t)})')}", end=" ")
                    if self.language == "zh":
                        t = process_cn_text(t_preview)
                        t = get_cn_num(t)
                    else:
                        t = t_preview
                    l = 0
                    # try:
                    l = self.simple_convert(t)
                    # except Exception as e:
                        # self.output_status("\nError converting, retrying... " + str(e) + "\n")
                        # l = self.simple_convert(t[:len(t)//2]) + self.simple_convert(t[len(t)//2:])

                    srt += f"{i}\n{parse_srt_time(srt_time)} --> {parse_srt_time(srt_time + l / self.sample_rate)}\n{t_preview}\n\n"
                    lrc += f"[{parse_lrc_time(srt_time)}]{t_preview}\n"
                    srt_time += l / self.sample_rate
                self.output_status("Generating subtitles/lyrics file...")
                with open(f"{self.out_dir}/{self.out_name}.srt", encoding="utf-8", mode="w") as srt_file:
                    srt_file.write(srt)
                with open(f"{self.out_dir}/{self.out_name}.lrc", encoding="utf-8", mode="w") as lrc_file:
                    lrc_file.write(lrc)
                import concurrent.futures
                concurrent.futures.wait(self.save_tasks)
                self.save_tasks.clear()
            self.comm("[conversion-done]")
            self.output_status("Conversion done! Saved at " + os.path.abspath(f"{self.out_dir}/{self.out_name}.wav"))
        except Exception as e:
            self.output_err("Conversion error")

    def output_err(self, err_type, e):
        import traceback
        self.output_status(f"\n[ERROR]\n----------------------------------------\n{err_type}: " + str(e) + f"\n{''.join(traceback.format_exception(type(e),e, e.__traceback__))}----------------------------------------\n[END OF ERROR]")


    def convert(self, background=True):
        if background: self.convert_executor.submit(self._convert)
        else: self._convert()

    def __del__(self):
        if self.socket:
            self.socket.close()
        if self.convert_executor:
            self.convert_executor.shutdown(wait=False)
            # self.convert_executor._threads.clear()
        if self.save_executor:
            self.save_executor.shutdown(wait=False)
        #     self.save_executor._threads.clear()
        # from concurrent.futures import thread
        # concurrent.futures.thread._threads_queues.clear()

class ConverterController:
    def __init__(self, out_dir=".", out_name="out", lang="zh"):
        print("Starting converter controller")
        self.initialize(out_dir, out_name, lang)

    def initialize(self, out_dir=".", out_name="out", lang="zh"):
        self.converter = Converter(out_dir, out_name, None, lang)
        ctx = zmq.Context()
        socket = ctx.socket(zmq.SUB)
        # socket.getsockopt()
        self.socket = socket
        socket.connect("tcp://127.0.0.1:10289")
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.setsockopt(zmq.LINGER, 0)
        while True:
            msg = socket.recv_string()
            cmd, data = msg.split("|", maxsplit=1)
            # print("Got ui msg:", cmd, data)
            if cmd == "[convert]":
                if data == "":  # file
                    self.converter.convert()
                else:
                    self.converter.convert_executor.submit(self.converter.set_text, data)
                    self.converter.convert()
            elif cmd == "[file]":
                self.converter.convert_executor.submit(self.converter.set_text_from_file, data)
            elif cmd == "[lang]":
                if data:
                    self.converter.autoDetectLang = False
                    self.converter.set_language(data)
                else:
                    self.converter.autoDetectLang = True
            elif cmd == "[esp-model]":
                self.converter.set_custom_model(esp_tag=data)
            elif cmd == "[vocoder-model]":
                self.converter.set_custom_model(vocoder_tag=data)
            elif cmd == "[out-name]":
                self.converter.out_name = data
            elif cmd == "[out-dir]":
                self.converter.out_dir = data
            elif cmd == "[calibre]":
                self.converter.force_calibre = data == "1"
            elif cmd == "[exit]":
                print("Got exit signal from UI")
                return

    def __del__(self):
        if self.socket:
            self.socket.close()