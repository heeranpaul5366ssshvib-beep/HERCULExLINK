"""HERCULE-LM training entry points (N3 §15).

Canonical implementation lives in ``models.hercule_lm``; these are
thin command shims so the documented CLI surface holds::

    python -m training.train --config hercule_lm_nano --steps 200
    python -m training.generate --checkpoint <dir> --prompt "..."
    python -m training.evaluate --checkpoint <dir>
    python -m training.prepare_data
"""
