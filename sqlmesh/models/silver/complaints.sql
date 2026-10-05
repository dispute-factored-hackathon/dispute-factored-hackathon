MODEL (
  NAME silver.complaints,
  KIND INCREMENTAL_BY_UNIQUE_KEY (
    unique_key complaint_id,
    lookback 3,
    --batch_size 1,
    disable_restatement false
  ),
  COLUMNS (
    complaint_id VARCHAR(30) PRIMARY KEY,
    creation_date TIMESTAMP NOT NULL,
    process_date DATE NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    case_type VARCHAR(30) NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    reception_channel VARCHAR(30) NOT NULL,
    affected_product_id VARCHAR(20),
    related_branch_id VARCHAR(20),
    origin_interaction_id VARCHAR(30),
    description VARCHAR NOT NULL,
    claimed_amount DECIMAL(15, 2),
    currency VARCHAR(3),
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL,
    assigned_agent_id VARCHAR(20),
    assignment_date TIMESTAMP,
    first_response_date TIMESTAMP,
    resolution_date TIMESTAMP,
    closing_date TIMESTAMP,
    sla_breached BOOLEAN NOT NULL,
    resolution_days INTEGER,
    resolution VARCHAR,
    compensation_granted DECIMAL(15, 2),
    resolution_satisfaction INTEGER,
    is_repeat_complainer BOOLEAN NOT NULL,
    has_first_response_after_resolution BOOLEAN NOT NULL,
    is_future_creation BOOLEAN NOT NULL,
    _source_file VARCHAR(255) NOT NULL,
    _dlt_load_id VARCHAR(64) NOT NULL,
    _dlt_id VARCHAR(64) NOT NULL,
    _processed_at TIMESTAMP WITH TIME ZONE NOT NULL
  ),
  START '2023-06-17',
  CRON '@daily',
  GRAIN (complaint_id)
);

-- Accumulating snapshot: one row per complaint_id, upserted in place as it moves
-- through its lifecycle milestones (creation -> assignment -> first_response ->
-- resolution -> closing). INCREMENTAL_BY_UNIQUE_KEY merges on complaint_id, so a
-- later run that picks up the same case with a newer status simply overwrites
-- the existing row instead of appending a new one.

WITH staged_data AS (
  SELECT
    -- Clean and cast identifier keys
    TRIM(complaint_id) AS complaint_id,
    TRY_CAST(creation_date AS TIMESTAMP) AS creation_date,
    -- Already a DATE in bronze: it comes from the partition folder, not from the CSV
    process_date,
    TRIM(customer_id) AS customer_id,

    -- Normalized categorical fields (NOT NULL)
    @NORMALIZE_STRING(case_type) AS case_type,
    @NORMALIZE_STRING(category) AS category,
    @NORMALIZE_STRING(reception_channel) AS reception_channel,
    @NORMALIZE_STRING(priority) AS priority,
    @NORMALIZE_STRING(status) AS status,

    -- Nullable normalized / free-text / id fields
    NULLIF(@NORMALIZE_STRING(subcategory), '') AS subcategory,
    NULLIF(TRIM(affected_product_id), '') AS affected_product_id,
    NULLIF(TRIM(related_branch_id), '') AS related_branch_id,
    NULLIF(TRIM(origin_interaction_id), '') AS origin_interaction_id,
    NULLIF(TRIM(assigned_agent_id), '') AS assigned_agent_id,
    TRIM(description) AS description,
    NULLIF(TRIM(resolution), '') AS resolution,

    -- Financial fields
    TRY_CAST(claimed_amount AS DECIMAL(15, 2)) AS claimed_amount,
    NULLIF(UPPER(TRIM(currency)), '') AS currency,
    TRY_CAST(compensation_granted AS DECIMAL(15, 2)) AS compensation_granted,

    -- Milestone timestamps (the accumulating snapshot's date columns)
    TRY_CAST(assignment_date AS TIMESTAMP) AS assignment_date,
    TRY_CAST(first_response_date AS TIMESTAMP) AS first_response_date,
    TRY_CAST(resolution_date AS TIMESTAMP) AS resolution_date,
    TRY_CAST(closing_date AS TIMESTAMP) AS closing_date,

    -- Flags and source-provided metrics
    TRY_CAST(sla_breached AS BOOLEAN) AS sla_breached,
    TRY_CAST(resolution_days AS INTEGER) AS resolution_days,
    TRY_CAST(resolution_satisfaction AS INTEGER) AS resolution_satisfaction,
    TRY_CAST(is_repeat_complainer AS BOOLEAN) AS is_repeat_complainer,

    -- Data quality check: first response should not come after resolution
    COALESCE(
      TRY_CAST(first_response_date AS TIMESTAMP) > TRY_CAST(resolution_date AS TIMESTAMP),
      FALSE
    ) AS has_first_response_after_resolution,

    -- Flag, never drop: a complaint cannot be created after the day it was recorded.
    -- Compared date to date so a same-day creation is not flagged.
    COALESCE(TRY_CAST(creation_date AS TIMESTAMP)::DATE > process_date, FALSE) AS is_future_creation,

    -- Lineage
    _source_file,
    _dlt_load_id,
    _dlt_id
  FROM bronze.complaints AS b
  WHERE
    -- Bronze is append-only: a replayed day keeps its older loads. Only the newest
    -- load of each day counts, so rows removed upstream do not linger in silver.
    @LATEST_LOAD(b, 'bronze.complaints', process_date)
    AND process_date BETWEEN @start_date AND @end_date
    AND TRIM(complaint_id) IS NOT NULL
  -- Keep the most advanced state per complaint within the batch (handles the
  -- ~2% source duplicates). Updates across batches are handled by the
  -- INCREMENTAL_BY_UNIQUE_KEY merge on complaint_id, not by this dedup.
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TRIM(complaint_id)
    ORDER BY COALESCE(
      TRY_CAST(closing_date AS TIMESTAMP),
      TRY_CAST(resolution_date AS TIMESTAMP),
      TRY_CAST(first_response_date AS TIMESTAMP),
      TRY_CAST(assignment_date AS TIMESTAMP),
      TRY_CAST(creation_date AS TIMESTAMP)
    ) DESC,
    -- Deterministic tie-breaks: latest day first, then dlt row id
    process_date DESC,
    _dlt_id
  ) = 1
)

SELECT
  complaint_id,
  creation_date,
  process_date,
  customer_id,
  case_type,
  category,
  subcategory,
  reception_channel,
  affected_product_id,
  related_branch_id,
  origin_interaction_id,
  description,
  claimed_amount,
  currency,
  priority,
  status,
  assigned_agent_id,
  assignment_date,
  first_response_date,
  resolution_date,
  closing_date,
  sla_breached,
  resolution_days,
  resolution,
  compensation_granted,
  resolution_satisfaction,
  is_repeat_complainer,
  has_first_response_after_resolution,
  is_future_creation,
  _source_file,
  _dlt_load_id,
  _dlt_id,
  @NOW_IN_BOGOTA_TZ() AS _processed_at
FROM staged_data;