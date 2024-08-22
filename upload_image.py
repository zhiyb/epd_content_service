#!/usr/bin/env python3
import os
import subprocess
import argparse
import logging
from datetime import datetime, timedelta, timezone

from main import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG)

def main():
    parser = argparse.ArgumentParser(
        prog = 'epd',
        description = 'ePaper display content service')
    parser.add_argument("--build")
    parser.add_argument("--dither", default="FloydSteinberg")
    parser.add_argument("token")
    parser.add_argument("type")
    parser.add_argument("image")
    args = parser.parse_args()

    token = args.token
    image = os.path.abspath(args.image)
    root_dir = os.path.dirname(__file__)
    logger = logging.getLogger(token)
    logger.setLevel(logging.DEBUG)

    if args.build:
        # Build C Python extension
        if os.system("cc -O3 -fPIC -shared -I `echo /usr/include/python3.*` -o conv.so conv.c") != 0:
            raise RuntimeError("Failed to build conv.c")

    # Set display type
    disp = parse_disp_type(args.type)
    ddss_post(args.type.encode("utf8"), token=token, action="update", key="type")

    # Convert image format and zoom to fit
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    image_png_remap = os.path.join(tmp_dir, f"{token}.png")
    cmd = ["convert", image, "-auto-orient", "-resize", f"{disp['w']}x{disp['h']}^",
        "-gravity", "center", "-extent", f"{disp['w']}x{disp['h']}",
        "-dither", args.dither, "-remap", disp["palette"], image_png_remap]
    logger.debug("exec: %s", " ".join(cmd))
    subprocess.run(cmd)
    with open(image_png_remap, "rb") as f:
        ddss_post(f.read(), token=token, action="update", key="png_remap")
    logger.info("PNG remap: %s", ddss_url(token=token, action="peek", key="png_remap", mime="image/png"))

    # Convert to EPD format and upload to DDSS
    epd_data = conv_epd_image(disp, image_png_remap)
    if epd_data:
        ddss_post(epd_data, token=token, action="update")
        logger.info("DATA: %s", ddss_url(token=token, action="peek"))

    # Update scheduling, set update far in the future
    next = datetime.now(timezone.utc) + timedelta(weeks=520)
    ddss_get(token=token, action="schedule",
             ts=next.astimezone(timezone.utc).isoformat(timespec="seconds"))

if __name__ == "__main__":
    main()
