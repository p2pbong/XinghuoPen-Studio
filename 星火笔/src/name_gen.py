# -*- coding: utf-8 -*-
"""本地随机中文姓名生成器（v0.47，借鉴 51mazi/好好码字/中文姓名生成器）。

纯本地、无 API：提供常见姓氏 + 男女/中性名用字库，可指定姓氏或随机、单字/双字名、
单性别或随机性别；种子可控（便于测试）。供角色页「随机名字」使用。
"""
import random

SURNAMES = [
    "李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱",
    "高", "林", "何", "郭", "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于",
    "董", "萧", "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕", "苏", "卢",
    "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎", "余", "潘", "杜", "戴", "夏", "钟",
    "汪", "田", "任", "姜", "范", "方", "石", "姚", "谭", "廖", "邹", "熊", "金", "陆",
    "郝", "孔", "白", "崔", "康", "毛", "邱", "秦", "江", "史", "顾", "侯", "邵", "孟",
    "龙", "万", "段", "雷", "钱", "汤", "尹", "黎", "易", "常", "武", "乔", "贺", "赖",
    "龚", "文", "秦", "沈",
]
CHAR_MALE = [
    "子", "毅", "司", "墨", "晏", "承", "策", "临", "川", "池", "瑾", "珩", "骁", "博",
    "远", "铭", "宸", "砚", "格", "睿", "桀", "烬", "野", "箫", "暮", "商", "云", "澜",
    "衍", "玦", "玄", "岳", "珩", "佑", "邺", "圣", "珩", "霆", "邺",
]
CHAR_FEMALE = [
    "瑶", "菀", "初", "绾", "知", "槿", "岚", "依依", "茕", "汐", "澈", "宁", "双", "黛",
    "桃", "柳", "雁", "芫", "茉", "蕊", "婧", "纨", "蕊", "妆", "黛", "芩", "荨",
]
CHAR_NEUTRAL = [
    "一", "之", "尘", "衍", "弈", "川", "阙", "洲", "野", "荀", "韦", "寒", "岚", "芃",
    "砚", "辰", "聿", "蘅", "艮", "殊", "苍", "元", "白", "砚", "苏",
]

_SINGLE_SUFFIX = ["予", "衍", "安", "华", "昭", "京", "衡", "笃"]


def generate_name(surname="", gender="random", two_chars=True, rng=None):
    """生成一个中文名。

    surname：指定姓氏；留空则随机。
    gender：random/male/female；决定用字倾向。
    two_chars：True 双字名（姓+2字），False 单字名（姓+1字）。
    rng：可注入 random.Random（测试用）；None 用全局 random。
    """
    r = rng or random
    fam = surname.strip() or r.choice(SURNAMES)
    pool = (CHAR_MALE if gender == "male"
            else CHAR_FEMALE if gender == "female"
            else r.choice([CHAR_MALE, CHAR_FEMALE, CHAR_NEUTRAL]))
    given = r.choice(pool)
    if two_chars:
        g2 = r.choice(pool)
        given = given + g2 if given != g2 else given + r.choice(_SINGLE_SUFFIX)
    return fam + given


def generate_names(n=8, gender="random", two_chars=True, rng=None):
    """批量生成 n 个不重复的名字。"""
    seen = set()
    out = []
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        nm = generate_name("", gender, two_chars, rng)
        if nm not in seen and nm not in out:
            seen.add(nm)
            out.append(nm)
    return out