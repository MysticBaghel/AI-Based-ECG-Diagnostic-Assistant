"""Shared ECG code: preprocessing + model + inference. Import this in Colab AND in FastAPI."""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from math import gcd
from scipy.signal import butter, sosfiltfilt, resample_poly

FS = 300            # model sampling rate (Hz)
WIN = 9000          # 30 s window
CLASSES = ["N", "A", "O", "~"]
_SOS = butter(4, [0.5, 40], btype="band", fs=FS, output="sos")


def preprocess(x, fs=FS):
    """Raw 1-D ECG at `fs` Hz -> filtered, z-scored float32 at 300 Hz."""
    x = np.asarray(x, dtype=np.float64)
    if int(fs) != FS:
        g = gcd(int(fs), FS)
        x = resample_poly(x, FS // g, int(fs) // g)
    x = x - x.mean()
    x = sosfiltfilt(_SOS, x)
    x = (x - x.mean()) / (x.std() + 1e-8)
    return x.astype(np.float32)


def tile_pad(x, n=WIN):
    if len(x) >= n:
        return x
    return np.tile(x, int(np.ceil(n / len(x))))[:n]


def windows(x, n=WIN, stride=WIN // 2):
    x = tile_pad(x, n)
    starts = list(range(0, len(x) - n + 1, stride))
    if starts[-1] != len(x) - n:
        starts.append(len(x) - n)
    return [x[s:s + n] for s in starts]


class SE(nn.Module):
    def __init__(self, c, r=8):
        super().__init__()
        self.fc1 = nn.Linear(c, c // r)
        self.fc2 = nn.Linear(c // r, c)

    def forward(self, x):
        s = x.mean(-1)
        s = torch.sigmoid(self.fc2(F.relu(self.fc1(s))))
        return x * s.unsqueeze(-1)


class Block(nn.Module):
    def __init__(self, cin, cout, stride):
        super().__init__()
        self.c1 = nn.Conv1d(cin, cout, 7, stride, 3, bias=False)
        self.b1 = nn.BatchNorm1d(cout)
        self.c2 = nn.Conv1d(cout, cout, 7, 1, 3, bias=False)
        self.b2 = nn.BatchNorm1d(cout)
        self.se = SE(cout)
        self.sc = None
        if stride != 1 or cin != cout:
            self.sc = nn.Sequential(nn.Conv1d(cin, cout, 1, stride, bias=False), nn.BatchNorm1d(cout))

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.se(self.b2(self.c2(y)))
        return F.relu(y + (x if self.sc is None else self.sc(x)))


class ECGNet(nn.Module):
    def __init__(self, n_classes=4):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv1d(1, 32, 15, 2, 7, bias=False), nn.BatchNorm1d(32), nn.ReLU())
        cfg = [(32, 32, 2), (32, 64, 2), (64, 64, 2), (64, 128, 2), (128, 128, 2), (128, 128, 2)]
        self.blocks = nn.Sequential(*[Block(*c) for c in cfg])
        self.drop = nn.Dropout(0.3)
        self.fc = nn.Linear(256, n_classes)

    def forward(self, x):                      # x: (B, 1, WIN)
        x = self.blocks(self.stem(x))
        x = torch.cat([x.mean(-1), x.amax(-1)], 1)
        return self.fc(self.drop(x))


@torch.no_grad()
def predict(model, raw_signal, fs=FS, device="cpu"):
    """Raw ECG array (any length >= ~2 s) at `fs` Hz -> label + probabilities."""
    model.eval()
    x = preprocess(raw_signal, fs)
    w = torch.from_numpy(np.stack(windows(x)))[:, None].to(device)
    p = F.softmax(model(w), 1).mean(0).cpu().numpy()
    return {"label": CLASSES[int(p.argmax())], "probs": {c: float(v) for c, v in zip(CLASSES, p)}}


def load_model(path, device="cpu"):
    ck = torch.load(path, map_location=device)
    m = ECGNet(len(ck["classes"]))
    m.load_state_dict(ck["state_dict"])
    return m.to(device).eval()
