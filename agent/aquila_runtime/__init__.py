"""Packaged-runtime helpers: frozen install paths, hardware profiles, model setup."""
from .hardware_profile import HardwareProfile, detect_hardware_profile
from .model_setup import ensure_recommended_model, modelfile_for_profile
from .paths import (
    get_bundled_path,
    get_default_data_root,
    get_install_root,
    is_frozen,
    launch_mode,
)

__all__ = [
    "HardwareProfile",
    "detect_hardware_profile",
    "ensure_recommended_model",
    "modelfile_for_profile",
    "get_bundled_path",
    "get_default_data_root",
    "get_install_root",
    "is_frozen",
    "launch_mode",
]
