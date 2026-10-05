MODEL (
  NAME silver.call_center_interactions,
  KIND INCREMENTAL_BY_TIME_RANGE (
    time_column process_date,
    lookback 3
  ),
  COLUMNS (
    interaction_id VARCHAR(30) PRIMARY KEY,
    interaction_date TIMESTAMP NOT NULL,
    process_date DATE NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    agent_id VARCHAR(20),
    interaction_type VARCHAR(30) NOT NULL,
    channel VARCHAR(30) NOT NULL,
    contact_reason VARCHAR(100) NOT NULL,
    reason_category VARCHAR(50) NOT NULL,
    duration_seconds UINTEGER,
    wait_time_seconds UINTEGER,
    was_resolved BOOLEAN,
    requires_followup BOOLEAN NOT NULL,
    detected_sentiment VARCHAR(20),
    sentiment_score DECIMAL(3, 2),
    customer_detected_accent VARCHAR(50),
    agent_used_accent VARCHAR(50),
    was_escalated BOOLEAN NOT NULL,
    mentioned_products VARCHAR(20)[],
    has_transcript BOOLEAN NOT NULL,
    has_recording BOOLEAN NOT NULL,
    _source_file VARCHAR(255) NOT NULL,
    _dlt_load_id VARCHAR(64) NOT NULL,
    _dlt_id VARCHAR(64) NOT NULL,
    _processed_at TIMESTAMP WITH TIME ZONE NOT NULL
  ),
  START '2023-06-17',
  CRON '@daily',
  GRAIN (interaction_id)
);

-- LOOKBACK reprocesses the last 3 days on every run, so interactions that
-- arrive late against process_date still get merged into the right partition
-- instead of being silently dropped.

WITH staged_data AS (
  SELECT
    -- Clean and cast identifier keys
    TRIM(interaction_id) AS interaction_id,
    TRY_CAST(interaction_date AS TIMESTAMP) AS interaction_date,
    -- Already a DATE in bronze: it comes from the partition folder, not from the CSV
    process_date,
    TRIM(customer_id) AS customer_id,
    NULLIF(TRIM(agent_id), '') AS agent_id,

    -- Normalize enum / descriptive text fields
    @NORMALIZE_STRING(interaction_type) AS interaction_type,
    @NORMALIZE_STRING(channel) AS channel,
    @NORMALIZE_STRING(contact_reason) AS contact_reason,

    -- reason_category arrives in a mix of English and Spanish; translate the
    -- Spanish variants to their English equivalent so downstream consumers
    -- see a single vocabulary.
    @NORMALIZE_STRING(
      CASE TRIM(reason_category)
        WHEN 'Técnico' THEN 'Technical'
        WHEN 'Transaccional' THEN 'Transactional'
        WHEN 'Retención' THEN 'Retention'
        WHEN 'Producto' THEN 'Product'
        WHEN 'Comercial' THEN 'Commercial'
        WHEN 'Queja' THEN 'Complaint'
        ELSE TRIM(reason_category)
      END
    ) AS reason_category,

    -- Numerical metrics
    TRY_CAST(duration_seconds AS UINTEGER) AS duration_seconds,
    TRY_CAST(wait_time_seconds AS UINTEGER) AS wait_time_seconds,

    -- Boolean flags
    TRY_CAST(was_resolved AS BOOLEAN) AS was_resolved,
    TRY_CAST(requires_followup AS BOOLEAN) AS requires_followup,

    -- detected_sentiment arrives in a mix of English and Spanish; translate
    -- the Spanish variants to their English equivalent.
    NULLIF(
      @NORMALIZE_STRING(
        CASE TRIM(detected_sentiment)
          WHEN 'Negativo' THEN 'Negative'
          WHEN 'Muy Negativo' THEN 'Very Negative'
          WHEN 'Positivo' THEN 'Positive'
          WHEN 'Muy Positivo' THEN 'Very Positive'
          ELSE TRIM(detected_sentiment)
        END
      ),
      ''
    ) AS detected_sentiment,

    TRY_CAST(sentiment_score AS DECIMAL(3, 2)) AS sentiment_score,
    NULLIF(@NORMALIZE_STRING(customer_detected_accent), '') AS customer_detected_accent,
    NULLIF(@NORMALIZE_STRING(agent_used_accent), '') AS agent_used_accent,
    TRY_CAST(was_escalated AS BOOLEAN) AS was_escalated,
    -- Split the CSV list of product_ids into an array; NULL/empty stays NULL
    CASE
      WHEN NULLIF(TRIM(mentioned_products), '') IS NULL THEN NULL
      ELSE LIST_TRANSFORM(STRING_SPLIT(TRIM(mentioned_products), ','), x -> TRIM(x))
    END AS mentioned_products,
    TRY_CAST(has_transcript AS BOOLEAN) AS has_transcript,
    TRY_CAST(has_recording AS BOOLEAN) AS has_recording,
    COALESCE(TRY_CAST(interaction_date AS TIMESTAMP)::DATE > process_date, FALSE) AS is_future_interaction,

    -- Lineage
    _source_file,
    _dlt_load_id,
    _dlt_id
  FROM bronze.call_center_interactions AS b
  WHERE
    -- Bronze is append-only: a replayed day keeps its older loads. Only the newest
    -- load of each day counts, so rows removed upstream do not linger in silver.
    @LATEST_LOAD(b, 'bronze.call_center_interactions', process_date)
    AND process_date BETWEEN @start_date AND @end_date
    AND TRIM(interaction_id) IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TRIM(interaction_id)
    ORDER BY TRY_CAST(interaction_date AS TIMESTAMP) DESC, _dlt_id
  ) = 1
)

SELECT
  interaction_id,
  interaction_date,
  process_date,
  customer_id,
  agent_id,
  interaction_type,
  channel,
  contact_reason,
  reason_category,
  duration_seconds,
  wait_time_seconds,
  was_resolved,
  requires_followup,
  detected_sentiment,
  sentiment_score,
  customer_detected_accent,
  agent_used_accent,
  was_escalated,
  mentioned_products,
  has_transcript,
  has_recording,
  is_future_interaction,
  _source_file,
  _dlt_load_id,
  _dlt_id,
  @NOW_IN_BOGOTA_TZ() AS _processed_at
FROM staged_data;