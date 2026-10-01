# Demand Forecasting — January 2024

The target is valid trip count per known TLC pickup zone and NYC-local hour. The panel inserts zero-count zone-hours, then uses 1, 2, 3, 24, and 168-hour lags plus 24/168-hour trailing means. Every target-derived feature is shifted at least one hour, so it only uses information available at prediction time. Weather inputs are also lagged one hour: actual contemporaneous weather is not used as an oracle feature.

Evaluation is chronological: the final seven days are test, the preceding seven days validation, and earlier records training. Two expanding rolling-origin folds precede final model selection. A full 2–4 week test split is not feasible with the one-month MVP; expand this configuration when more months are ingested.

Models include a trailing 24-hour moving average, same-hour-last-week seasonal naive, StatsForecast AutoETS on the top 10 zones, and global LightGBM with lag, calendar, weather, and holiday fields. MLflow records the local run and artifacts. Metrics are written to ignored `artifacts/demand/metrics.json`.

The one-step prediction assumption is explicit: lagged target features are refreshed as completed hourly demand becomes available. Multi-hour recursive forecasting needs a separate prediction loop and is not represented by this backtest.

## January holdout result

The final seven-day January holdout is retained for one final, unseen comparison. The tracked LightGBM candidate achieved MAE 14.02 trips, RMSE 25.96, WAPE 13.56%, and +6.38% demand bias; the same-hour-last-week baseline achieved MAE 13.87, RMSE 26.41, WAPE 13.42%, and +2.74% bias. The 24-hour moving-average baseline had 41.46% WAPE. LightGBM was better on RMSE but did not beat seasonal naive on the selection criterion (WAPE), so seasonal naive is the current champion. AutoETS is evaluated separately on the top 10 zones; its WAPE is reported as a contextual benchmark only because a one-month history is inadequate for a production statistical model.

The two expanding folds start on 11 and 18 January. LightGBM WAPE is 14.61% and 13.81% respectively; its fold-one seasonal-naive comparison is unstable because just three days of post-warmup history precede that fold. This supports retaining LightGBM as a candidate, not deploying it. On the final holdout the wet slice has 16.30% WAPE versus 12.55% in dry hours; this is an accuracy slice, not causal evidence about weather.
