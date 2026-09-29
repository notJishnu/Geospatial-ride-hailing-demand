{{ config(materialized='view') }}

select
    cast(calendar_date as date) as calendar_date,
    cast(is_holiday as boolean) as is_holiday,
    cast(holiday_name as varchar) as holiday_name,
    cast(event_name as varchar) as event_name,
    cast(event_borough as varchar) as event_borough,
    cast(event_notes as varchar) as event_notes
from read_parquet('{{ var("calendar_path") }}')
