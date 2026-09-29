# Demand Forecasting — January 2024

The target is valid trip count per known TLC pickup zone and NYC-local hour. The panel inserts zero-count zone-hours, then uses 1, 2, 3, 24, and 168-hour lags plus 24/168-hour trailing means. Every target-derived feature is shifted at least one hour, so it only uses information available at prediction time.

Evaluation is chronological: the final seven days are test, the preceding seven days validation, and earlier records training. A full 2–4 week test split is not feasible with the one-month MVP; expand this configuration when more months are ingested.

Models include same-hour-last-week seasonal naive; StatsForecast AutoETS on the top 10 zones; and global LightGBM with lag, calendar, weather, and holiday fields. MLflow records the local run and artifacts. Metrics are written to ignored `artifacts/demand/metrics.json`.

The one-step prediction assumption is explicit: lagged target features are refreshed as completed hourly demand becomes available. Multi-hour recursive forecasting needs a separate prediction loop and is not represented by this backtest.

## Initial result

On the final seven-day January holdout, LightGBM achieved MAE 13.50 trips, RMSE 25.52, WAPE 13.06%, and a +5.35% demand bias. The seasonal-naive baseline achieved MAE 13.87, RMSE 26.41, WAPE 13.42%, and +2.74% bias. AutoETS was evaluated separately on the top 10 zones and performed materially worse (WAPE 74.19%); this small one-month context is insufficient for treating that benchmark as production-ready. Slice metrics by hour, wet/dry status, and training-volume tier are saved with the run.

The wet holdout slice had 15.37% WAPE versus 12.20% in dry hours. This is an accuracy slice, not evidence that weather causes forecasting error.
