#!/usr/bin/env python3
import sys
if len(sys.argv) < 2: exit(-1)
txt = ""
out_name = "final_out" if len(sys.argv) < 3 else sys.argv[2]

def use_calibre():
    import os
    calibre_cmd = 'ebook-convert "' + sys.argv[1] + f'" "./{out_name}.txt" --enable-heuristics --unsmarten-punctuation'
    print(calibre_cmd)
    os.system(calibre_cmd)
    with open(f'./{out_name}.txt', "r") as f:
        return f.read()

if len(sys.argv) > 3: # assume the thrid argument is calibre
    txt = use_calibre()
else:
    try:
        with open(sys.argv[1], encoding="utf-8", mode="r") as f:
            txt = f.read()
    except UnicodeDecodeError: # non-binary
        txt = use_calibre()

import re
txt = txt.strip().replace("\n\n","\n")
txt = re.sub(r'\n+','\n\n',txt)

if len(txt) == 0:
    print("Input is empty/invalid")
    exit(-2)

print(f"Got text (characters: {len(txt)})")

print("Detecting language...")

from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0 # enforcing consistent output
language = detect(txt[:1000])

sample_rate, lang, tag, vocoder_tag = None, None, None, None

if language == 'en':
    ###################################
    #          ENGLISH MODELS         #
    ###################################
    sample_rate, lang = 22050, "English"
    corpus = "ljspeech"
    # speech_model = "conformer_fastspeech2"
    # speech_model = "fastspeech2"
    speech_model = "tacotron2"
    tag = "kan-bayashi/" + corpus + "_" + speech_model
    # tag = "kan-bayashi/ljspeech_tacotron2"
    # tag = "kan-bayashi/jsut_tacotron2"
    # tag = "kan-bayashi/ljspeech_fastspeech"
    # tag = "kan-bayashi/ljspeech_fastspeech2"
    # tag = "kan-bayashi/ljspeech_conformer_fastspeech2"
    vocoder_tag = "ljspeech_parallel_wavegan.v3"
    # vocoder_tag = "ljspeech_full_band_melgan.v2"
    # vocoder_tag = "ljspeech_multi_band_melgan.v2"
elif 'zh' in language:
    language = 'zh'
    from num2chinese import num2chinese

    ###################################
    #         MANDARIN MODELS         #
    ###################################
    sample_rate, lang = 24000, "Mandarin"
    # tag = "kan-bayashi/csmsc_tacotron2"
    # tag = "kan-bayashi/csmsc_transformer"
    # tag = "kan-bayashi/csmsc_fastspeech"
    # tag = "kan-bayashi/csmsc_fastspeech2"
    tag = "kan-bayashi/csmsc_conformer_fastspeech2"
    vocoder_tag = "csmsc_parallel_wavegan.v1"
    # vocoder_tag = "csmsc_multi_band_melgan.v2"

print("Setting up model stuff...")

# setup nltk
import nltk
nltk.data.path.append('./nltk_models')
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', download_dir="./nltk_models")

# setup model
import time
import torch
from espnet_model_zoo.downloader import ModelDownloader
from espnet2.bin.tts_inference import Text2Speech
from parallel_wavegan.utils import download_pretrained_model
from parallel_wavegan.utils import load_model

mlDevice = "cuda" if torch.cuda.is_available() else "cpu"
print("Running on", mlDevice)

d = ModelDownloader("./espnet_models")
text2speech = Text2Speech(
    **d.download_and_unpack(tag),
    device=mlDevice,
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
text2speech.spc2wav = None  # Disable griffin-lim
# NOTE: Sometimes download is failed due to "Permission denied". That is 
#   the limitation of google drive. Please retry after serveral hours.
vocoder = load_model(download_pretrained_model(vocoder_tag, download_dir='./vocoder_models')).to(mlDevice).eval()
vocoder.remove_weight_norm()

import scipy.io.wavfile as wv
import os

if os.path.isfile(out_name + ".wav"): os.remove(out_name + ".wav")

from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)

def save_wav(wav, count=-1):
    # print("Outputing wav file...")
    out_arr = wav.view(-1).cpu().numpy()
    fname = out_name + ".wav"
    import soundfile
    from soundfile import SoundFile
    try:
        with SoundFile(fname, mode="r+") as wav_file:
            wav_file.seek(0, soundfile.SEEK_END)
            wav_file.write(out_arr)
    except Exception as e:
        soundfile.write(fname, out_arr, samplerate=sample_rate, format="WAV")
    # if count != -1: fname = f"./tmp/out{count}.wav"
    # wv.write(out_name + ".wav", sample_rate, out_arr)

