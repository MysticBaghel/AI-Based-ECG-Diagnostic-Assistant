"""ECG machine-learning runtime.

The heavy imports (PyTorch, NumPy, SciPy) live only in :mod:`app.ml.ecg_cnn`.
:mod:`app.ml.taxonomy` is dependency-free so the API can describe the classes
and stay up when the ML runtime is not installed.
"""
