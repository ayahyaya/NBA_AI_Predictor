import pandas as pd
from model import merge_all, train_ml_models, predict_replacement_stats

# ============================
# 1) Load full dataset
# ============================
df = merge_all()

print("\nAll seasons available:", df["season"].unique())
print("Merged dataset shape:", df.shape)

# ============================
# 2) TEMPORARY FILTER: only 2024 + 2025
# ============================
recent_df = df[df["season"].isin([2024, 2025])]

print("\nOriginal dataset:", df.shape)
print("Recent-only dataset:", recent_df.shape)

# If too small, exit
if len(recent_df) < 300:
    print("\n❌ Not enough 2024–2025 data to train a model.")
    exit()

# ============================
# 3) Train TEMPORARY MODELS (not saved)
# ============================
models, error_std = train_ml_models(recent_df)

print("\nTemporary recent-season models trained successfully!\n")

# ============================
# 4) Run prediction manually (bypass run_prediction)
# ============================
injured_name = "Marcus Smart"

print(f"\nPredicting replacements for: {injured_name}\n")

output = predict_replacement_stats(recent_df, models, injured_name)

print(output.head(10))
