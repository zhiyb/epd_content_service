#!/usr/bin/env python3
import os, io, subprocess
import datetime, time
import psutil
import json
import traceback
import png
import schedule
import pytz
from datetime import datetime
from pytz import timezone
from uuid import UUID
from urllib import request, parse
from xml.dom import minidom

from config import *

parser_data = {}

def http_req(url, data = None):
    try:
        req = request.Request(url, data = data)
        resp = request.urlopen(req).read()
        resp = json.loads(resp)
    except:
        print("Error:", url, type(data))
        traceback.print_exc()
        return None
    return resp

def parse_str(src, parser_data):
    def date(tz = pytz.utc, fmt = '%Y-%m-%d'):
        return datetime.now(timezone(tz)).strftime(fmt)
    def time(tz = pytz.utc, fmt = '%H:%M'):
        return date(tz, fmt)

    if src.startswith('='):
        try:
            d = parser_data
            out = eval(src[1:])
        except:
            traceback.print_exc()
            out = 'except!'
        return out
    return src

def parse_template(src, parser_data):
    for tspan in src.getElementsByTagName('tspan'):
        for text in tspan.childNodes:
            if text.nodeName == '#text':
                text.nodeValue = parse_str(text.nodeValue, parser_data)
    return src

def update_img(uuid, info, parser_data):
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template',
                            f"{info['type']}_{str(uuid)}.svg")
    svgimg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'svg',
                          f"{info['type']}_{str(uuid)}.svg")
    pngimg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'png',
                          f"{info['type']}_{str(uuid)}.png")

    # Template -> SVG
    doc = minidom.parse(template)
    doc = parse_template(doc, parser_data)
    with open(svgimg, 'w') as f:
        doc.writexml(f)

    # SVG -> PNG
    subprocess.run(["convert", svgimg, "-resize", f"{info['w']}x{info['h']}", pngimg])

    # Read final PNG
    with open(pngimg, 'rb') as f:
        png_data = f.read()
        f.seek(0)
        reader = png.Reader(file=f)
        w,h,imgdata,pnginfo = reader.read()
        imgdata = list(imgdata)
    img = []
    for y in range(h):
        row = []
        for x in range(w):
            ofs = x * pnginfo['planes']
            row.append(imgdata[y][ofs : ofs+pnginfo['planes']])
        img.append(row)
    return img, png_data

def img_to_rwb(img):
    data_bw = bytearray()
    data_r = bytearray()
    for y in range(len(img)):
        v_bw = 0
        v_r = 0
        for x in range(len(img[0])):
            r,g,b = img[y][x][0:3]

            if b >= 0x80:
                v_bw |= 1
            if x % 8 == 7:
                data_bw.append(v_bw)
                v_bw = 0
            v_bw <<= 1

            if b >= r:
                v_r |= 1
            if x % 8 == 7:
                data_r.append(v_r)
                v_r = 0
            v_r <<= 1

    return data_bw + data_r

def update_displays():
    for u in uuid_list:
        uuid = UUID(u)
        info = http_req(f"{url_base}?info={str(uuid)}")
        if info == None:
            continue

        try:
            img, png_data = update_img(uuid, info, parser_data)
        except:
            raise
            continue

        if info['c'] == 'rwb':
            data = img_to_rwb(img)
            http_req(f"{url_base}?upd={str(uuid)}", data)

        http_req(f"{url_base}?thumb={str(uuid)}", png_data)

def update_bin_collection():
    resp = http_req(bin_url)
    if (resp == None):
        return
    collection = resp['collections'][0]
    parser_data['bin'] = collection

# Initial
update_bin_collection()
update_displays()

# Scheduling
schedule.every(bin_update_min).minutes.do(update_bin_collection)
schedule.every(display_update_min).minutes.do(update_displays)

# Run scheduler
while True:
    schedule.run_pending()
    time.sleep(scheduler_period_sec)
