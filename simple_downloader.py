# install pip dependencies
import subprocess
import sys

pkgs = ["nltk", "gdown"]


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


for pkg in pkgs: install(pkg)

import hashlib
from pathlib import Path
import zipfile
import tarfile
from urllib.request import urlretrieve
import re

import nltk
import gdown

out_base = "./synthesizer_data"
out_base_path = Path(out_base)
out_base_path.mkdir(exist_ok=True)
esp_path = (out_base_path / "models/espnet_models")
esp_path.mkdir(parents=True, exist_ok=True)
voc_path = (out_base_path / "models/vocoder_models")
voc_path.mkdir(parents=True, exist_ok=True)
nltk_path = (out_base_path / "models/nltk_models")
nltk_path.mkdir(parents=True, exist_ok=True)

esp_urls = [
    "https://zenodo.org/record/4031955/files/tts_train_conformer_fastspeech2_raw_phn_pypinyin_g2p_phone_train.loss.ave.zip?download=1",
]

vocoder_tags = [
    "csmsc_multi_band_melgan.v2",
]

nltk_models = [
    "punkt",
]

VOCODER_PRETRAINED_MODEL_LIST = {
    "ljspeech_parallel_wavegan.v1": "1PdZv37JhAQH6AwNh31QlqruqrvjTBq7U",
    "ljspeech_parallel_wavegan.v1.long": "1A9TsrD9fHxFviJVFjCk5W6lkzWXwhftv",
    "ljspeech_parallel_wavegan.v1.no_limit": "1CdWKSiKoFNPZyF1lo7Dsj6cPKmfLJe72",
    "ljspeech_parallel_wavegan.v3": "1-oZpwpWZMMolDYsCqeL12dFkXSBD9VBq",
    "ljspeech_full_band_melgan.v2": "1Kb7q5zBeQ30Wsnma0X23G08zvgDG5oen",
    "ljspeech_multi_band_melgan.v2": "1b70pJefKI8DhGYz4SxbEHpxm92tj1_qC",
    "jsut_parallel_wavegan.v1": "1qok91A6wuubuz4be-P9R2zKhNmQXG0VQ",
    "jsut_multi_band_melgan.v2": "1chTt-76q2p69WPpZ1t1tt8szcM96IKad",
    "csmsc_parallel_wavegan.v1": "1QTOAokhD5dtRnqlMPTXTW91-CG7jf74e",
    "csmsc_multi_band_melgan.v2": "1G6trTmt0Szq-jWv2QDhqglMdWqQxiXQT",
    "arctic_slt_parallel_wavegan.v1": "1_MXePg40-7DTjD0CDVzyduwQuW_O9aA1",
    "jnas_parallel_wavegan.v1": "1D2TgvO206ixdLI90IqG787V6ySoXLsV_",
    "vctk_parallel_wavegan.v1": "1bqEFLgAroDcgUy5ZFP4g2O2MwcwWLEca",
    "vctk_parallel_wavegan.v1.long": "1tO4-mFrZ3aVYotgg7M519oobYkD4O_0-",
    "vctk_multi_band_melgan.v2": "10PRQpHMFPE7RjF-MHYqvupK9S0xwBlJ_",
    "libritts_parallel_wavegan.v1": "1zHQl8kUYEuZ_i1qEFU6g2MEu99k3sHmR",
    "libritts_parallel_wavegan.v1.long": "1b9zyBYGCCaJu0TIus5GXoMF8M3YEbqOw",
    "libritts_multi_band_melgan.v2": "1kIDSBjrQvAsRewHPiFwBZ3FDelTWMp64",
}


def download_and_unpack_esp(url):
    ma = re.match(r"https://.*/([^/]*)\?download=[0-9]*$", url)
    if not ma: return
    fname = ma.groups()[0]
    outdir = esp_path / hashlib.md5(str(url).encode("utf-8")).hexdigest()
    outdir.mkdir()
    with (outdir / "url").open("w", encoding="utf-8") as f:
        f.write(url)
    urlretrieve(url, outdir / fname)  # download
    with zipfile.ZipFile(outdir / fname, 'r') as zip_ref:
        zip_ref.extractall(outdir)


def download_and_unpack_voc(tag):
    id = VOCODER_PRETRAINED_MODEL_LIST[tag]
    outfile = voc_path / f"{tag}.tar.gz"
    gdown.download(f"https://drive.google.com/uc?id={id}", str(outfile), quiet=True)
    tar = tarfile.open(outfile, "r:gz")
    tar.extractall(path=voc_path / tag)
    tar.close()


print("Downloading ESP...")
for url in esp_urls: download_and_unpack_esp(url)
print("Downloading Vocoder...")
for tag in vocoder_tags: download_and_unpack_voc(tag)
print("Downloading NLTK...")
for model in nltk_models: nltk.download(model, download_dir=nltk_path, quiet=True)
