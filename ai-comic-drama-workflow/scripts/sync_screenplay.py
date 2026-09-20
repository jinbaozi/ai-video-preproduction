"""Distribute the screenplay-owned protocol to the self-contained director package."""
from pathlib import Path
import hashlib

def sync(workspace, check=False):
    workspace=Path(workspace);source=workspace/'screenplay-grammar';target=workspace/'director-grammar'
    pairs=[(source/'scripts/screenplay_protocol.py',target/'scripts/screenplay_protocol.py')]
    pairs += [(p,target/'schemas/screenplay'/p.name) for p in (source/'schemas').glob('*.schema.json')]
    result={}
    for src,dst in pairs:
        data=src.read_bytes()
        if check:
            if not dst.is_file() or dst.read_bytes()!=data:raise ValueError('Screenplay shared protocol drift: '+str(dst))
        else:
            dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
        result[str(dst.relative_to(workspace))]=hashlib.sha256(data).hexdigest()
    return result

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--workspace',default=str(Path(__file__).resolve().parents[2]));p.add_argument('--check',action='store_true')
    a=p.parse_args();print(json.dumps(sync(a.workspace,a.check),indent=2))
