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
    from num2chinese import num2chinese
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

def process_cn_text(s):
    return s.replace("、", "，").replace("“", '').replace("”", '').replace("‘", "") \
        .replace("’", "").replace("（", "").replace("）", "")

def get_full_esp_model_tag(tag, lang):
    if lang == "en":
        corpus = "ljspeech"
    else:
        corpus = "csmsc"
    return "kan-bayashi/" + corpus + "_" + tag

def get_full_vocoder_model_tag(tag, lang):
    if lang == "en":
        corpus = "ljspeech"
        if "wavegan" in tag: version = "v3"
        else: version = "v2"
    else:
        corpus = "csmsc"
        if "wavegan" in tag: version = "v1"
        else:
            if "full_band_melgan" == tag: tag = "multi_band_melgan"
            version = "v2"
    return corpus + "_" + tag + "." + version