#!/usr/bin/env python3
"""Render a framework demo HTML to MP4 (+ optional GIF) by stepping the animation
headlessly and stitching the frames with ffmpeg.

  python scripts/demo_to_video.py demos/framework_nces.html -o demos/nces \
      [--frames 160] [--fps 30] [--gif] [--gif-width 1100] [--scale 1.5]

Requires playwright chromium (already installed) + its bundled ffmpeg.
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

def _find_ffmpeg():
    # prefer a full-featured ffmpeg (imageio-ffmpeg bundles one with libx264 + gif);
    # the Playwright build only has VP8/WebM.
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg") or (
        glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux")) or [None])[0]


FFMPEG = _find_ffmpeg()
if not FFMPEG:
    sys.exit("ffmpeg not found (pip install imageio-ffmpeg)")


def capture(html, frames_dir, n_frames, scale):
    errs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--force-color-profile=srgb"])
        pg = b.new_page(device_scale_factor=scale)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("file://" + os.path.abspath(html))
        pg.wait_for_function("window.__seek !== undefined")
        # size viewport to the scene so nothing needs scrolling
        sz = pg.evaluate("window.__sceneSize()")
        pg.evaluate("document.getElementById('ctl').style.display='none'")
        pg.set_viewport_size({"width": min(int(sz["w"]) + 30, 2600),
                              "height": max(200, min(int(sz["h"]) + 16, 2000))})
        pg.wait_for_timeout(400)
        for i in range(n_frames):
            pg.evaluate(f"window.__seek({i/(n_frames-1)})")
            pg.wait_for_timeout(20)
            pg.screenshot(path=os.path.join(frames_dir, f"f_{i:04d}.png"), full_page=True)
        # hold the final frame ~1s
        last = os.path.join(frames_dir, f"f_{n_frames-1:04d}.png")
        for j in range(n_frames, n_frames + 24):
            shutil.copy(last, os.path.join(frames_dir, f"f_{j:04d}.png"))
        b.close()
    if errs:
        print("page errors:", errs, file=sys.stderr)


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True, help="output prefix (no extension)")
    ap.add_argument("--frames", type=int, default=160)
    ap.add_argument("--fps", type=int, default=18, help="gif playback fps")
    ap.add_argument("--gif-width", type=int, default=1200)
    ap.add_argument("--scale", type=float, default=1.5)
    ap.add_argument("--mp4", action="store_true", help="also emit an h264 .mp4")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="demo_frames_")
    try:
        print(f"capturing {a.frames} frames @ scale {a.scale} ...", file=sys.stderr)
        capture(a.html, tmp, a.frames, a.scale)
        seq = os.path.join(tmp, "f_%04d.png")
        vf = f"fps={a.fps},scale={a.gif_width}:-1:flags=lanczos"
        # GIF straight from the frame sequence (two-pass palette, no mp4 needed)
        pal = os.path.join(tmp, "pal.png")
        run([FFMPEG, "-y", "-framerate", str(a.fps), "-i", seq,
             "-vf", vf + ",palettegen=stats_mode=diff", pal])
        gif = a.out + ".gif"
        run([FFMPEG, "-y", "-framerate", str(a.fps), "-i", seq, "-i", pal, "-lavfi",
             vf + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3", gif])
        print("wrote", gif, f"({os.path.getsize(gif)/1048576:.1f} MB)")
        if a.mp4:
            mp4 = a.out + ".mp4"
            run([FFMPEG, "-y", "-framerate", str(a.fps), "-i", seq,
                 "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                 "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                 "-movflags", "+faststart", mp4])
            print("wrote", mp4, f"({os.path.getsize(mp4)/1048576:.1f} MB)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
