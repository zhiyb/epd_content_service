#!/usr/bin/env python3
import os
import subprocess
import argparse
import math
import datetime
import json
import traceback
import png
import sched
import logging
import urllib
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from xml.dom import minidom

from config import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

retry_secs = 10


# HTTP connection

def http_req_json(url, data=None):
    logger = logging.getLogger("http")
    try:
        with urllib.request.urlopen(url, data=data) as f:
            resp = f.read()
            resp = json.loads(resp)
    except Exception as e:
        logger.warning("GET error: %s", e)
        return None
    return resp

def ddss_url(**kwargs):
    str_args = "&".join([f"{k}={urllib.parse.quote_plus(v)}" for k,v in kwargs.items()])
    url = f"{ddss_url_base}?{str_args}"
    return url

def ddss_get(binary=False, **kwargs):
    logger = logging.getLogger("ddss")
    url = ddss_url(**kwargs)
    logger.debug("GET: %s", url)
    try:
        with urllib.request.urlopen(url) as f:
            data = f.read()
            return data if binary else data.decode("utf8")
    except Exception as e:
        logger.warning("GET error: %s", e)
        return None

def ddss_post(data, binary=False, **kwargs):
    logger = logging.getLogger("ddss")
    url = ddss_url(**kwargs)
    logger.debug("POST: %s", url)
    try:
        with urllib.request.urlopen(url, data) as f:
            data = f.read()
            return data if binary else data.decode("utf8")
    except Exception as e:
        logger.warning("POST error: %s", e)
        return None


# Custom services

def update_bin_collection(s: sched.scheduler, parser_data):
    resp = http_req_json(bin_url)
    if (resp):
        parser_data['bin'] = resp['collections']
        logging.getLogger("bin_collections").info("Updated: %r", resp['collections'])
        s.enter(24 * 60 * 60, 0, update_bin_collection, (s, parser_data))
    else:
        logging.getLogger("bin_collections").info("Update failed")
        s.enter(retry_secs, 0, update_bin_collection, (s, parser_data))


# SVG template parser

def eval_text(text, parser_data):
    d = parser_data
    cfg = d["cfg"]
    tz = cfg.get("timezone", "UTC")

    def date(fmt='%Y-%m-%d', tz=tz):
        return datetime.now(ZoneInfo(tz)).strftime(fmt)
    def time(fmt='%H:%M', tz=tz):
        return date(fmt, tz)

    def bindate(clc):
        return datetime.fromisoformat(clc['date'][0:10]).strftime('%m-%d %A')
    def binweekday(clc):
        return datetime.fromisoformat(clc['date'][0:10]).weekday()
    def nextbin(tz=tz):
        now = datetime.now(ZoneInfo(tz))
        for clc in parser_data['bin']:
            date = datetime.fromisoformat(clc['date'][0:10]).astimezone(ZoneInfo(tz))
            days = math.ceil((date - now) / timedelta(days=1))
            if days >= 0:
                return clc, days
        return None, 0
    def nextbindays(tz=tz):
        clc, days = nextbin(tz)
        if clc == None:
            return '???'
        return days

    def sensor(name):
        return float("inf")

    try:
        val = eval(text)
    except Exception as e:
        logging.getLogger("eval").warning("Error parsing %s", text)
        traceback.print_exc()
        val = f"ERROR"
    logging.getLogger("eval").debug("%s -> %s", text, val)
    return val


def hide_group(e):
    while e:
        if e.nodeName == 'g':
            e.attributes['visibility'] = 'hidden'
            return
        e = e.parentNode

def replace_text(tnode, new_text):
    first = True
    for tspan in tnode.getElementsByTagName('tspan'):
        for text in tspan.childNodes:
            if text.nodeName == '#text':
                if first:
                    text.nodeValue = new_text
                else:
                    raise RuntimeError("TODO")

def eval_text_node(tnode, strings, parser_data):
    if strings[0].strip().startswith("="):
        text = "\n".join(strings).strip()[1:]
        val = eval_text(text, parser_data)
        if type(val) == bool:
            if not val:
                hide_group(tnode)
        else:
            val = str(val)
            replace_text(tnode, val)

def eval_cfg(tnode, strings, parser_data):
    if strings[0].strip() == "[cfg]":
        for s in strings[1:]:
            s = s.strip()
            if not s or s.startswith("#"):
                continue
            k,v = s.split("=", 2)
            parser_data["cfg"][k.strip()] = v.strip()
        logging.getLogger("eval").debug("cfg=%s", parser_data["cfg"])

