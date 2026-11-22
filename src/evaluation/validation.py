"""Leave-one-material-out validation: every test material is unseen."""
from __future__ import annotations

from typing import Callable

import numpy as np


def leave_one_material_out(make: Callable, X: np.ndarray, y: np.ndarray, groups: np.ndarray,
                           n_classes: int = 2) -> np.ndarray:
    pred = np.empty(len(y), int)
    for material in np.unique(groups):
        test = groups == material
        train = ~test
        if len(np.unique(y[train])) < 2:
            pred[test] = np.bincount(y[train]).argmax()
            continue
        pred[test] = make().fit(X[train], y[train], n_classes).predict(X[test])
    return pred


def confusion(y: np.ndarray, pred: np.ndarray) -> np.ndarray:
    matrix = np.zeros((2, 2), int)
    for truth, guess in zip(y, pred):
        matrix[truth, guess] += 1
    return matrix
