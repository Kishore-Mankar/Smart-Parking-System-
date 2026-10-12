"""
ml_models.py  –  Parking occupancy prediction using multiple ML algorithms.
Models: Random Forest, Decision Tree, Linear Regression, SVM
"""

import numpy as np
import json
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.tree import DecisionTreeRegressor
from sklearn.linear_model import LinearRegression
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ── Synthetic Training Data Generator ────────────────────────────────────────

def _generate_training_data(n_samples: int = 5000):
    """Generate realistic parking occupancy training data."""
    np.random.seed(42)

    hours        = np.random.randint(0, 24, n_samples)
    days         = np.random.randint(0, 7, n_samples)
    months       = np.random.randint(1, 13, n_samples)
    is_holiday   = np.random.choice([0, 1], n_samples, p=[0.92, 0.08])
    lot_ids      = np.random.randint(1, 6, n_samples)

    occupancy = np.zeros(n_samples)
    for i in range(n_samples):
        h, d, m, hol = hours[i], days[i], months[i], is_holiday[i]

        # Base by hour (rush-hour bell curves)
        if   7  <= h <= 9:  base = 70 + np.random.normal(0, 8)
        elif 10 <= h <= 12: base = 80 + np.random.normal(0, 7)
        elif 12 <= h <= 14: base = 85 + np.random.normal(0, 6)
        elif 14 <= h <= 17: base = 75 + np.random.normal(0, 8)
        elif 17 <= h <= 19: base = 88 + np.random.normal(0, 5)
        elif 19 <= h <= 21: base = 65 + np.random.normal(0, 10)
        elif 22 <= h or h <= 5: base = 20 + np.random.normal(0, 8)
        else:               base = 50 + np.random.normal(0, 10)

        # Weekend effect
        if d >= 5:   base += 10
        # Holiday effect
        if hol:      base -= 25
        # Month seasonality
        if m in [11, 12, 1]: base += 8
        if m in [5, 6, 7]:   base += 5

        occupancy[i] = np.clip(base, 0, 100)

    X = np.column_stack([hours, days, months, is_holiday, lot_ids])
    y = occupancy
    return X, y


# ── ParkingPredictor Class ─────────────────────────────────────────────────

class ParkingPredictor:
    MODELS = {
        'random_forest':   RandomForestRegressor(n_estimators=150, random_state=42, n_jobs=-1),
        'decision_tree':   DecisionTreeRegressor(max_depth=10, random_state=42),
        'linear_regression': LinearRegression(),
        'svm':             SVR(kernel='rbf', C=100, gamma=0.1, epsilon=0.1),
    }
    MODEL_LABELS = {
        'random_forest':     'Random Forest',
        'decision_tree':     'Decision Tree',
        'linear_regression': 'Linear Regression',
        'svm':               'SVM (RBF)',
    }

    def __init__(self):
        self.trained_models  = {}
        self.scaler          = StandardScaler()
        self.metrics         = {}
        self._metrics_file   = os.path.join(os.path.dirname(__file__), 'data', 'metrics.json')
        os.makedirs(os.path.dirname(self._metrics_file), exist_ok=True)
        self._load_metrics()

    # ── Training ──────────────────────────────────────────────────────────

    def train_all_models(self) -> dict:
        X, y = _generate_training_data(6000)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42)

        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s  = self.scaler.transform(X_test)

        self.metrics = {}
        for name, model in self.MODELS.items():
            # SVM & Linear Regression need scaled data; trees don't, but it's fine
            use_scaled = name in ('svm', 'linear_regression')
            Xtr = X_train_s if use_scaled else X_train
            Xte = X_test_s  if use_scaled else X_test

            model.fit(Xtr, y_train)
            preds = model.predict(Xte)

            mae  = float(mean_absolute_error(y_test, preds))
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
            r2   = float(r2_score(y_test, preds))
            acc  = float(max(0, 100 - mae))  # simple accuracy proxy

            self.trained_models[name] = model
            self.metrics[name] = {
                'label':    self.MODEL_LABELS[name],
                'mae':      round(mae,  2),
                'rmse':     round(rmse, 2),
                'r2':       round(r2,   4),
                'accuracy': round(acc,  2),
            }

        self._save_metrics()
        return self.metrics

    # ── Prediction ────────────────────────────────────────────────────────

    def predict(self, lot_id: int, hour: int, day_of_week: int, month: int,
                is_holiday: int, total_spots: int,
                model_name: str = 'random_forest') -> dict:

        if model_name not in self.trained_models:
            self.train_all_models()

        model = self.trained_models[model_name]
        X = np.array([[hour, day_of_week, month, is_holiday, lot_id]])
        use_scaled = model_name in ('svm', 'linear_regression')
        Xin = self.scaler.transform(X) if use_scaled else X

        raw = float(model.predict(Xin)[0])
        occ = round(np.clip(raw, 0, 100), 1)

        occupied   = int(occ / 100 * total_spots)
        available  = max(0, total_spots - occupied)
        status     = self._status(occ)

        # Confidence as 100 – model MAE (fallback 85)
        mae  = self.metrics.get(model_name, {}).get('mae', 15)
        conf = round(min(99, max(60, 100 - mae)), 1)

        return {
            'occupancy_pct':  occ,
            'occupied_spots': occupied,
            'available_spots': available,
            'total_spots':    total_spots,
            'status':         status,
            'status_color':   self._status_color(status),
            'confidence':     conf,
            'model_name':     model_name,
            'model_label':    self.MODEL_LABELS.get(model_name, model_name),
        }

    def get_predictions_all_models(self, lot_id, hour, day_of_week, month,
                                   is_holiday, total_spots) -> list:
        if not self.trained_models:
            self.train_all_models()
        return [
            {**self.predict(lot_id, hour, day_of_week, month, is_holiday,
                            total_spots, name), 'model_key': name}
            for name in self.MODELS
        ]

    # ── Metrics ───────────────────────────────────────────────────────────

    def get_model_metrics(self) -> dict:
        if not self.metrics:
            self._load_metrics()
        if not self.metrics:
            self.train_all_models()
        return self.metrics

    # ── Private Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _status(pct: float) -> str:
        if pct < 50:   return 'Available'
        if pct < 75:   return 'Moderate'
        if pct < 90:   return 'Busy'
        return 'Full'

    @staticmethod
    def _status_color(status: str) -> str:
        return {'Available': '#22c55e', 'Moderate': '#f59e0b',
                'Busy': '#f97316', 'Full': '#ef4444'}.get(status, '#64748b')

    def _save_metrics(self):
        try:
            with open(self._metrics_file, 'w') as f:
                json.dump(self.metrics, f)
        except Exception:
            pass

    def _load_metrics(self):
        try:
            if os.path.exists(self._metrics_file):
                with open(self._metrics_file) as f:
                    self.metrics = json.load(f)
        except Exception:
            self.metrics = {}
