#!/usr/bin/env python3
"""Rebind the storyboard after the accepted coordinate repair.

The prior storyboard is a design reference only. The current DirectorIR and
ArtIR are frozen inputs, and the two declared coordinate orders are mapped
explicitly before the fresh semantic review hash is written.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

PROJECT = Path('/private/tmp/ai-video-v6-real-efKlQy/project')
BASE = PROJECT / 'runtime/v6/candidates'
OUT = BASE / 'TASK_4f81cc62bc1b268a8f8be7b0/1'
OLD = BASE / 'TASK_afc04f54b23b01071a0b14e3/1/storyboard-ir.json'
MODULE = PROJECT / 'runtime/modules/dde48be75afdb1f12dadbc01e2cbf26c2ea67de691c8d605db7912ebb241ceb8/storyboard-grammar'
sys.path.insert(0, str(MODULE / 'scripts'))
import detail_runtime  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text())


def hash_file(path: Path):
    return sha256(path.read_bytes()).hexdigest()


def hash_text(value: str):
    return sha256(value.encode('utf-8')).hexdigest()


state = load(PROJECT / 'runtime/v6/state.json')
envelope = state['tasks']['TASK_4f81cc62bc1b268a8f8be7b0']['envelope']
task = load(PROJECT / 'runtime/tasks/TASK_4f81cc62bc1b268a8f8be7b0.json')
assert envelope['batch'] == 1 and envelope['node_id'] == 'storyboard'
assert task['context_fingerprint'] == '4f81cc62bc1b268a8f8be7b025325e5b3040e493022fb7888236bf282b34355a'
for item in envelope['inputs'] + envelope['resources']:
    assert hash_file(PROJECT / item['uri']) == item['sha256'], item['uri']

inputs = {item['slot']: item for item in envelope['inputs']}
canon = inputs['canon:project:project:Canon']
director = inputs['director:project:project:DirectorIR']
art = inputs['art:scene:13x53435f5241494e5f4e49474854:ArtIR']
director_ir = load(PROJECT / director['uri'])
art_ir = load(PROJECT / art['uri'])
prior = load(OLD)
ir = deepcopy(prior)
ir['revision'] = 3

# The fixed shot, five director actions and six sampled states remain exactly
# the current accepted director design.  The storyboard adds seven reviewable
# points and authored visibility in the unchanged 12-second shot.
for field in ('action_groups', 'actions', 'audio_events',
              'composition_tracks', 'coordinate_system', 'extensions',
              'motion_tracks', 'performances', 'schema', 'segments',
              'source_time_maps', 'spatial_nodes', 'spatial_relations',
              'state_samples'):
    assert ir['timeline'][field] == director_ir['timeline'][field], field
ir['timeline']['camera_operations'] = deepcopy(director_ir['timeline']['camera_operations'])
assert len(ir['timeline']['camera_operations']) == 1
assert ir['timeline']['camera_operations'][0]['start_position'] == ir['timeline']['camera_operations'][0]['end_position']
assert '[0,1.2,-2.8]' in ir['timeline']['camera_operations'][0]['start_position']
assert director_ir['format'] == {'fps': 24, 'height': 720, 'total_frames': 288, 'width': 1280}
assert director_ir['shots'][0]['id'] == ir['shots'][0]['id'] == 'S1'
assert director_ir['shots'][0]['camera']['movement'] == 'locked'
assert director_ir['shots'][0]['camera']['axis_side'] == ir['shots'][0]['camera']['axis_side'] == 'negative'
static_camera = director_ir['shots'][0]['camera']['start_m']
timeline_camera = ir['shots'][0]['camera']['start_m']
assert static_camera == director_ir['shots'][0]['camera']['end_m'] == [0, -2.8, 1.2]
assert timeline_camera == ir['shots'][0]['camera']['end_m'] == [0, 1.2, -2.8]
assert timeline_camera == [static_camera[0], static_camera[2], static_camera[1]]
ir['scenes'][0]['coordinates']['origin'] = (
    '当前 DirectorIR 静态场景坐标为 X右、Y深、Z上：[0,-2.8,1.2] 米；'
    'StoryboardIR 时间轴坐标为 x右、y上、z深：[0,1.2,-2.8] 米。'
    '两者按轴序 (X,Z,Y) 换算为同一物理固定机位；均为预演意图，不是实测。'
)
assert art_ir['set']['scene_id'] == ir['scenes'][0]['id'] == 'SC_RAIN_NIGHT'
assert art_ir['assets'][2]['id'] == ir['entities'][2]['id'] == 'PROP_LETTER'
assert art_ir['references'] and all(x['status'] == 'planned' and x['file'] is None for x in art_ir['references'])

source_by_id = {x['id']: x for x in ir['sources']}
for source_id, item, payload, excerpt, locator in (
    ('DIRECTOR_INPUT', director, director_ir, director_ir['shots'][0]['purpose'], '/shots/0/purpose'),
    ('ART_INPUT', art, art_ir, art_ir['world']['thesis'], '/world/thesis'),
):
    source = source_by_id[source_id]
    assert excerpt in (PROJECT / item['uri']).read_text()
    source['uri'] = str(PROJECT / item['uri'])
    source['file_sha256'] = item['sha256']
    source['excerpt'] = excerpt
    source['excerpt_sha256'] = hash_text(excerpt)
    source['locator'] = locator
    source['revision'] = str(payload['revision'])
source_by_id['DIRECTOR_DESIGN']['uri'] = 'design://TASK_19a3cd14f25bf90e50215d4d/director'
source_by_id['STORYBOARD_DESIGN']['uri'] = 'design://TASK_4f81cc62bc1b268a8f8be7b0/storyboard'

for upstream, item, payload in (
    (ir['upstreams'][0], canon, load(PROJECT / canon['uri'])),
    (ir['upstreams'][1], director, director_ir),
    (ir['upstreams'][2], art, art_ir),
):
    upstream['uri'] = str(PROJECT / item['uri'])
    upstream['sha256'] = item['sha256']
    upstream['revision'] = str(payload['revision'])
    for lock in upstream['locks']:
        pointer = lock['source_pointer']
        value = payload
        for key in pointer.strip('/').split('/') if pointer else []:
            value = value[int(key)] if isinstance(value, list) else value[key]
        assert value == lock['source_value'], (upstream['id'], pointer)

ir['timeline']['semantic_review'] = {
    'status': 'PASS',
    'reviewer': '/root/host_bridge/v6_47406a68b592393955a28d31 / creator source-bound semantic check; independent V6 review pending',
    'input_sha256': None,
    'findings': [
        '当前冻结 Canon 的三事件顺序是甲交同一封未拆信、乙确认完整封口、乙随后收进同一背包；源文只给雨夜，不给地点、身份、动机、对白或后续。',
        '逐项对照当前 DirectorIR：单镜 S1、24 fps 共 288 帧、负轴侧固定摄影机，五个动作及六个状态样本未改写；乙右手先接触，甲后松开，乙确认后左手撑包、右手送信。',
        '导演静态场景坐标 [X右,Y深,Z上] [0,-2.8,1.2] 与时间轴坐标 [x右,y上,z深] [0,1.2,-2.8] 按 (X,Z,Y) 换算；分镜数值和摄影机操作文字均使用后一轴序，固定机位物理位置一致。',
        '对照当前 ArtIR 的场景、信件和背包资产：七个画格细化关键时点，信、完整封口和包口保持可读；参考仍仅 planned，实际美术素材、灯位和媒体审图未发生。',
        '世界坐标、固定机位和画格是预演意图；真实三维碰撞、手部可达性、投影和模型轨迹控制尚未由媒体或专用控制入口验证。',
        '文本项目只交付分镜计划；图像、视频、声音生成和最终媒体审阅均 NOT_RUN。',
    ],
}
ir['timeline']['semantic_review']['input_sha256'] = detail_runtime.content_hash(ir)
assert detail_runtime.semantic_status(ir)

OUT.mkdir(parents=True, exist_ok=True)
target = OUT / 'storyboard-ir.json'
target.write_text(json.dumps(ir, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
print(target)
print(hash_file(target))
