"""Python 3.11 compatibility for fairseq 0.12.2 and Hydra 1.0.7."""

import dataclasses
import inspect
import os
import sys
from pathlib import Path


def enable_fairseq_py311_compatibility() -> None:
    """Allow legacy config instances as defaults only while importing fairseq/Hydra."""
    if sys.version_info < (3, 11):
        return

    original_get_field = dataclasses._get_field
    if getattr(original_get_field, "_rvc_py311_compat", False):
        return

    def compatible_get_field(cls, name, annotation, kw_only):
        default = getattr(cls, name, dataclasses.MISSING)
        if isinstance(default, dataclasses.Field):
            default = default.default

        module = cls.__module__
        default_type = type(default)
        should_compat = (
            (module == "fairseq" or module.startswith("fairseq."))
            or (module == "hydra" or module.startswith("hydra."))
        )
        if (
            should_compat
            and default is not dataclasses.MISSING
            and default_type.__hash__ is None
        ):
            default_type.__hash__ = object.__hash__
            try:
                return original_get_field(cls, name, annotation, kw_only)
            finally:
                default_type.__hash__ = None

        return original_get_field(cls, name, annotation, kw_only)

    compatible_get_field._rvc_py311_compat = True
    dataclasses._get_field = compatible_get_field


def enable_trusted_checkpoint_loading(hubert_path: str) -> None:
    """Use legacy pickle loading only for the verified local HuBERT checkpoint."""
    import torch

    original_load = torch.load
    if getattr(original_load, "_rvc_trusted_checkpoint_compat", False):
        return
    if "weights_only" not in inspect.signature(original_load).parameters:
        return

    trusted_path = os.path.normcase(str(Path(hubert_path).resolve()))

    def load_trusted_checkpoint(file, *args, **kwargs):
        file_path = getattr(file, "name", file)
        try:
            resolved_path = os.path.normcase(str(Path(file_path).resolve()))
        except (OSError, TypeError, ValueError):
            resolved_path = None
        if resolved_path == trusted_path and "weights_only" not in kwargs:
            kwargs["weights_only"] = False
        return original_load(file, *args, **kwargs)

    load_trusted_checkpoint._rvc_trusted_checkpoint_compat = True
    torch.load = load_trusted_checkpoint
