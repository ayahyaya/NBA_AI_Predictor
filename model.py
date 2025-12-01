import numpy as np
import math
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error


# =====================================================
# CONFIG
# =====================================================

BASE_DIR = Path("NBA CSV's")

POS_TO_COL = {
    "PG": "pg_percent",
    "SG": "sg_percent",
    "SF": "sf_percent",
    "PF": "pf_percent",
    "C":  "c_percent",
}

# Stats we care about
STAT_KEYS = ["pts", "ast", "trb"]

# Features used by the per-minute models
ML_FEATURE_COLS = [
    # Minutes (mp_per_game will be replaced with predicted_new_minutes at inference)
    "mp_per_game",

    # Shooting volume
    "fga_per_game",
    "x3pa_per_game",
    "fta_per_game",

    # Playmaking & rebounds
    "ast_per_game",
    "tov_per_game",
    "orb_per_game",
    "drb_per_game",

    # Opponent difficulty (NEW!)
    "opp_pts_per_game",
    "opp_ast_per_game",
    "opp_trb_per_game",
    "opp_stl_per_game",
    "opp_blk_per_game",
]


# =====================================================
# BASIC HELPERS
# =====================================================

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (
        df.columns.str.lower()
        .str.strip()
        .str.replace(" ", "_")
    )
    return df


def clean_player_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return (
        name.lower()
        .replace("ö", "o")
        .replace("ó", "o")
        .replace(".", "")
        .replace(",", "")
        .strip()
    )


def add_clean_names(df: pd.DataFrame) -> pd.DataFrame:
    df["player_clean"] = df["player"].apply(clean_player_name)
    return df


