import typing

import torch

from comfy.model_downloader import add_known_models, get_or_download
from comfy.model_downloader_types import HuggingFile
from comfy.model_management import get_torch_device
from .amt_arch import AMT_S, AMT_L, AMT_G, InputPadder
from ...vfi_utils import preprocess_frames, postprocess_frames, generic_frame_loop, InterpolationStateList, VFI_MODELS_FOLDER_NAME

# https://github.com/MCG-NKU/AMT/tree/main/cfgs
CKPT_CONFIGS = {
    "amt-s.pth": {
        "network": AMT_S,
        "params": {"corr_radius": 3, "corr_lvls": 4, "num_flows": 3}
    },
    "amt-l.pth": {
        "network": AMT_L,
        "params": {"corr_radius": 3, "corr_lvls": 4, "num_flows": 5}
    },
    "amt-g.pth": {
        "network": AMT_G,
        "params": {"corr_radius": 3, "corr_lvls": 4, "num_flows": 5}
    },
    "gopro_amt-s.pth": {
        "network": AMT_S,
        "params": {"corr_radius": 3, "corr_lvls": 4, "num_flows": 3}
    }
}

for ckpt_config_filename in CKPT_CONFIGS.keys():
    add_known_models(VFI_MODELS_FOLDER_NAME, HuggingFile("lalala125", "AMT", ckpt_config_filename))


class AMT_VFI:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "ckpt_name": (list(CKPT_CONFIGS.keys()),),
                "frames": ("IMAGE",),
                "clear_cache_after_n_frames": ("INT", {"default": 1, "min": 1, "max": 100}),
                "multiplier": ("INT", {"default": 2, "min": 2, "max": 1000})
            },
            "optional": {
                "optional_interpolation_states": ("INTERPOLATION_STATES",)
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "vfi"
    CATEGORY = "ComfyUI-Frame-Interpolation/VFI"

    def vfi(
            self,
            ckpt_name: typing.AnyStr,
            frames: torch.Tensor,
            clear_cache_after_n_frames: typing.SupportsInt = 1,
            multiplier: typing.SupportsInt = 2,
            optional_interpolation_states: InterpolationStateList = None,
            **kwargs
    ):
        model_path = get_or_download(VFI_MODELS_FOLDER_NAME, ckpt_name)
        ckpt_config = CKPT_CONFIGS[ckpt_name]

        interpolation_model = ckpt_config["network"](**ckpt_config["params"])
        interpolation_model.load_state_dict(torch.load(model_path)["state_dict"])
        interpolation_model.eval().to(get_torch_device())

        frames = preprocess_frames(frames)
        padder = InputPadder(frames.shape, 16)
        frames = padder.pad(frames)

        def return_middle_frame(frame_0, frame_1, timestep, model):
            return model(
                frame_0,
                frame_1,
                embt=torch.FloatTensor([timestep] * frame_0.shape[0]).view(frame_0.shape[0], 1, 1, 1).to(get_torch_device()),
                scale_factor=1.0,
                eval=True
            )["imgt_pred"]

        args = [interpolation_model]
        out = generic_frame_loop(type(self).__name__, frames, clear_cache_after_n_frames, multiplier, return_middle_frame, *args,
                                 interpolation_states=optional_interpolation_states, dtype=torch.float32)
        out = padder.unpad(out)
        out = postprocess_frames(out)
        return (out,)
