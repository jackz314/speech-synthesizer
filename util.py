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


def replace_with_cn_num(s):
    from num2chinese import num2chinese
    import re
    def replace_fn(match):
        return num2chinese(match.group(0))
    return re.sub(r"[+-]?\d+\.?[\d]*", replace_fn, s)


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

def cn_spell_out_unit(s):
    import re

    def replace_units(match):
        unit = match.group(2).lower()
        if unit == "m": unit="米"
        elif unit == "v": unit="伏"
        elif unit == "s": unit="秒"
        elif unit == "h": unit="小时"
        elif unit == "g": unit="克"
        elif unit == "w": unit="瓦"
        elif unit == "a": unit="安"
        elif unit == "pa": unit="帕"
        else: return match.group(0)

        return match.group(1) + unit

    s = re.sub(r"([+-]?\d+\.?\d*)([a-z]{1,4})", replace_units, s, flags=re.IGNORECASE)

    s = re.sub("kpa", "千帕", s, flags=re.IGNORECASE)
    s = re.sub("kg", "千克", s, flags=re.IGNORECASE)
    s = re.sub("km", "千米", s, flags=re.IGNORECASE)
    s = re.sub("kw", "千瓦", s, flags=re.IGNORECASE)
    s = re.sub("kv", "千伏", s, flags=re.IGNORECASE)
    s = re.sub("cm", "厘米", s, flags=re.IGNORECASE)
    s = re.sub("mm", "毫米", s, flags=re.IGNORECASE)
    s = re.sub("mg", "毫克", s, flags=re.IGNORECASE)
    s = re.sub("ma", "毫安", s, flags=re.IGNORECASE)
    s = re.sub("mah", "毫安时", s, flags=re.IGNORECASE)
    s = re.sub("kwh", "千瓦时", s, flags=re.IGNORECASE)
    s = re.sub("mmhg", "毫米汞柱", s, flags=re.IGNORECASE)

    def replace_yuan(match):
        return match.group(0)[1:] + "元"

    s = re.sub(r"¥[+-]?\d+\.?\d*", replace_yuan, s, flags=re.IGNORECASE)
    return s.replace("℃", "摄氏度").replace("¥", "元")

def preprocess_cn_text(s):
    import re
    def replace_fn(match):
        return "百分之" + match.group(0)[:-1]

    s = re.sub(r"[+-]?\d+\.?\d*%", replace_fn, s)

    s = cn_spell_out_unit(s)

    return s.replace("、", "，").replace("：", "，").replace("；", "，").replace("．", "，").replace("“", '')\
        .replace("”", '').replace("‘", "").replace("’", "").replace("（", "，").replace("）", "，")\
        .replace("(", "，").replace(")", "，").replace("＞", "大于").replace("＜", "小于").replace("~", "至")

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

def uncircle(s):
    for i in range(1, 21):
        s = s.replace(chr(0x245f + i), str(i))
    return s.replace('\u24ea', '0')

def general_preprocess(txt):
    return uncircle(txt)