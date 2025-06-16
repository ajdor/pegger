#!/usr/bin/env python3
import fcntl
import json
import os
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen

from flask import Flask, abort, after_this_request, request, send_file

app = Flask(__name__)


def download_to_tmp(url: str, prefix: str, default_ext: str, tmpdir: str):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1] or default_ext
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=ext, dir=tmpdir)
    os.close(fd)
    try:
        with urlopen(url) as resp, open(path, "wb") as out:
            out.write(resp.read())
    except:
        os.remove(path)
        raise
    return path


@app.route("/render", methods=["POST"])
def render():
    imgs_upload = request.files.getlist("images")
    img_urls = request.form.get("image_urls")
    audio_upload = request.files.get("audio")
    audio_url = request.form.get("audio_url")
    if not (imgs_upload or img_urls) or not (audio_upload or audio_url):
        abort(
            400, "Need at least one image (upload or URL) and one audio (upload or URL)"
        )

    try:
        sec = float(request.form.get("image_duration", 4))
    except ValueError:
        abort(400, "Invalid image_duration")

    tmpdir = tempfile.mkdtemp()
    img_paths = []

    if img_urls:
        try:
            url_list = json.loads(img_urls)
        except:
            abort(400, "Invalid JSON in image_urls")
        for i, u in enumerate(url_list):
            try:
                p = download_to_tmp(u, f"img{i}_", ".webp", tmpdir)
            except:
                abort(400, f"Failed to download image URL: {u}")
            img_paths.append(p)

    for i, img in enumerate(imgs_upload):
        ext = os.path.splitext(img.filename)[1] or ".img"
        p = os.path.join(tmpdir, f"img_up_{i}{ext}")
        img.save(p)
        img_paths.append(p)

    if audio_url:
        try:
            audio_path = download_to_tmp(audio_url, "audio_", ".mp3", tmpdir)
        except:
            abort(400, f"Failed to download audio URL: {audio_url}")
    else:
        ext = os.path.splitext(audio_upload.filename)[1] or ".mp3"
        audio_path = os.path.join(tmpdir, f"audio_up{ext}")
        audio_upload.save(audio_path)

    list_file = os.path.join(tmpdir, "list.txt")
    with open(list_file, "w") as f:
        for p in img_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {sec}\n")
        f.write(f"file '{img_paths[-1]}'\n")

    # serialize renders
    lock = open("/tmp/pegger_render.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)

    try:
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
        subprocess.run(cmd, check=True, cwd=tmpdir)

        @after_this_request
        def cleanup(response):
            # release lock
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
            # remove tmp files
            for fn in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, fn))
                except:
                    pass
            try:
                os.rmdir(tmpdir)
            except:
                pass
            return response

        return send_file(out_path, as_attachment=True, download_name="video.mp4")

    except subprocess.CalledProcessError:
        abort(500, "FFmpeg render failed")
    # no finally: cleanup deferred to after_request


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)