# =====================================================
# LOADING + MERGING (FINAL VERSION WITH OPPONENT STATS)
# =====================================================

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load the CSVs needed for the model:
      - Player Per Game
      - Player Play By Play (for position %)
      - Team Abbrev (for mapping full name → abbreviation)
      - Opponent Stats Per Game (for defensive difficulty)
    """
    per_game = clean_columns(pd.read_csv(BASE_DIR / "Player Per Game.csv"))
    pbp      = clean_columns(pd.read_csv(BASE_DIR / "Player Play By Play.csv"))
    teams    = clean_columns(pd.read_csv(BASE_DIR / "Team Abbrev.csv"))
    opp      = clean_columns(pd.read_csv(BASE_DIR / "Opponent Stats Per Game.csv"))

    # Ensure required columns exist
    if "team" not in teams.columns or "abbreviation" not in teams.columns:
        raise KeyError("Team Abbrev.csv must contain 'team' and 'abbreviation' columns.")

    # Map full team names → short abbreviations
    team_map = dict(zip(teams["team"], teams["abbreviation"]))

    per_game["team"] = per_game["team"].map(team_map).fillna(per_game["team"])
    pbp["team"]      = pbp["team"].map(team_map).fillna(pbp["team"])
    opp["team"]      = opp["team"].map(team_map).fillna(opp["team"])

    # Convert season to int if it exists
    for df in (per_game, pbp, teams, opp):
        if "season" in df.columns:
            df["season"] = df["season"].astype(int)

    return per_game, pbp, teams, opp



def merge_all() -> pd.DataFrame:
    """
    Build the master dataset:
      - Per Game stats
      - Position shares (from Play By Play)
      - Opponent defensive stats (team-based)
    """
    per_game, pbp, teams, opp = load_data()

    # Merge per game + PBP (position %)
    df = per_game.merge(
        pbp,
        on=["player_id", "season", "team"],
        how="left",
        suffixes=("", "_pbp"),
    )

    # Merge opponent defensive stats
    df = df.merge(
        opp,
        on=["team", "season"],
        how="left",
        suffixes=("", "_opp"),
    )

    # Add cleaned version of player names
    df = add_clean_names(df)

    print("Merged dataset shape:", df.shape)
    return df



# =====================================================
# INJURED PLAYER + MINUTES REDISTRIBUTION
# =====================================================

def get_injured_row(master_df: pd.DataFrame, injured_name: str) -> pd.Series:
    """
    Find the most recent season row for the injured player.
    """
    name_clean = clean_player_name(injured_name)
    subset = master_df[master_df["player_clean"] == name_clean]

    if subset.empty:
        last = injured_name.split()[-1]
        suggestions = master_df[
            master_df["player"].str.contains(last, case=False, na=False)
        ]["player"].unique()[:10]
        raise ValueError(
            f"Player '{injured_name}' not found. Suggestions: {list(suggestions)}"
        )

    # Most recent season
    subset = subset.sort_values("season", ascending=False)
    return subset.iloc[0]


def redistribute_minutes(master_df: pd.DataFrame, injured_name: str) -> pd.DataFrame:
    """
    Take the minutes of the injured player and spread them to teammates
    based on position share (pg_percent, sg_percent, etc).
    Returns a dataframe of teammates with a 'predicted_new_minutes' column.
    """
    injured = get_injured_row(master_df, injured_name)

    team   = injured["team"]
    season = injured["season"]
    pos    = str(injured["pos"]).split("-")[0]  # e.g. "SG-SF" -> "SG"

    pos_col = POS_TO_COL.get(pos, None)
    freed_minutes = injured["mp_per_game"]

    # All teammates that season
    teammates = master_df[
        (master_df["team"] == team)
        & (master_df["season"] == season)
        & (master_df["player_clean"] != injured["player_clean"])
    ].copy()

    if teammates.empty:
        raise ValueError(f"No teammates found for team {team}, season {season}.")

    # Share of minutes based on position % if available
    if pos_col and pos_col in teammates.columns:
        # percentages like 40, 60 etc
        teammates["minute_share"] = teammates[pos_col].fillna(0) / 100.0
        total_share = teammates["minute_share"].sum()

        if total_share <= 0:
            # fallback to equal share
            teammates["minute_share"] = 1.0 / len(teammates)
        else:
            teammates["minute_share"] = teammates["minute_share"] / total_share
    else:
        teammates["minute_share"] = 1.0 / len(teammates)

    teammates["predicted_new_minutes"] = (
        teammates["mp_per_game"] + freed_minutes * teammates["minute_share"]
    )

    # Keep useful columns only
    keep_cols = list(
        dict.fromkeys(  # keep order, drop dupes
            ["player", "player_id", "team", "season", "pos",
             "mp_per_game", "predicted_new_minutes"]
            + ML_FEATURE_COLS
            + [f"{k}_per_game" for k in STAT_KEYS]
        )
    )

    existing_cols = [c for c in keep_cols if c in teammates.columns]
    return teammates[existing_cols].reset_index(drop=True)


# =====================================================
# TRAINING TABLE + PER-MINUTE MODELS
# =====================================================

def build_training_table(master_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a training table where the targets are per-minute stats.
    We train on normal games and later scale by predicted minutes.
    """
    df = master_df.copy()

    # Reasonable filters
    if "g" in df.columns:
        df = df[df["g"] >= 10]
    df = df[df["mp_per_game"] > 5]  # ignore junk minutes

    # Need all features + stats
    needed = ML_FEATURE_COLS + [f"{k}_per_game" for k in STAT_KEYS]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns in training data: {missing}")

    df = df.dropna(subset=needed)

    # Targets: per-minute rates
    for k in STAT_KEYS:
        per_game_col = f"{k}_per_game"
        df[f"{k}_per_min"] = df[per_game_col] / df["mp_per_game"]

    return df


def train_ml_models(master_df: pd.DataFrame):
    """
    Train RandomForest models to predict pts/ast/trb per minute.
    Also compute residual standard deviations for over/under probabilities.
    """
    train_df = build_training_table(master_df)

    X = train_df[ML_FEATURE_COLS]

    models: Dict[str, RandomForestRegressor] = {}
    error_std: Dict[str, float] = {}

    for k in STAT_KEYS:
        y = train_df[f"{k}_per_min"]

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        model = RandomForestRegressor(
            n_estimators=250,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_val)
        mse = mean_squared_error(y_val, y_pred)
        rmse = math.sqrt(mse)

        models[k] = model
        error_std[k] = rmse

        print(f"RMSE per-minute ({k}): {rmse:.5f}")

    return models, error_std


# =====================================================
# PREDICTION PIPELINE
# =====================================================

