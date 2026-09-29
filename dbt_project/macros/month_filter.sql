{% macro month_filter(column_name) %}
  {% set target_month = var('target_month', none) %}
  {% if target_month is not none %}
    {{ column_name }} = '{{ target_month }}'
  {% elif is_incremental() %}
    {{ column_name }} > (select coalesce(max(ingestion_month), '0000-00') from {{ this }})
  {% else %}
    true
  {% endif %}
{% endmacro %}
