import pandas as pd
import joblib
import numpy as np
from features import prepare_data
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, r2_score

def train_dual_models():
    # Load and sort data chronologically
    df = pd.read_csv("training_data.csv")
    df['dt'] = pd.to_numeric(df['dt'])
    df = df.sort_values('dt')
    
    # Configure Time Series Split
    tscv = TimeSeriesSplit(n_splits=5)
    
    for mode in ["sprinter", "marathoner"]:
        print(f"\n{'='*20}")
        print(f" VALIDATING: {mode.upper()} MODEL")
        print(f"{'='*20}")
        
        # Prepare data for the specific mode
        X, y = prepare_data(df, is_training=True, mode=mode)
        
        fold_maes = []
        fold_r2s = []
        
        # Cross-validation loop
        for i, (train_index, val_index) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_index], X.iloc[val_index]
            y_train, y_val = y.iloc[train_index], y.iloc[val_index]
            
            # Use hyperparameters optimized for time-series
            model = XGBRegressor(
                n_estimators=150,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42
            )
            
            model.fit(X_train, y_train)
            
            preds = model.predict(X_val)
            mae = mean_absolute_error(y_val, preds)
            r2 = r2_score(y_val, preds)
            
            fold_maes.append(mae)
            fold_r2s.append(r2)
            
            print(f" Fold {i+1}: MAE: {mae:.2f} | R2: {r2:.4f}")

        print(f"\n--- {mode.upper()} Final Results ---")
        print(f" Mean MAE: {np.mean(fold_maes):.2f} µg/m³")
        print(f" Mean R2:  {np.mean(fold_r2s):.4f}")
        
        # Train final model on full dataset
        final_model = XGBRegressor(n_estimators=150, max_depth=6, random_state=42)
        final_model.fit(X, y)
        
        # Save the specific model
        model_filename = f'model_{mode}.pkl'
        joblib.dump(final_model, model_filename)
        print(f" Successfully saved to {model_filename}")

        # Optional: Print feature importance to see weather impact
        importances = final_model.feature_importances_
        feature_names = X.columns
        print(f"\nTop 3 Features for {mode}:")
        sorted_idx = np.argsort(importances)[::-1]
        for idx in sorted_idx[:3]:
            print(f" - {feature_names[idx]}: {importances[idx]:.4f}")

if __name__ == "__main__":
    train_dual_models()