def parse_text(src, func, args):
    for tnode in src.getElementsByTagName('text'):
        strings = []
        for tspan in tnode.getElementsByTagName('tspan'):
            for text in tspan.childNodes:
                if text.nodeName == '#text':
                    strings.append(text.nodeValue)
        if strings:
            func(tnode, strings, args)

def parse_template(src, parser_data):
    # Parse configs first
    parser_data["cfg"] = {}
    parse_text(src, eval_cfg, parser_data)
    # Now ready to parse text elements
    parse_text(src, eval_text_node, parser_data)
    return src


# Image data format converter

def read_img(fpath):
    with open(fpath, "rb") as f:
        reader = png.Reader(file=f)
        w,h,imgdata,pnginfo = reader.asRGBA8()
        imgdata = list(imgdata)
    return imgdata, pnginfo

def img_to_7c(disp, img):
    import conv
    pltdata,_ = read_img(disp["palette"])
    imgdata,pnginfo = read_img(img)
    return conv.img_to_7c(disp["w"], disp["h"], pltdata, pnginfo['planes'], imgdata)

def img_to_rwb(disp, img):
    import conv
    pltdata,_ = read_img(disp["palette"])
    imgdata,pnginfo = read_img(img)
    return conv.img_to_rwb(disp["w"], disp["h"], pltdata, pnginfo['planes'], imgdata)

def img_to_rwb4(disp, img):
    import conv
    pltdata,_ = read_img(disp["palette"])
    imgdata,pnginfo = read_img(img)
    return conv.img_to_rwb4(disp["w"], disp["h"], pltdata, pnginfo['planes'], imgdata)


# cron scheduling

def cron_schedule(s: sched.scheduler, token, tz, cron, func, args):
    # Add 1 minute delta so it won't immediately retrigger
    now = datetime.now(ZoneInfo(tz)) + timedelta(minutes=1)
    next = now
    m,h,dom,mon,dow = cron
    logger = logging.getLogger("cron")

    d = (60 - next.second) % 60
    next += timedelta(seconds=d)

    if m != "*":
        d = (60 + int(m) - next.minute) % 60
        next += timedelta(minutes=d)

    if h != "*":
        d = (24 + int(h) - next.hour) % 24
        next += timedelta(hours=d)

    if dow != "*":
        d = (7 + int(dow) - next.isoweekday()) % 7
        next += timedelta(days=d)

    if dom != "*":
        raise RuntimeError("TODO")

    if mon != "*":
        raise RuntimeError("TODO")

    delta = next - now
    logger.debug("tz=%s, cron=%r, now=%r, next=%r, delta=%r", tz, cron, now, next, delta)
    logger.info("%s after %d seconds", token, delta.total_seconds())
    if func:
        s.enter(math.ceil(delta.total_seconds()), 0, func, args)
    return next


# Clients

