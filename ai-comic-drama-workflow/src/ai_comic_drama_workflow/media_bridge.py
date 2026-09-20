"""Host-owned image execution: Python dispatches/imports, never calls a fake API."""
from copy import deepcopy
from pathlib import Path

from .schema import load_schema, validate
from .utils import canonical_json, sha256_bytes, sha256_file, stable_id


class HostMediaRequired(Exception):
    def __init__(self, job):
        self.job = job
        super().__init__('Codex host must execute or user must provide this image')


def check_reference(store, binding):
    validate(binding, load_schema('reference-binding.schema.json'))
    path = store.path(binding['path'])
    if not path.is_file() or sha256_file(path) != binding['sha256']:
        raise ValueError(f"Reference missing or changed: {binding['reference_id']}")


def acquire_candidate(store, *, stage_id, key, prompt, bindings, folder, output_kind, revision_token=None, allowed_providers=('codex-imagegen', 'provided')):
    for binding in bindings:
        check_reference(store, binding)
    payload = {'stage_id': stage_id, 'key': key, 'prompt': prompt, 'reference_bindings': bindings,
               'revision_token': revision_token, 'allowed_providers': list(allowed_providers)}
    content_identity = {**payload, 'reference_bindings': [{k: v for k, v in b.items() if k != 'approval_ref'} for b in bindings]}
    # Renewed approval of unchanged bytes is not a new creative image request.
    digest = sha256_bytes(canonical_json(content_identity).encode())
    receipt_path = f'runtime/media-results/{digest}.json'
    if store.exists(receipt_path):
        receipt = store.read(receipt_path)
        from .pipeline import inspect_image
        if sha256_file(store.path(receipt['media_path'])) != receipt['sha256']:
            raise ValueError('Imported media changed after receipt')
        if not inspect_image(store.path(receipt['media_path']))['verified']:
            raise ValueError('Imported image is no longer readable')
        return receipt
    job = {**payload, 'job_id': stable_id('media-job', digest), 'input_hash': digest,
           'prompt_sha256': sha256_bytes(prompt.encode()), 'execution_context': 'codex-host',
           'output_kind': output_kind, 'status': 'pending', 'destination_folder': folder,
           'receipt_path': receipt_path,
           'boundary': 'Host must inspect references, call native image_gen or import user-provided image; no automatic API fallback.'}
    raise HostMediaRequired(job)


def import_candidate(store, job, result):
    if result.get('job_id') != job['job_id'] or result.get('input_hash') != job['input_hash']:
        raise ValueError('Media result does not match the dispatched job')
    if result.get('provider') not in {'codex-imagegen', 'provided'}:
        raise ValueError('Native job accepts only real host output or explicitly provided media')
    if result['provider'] not in job.get('allowed_providers', ['codex-imagegen', 'provided']):
        raise ValueError('This task permits image import only, not a generation call')
    if result.get('reference_bindings') != job['reference_bindings']:
        raise ValueError('Actual input reference receipt must match every dispatched binding')
    if result['provider'] == 'codex-imagegen' and not result.get('call_evidence'):
        raise ValueError('Native output requires available call evidence; do not invent tool metadata')
    for binding in job['reference_bindings']:
        check_reference(store, binding)
    source = Path(result['output_path']).resolve(strict=True)
    if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        raise ValueError('A finished raster image is required; SVG/whitebox is not a storyboard image')
    digest = sha256_file(source)
    if digest != result.get('sha256'):
        raise ValueError('Returned file hash mismatch')
    from .pipeline import inspect_image
    inspection = inspect_image(source)
    if not inspection['verified']:
        raise ValueError('Returned image failed file inspection')
    relative = f"{job['destination_folder']}/{job['input_hash'][:16]}-{digest[:16]}{source.suffix.lower()}"
    store.copy_source(source, relative)
    receipt = {**deepcopy(result), 'media_path': relative, 'sha256': digest,
               'reference_bindings': deepcopy(job['reference_bindings']), 'prompt_sha256': job['prompt_sha256'],
               'file_validation': inspection, 'creative_review': 'pending', 'human_approval': 'pending'}
    # Raw execution receipt is runtime evidence, not a formal business artifact.
    store.write_text(job['receipt_path'], canonical_json(receipt))
    return receipt
