"""Recoverable deletion only; never fall back to permanent removal."""
def move_to_trash(path):
    try:
        from send2trash import send2trash
    except ImportError as exc:
        raise RuntimeError('Install Send2Trash from requirements.txt') from exc
    send2trash(str(path))