def update_display(s: sched.scheduler, token, template, template_ext, dtype, parser_data):
    parser_data["cfg"] = {}
    parser_data["cfg"]["token"] = token

    fpath = template
    ext = template_ext
    tmpdir = os.path.join(os.path.dirname(template), "..", "tmp")
    pltdir = os.path.join(os.path.dirname(template), "..", "palette")

    logger = logging.getLogger(token)
    logger.info("Template: %s, type: %s", template, dtype)

    # Parse display type
    disp = {}
    if dtype == "epd_5in65_7c_600x448":
        disp = {
            "w": 600, "h": 448,
            "type": "7c",
        }
        disp["palette"] = os.path.join(pltdir, f"{disp['type']}.png")

    elif dtype == "epd_4in2_rwb_400x300":
        disp = {
            "w": 400, "h": 300,
            "type": "rwb",
        }
        disp["palette"] = os.path.join(pltdir, f"{disp['type']}.png")

    elif dtype == "epd_2in13_rwb_122x250":
        disp = {
            "w": 128, "h": 250,
            "type": "rwb",
        }
        disp["palette"] = os.path.join(pltdir, f"{disp['type']}.png")

    elif dtype == "epd_7in5_rwb4_640x384":
        disp = {
            "w": 640, "h": 384,
            "type": "rwb4",
        }
        disp["palette"] = os.path.join(pltdir, f"rwb.png")

    else:
        raise RuntimeError(f"Unknown display type: {dtype}")


    if ext == ".svg":
        # Template -> SVG
        svgimg = os.path.join(tmpdir, f"{token}{ext}")
        #logger.info("SVG: %s", svgimg)
        doc = minidom.parse(fpath)
        doc = parse_template(doc, parser_data)
        xml = doc.toxml()
        with open(svgimg, 'w', encoding="utf8") as f:
            f.write(xml)
        ddss_post(xml.encode("utf8"), token=token, action="update", key="svg")
        logger.info("SVG: %s", ddss_url(token=token, action="peek", key="svg", mime="image/svg+xml"))
        fpath = svgimg

        # Extract SVG size
        svg = doc.getElementsByTagName("svg")[0]
        width = int(svg.attributes["width"].value)
        height = int(svg.attributes["height"].value)

        # SVG -> PNG
        ext = ".png"
        pngimg = os.path.join(tmpdir, f"{token}{ext}")
        cmd = ["rsvg-convert", fpath, "-a"]
        # zoom to fill
        if ((width / disp["w"]) <= (height / disp["h"])):
            cmd += ["-w", str(disp["w"])]
        else:
            cmd += ["-h", str(disp["h"])]
        cmd += ["-o", pngimg]
        logger.debug("exec: %s", " ".join(cmd))
        subprocess.run(cmd)
        with open(pngimg, "rb") as f:
            ddss_post(f.read(), token=token, action="update", key="png")
        logger.info("PNG: %s", ddss_url(token=token, action="peek", key="png", mime="image/png"))
        fpath = pngimg


    if ext == ".png":
        # PNG palette remap
        pngremapimg = os.path.join(tmpdir, f"{token}_remap{ext}")
        if 0:
            cmd = ["convert", pngimg, "-resize", f"{disp['w']}x{disp['h']}^",
                "-gravity", "center", "-extent", f"{disp['w']}x{disp['h']}",
                "-dither", "FloydSteinberg", "-remap", disp["palette"], pngremapimg]
        else:
            cmd = ["convert", pngimg, "-resize", f"{disp['w']}x{disp['h']}^",
                "-gravity", "center", "-extent", f"{disp['w']}x{disp['h']}",
                "-dither", "None", "-remap", disp["palette"], pngremapimg]
        logger.debug("exec: %s", " ".join(cmd))
        subprocess.run(cmd)
        with open(pngremapimg, "rb") as f:
            ddss_post(f.read(), token=token, action="update", key="png_remap")
        logger.info("PNG remap: %s", ddss_url(token=token, action="peek", key="png_remap", mime="image/png"))
        fpath = pngremapimg


    # Convert to EPD data format
    epd_data = None
    if disp["type"] == "7c":
        epd_data = img_to_7c(disp, fpath)
    elif disp["type"] == "rwb":
        epd_data = img_to_rwb(disp, fpath)
    elif disp["type"] == "rwb4":
        epd_data = img_to_rwb4(disp, fpath)
    else:
        logger.warning("Unknown display type: %s", disp["type"])
    if epd_data:
        ddss_post(epd_data, token=token, action="update")
        logger.info("DATA: %s", ddss_url(token=token, action="peek"))


    # Schedule next update
    cron = parser_data["cfg"].get("cron", None)
    if (cron):
        cron = cron.split()
        if (len(cron) != 5):
            logger.info("Invalid cron specification: %s", cron)
        else:
            next = cron_schedule(
                s, token, parser_data["cfg"].get("timezone", "UTC"), cron,
                update_display, (s, token, template, template_ext, dtype, parser_data))
            # Update downstream after a while
            next += timedelta(seconds=30)
            ddss_get(token=token, action="schedule",
                     ts=next.astimezone(timezone.utc).isoformat(timespec="seconds"))


def check_displays(s: sched.scheduler, parser_data):
    logger = logging.getLogger("check_displays")
    template_dir = "template"

    # Wait for other services to be ready first
    if "bin" not in parser_data:
        logger.warning("Not ready")
        s.enter(retry_secs, 0, check_displays, (s, parser_data))
        return

    found = False
    for fname in os.listdir(template_dir):
        token, ext = os.path.splitext(fname)
        if not ext:
            continue
        dtype = ddss_get(token=token, action="peek", key="type")
        if dtype:
            found = True
            s.enter(0, 0, update_display, (
                s, token, os.path.join(template_dir, fname), ext, dtype, parser_data))

    # If no valid template found, try again later
    if not found:
        logger.warning("No valid templates")
        s.enter(retry_secs, 0, check_displays, (s, parser_data))


def main():
    parser = argparse.ArgumentParser(
        prog = 'epd',
        description = 'ePaper display content service')
    args = parser.parse_args()

    # Build C Python extension
    if os.system("cc -O3 -fPIC -shared -I `echo /usr/include/python3.*` -o conv.so conv.c") != 0:
        raise RuntimeError("Failed to build conv.c")

    # Initial
    s = sched.scheduler()
    parser_data = {}
    update_bin_collection(s, parser_data)
    check_displays(s, parser_data)

    # Run scheduler
    s.run()


if __name__ == "__main__":
    main()
