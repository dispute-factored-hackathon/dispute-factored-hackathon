MODEL (
  NAME silver.call_transcripts,
  KIND INCREMENTAL_BY_TIME_RANGE (
    time_column process_date,
    lookback 3
  ),
  COLUMNS (
    transcript_id VARCHAR(30) PRIMARY KEY,
    interaction_id VARCHAR(30) NOT NULL,
    process_date DATE NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    agent_id VARCHAR(20),
    full_text VARCHAR NOT NULL,
    customer_text VARCHAR,
    agent_text VARCHAR,
    detected_language VARCHAR(10) NOT NULL,
    detected_accent VARCHAR(50),
    accent_confidence DECIMAL(3, 2),
    detected_keywords VARCHAR(50)[],
    mentioned_entities JSON,
    detected_intents VARCHAR(300),
    main_topics VARCHAR(20),
    transcription_model VARCHAR(50) NOT NULL,
    audio_quality VARCHAR(20),
    duration_seconds UINTEGER,
    _source_file VARCHAR(255) NOT NULL,
    _dlt_load_id VARCHAR(64) NOT NULL,
    _dlt_id VARCHAR(64) NOT NULL,
    _processed_at TIMESTAMP WITH TIME ZONE NOT NULL
  ),
  START '2023-06-17',
  CRON '@daily',
  GRAIN (transcript_id)
);

-- LOOKBACK reprocesses the last 3 days on every run, so transcripts that
-- arrive late against process_date still get merged into the right partition
-- instead of being silently dropped.

WITH staged_data AS (
  SELECT
    -- Clean and cast identifier keys
    TRIM(transcript_id) AS transcript_id,
    TRIM(interaction_id) AS interaction_id,
    -- Already a DATE in bronze: it comes from the partition folder, not from the CSV
    process_date,
    TRIM(customer_id) AS customer_id,
    NULLIF(TRIM(agent_id), '') AS agent_id,

    -- full_text / agent_text are passed through as-is, no cleaning applied
    full_text,
    NULLIF(TRIM(customer_text), '') AS customer_text,
    agent_text,

    -- Language / accent detection fields
    @NORMALIZE_STRING(detected_language) AS detected_language,
    @NORMALIZE_STRING(detected_accent) AS detected_accent,
    TRY_CAST(accent_confidence AS DECIMAL(3, 2)) AS accent_confidence,

    -- Normalize the whole CSV string first (macro applied once, outside any
    -- CASE/lambda), then split into an array; NULL/empty collapses to NULL
    -- because STRING_SPLIT(NULL, ',') is NULL in DuckDB.
    STRING_SPLIT(
      NULLIF(@NORMALIZE_STRING(REGEXP_REPLACE(TRIM(detected_keywords), ',\s*', ',', 'g')), ''),
      ','
    ) AS detected_keywords,

    -- Keep as native JSON; the contract already validates its object shape
    TRY_CAST(NULLIF(TRIM(mentioned_entities), '') AS JSON) AS mentioned_entities,

    NULLIF(TRIM(detected_intents), '') AS detected_intents,

    -- @NORMALIZE_STRING is applied afterwards in the outer SELECT.
    CASE TRIM(main_topics)
      WHEN 'Técnico' THEN 'Technical'
      WHEN 'Transaccional' THEN 'Transactional'
      WHEN 'Retención' THEN 'Retention'
      WHEN 'Producto' THEN 'Product'
      WHEN 'Comercial' THEN 'Commercial'
      WHEN 'Queja' THEN 'Complaint'
      ELSE TRIM(main_topics)
    END AS main_topics,

    @NORMALIZE_STRING(transcription_model) AS transcription_model,
    @NORMALIZE_STRING(audio_quality) AS audio_quality,
    TRY_CAST(duration_seconds AS UINTEGER) AS duration_seconds,

    -- Flag, never drop: a transcript cannot be recorded after today. Transcripts have
    -- no timestamp of their own, so process_date is the only date to bound.
    -- Compared date to date so a transcript from today is not flagged.
    COALESCE(process_date > CURRENT_DATE, FALSE) AS is_future_process_date,

    -- Lineage
    _source_file,
    _dlt_load_id,
    _dlt_id
  FROM bronze.call_transcripts AS b
  WHERE
    -- Bronze is append-only: a replayed day keeps its older loads. Only the newest
    -- load of each day counts, so rows removed upstream do not linger in silver.
    @LATEST_LOAD(b, 'bronze.call_transcripts', process_date)
    AND process_date BETWEEN @start_date AND @end_date
    AND TRIM(transcript_id) IS NOT NULL
  -- _dlt_id is the deterministic tie-break between duplicated transcript_ids
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TRIM(transcript_id)
    ORDER BY process_date DESC, _dlt_id
  ) = 1
)

SELECT
  transcript_id,
  interaction_id,
  process_date,
  customer_id,
  agent_id,
  full_text,
  customer_text,
  agent_text,
  detected_language,
  detected_accent,
  accent_confidence,
  detected_keywords,
  mentioned_entities,
  detected_intents,
  @NORMALIZE_STRING(main_topics) AS main_topics,
  transcription_model,
  audio_quality,
  duration_seconds,
  _source_file,
  _dlt_load_id,
  _dlt_id,
  @NOW_IN_BOGOTA_TZ() AS _processed_at
FROM staged_data;