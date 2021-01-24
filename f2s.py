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
        with open(sys.argv[1], "r") as f:
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

print("Setting up model stuff...")

from textblob import TextBlob

b = TextBlob(txt[:5000])
language = b.detect_language()

fs, lang, tag, vocoder_tag = None, None, None, None

if language == 'en':
    ###################################
    #          ENGLISH MODELS         #
    ###################################
    fs, lang = 22050, "English"
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
    fs, lang = 24000, "Mandarin"
    # tag = "kan-bayashi/csmsc_tacotron2"
    # tag = "kan-bayashi/csmsc_transformer"
    # tag = "kan-bayashi/csmsc_fastspeech"
    # tag = "kan-bayashi/csmsc_fastspeech2"
    tag = "kan-bayashi/csmsc_conformer_fastspeech2"
    vocoder_tag = "csmsc_parallel_wavegan.v1"
    # vocoder_tag = "csmsc_multi_band_melgan.v2"

# setup model
import time
import torch
from espnet_model_zoo.downloader import ModelDownloader
from espnet2.bin.tts_inference import Text2Speech
from parallel_wavegan.utils import download_pretrained_model
from parallel_wavegan.utils import load_model
d = ModelDownloader()
text2speech = Text2Speech(
    **d.download_and_unpack(tag),
    device="cuda",
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
vocoder = load_model(download_pretrained_model(vocoder_tag, download_dir='./models')).to("cuda").eval()
vocoder.remove_weight_norm()

import scipy.io.wavfile as wv

from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)

def save_wav(wav, count=-1):
    # print("Outputing wav file...")
    out_arr = wav.view(-1).cpu().numpy()
    fname = None
    if count != -1: fname = f"./tmp/out{count}.wav"
    else: fname = out_name+".wav"
    wv.write(fname, fs, out_arr)

def convert(t, count=-1):
    with torch.no_grad():
        start = time.time()
        wav, c, *_ = text2speech(t)
        wav = vocoder.inference(c)
    rtf = (len(wav) / fs) / (time.time() - start)
    print(f"Speed: {rtf:5f}x")
    # save_wav(wav, count)
    executor.submit(save_wav, wav, count)
    return len(wav)

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

def conv(txt, out_name):
    if len(txt) <= 30: convert(txt)
    else:
        srt = ""
        srt_time = 0
        # import nltk
        # from nltk import tokenize
        # try:
        #     nltk.data.find('tokenizers/punkt')
        # except LookupError:
        #     nltk.download('punkt')
        # sentence_list = tokenize.sent_tokenize(txt)

        import stanza
        nlp = stanza.Pipeline(lang=language, processors='tokenize')
        doc = nlp(txt)
        sentence_list = [s.text for s in doc.sentences]

        import os
        if not os.path.exists("./tmp"): os.mkdir("./tmp")

        sox_cmd = "sox "
        for i, t in enumerate(sentence_list, 1):
            t_preview = t.replace("\n"," ")
            print(f"Converting part {i} out of {len(sentence_list)}: {t_preview if len(t) < 50 else (t_preview[:50] + f'... ({len(t)})')}", end = " ")
            if language == "zh": 
                t = t_preview.replace("、","，").replace("“",'').replace("”",'').replace("‘","").replace("’","").replace("（","").replace("）","").replace(" ", "")
                t = get_cn_num(t)
            else: t = t_preview
            l = convert(t,i)
            srt += f"{i}\n{parse_srt_time(srt_time)} --> {parse_srt_time(srt_time+l/fs)}\n{t_preview}\n\n"
            srt_time += l/fs
            sox_cmd += "./tmp/out" + str(i) + ".wav "
        executor.shutdown(wait=True)
        print("Combining final output wav...")
        sox_cmd += f"{out_name}.wav"
        os.system(sox_cmd)
        os.system("rm -rf ./tmp")
        # os.system("rm " + sox_cmd[4:sox_cmd.index(out_name)])
        with open(f"{out_name}.srt","w") as srt_file:
            srt_file.write(srt)

print("Converting...")
conv(txt, out_name)
