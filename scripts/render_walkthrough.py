"""Burn chapter annotations below real browser footage and package a chaptered MP4."""
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "walkthrough"
OUT = ROOT / "docs" / "demo"


def stamp(seconds):
    ticks = round(seconds * 100)
    hour, ticks = divmod(ticks, 360000)
    minute, ticks = divmod(ticks, 6000)
    second, fraction = divmod(ticks, 100)
    return f"{hour}:{minute:02}:{second:02}.{fraction:02}"


def run(args):
    subprocess.run(args, check=True, cwd=WORK)


def main():
    report = json.loads((WORK / "recording-report.json").read_text(encoding="utf-8"))
    boards = json.loads((WORK / "boards-report.json").read_text(encoding="utf-8"))
    if (WORK / "recording-failure.txt").exists():
        raise SystemExit("Inspect the current recording failure before packaging.")
    assert report["segments"][-1]["name"] == "mobile"
    OUT.mkdir(parents=True, exist_ok=True)
    replacements = {x["title"]: x for x in boards["boards"]}
    board_chapters = {x["title"]: x for x in boards["chapters"]}
    plan = []
    for segment in report["segments"]:
        duration = float(json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "json", str(WORK / segment["source"])], text=True))["format"]["duration"])
        assert duration >= segment["end"] - 2
        for i, chapter in enumerate(segment["chapters"]):
            end = segment["chapters"][i+1]["start"] if i+1 < len(segment["chapters"]) else duration
            clip = dict(chapter, source=segment["source"], source_start=chapter["start"],
                        duration=end-chapter["start"], width=segment["width"], height=segment["height"])
            if chapter["title"] in replacements:
                replacement = replacements[chapter["title"]]
                clip.update(source=replacement.get("source", boards["source"]), source_start=replacement["start"],
                            duration=replacement["end"]-replacement["start"], width=1600, height=900,
                            caption=board_chapters[chapter["title"]]["caption"])
            if clip["duration"] > 24:
                clip["duration"] = 14
                clip["wait_shortened"] = True
                clip["caption"] = "Processing wait shortened. Actual elapsed time, retries and token usage remain in the saved execution record."
            plan.append(clip)
            if chapter["title"] == "Demo approval and configuration boundary":
                for title in ("Retry delivery without configuration", "Reject a labelled replay brief"):
                    replacement = replacements[title]
                    plan.append(dict(board_chapters[title], source=boards["source"], source_start=replacement["start"],
                                     duration=replacement["end"]-replacement["start"], width=1600, height=900))
            if chapter["title"] == "Cancellation preserves the audit":
                title = "Operator sign-out"
                replacement = replacements[title]
                plan.append(dict(board_chapters[title], source=boards["source"], source_start=replacement["start"],
                                 duration=replacement["end"]-replacement["start"], width=1600, height=900))
    styles = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1600", "PlayResY: 1020", "WrapStyle: 0", "",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Segoe UI,24,&H00FFFFFF,&H00FFFFFF,&H00232E17,&H00232E17,0,0,0,0,100,100,0,0,1,0,0,2,30,30,18,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    metadata = [";FFMETADATA1", "title=SignalBrief - detailed annotated walkthrough",
                "comment=Real UI footage. Processing waits shortened and labelled. Annotations burned in."]
    offset = 0
    files = []
    for i, clip in enumerate(plan):
        lines = textwrap.wrap(clip["caption"].replace("{", "(").replace("}", ")"), width=118)
        assert len(lines) <= 2, clip["title"]
        title = clip["title"].replace("{", "(").replace("}", ")")
        caption = r"{\b1}"+title+r"{\b0}\N"+r"\N".join(lines)
        ass_name = f"clip-{i:03}.ass"
        (WORK / ass_name).write_text("\n".join(styles + [f"Dialogue: 0,0:00:00.00,{stamp(clip['duration'])},Default,,0,0,0,,{caption}"]), encoding="utf-8")
        padding = ("pad=1600:1020:0:0:color=0x172e23" if clip["width"] == 1600 else
                   "pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=0xf5f6f0,pad=1600:1020:0:0:color=0x172e23")
        target = f"clip-{i:03}.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(clip["source_start"]),
             "-i", clip["source"], "-t", str(clip["duration"]), "-vf", padding+f",ass=filename={ass_name},fps=25",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", target])
        actual = float(json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "json", str(WORK / target)], text=True))["format"]["duration"])
        clip["video_start"] = round(offset, 3)
        clip["video_duration"] = actual
        metadata.extend(["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(offset*1000)}",
                         f"END={round((offset+actual)*1000)}", "title="+title.replace("=", "-").replace(";", ",")])
        files.append(f"file '{target}'")
        offset += actual
        print(f"Encoded {i+1}/{len(plan)}: {title}", flush=True)
    (WORK / "concat.txt").write_text("\n".join(files), encoding="utf-8")
    (WORK / "chapters.txt").write_text("\n".join(metadata), encoding="utf-8")
    output = OUT / "signalbrief-walkthrough.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt",
         "-i", "chapters.txt", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", str(output)])
    report.update(video="docs/demo/signalbrief-walkthrough.mp4", duration_seconds=round(offset, 3),
                  annotation_placement="Burned-in 120px band below untouched app viewport", edit_plan=plan,
                  sha256=hashlib.sha256(output.read_bytes()).hexdigest(), file_bytes=output.stat().st_size)
    (WORK / "final-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Packaged {offset:.1f}s video, {output.stat().st_size/1048576:.1f} MiB; no subtitle track.")


if __name__ == "__main__":
    main()
