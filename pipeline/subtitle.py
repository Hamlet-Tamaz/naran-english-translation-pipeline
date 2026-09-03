from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeAudioClip,
    TextClip, CompositeVideoClip
)
import os

def burn(video_path: str, translation: dict, voiceover_path: str, output_dir: str) -> str:
    video = VideoFileClip(video_path)
    voiceover = AudioFileClip(voiceover_path)
    original = video.audio
    if original:
        mixed = CompositeAudioClip([voiceover.volumex(1.0), original.volumex(0.15)])
    else:
        mixed = voiceover
    final_dur = min(video.duration, voiceover.duration)
    video = video.subclip(0, final_dur)
    mixed = mixed.subclip(0, final_dur)
    video = video.set_audio(mixed)
    clips = [video]
    for seg in translation["segments"]:
        if seg["start"] >= final_dur:
            break
        end = min(seg["end"], final_dur)
        dur = end - seg["start"]
        txt = seg["text"].strip()
        if len(txt) > 55:
            words = txt.split()
            mid = len(words) // 2
            txt = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        tc = (TextClip(
            txt, fontsize=30, color="white", font="Arial-Bold",
            stroke_color="black", stroke_width=2, method="caption",
            size=(int(video.w * 0.9), None), align="center"
        )
        .set_start(seg["start"])
        .set_duration(dur)
        .set_position(("center", int(video.h * 0.82))))
        clips.append(tc)
    final = CompositeVideoClip(clips, size=video.size)
    final = final.set_audio(mixed)
    out = os.path.join(output_dir, "final.mp4")
    final.write_videofile(
        out, codec="libx264", audio_codec="aac",
        temp_audiofile=os.path.join(output_dir, "tmp.m4a"),
        remove_temp=True, fps=30, threads=4, logger=None
    )
    video.close()
    final.close()
    return out