def normal_cdf(x: float) -> float:
    """Standard normal CDF using erf (no SciPy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def add_over_under_probabilities(
    df: pd.DataFrame,
    lines: Dict[str, float],
    error_std: Dict[str, float],
) -> pd.DataFrame:
    """
    For each stat where you supply a line, add a column like 'prob_pts_over'
    based on a normal distribution around the model prediction.
    """
    df = df.copy()

    for k in STAT_KEYS:
        line = lines.get(k)
        if line is None:
            continue

        pred_col = f"final_{k}"
        if pred_col not in df.columns:
            continue

        sigma = error_std.get(k, 0.5)  # fallback sigma

        # Avoid zero sigma
        if sigma <= 0:
            sigma = 0.5

        # P(X > line) for each row
        z = (line - df[pred_col]) / sigma
        prob_over = 1.0 - normal_cdf(z)
        df[f"prob_{k}_over"] = prob_over

    return df


def predict_replacement_stats(
    master_df: pd.DataFrame,
    models: Dict[str, RandomForestRegressor],
    injured_name: str,
) -> pd.DataFrame:
    """
    1. Redistribute minutes from the injured player.
    2. Predict per-minute stats for each teammate.
    3. Scale by predicted_new_minutes to get full-game stats.
    """
    base = redistribute_minutes(master_df, injured_name)

    if base.empty:
        return base

    # Build feature matrix, but replace mp_per_game with predicted_new_minutes
    X_new = base.copy()
    for col in ML_FEATURE_COLS:
        if col not in X_new.columns:
            X_new[col] = 0.0

    X_new["mp_per_game"] = base["predicted_new_minutes"]

    X_feat = X_new[ML_FEATURE_COLS]

    # Predictions
    out = base[["player", "team", "season", "predicted_new_minutes"]].copy()

    for k in STAT_KEYS:
        model = models[k]
        per_min_pred = model.predict(X_feat)  # stat per minute
        out[f"final_{k}"] = per_min_pred * base["predicted_new_minutes"]

    # Sort by minutes (most important replacements first)
    out = out.sort_values("predicted_new_minutes", ascending=False).reset_index(drop=True)
    return out


# =====================================================
# PUBLIC ENTRY POINT (USED BY DISCORD BOT)
# =====================================================

# These will be populated at import time
MASTER_DF: Optional[pd.DataFrame] = None
MODELS: Dict[str, RandomForestRegressor] = {}
ERROR_STD: Dict[str, float] = {}


def _init_if_needed():
    global MASTER_DF, MODELS, ERROR_STD
    if MASTER_DF is not None and MODELS:
        return

    MASTER_DF = merge_all()
    MODELS, ERROR_STD = train_ml_models(MASTER_DF)


def run_prediction(
    injured_name: str,
    opponent_abbrev: Optional[str] = None,  # kept for compatibility, not used in option 1
    lines: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Main function the Discord bot calls.

    Parameters
    ----------
    injured_name : str
        Name of the injured player ("Dennis Schroder").
    opponent_abbrev : str | None
        Kept for later (option 2). Ignored in this simple version.
    lines : dict | None
        Optional. Example: {"pts": 14.5, "ast": 4.5, "trb": 3.5}

    Returns
    -------
    pandas.DataFrame with columns:
      player, team, season, predicted_new_minutes,
      final_pts, final_ast, final_trb,
      and (if lines given) prob_pts_over, prob_ast_over, prob_trb_over.
    """
    _init_if_needed()

    df_base = predict_replacement_stats(MASTER_DF, MODELS, injured_name)

    if df_base.empty:
        return df_base

    if lines:
        df_full = add_over_under_probabilities(df_base, lines, ERROR_STD)
    else:
        df_full = df_base

    return df_full


# =====================================================
# CLI TEST (optional)
# =====================================================

if __name__ == "__main__":
    # Example quick test
    test_lines = {"pts": 14.5, "ast": 4.5, "trb": 3.5}
    df_test = run_prediction("Dennis Schroder", opponent_abbrev=None, lines=test_lines)
    print(
        df_test[
            [
                "player",
                "predicted_new_minutes",
                "final_pts",
                "final_ast",
                "final_trb",
                "prob_pts_over",
                "prob_ast_over",
                "prob_trb_over",
            ]
        ].head(5)
    )
