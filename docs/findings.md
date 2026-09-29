# January 2024 Gold-Layer Findings

These are descriptive findings from one month of cleaned NYC HVFHV data. They are not causal claims and should be re-evaluated as new monthly partitions arrive.

1. **Demand peaks at 18:00 local time.** The geographic zone-hour mart recorded 1,217,419 trips at that hour across January, making it the strongest first candidate for pre-positioning analysis.
2. **Zone 132 generated the most mapped pickup demand.** It had 374,150 trips after excluding unknown/outside-NYC pickup zones. Zone labels and map interpretation should be used in the dashboard rather than treating a zone centroid as a precise pickup coordinate.
3. **Rainy zone-hours had longer observed waits.** The average wait was 261.0 seconds in wet hours versus 252.0 seconds in dry hours. This is an observational comparison, not evidence that precipitation caused the difference.
4. **Sharing was uncommon in this January sample.** 3.73% of trips were requested as shared and 1.16% were matched. That distinction matters: a shared request does not necessarily become a matched shared ride.
5. **Base-fare economics show a sizeable residual after driver pay.** Total base passenger fares were $470.95M and driver pay was $359.13M, leaving a $111.83M approximate residual (23.75% of base fares). This is not verified platform profit: tolls, taxes, incentives, operations, and fields outside the approximation are excluded.

Additional coverage note: 741,513 valid trips had an unknown/outside-NYC endpoint (zone 264 or 265). They remain in `fct_trips` but are excluded from geographic demand and OD marts to avoid misleading maps and zone features.
