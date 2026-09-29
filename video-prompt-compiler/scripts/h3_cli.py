"""On-demand H3/RunningHub CLI. No third-party SDK or network required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import h3_runtime as h3
import runninghub_h3 as rh


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('E_JSON_DUPLICATE: ' + key)
        result[key] = value
    return result


def read_json(path):
    data = Path(path).read_bytes()
    h3.require(len(data) <= 16*1024*1024, 'E_INPUT_SIZE', 'JSON file exceeds 16 MiB')
    return json.loads(data, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('E_JSON_NUMBER: ' + value)))


def write_json(path, data):
    # DO NOT sort keys: H3 Autogrow input order controls reference label assignment.
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def prepare(path):
    root = Path(path)
    h3.require(not root.exists() or (root.is_dir() and not any(root.iterdir())),
               'E_OUTPUT_EXISTS', 'choose a new empty output directory')
    root.mkdir(parents=True, exist_ok=True)
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect', help='inspect a supplied RunningHub API export')
    p.add_argument('workflow')
    p = sub.add_parser('plan', help='produce a prompt/node plan and patched COPY; never submit')
    p.add_argument('workflow'); p.add_argument('--node', required=True)
    p.add_argument('--sha256', required=True); p.add_argument('--prompt', required=True)
    p.add_argument('--edits'); p.add_argument('--prompt-binding'); p.add_argument('--upload-receipts')
    p.add_argument('--out', required=True)
    p = sub.add_parser('lint', help='check public H3 prompt grammar, not its visual truth')
    p.add_argument('prompt'); p.add_argument('--mode', choices=h3.MODES, required=True)
    p.add_argument('--duration', type=float, required=True); p.add_argument('--refs')
    p = sub.add_parser('context-request', help='build an OFFLINE official API request')
    p.add_argument('brief'); p.add_argument('--mode', choices=h3.MODES, required=True)
    p.add_argument('--duration', type=int, required=True); p.add_argument('--ratio', required=True)
    p.add_argument('--media'); p.add_argument('--out', required=True)
    p = sub.add_parser('context-import', help='import caller-supplied official task receipts as a candidate')
    p.add_argument('request'); p.add_argument('created'); p.add_argument('result'); p.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    optional = lambda path: read_json(path) if path else None
    try:
        if args.command == 'inspect':
            result = rh.inspect(read_json(args.workflow))
        elif args.command == 'lint':
            result = h3.check_prompt(Path(args.prompt).read_text(encoding='utf-8'), args.mode, args.duration, optional(args.refs))
        elif args.command == 'plan':
            prompt = Path(args.prompt).read_text(encoding='utf-8')
            result, graph = rh.plan(read_json(args.workflow), prompt, args.node, args.sha256,
                                    optional(args.edits), optional(args.prompt_binding), optional(args.upload_receipts))
            root = prepare(args.out)
            write_json(root/'runninghub-plan.json', result)
            write_json(root/'workflow-api.patched.json', graph)
            (root/'h3-prompt.txt').write_text(prompt, encoding='utf-8')
            rows = ['# H3 → RunningHub', '',
                    '**仅完成静态交接，未提交生成、未扣费、未做媒体验收。**', '',
                    f"模式：{result['mode']}；节点：{args.node}；工作流指纹：`{args.sha256}`。", '',
                    '将 `h3-prompt.txt` 复制到下表指定字段；或审阅 `workflow-api.patched.json` 的副本。',
                    '`nodeInfoList` 是 API 字段修改草案，不是完整请求，不含 workflowId/API Key。', '',
                    '| 节点 | 类型 | 字段 | 操作 |', '|---|---|---|---|']
            rows += [f"| {e['nodeId']} | {e['classType']} | {e['fieldName']} | " +
                     ('固定种子' if e['fieldName'] in ('seed','noise_seed') else '采用明确的新值') + ' |'
                     for e in result['edits']]
            rows += ['', '## 引用连接顺序']
            rows += [f"{r['label']} → {'.'.join(r['input_path'])} → 节点 {r['source_node_id']} 输出 {r['source_output']}；{r['role']}。"
                     for r in result['references']]
            rows += ['', '## 运行前检查',
                     '确认真实模型/编码器/VAE/节点版本、素材内容与上传回执；逐项复核台词、左右、动作、色彩和焦点转移。',
                     '确认有效时长与首尾帧、视频声轨编号。实际生成后才记录 RunningHub taskId、媒体哈希与 QA；不要把本计划提升为 VIDEO_DELIVERED。',
                     '', *result['warnings']]
            (root/'README.md').write_text('\n'.join(rows)+'\n', encoding='utf-8')
            result = {k: result[k] for k in ('status','mode','submitted','runnable','warnings')}
            result['out'] = str(root.resolve())
        elif args.command == 'context-request':
            request = h3.context_request(Path(args.brief).read_text(encoding='utf-8'), args.mode,
                                         args.duration, args.ratio, optional(args.media))
            root = prepare(args.out)
            write_json(root/'context-request.json', request)
            result = {'status': 'OFFLINE_REQUEST_DRAFT', 'endpoint': h3.CONTEXT_ENDPOINT,
                      'request_sha256': h3.fingerprint(request), 'media_limits_verified': False,
                      'submitted': False, 'runnable': False}
            write_json(root/'context-request-metadata.json', result)
        else:
            result = h3.import_context(read_json(args.request), read_json(args.created), read_json(args.result))
            root = prepare(args.out)
            write_json(root/'context-candidate.json', result)
            (root/'prompt-candidate.txt').write_text(result['prompt'], encoding='utf-8')
            result = {k: v for k, v in result.items() if k != 'prompt'}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if result.get('status') == 'BLOCKED' else 0
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error), 'submitted': False}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as error:
        print(json.dumps({'status': 'ERROR', 'error': str(error), 'submitted': False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
