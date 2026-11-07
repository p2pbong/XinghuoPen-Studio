# -*- coding: utf-8 -*-
"""导出工具：统一导出位置（项目根目录下的 output/），按项目名分目录归类。"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_ROOT, "output")


def _safe_name(name):
    """去掉 Windows 文件名非法字符，空名兜底。"""
    safe = "".join(c for c in (name or "") if c not in '\\/:*?"<>|').strip()
    return safe or "未命名"


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def project_output_dir(title):
    """每个项目的导出专属目录：output/<项目名>/（同名项目自动合并）。"""
    d = os.path.join(ensure_output_dir(), _safe_name(title))
    os.makedirs(d, exist_ok=True)
    return d


def default_novel_path(title):
    """小说导出默认路径：output/<项目名>/<项目名>.txt"""
    safe = _safe_name(title)
    return os.path.join(project_output_dir(safe), safe + ".txt")


def default_cards_dir(title):
    """角色卡导出默认目录：output/<项目名>/角色卡/"""
    d = os.path.join(project_output_dir(title), "角色卡")
    os.makedirs(d, exist_ok=True)
    return d


def default_project_zip_path(title):
    """项目包导出默认路径：output/<项目名>/<项目名>.zip"""
    safe = _safe_name(title)
    return os.path.join(project_output_dir(safe), safe + ".zip")


def default_epub_path(title):
    """EPUB 电子书导出默认路径：output/<项目名>/<项目名>.epub"""
    safe = _safe_name(title)
    return os.path.join(project_output_dir(safe), safe + ".epub")


def export_novel_epub(project, store, out_path):
    """导出 EPUB3 电子书（纯 Python 标准库实现，无第三方依赖）。

    结构：mimetype（必须 ZIP_STORED 且为压缩包首文件）/ META-INF/container.xml /
    OEBPS/content.opf / OEBPS/nav.xhtml（EPUB3 导航）+ toc.ncx（EPUB2 兜底）/
    OEBPS/style.css / OEBPS/title.xhtml（书名+故事设定封面页）/ OEBPS/chapNNNN.xhtml 每章。

    返回是否成功（无已写章节返回 False）。
    """
    import html as _html
    import time as _time
    import uuid as _uuid
    import zipfile

    indices = sorted(store.list_chapter_indices())
    if not indices:
        return False
    uid = "urn:uuid:%s" % _uuid.uuid4()
    modified = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())

    def _xhtml(title, body_parts):
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="zh-CN" lang="zh-CN">\n<head>\n'
            '<meta charset="utf-8"/>\n<title>%s</title>\n'
            '<link rel="stylesheet" type="text/css" href="style.css"/>\n</head>\n<body>\n%s\n</body>\n</html>'
            % (_html.escape(title), "\n".join(body_parts)))

    # ---- 组装各文件内容 ----
    # 封面页 = 书名 + 可选的故事设定摘要
    brief_parts = []
    if (project.story_brief or "").strip():
        brief_parts.append('<h2>故事设定</h2><div class="brief">%s</div>'
                           % _html.escape(project.story_brief.strip()))
    if (project.story_world or "").strip():
        brief_parts.append('<h2>世界观</h2><div class="brief">%s</div>'
                           % _html.escape(project.story_world.strip()))
    title_xhtml = _xhtml(project.title, [
        "<h1>%s</h1>" % _html.escape(project.title),
        '<p class="meta">AI 小说写作室 · 星火笔 导出</p>',
    ] + brief_parts)

    chap_items = []       # (id, href, label)
    chap_xhtmls = {}      # href -> 内容
    last_vol = None
    vol_no = 0
    for i, ch_no in enumerate(indices, 1):
        ch = store.load_chapter(ch_no)
        if not ch:
            continue
        # v0.51 分卷：卷变化时插入卷标题页（自动进入目录/spine/nav）
        vol = int(getattr(ch, "volume", 1) or 1)
        if vol != last_vol:
            last_vol = vol
            vol_no += 1
            vhref = "vol%04d.xhtml" % vol_no
            chap_items.append(("vol%d" % vol_no, vhref, "第%d卷" % vol))
            chap_xhtmls[vhref] = _xhtml("第%d卷" % vol,
                                        ["<h1>第%d卷</h1>" % vol])
        href = "chap%04d.xhtml" % i
        chap_items.append(("chap%d" % i, href, ch.title or "第%d章" % ch_no))
        paras = []
        for para in (ch.content or "").split("\n"):
            p = para.strip()
            if p:
                paras.append("<p>%s</p>" % _html.escape(p))
            else:
                paras.append('<p class="blank">&nbsp;</p>')
        chap_xhtmls[href] = _xhtml(ch.title or "第%d章" % ch_no,
                                   ["<h1>%s</h1>" % _html.escape(ch.title or "第%d章" % ch_no)] + paras)

    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="style.css" media-type="text/css"/>',
                '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>']
    spine = ['<itemref idref="title"/>']
    nav_ol = ['<li><a href="title.xhtml">%s</a></li>' % _html.escape(project.title)]
    ncx_navpoints = ['<navPoint id="nav_title" playOrder="1"><navLabel><text>%s</text></navLabel>'
                     '<content src="title.xhtml"/></navPoint>' % _html.escape(project.title)]
    play = 2
    for cid, href, label in chap_items:
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (cid, href))
        spine.append('<itemref idref="%s"/>' % cid)
        nav_ol.append('<li><a href="%s">%s</a></li>' % (href, _html.escape(label)))
        ncx_navpoints.append(
            '<navPoint id="%s" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>' % (cid, play, _html.escape(label), href))
        play += 1

    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '<dc:identifier id="bookid">%s</dc:identifier>\n'
        '<dc:title>%s</dc:title>\n'
        '<dc:language>zh-CN</dc:language>\n'
        '<dc:creator>星火笔</dc:creator>\n'
        '<meta property="dcterms:modified">%s</meta>\n'
        '</metadata>\n'
        '<manifest>\n%s\n</manifest>\n'
        '<spine>\n%s\n</spine>\n'
        '</package>\n' % (uid, _html.escape(project.title), modified,
                          "\n".join(manifest), "\n".join(spine)))

    nav_xhtml = _xhtml("目录", [
        '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>%s</ol></nav>' % "\n".join(nav_ol)])

    toc_ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '<head>\n<meta name="dtb:uid" content="%s"/>\n'
        '<meta name="dtb:depth" content="1"/>\n'
        '<meta name="dtb:totalPageCount" content="0"/>\n'
        '<meta name="dtb:maxPageNumber" content="0"/>\n</head>\n'
        '<docTitle><text>%s</text></docTitle>\n'
        '<navMap>\n%s\n</navMap>\n</ncx>\n'
        % (uid, _html.escape(project.title), "\n".join(ncx_navpoints)))

    style_css = (
        "body { font-family: serif; line-height: 1.8; margin: 1em; }\n"
        "h1 { font-size: 1.5em; text-align: center; margin: 1em 0; }\n"
        "h2 { font-size: 1.2em; }\n"
        "p { text-indent: 2em; margin: 0.4em 0; }\n"
        "p.blank { text-indent: 0; }\n"
        "p.meta, .brief { color: #555; }\n")

    # ---- 写 zip（mimetype 必须无压缩且为第一个文件，EPUB 规范硬性要求） ----
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                        compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles>\n'
                '</container>\n'))
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
            zf.writestr("OEBPS/toc.ncx", toc_ncx)
            zf.writestr("OEBPS/style.css", style_css)
            zf.writestr("OEBPS/title.xhtml", title_xhtml)
            for href, body in chap_xhtmls.items():
                zf.writestr("OEBPS/" + href, body)
    except OSError:
        return False
    return True