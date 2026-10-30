# ECG 1-D CNN classifier

This folder contains the model definition and the Colab training notebook. The
FastAPI runtime copies the same preprocessing and architecture in
`backend/fastapi/app/ml/ecg_cnn.py`; the two must stay in sync.

```
ml/
  ecg_core.py          preprocessing + ECGNet + predict/load_model (shared with Colab)
  ecg_train.ipynb      PhysioNet/CinC 2017 training notebook (N / A / O / ~)
  README.md            this file
  ecg_model.pt         NOT in the repository - export it from the notebook
```

## 1. Export the checkpoint

Run `ecg_train.ipynb` on a GPU runtime. The final cell saves:

```python
torch.save({
    "state_dict": best_state,
    "classes": ["N", "A", "O", "~"],
    "fs": 300,
    "win": 9000,
    "name": "ecg-cnn-physionet2017",   # optional, recommended
    "version": "1.0.0",                # optional, recommended
}, "ecg_model.pt")
```

Copy the file into this folder (`ml/ecg_model.pt`) or anywhere the API can read.

## 2. Install the optional ML runtime

The telemetry API starts without PyTorch; the classifier reports itself as
unavailable until the runtime and a checkpoint are present.

```bash
cd backend/fastapi

# Option A - simplest (PyTorch may pull CUDA libraries on Linux):
.venv/bin/pip install -r requirements-ml.txt

# Option B - CPU-only, much smaller:
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
.venv/bin/pip install numpy==2.2.6 scipy==1.15.3
```

## 3. Point the API at the checkpoint

In the repository-root `.env`:

```dotenv
ECG_MODEL_PATH=ml/ecg_model.pt
ECG_MODEL_DEVICE=cpu          # or cuda / mps
ECG_MAX_WINDOWS=8             # cap the CNN passes per analysis
```

Relative paths are tried from the process working directory and then from the
repository root, so `ECG_MODEL_PATH=ml/ecg_model.pt` works whether uvicorn is
started from `backend/fastapi` or from the repository root. An absolute path is
still the least surprising choice:

```dotenv
ECG_MODEL_PATH=/home/you/Projects/AI-Based-ECG-Diagnostic-Assistant/ml/ecg_model.pt
```

Restart FastAPI, then check:

```bash
curl http://127.0.0.1:8001/health
# analysis.inference_available should be true
```

## 4. How the pipeline uses it

`POST /sessions/<id>/analysis`:

1. `app/dsp.py` validates the chunks and computes heart rate, RR intervals and
   signal quality.
2. `app/analysis.py` joins the raw samples into one trace and calls
   `app/inference.py`.
3. `app/ml/ecg_cnn.py` resamples to 300 Hz, applies the 0.5-40 Hz band-pass,
   z-scores, scores up to `ECG_MAX_WINDOWS` 30-second windows and averages the
   softmax.
4. The result (classes, predicted label, probabilities, confidence, window
   count, model name/version/SHA-256) is stored in
   `analysis_results.analysis` and in the queryable `ml_predictions` table.
5. `app/ai/advisory.py` packages the measurements + classification into the
   advisor input contract and calls the configured provider.
6. The advisory is stored alongside the analysis and rendered in the UI, the
   report PDF and `GET /sessions/<id>/ml-predictions`.

The live monitor (`GET .../analysis/live`) deliberately skips the CNN and the
advisor so a 4-second poll does not run a model or spend API quota.

## 5. Classes and labels

| Code | Label | Meaning |
| --- | --- | --- |
| `N` | Normal rhythm | Predominantly normal rhythm pattern |
| `A` | Atrial fibrillation pattern | Pattern associated with AF |
| `O` | Other rhythm | Neither normal nor AF |
| `~` | Noisy / unreadable | Model cannot classify reliably |

The model is a **screening aid**, not a diagnosis. The API never invents a
class or probability when the checkpoint is missing, malformed or the signal is
unusable; it returns `available: false` with a reason.

## 6. Replacing the model later

Any checkpoint with the same `ECGNet` state-dict keys and a `classes` list works.
If the architecture changes, update `app/ml/ecg_cnn.py` and the training
notebook together, then bump the model `version` so stored analyses remain
traceable.

## 7. Troubleshooting

| Symptom | Cause |
| --- | --- |
| `PyTorch is not installed` | Install `backend/fastapi/requirements-ml.txt`. |
| `configured ECG model file was not found` | `ECG_MODEL_PATH` is wrong or relative to a different working directory. |
| `does not match the ECGNet 1-D CNN architecture` | The checkpoint was saved from a different model class. |
| `inference_available: false` in `/health` | Check `analysis.inference_reason`; it names the exact failure. |
| Predictions look random | The checkpoint is untrained or was trained for a different sampling rate/class order. |
