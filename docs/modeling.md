# Demand Forecasting — January 2024

The target is valid trip count per known TLC pickup zone and NYC-local hour. The panel inserts zero-count zone-hours, then uses 1, 2, 3, 24, and 168-hour lags plus 24/168-hour trailing means. Every target-derived feature is shifted at least one hour, so it only uses information available at prediction time. Weather inputs are also lagged one hour: actual contemporaneous weather is not used as an oracle feature.

Evaluation is chronological: the final seven days are test, the preceding seven days validation, and earlier records training. Two expanding rolling-origin folds precede final model selection. A full 2–4 week test split is not feasible with the one-month MVP; expand this configuration when more months are ingested.

Models include a trailing 24-hour moving average, same-hour-last-week seasonal naive, StatsForecast AutoETS on the top 10 zones, and global LightGBM with lag, calendar, weather, and holiday fields. MLflow records the local run and artifacts. Metrics are written to ignored `artifacts/demand/metrics.json`.

The one-step prediction assumption is explicit: lagged target features are refreshed as completed hourly demand becomes available. Multi-hour recursive forecasting needs a separate prediction loop and is not represented by this backtest.

## January holdout result

The final seven-day January holdout is retained for one final, unseen comparison. The tracked LightGBM candidate achieved MAE 14.02 trips, RMSE 25.96, WAPE 13.56%, and +6.38% demand bias; the same-hour-last-week baseline achieved MAE 13.87, RMSE 26.41, WAPE 13.42%, and +2.74% bias. The 24-hour moving-average baseline had 41.46% WAPE. LightGBM was better on RMSE but did not beat seasonal naive on the selection criterion (WAPE), so seasonal naive is the current champion. AutoETS is evaluated separately on the top 10 zones; its WAPE is reported as a contextual benchmark only because a one-month history is inadequate for a production statistical model.

The two expanding folds start on 11 and 18 January. LightGBM WAPE is 14.61% and 13.81% respectively; its fold-one seasonal-naive comparison is unstable because just three days of post-warmup history precede that fold. This supports retaining LightGBM as a candidate, not deploying it. On the final holdout the wet slice has 16.30% WAPE versus 12.55% in dry hours; this is an accuracy slice, not causal evidence about weather.

## ETA model — January 2024

The ETA target is `actual_trip_seconds`. Feature generation is deliberately pre-trip: pickup/dropoff zone, request-time calendar and weather fields, plus OD/pickup/city aggregate distance, speed, and duration computed only through the preceding completed hour. Actual `trip_miles` is never a model input. Cold-start OD pairs use pickup-zone history, then citywide history.

The one-month MVP uses the first 17 days for training, the next 7 days for tuning, and the final 7 days as an untouched test. A deterministic hash sample keeps Optuna laptop-friendly while the final test remains complete. Baselines are historical OD duration and historical-distance divided by historical speed. Results, SHAP global importance, and one local explanation are written under ignored `artifacts/eta/` and logged to local MLflow. Cross-borough reporting is only a bridge/tunnel proxy; it does not establish a route's infrastructure.

On the complete 4,385,663-trip final holdout, the tuned LightGBM model achieved MAE **224.47 seconds** (3.74 minutes), MAPE **24.83%**, median absolute error **160.15 seconds**, P90 absolute error **465.52 seconds**, 38.98% within two minutes, and 76.65% within five minutes. It improves on the historical-OD-duration baseline's 264.63-second MAE; the historical-distance/pickup-speed baseline has 407.68-second MAE. LightGBM is therefore the MAE-selected January candidate and has been registered locally as `nyc_eta_lightgbm`, version 1. SHAP ranks historical OD duration, historical OD distance, and pickup hour as the three most influential features. These results are a one-month MVP benchmark, not evidence of performance across seasons or future months.