def convert(t, count=-1):
    with torch.no_grad():
        start = time.time()
        wav, c, *_ = text2speech(t)
        wav = vocoder.inference(c)
    rtf = (len(wav) / sample_rate) / (time.time() - start)
    print(f"Speed: {rtf:5f}x")
    # save_wav(wav, count)
    executor.submit(save_wav, wav, count)
    return len(wav)

def parse_lrc_time(t):
    m, rem = divmod(t, 60)
    s = int(rem)
    ms = int(round(rem-s,2) * 100)
    return f"{m:02.0f}:{s:02}.{ms:02}"

def parse_srt_time(t):
    hr, rem = divmod(t, 3600)
    m, rem = divmod(rem, 60)
    s = int(rem)
    ms = int(round(rem-s,3) * 1000)
    return f"{hr:02.0f}:{m:02.0f}:{s:02},{ms:03}"

def get_cn_num(t):
    l = []
    num = ""
    for c in t:
        if c.isdigit(): num += c
        else: 
            if num != "":
                l.append(num2chinese(int(num)))
                num = ""
            l.append(c)
    if num != "":
        l.append(num2chinese(int(num)))
    return "".join(l)

def cn_sent_tokenize(s):
    # from https://blog.csdn.net/blmoistawinde/article/details/82379256
    import re
    s = re.sub('([。！？\?])([^”’])', r"\1\n\2", s.lstrip())  # 单字符断句符
    s = re.sub('(\.{6})([^”’])', r"\1\n\2", s)  # 英文省略号
    s = re.sub('(\…{2})([^”’])', r"\1\n\2", s)  # 中文省略号
    s = re.sub('([。！？\?][”’])([^，。！？\?])', r'\1\n\2', s)
    # 如果双引号前有终止符，那么双引号才是句子的终点，把分句符\n放到双引号后，注意前面的几句都小心保留了双引号
    s = s.rstrip()  # 段尾如果有多余的\n就去掉它
    # 很多规则中会考虑分号;，但是这里我把它忽略不计，破折号、英文双引号等同样忽略，需要的再做些简单调整即可。
    return s.split("\n")

def conv(txt, out_name):
    if len(txt) <= 30: convert(txt)
    else:
        txt = txt.replace("\n"," ")
        if language == 'zh':
            # txt = txt.replace(" ", "").replace("　", "")
            txt = re.sub("\s+", "", txt)
            sentence_list = cn_sent_tokenize(txt)
        else:
            from nltk import tokenize
            sentence_list = tokenize.sent_tokenize(txt)

        # heavy dependency, might be more accurate, also supports more languages
        # import stanza
        # nlp = None
        # try:
        #     nlp = stanza.Pipeline(lang=language, processors='tokenize', dir="./stanza_models")
        # except:
        #     stanza.download(lang=language, dir="./stanza_models")
        #     nlp = stanza.Pipeline(lang=language, processors='tokenize', dir="./stanza_models")
        # doc = nlp(txt)
        # sentence_list = [s.text for s in doc.sentences]
        # end of stanza usage

        # if not os.path.exists("./tmp"): os.mkdir("./tmp")

        srt = ""
        lrc = ""
        srt_time = 0

        for i, t in enumerate(sentence_list, 1):
            t_preview = t
            print(f"Converting part {i} out of {len(sentence_list)}: {t_preview if len(t) < 50 else (t_preview[:50] + f'... ({len(t)})')}", end = " ")
            if language == "zh": 
                t = t_preview.replace("、","，").replace("“",'').replace("”",'').replace("‘","").replace("’","").replace("（","").replace("）","")
                t = get_cn_num(t)
            else: t = t_preview
            l = convert(t,i)
            srt += f"{i}\n{parse_srt_time(srt_time)} --> {parse_srt_time(srt_time + l / sample_rate)}\n{t_preview}\n\n"
            lrc += f"[{parse_lrc_time(srt_time)}]{t_preview}\n"
            srt_time += l / sample_rate
        executor.shutdown(wait=True)
        print("Generating subtitles/lyrics file...")
        with open(f"{out_name}.srt", encoding="utf-8", mode="w") as srt_file:
            srt_file.write(srt)
        with open(f"{out_name}.lrc", encoding="utf-8", mode="w") as lrc_file:
            lrc_file.write(lrc)

print("Converting...")
conv(txt, out_name)
print("Done!")
