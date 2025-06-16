import os
import subprocess
import tempfile

from flask import Flask, abort, request, send_file

app = Flask(__name__)

@app.route('/render', methods=['POST'])
def render():
    files = request.files.getlist('images')
    audio = request.files.get('audio')
    if not files or not audio:
        return abort(400, "Need at least one image and one audio file")

    # parse seconds-per-image
    try:
        sec = float(request.form.get('image_duration', 4))
    except ValueError:
        return abort(400, "Invalid image_duration")

    tmp = tempfile.mkdtemp()
    img_paths = []
    for idx, img in enumerate(files):
        p = os.path.join(tmp, f"img{idx}.webp")
        img.save(p); img_paths.append(p)
    ext = audio.filename.rsplit('.',1)[1]
    audio_path = os.path.join(tmp, f"audio.{ext}")
    audio.save(audio_path)

    # concat list
    list_txt = os.path.join(tmp, "list.txt")
    with open(list_txt, 'w') as f:
        for p in img_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {sec}\n")
        f.write(f"file '{img_paths[-1]}'\n")

    out_path = os.path.join(tmp, "out.mp4")
    cmd = [
        "ffmpeg","-y",
        "-f","concat","-safe","0","-i",list_txt,
        "-i",audio_path,
        "-c:v","libx264","-r","30","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k",
        "-shortest", out_path
    ]
    try:
        subprocess.run(cmd, check=True, cwd=tmp)
        return send_file(out_path, as_attachment=True, attachment_filename="video.mp4")
    finally:
        for f in os.listdir(tmp):
            os.unlink(os.path.join(tmp, f))
        os.rmdir(tmp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000)
