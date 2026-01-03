def main(*args, **kwargs):
    from .automation import main as _main

    return _main(*args, **kwargs)


__all__ = ["main"]
