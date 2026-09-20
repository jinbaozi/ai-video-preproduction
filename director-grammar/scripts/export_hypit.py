#!/usr/bin/env python3
"""Export accepted, already-trimmed local takes to Hypit 0.1.10 sources. Never build."""
import argparse
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import quoteattr

from dg import read, save, digest, file_digest, validate, schema_errors, dump


def export(ir, execution, manifest, media_root, out, test_fixture=False):
    errors = validate(ir) + schema_errors(execution,"execution-ir") + schema_errors(manifest,"edit-manifest")
    if errors:
        raise ValueError("\n".join(errors))
    if execution["ir_sha256"]!=digest(ir) or manifest["execution_sha256"]!=digest(execution):
        raise ValueError("STALE: input hashes do not match")
    if execution["status"]=="BLOCKED":
        raise ValueError("Execution plan is BLOCKED")
    takes = {t["shot_id"]:t for t in manifest["takes"]}
    if len(takes)!=len(manifest["takes"]) or set(takes)!={s["id"] for s in ir["shots"]}:
        raise ValueError("Exactly one selected Take per Shot is required")
    if len({t["id"] for t in manifest["takes"]}) != len(takes):
        raise ValueError("Duplicate Take ID")
    checked = []
    fmt = ir["format"]
    for shot in ir["shots"]:
        take = takes[shot["id"]]
        expected = "TEST_FIXTURE" if test_fixture else "ACCEPTED"
        if take["qa_status"] != expected:
            raise ValueError("Test fixtures and accepted production takes cannot be mixed")
        source = (Path(media_root)/take["path"]).resolve()
        evidence = Path(media_root)/take["evidence_ref"]
        if not source.is_file() or file_digest(source)!=take["sha256"]:
            raise ValueError(f"Missing or changed Take: {take['id']}")
        if not evidence.is_file():
            raise ValueError(f"Missing Take review: {take['id']}")
        probe = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-count_frames",
                                "-show_entries","stream=width,height,avg_frame_rate,nb_read_frames",
                                "-of","json",str(source)],capture_output=True,text=True,check=True)
        streams = json.loads(probe.stdout)["streams"]
        if not streams:
            raise ValueError("Take has no video stream")
        info = streams[0]
        if (int(info["nb_read_frames"])!=shot["frames"] or take["frames"]!=shot["frames"]
                or Fraction(info["avg_frame_rate"])!=fmt["fps"]
                or (info["width"],info["height"])!=(fmt["width"],fmt["height"])):
            raise ValueError("Take must already have exact contract frames, fps and canvas; no silent retiming/crop")
        checked.append((shot,take,source,info))
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Use a new empty output directory")
    (out/"media").mkdir()
    lines = ['<?svml using="@hypit/markup@1"?>','<svml>']
    for alias,pkg in [('time','timeline-author'),('space','spatial'),('asset','media'),('pipeline','media-pipeline'),('media','media-track'),('film','film'),('render','render-hyperframes')]:
        lines.append(f' <import as="{alias}" from="@hypit/{pkg}@1"/>')
    lines += [' <import as="look" source="./main.svs"/>',
              f' <time:Clock id="clock" frame-rate="{fmt["fps"]}"/>',
              f' <time:Timeline id="program" clock={{clock}} end="{fmt["total_frames"]/fmt["fps"]:g}s"/>',
              f' <space:Canvas id="canvas" width="{fmt["width"]}" height="{fmt["height"]}"/>',
              f' <space:Frame id="frame" within={{canvas}} left="0px" top="0px" right="{fmt["width"]}px" bottom="{fmt["height"]}px"/>']
    for i,(_,take,source,_) in enumerate(checked):
        filename=f'take-{i+1}{source.suffix.lower()}'
        shutil.copyfile(source,out/"media"/filename)
        lines += [f' <asset:Video id="source{i}" src={quoteattr("./media/"+filename)}/>',
                  f' <pipeline:Normalize id="clip{i}" source={{source{i}}} clock={{clock}} video="primary-moving" audio="default" span-authority="video"/>']
    lines.append(' <media:Track id="clips" timeline={program.timeline} canvas={canvas}>')
    cursor=0
    for i,(shot,_,_,_) in enumerate(checked):
        lines.append(f'  <media:Item media={{clip{i}.media}} frame={{frame}} at="{cursor/fmt["fps"]:g}s" for="{shot["frames"]/fmt["fps"]:g}s" appearance={{look.media.clip}} source-audio="content"/>')
        cursor+=shot["frames"]
    lines += [' </media:Track>',
              ' <film:Film id="main" canvas={canvas} timeline={program.timeline} appearance={look.film.main}>',
              '  <film:Track source={clips.visual}/>','  <film:Track source={clips.audio}/>',' </film:Film>',
              ' <render:Video id="final" composition={main.composition} timeline={program.timeline}/>','</svml>']
    (out/"main.svml").write_text("\n".join(lines)+"\n")
    (out/"main.svs").write_text('<?svml using="@hypit/svs@1"?>\n<sheet version="1">\n film.main { background: #000000; }\n media.clip { stack-order: 1; fit: contain; }\n</sheet>\n')
    (out/"build.svrun").write_text('<?svml using="@hypit/run-markup@1"?>\n<svrun version="1">\n <author source="./main.svml"/>\n <target output="final.video"/>\n</svrun>\n')
    receipt=dict(status="TEST_SOURCE_EXPORTED" if test_fixture else "SOURCE_EXPORTED",hypit_version="0.1.10",
                 execution_sha256=digest(execution),manifest_sha256=digest(manifest),built=False,
                 requires=["hypit check main.svml","hypit check build.svrun","hypit plan build.svrun"],
                 limitation="仅装配已裁切本地Take；未实现生成请求、自动裁切、配音或build-record转换。源音频随片复用。",
                 takes=[dict(take_id=t["id"],shot_id=s["id"],sha256=t["sha256"],probe=p) for s,t,_,p in checked])
    save(out/"export-receipt.json",receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input");p.add_argument("execution");p.add_argument("manifest")
    p.add_argument("--media-root",required=True);p.add_argument("--out",required=True)
    p.add_argument("--test-fixture",action="store_true")
    args=p.parse_args()
    try:
        print(dump(export(read(args.input),read(args.execution),read(args.manifest),args.media_root,args.out,args.test_fixture)))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as e:
        print(dump({"status":"ERROR","error":str(e)}),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
