#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen

from flask import Flask, abort, request, send_file

app = Flask(__name__)


def download_to_tmp(url: str, prefix: str, default_ext: str):
    """Download a URL to a temp file, inferring extension from URL or default."""
    parsed = urlparse(url)
    # Try to get extension from path
    ext = os.path.splitext(parsed.path)[1]
    if not ext:
        ext = default_ext
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=ext)
    os.close(fd)
    try:
        with urlopen(url) as resp, open(path, "wb") as out:
            out.write(resp.read())
    except Exception as e:
        os.remove(path)
        raise
    return path


@app.route("/render", methods=["POST"])
def render():
    # images: either uploaded or via URLs
    uploaded_images = request.files.getlist("images")
    image_urls = request.form.get("image_urls")
    # audio: either uploaded or via single URL
    uploaded_audio = request.files.get("audio")
    audio_url = request.form.get("audio_url")
    if not (uploaded_images or image_urls) or not (uploaded_audio or audio_url):
        abort(
            400, "Need at least one image (upload or URL) and one audio (upload or URL)"
        )

    # seconds per image
    try:
        sec = float(request.form.get("image_duration", 4))
    except ValueError:
        abort(400, "Invalid image_duration")

    tmpdir = tempfile.mkdtemp()
    img_paths = []

    # Download image URLs
    if image_urls:
        try:
            url_list = json.loads(image_urls)
        except json.JSONDecodeError:
            abort(400, "Invalid JSON in image_urls")
        for idx, u in enumerate(url_list):
            try:
                p = download_to_tmp(u, prefix=f"img{idx}_", default_ext=".webp")
            except:
                abort(400, f"Failed to download image URL: {u}")
            img_paths.append(p)

    # Save uploaded image files
    if uploaded_images:
        for idx, img in enumerate(uploaded_images):
            ext = os.path.splitext(img.filename)[1] or ".img"
            p = os.path.join(tmpdir, f"img_upload_{idx}{ext}")
            img.save(p)
            img_paths.append(p)

    # Determine audio source
    if audio_url:
        try:
            audio_path = download_to_tmp(audio_url, prefix="audio_", default_ext=".mp3")
        except:
            abort(400, f"Failed to download audio URL: {audio_url}")
    else:
        # uploaded_audio
        ext = os.path.splitext(uploaded_audio.filename)[1] or ".mp3"
        audio_path = os.path.join(tmpdir, f"audio_upload{ext}")
        uploaded_audio.save(audio_path)

    # Build ffmpeg concat list
    list_file = os.path.join(tmpdir, "list.txt")
    with open(list_file, "w") as f:
        for p in img_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {sec}\n")
        f.write(f"file '{img_paths[-1]}'\n")

    # Prepare output
    out_path = os.path.join(tmpdir, "out.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_file,
        "-i",
        audio_path,
        "-c:v",
        "libx264",
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, cwd=tmpdir)
        return send_file(out_path, as_attachment=True, download_name="video.mp4")
    finally:
        # cleanup
        for fn in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, fn))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)
