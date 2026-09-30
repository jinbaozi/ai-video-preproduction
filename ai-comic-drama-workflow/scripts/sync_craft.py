"""Single source for craft routing; standalone packages remain independently usable."""
from pathlib import Path

ROLES = ('screenplay-grammar', 'director-grammar', 'production-design-grammar', 'storyboard-grammar')
SKILLS = ('ai-comic-drama-workflow', *ROLES, 'image-prompt-optimizer', 'video-prompt-compiler')


def sync(workspace, check=False):
    from sync_shared import _copy
    root = Path(workspace)
    source = root/'ai-comic-drama-workflow/scripts/shared_craft'
    pairs = [(source/'craft-routing.md', root/name/'references/craft-routing.md') for name in SKILLS]
    pairs += [(source/'craft_router.py', root/name/'scripts/craft_router.py') for name in ROLES]
    pairs += [(source/'craft_router.py', root/'ai-comic-drama-workflow/src/ai_comic_drama_workflow/craft_router.py')]
    return _copy(pairs, check)
