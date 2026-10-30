"""The 1-D CNN from ``ml/ecg_core.py``, adapted for the API runtime.

This module is the only place in FastAPI that imports PyTorch, NumPy and SciPy.
It is imported lazily by :mod:`app.inference`, so a deployment without the ML
extras can still start and serve telemetry. The model definition and the
preprocessing are kept byte-for-byte compatible with the training notebook:

* resample to 300 Hz with ``resample_poly``;
* remove the mean;
* 4th-order 0.5-40 Hz Butterworth band-pass, forward-backward;
* z-score;
* tile/pad to 9000 samples (30 s) and score 50 %-overlapping windows;
* average the softmax over windows.

The checkpoint written by the notebook (``ecg_model.pt``) is::

    {"state_dict": ..., "classes": ["N", "A", "O", "~"], "fs": 300, "win": 9000}

A checkpoint without metadata is accepted when its state dict has the expected
shape; the class order then defaults to the notebook's order.
"""

from __future__ import annotations

import hashlib
from math import gcd
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.signal import butter, resample_poly, sosfiltfilt

FS = 300
WIN = 9000
ARCHITECTURE = "ECGNet-1DCNN"

_SOS = butter(4, [0.5, 40], btype="band", fs=FS, output="sos")


class CheckpointError(ValueError):
    """The checkpoint exists but cannot be used by this architecture."""


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preprocess(x, fs: int = FS) -> np.ndarray:
    """Raw 1-D ECG at ``fs`` Hz -> filtered, z-scored float32 at 300 Hz."""

    array = np.asarray(x, dtype=np.float64)
    if array.ndim != 1:
        array = array.reshape(-1)
    if array.size == 0:
        raise ValueError("The ECG signal is empty.")
    if not np.all(np.isfinite(array)):
        array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)

    rate = int(fs or 0)
    if rate <= 0:
        raise ValueError("The ECG sample rate must be positive.")
    if rate != FS:
        divisor = gcd(rate, FS)
        array = resample_poly(array, FS // divisor, rate // divisor)

    array = array - array.mean()
    if array.size > 32:
        array = sosfiltfilt(_SOS, array)
    array = (array - array.mean()) / (array.std() + 1e-8)
    return array.astype(np.float32)


def tile_pad(x: np.ndarray, n: int = WIN) -> np.ndarray:
    if len(x) >= n:
        return x
    return np.tile(x, int(np.ceil(n / max(1, len(x)))))[:n]


def windows(x: np.ndarray, n: int = WIN, stride: int = WIN // 2) -> list[np.ndarray]:
    """Split a signal into overlapping model windows, padding the tail."""

    x = tile_pad(x, n)
    starts = list(range(0, len(x) - n + 1, stride))
    if not starts:
        starts = [0]
    if starts[-1] != len(x) - n:
        starts.append(len(x) - n)
    return [x[start : start + n] for start in starts]


class SE(nn.Module):
    def __init__(self, c: int, r: int = 8):
        super().__init__()
        self.fc1 = nn.Linear(c, c // r)
        self.fc2 = nn.Linear(c // r, c)

    def forward(self, x):
        s = x.mean(-1)
        s = torch.sigmoid(self.fc2(F.relu(self.fc1(s))))
        return x * s.unsqueeze(-1)


class Block(nn.Module):
    def __init__(self, cin: int, cout: int, stride: int):
        super().__init__()
        self.c1 = nn.Conv1d(cin, cout, 7, stride, 3, bias=False)
        self.b1 = nn.BatchNorm1d(cout)
        self.c2 = nn.Conv1d(cout, cout, 7, 1, 3, bias=False)
        self.b2 = nn.BatchNorm1d(cout)
        self.se = SE(cout)
        self.sc = None
        if stride != 1 or cin != cout:
            self.sc = nn.Sequential(
                nn.Conv1d(cin, cout, 1, stride, bias=False),
                nn.BatchNorm1d(cout),
            )

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.se(self.b2(self.c2(y)))
        return F.relu(y + (x if self.sc is None else self.sc(x)))


class ECGNet(nn.Module):
    def __init__(self, n_classes: int = 4):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(1, 32, 15, 2, 7, bias=False),
            nn.BatchNorm1d(32),
            nn.ReLU(),
        )
        cfg = [
            (32, 32, 2),
            (32, 64, 2),
            (64, 64, 2),
            (64, 128, 2),
            (128, 128, 2),
            (128, 128, 2),
        ]
        self.blocks = nn.Sequential(*[Block(*layer) for layer in cfg])
        self.drop = nn.Dropout(0.3)
        self.fc = nn.Linear(256, n_classes)

    def forward(self, x):  # (B, 1, WIN)
        x = self.blocks(self.stem(x))
        x = torch.cat([x.mean(-1), x.amax(-1)], 1)
        return self.fc(self.drop(x))


def _state_dict(payload: dict) -> dict:
    for key in ("state_dict", "model_state_dict", "model_state"):
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return candidate
    # A bare state dict is also accepted.
    if payload and all(torch.is_tensor(value) for value in payload.values()):
        return payload
    raise CheckpointError(
        "The checkpoint has no state_dict. Save it with "
        "torch.save({'state_dict': model.state_dict(), 'classes': ..., ...})."
    )


def _strip_module_prefix(state: dict) -> dict:
    """Accept checkpoints saved from ``DataParallel``/``DistributedDataParallel``."""

    if state and all(key.startswith("module.") for key in state):
        return {key[len("module.") :]: value for key, value in state.items()}
    return state


def load_checkpoint(path: str | Path, device: str = "cpu") -> tuple[ECGNet, dict]:
    """Load ``ecg_model.pt`` and return ``(model, metadata)``.

    ``weights_only=True`` is used where the installed PyTorch supports it: the
    checkpoint is data, not code, and a model file should never be able to
    execute anything on load.
    """

    resolved = Path(path).expanduser()
    try:
        try:
            payload = torch.load(
                resolved, map_location="cpu", weights_only=True
            )
        except TypeError:  # PyTorch < 2.0 has no weights_only
            payload = torch.load(resolved, map_location="cpu")
    except (OSError, RuntimeError, ValueError, EOFError) as exc:
        raise CheckpointError(f"The model file could not be read: {exc}") from exc

    if not isinstance(payload, dict):
        raise CheckpointError("The model file does not contain a checkpoint dictionary.")

    state = _strip_module_prefix(_state_dict(payload))
    classes = payload.get("classes") or list(("N", "A", "O", "~"))
    if not isinstance(classes, (list, tuple)) or not classes:
        raise CheckpointError("The checkpoint's 'classes' field is not a non-empty list.")
    classes = [str(value) for value in classes]

    model = ECGNet(len(classes))
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as exc:
        raise CheckpointError(
            "The checkpoint does not match the ECGNet 1-D CNN architecture: "
            f"{exc}"
        ) from exc

    target = torch.device(device)
    if target.type == "cuda" and not torch.cuda.is_available():
        target = torch.device("cpu")
    model.to(target).eval()

    checksum = file_sha256(resolved)
    metadata = {
        "name": str(payload.get("name") or resolved.stem),
        "version": str(payload.get("version") or checksum[:12]),
        "classes": classes,
        "fs": int(payload.get("fs") or FS),
        "win": int(payload.get("win") or WIN),
        "sha256": checksum,
        "device": str(target),
        "architecture": ARCHITECTURE,
        "size_bytes": resolved.stat().st_size,
    }
    return model, metadata


def _select_windows(all_windows: list[np.ndarray], limit: int) -> list[np.ndarray]:
    if limit <= 0 or len(all_windows) <= limit:
        return all_windows
    # Evenly spaced, always including the first and last window, so a long
    # recording is summarised without loading every window into one batch.
    indexes = np.linspace(0, len(all_windows) - 1, limit).round().astype(int)
    return [all_windows[int(index)] for index in indexes]


def predict(
    model: ECGNet,
    raw_signal,
    *,
    fs: int = FS,
    device: str = "cpu",
    max_windows: int = 8,
    batch_size: int = 4,
) -> dict:
    """Score a raw ECG and return averaged softmax probabilities.

    The result deliberately reports how many windows were scored and how long
    the signal was. A one-window prediction from a 5-second trace is not the
    same evidence as eight windows from a multi-minute recording, and the API
    should not hide that.
    """

    if raw_signal is None:
        raise ValueError("The ECG signal is empty.")

    processed = preprocess(raw_signal, fs)
    selected = _select_windows(windows(processed), max_windows)
    batch = np.stack(selected).astype(np.float32)[:, None]

    target = torch.device(device)
    if target.type == "cuda" and not torch.cuda.is_available():
        target = torch.device("cpu")
    model.to(target).eval()

    totals = None
    with torch.no_grad():
        for start in range(0, len(batch), max(1, batch_size)):
            chunk = torch.from_numpy(batch[start : start + batch_size]).to(target)
            probabilities = F.softmax(model(chunk), dim=1)
            summed = probabilities.sum(dim=0).cpu().numpy()
            totals = summed if totals is None else totals + summed

    if totals is None:
        raise ValueError("No model window could be scored.")
    probabilities = totals / float(len(batch))
    order = np.argsort(probabilities)[::-1]
    return {
        "probabilities": [float(value) for value in probabilities],
        "predicted_index": int(order[0]),
        "window_count": len(batch),
        "window_seconds": WIN / FS,
        "signal_seconds": float(len(processed) / FS),
    }


__all__ = [
    "ARCHITECTURE",
    "CheckpointError",
    "ECGNet",
    "FS",
    "WIN",
    "file_sha256",
    "load_checkpoint",
    "predict",
    "preprocess",
    "tile_pad",
    "windows",
]
