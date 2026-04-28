import pandas as pd
import joblib
import numpy as np
from features import prepare_data
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, r2_score


def train_model():
    df = pd.read_csv("training_data.csv")
    
    df['dt'] = pd.to_numeric(df['dt'])
    df = df.sort_values('dt')
    
    X, y = prepare_data(df, is_training=True)
    
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_maes = []
    fold_r2s = []
    
    print(f"Time-Series Cross-Validation")
    
    for i, (train_index, val_index) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_index], X.iloc[val_index]
        y_train, y_val = y.iloc[train_index], y.iloc[val_index]
        
        n_train = len(train_index)
        n_val = len(val_index)
        
        model = XGBRegressor(
                    n_estimators=150,       
                    max_depth=5,            
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
        
        print(f" Fold {i+1}: [Train: {n_train} rows | Val: {n_val} rows] -> MAE: {mae:.2f} | R2: {r2:.4f}")

    print("\n--- Final Performance ---")
    print(f"Mean MAE: {np.mean(fold_maes):.2f} $µg/m³$")
    print(f"Mean R2:  {np.mean(fold_r2s):.4f}")
    
    
    print("\n Training final model on full dataset...")
    final_model = XGBRegressor(n_estimators=100, max_depth=10, random_state=42)
    final_model.fit(X, y)
    
    importances = final_model.feature_importances_
    feature_names = X.columns


    for name, importance in zip(feature_names, importances):
        print(f"Feature: {name:12} | Importance: {importance:.4f}")

    joblib.dump(final_model, 'model.pkl')
    print("model saved to model.pkl")

if __name__ == "__main__":
    train_model()