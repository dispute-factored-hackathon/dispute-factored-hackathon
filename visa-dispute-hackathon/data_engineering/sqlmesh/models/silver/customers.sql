MODEL (
  name silver.customers,
  kind FULL,
  grain (customer_id, valid_from),
  dialect duckdb
);

-- Rebuilds the whole customer history from every photo in bronze on each run.
-- Sorting by snapshot_ts makes the result independent of the order the photos were loaded in.
WITH source AS (
  -- Latest load per photo (re-deliveries append a new load; the newest one wins)
  SELECT *
  FROM bronze.customers AS c
  WHERE @LATEST_LOAD(c, 'bronze.customers', snapshot_ts)
),

typed AS (
  SELECT
    TRIM(customer_id) AS customer_id,
    TRIM(document_number) AS document_number,
    @NORMALIZE_STRING(document_type) AS document_type,
    @NORMALIZE_STRING(first_name) AS first_name,
    @NORMALIZE_STRING(last_name) AS last_name,
    TRY_CAST(TRIM(date_of_birth) AS DATE) AS date_of_birth,
    @NORMALIZE_STRING(gender) AS gender,
    LOWER(TRIM(email)) AS email,
    TRIM(mobile_phone) AS mobile_phone,
    TRIM(landline_phone) AS landline_phone,
    @NORMALIZE_STRING(address) AS address,
    @NORMALIZE_STRING(city) AS city,
    @NORMALIZE_STRING(state) AS state,
    @NORMALIZE_STRING(country) AS country,
    TRIM(postal_code) AS postal_code,
    @NORMALIZE_STRING(detected_accent) AS detected_accent,
    TRIM(segment) AS segment,
    TRY_CAST(TRIM(credit_score) AS INTEGER) AS credit_score,
    TRY_CAST(TRIM(estimated_monthly_income) AS DECIMAL(12,2)) AS estimated_monthly_income,
    @NORMALIZE_STRING(occupation) AS occupation,
    @NORMALIZE_STRING(marital_status) AS marital_status,
    @NORMALIZE_STRING(education_level) AS education_level,
    TRIM(registration_branch_id) AS registration_branch_id,
    @NORMALIZE_STRING(customer_status) AS customer_status,
    TRY_CAST(TRIM(accepts_marketing) AS BOOLEAN) AS accepts_marketing,
    TRY_CAST(TRIM(registration_date) AS TIMESTAMP) AS registration_date,
    TRY_CAST(TRIM(last_updated) AS TIMESTAMP) AS last_updated,
    snapshot_ts,
    _dlt_load_id,
    _dlt_id,
    _source_file
  FROM source
),

flagged AS (
  -- Flags are computed against each row's own snapshot, date to date,
  -- so a same-day update on the snapshot date is NOT considered future
  SELECT
    *,
    last_updated::DATE > snapshot_ts AS is_future_last_updated,
    registration_date::DATE > snapshot_ts AS is_future_registration,
    -- Clamp impossible timestamps to the end of the snapshot day (rows are kept, never imputed)
    LEAST(last_updated, (snapshot_ts + 1)::TIMESTAMP - INTERVAL 1 MICROSECOND) AS effective_updated_at
  FROM typed
),

deduplicated AS (
  -- One row per photo and customer: trustworthy dates first, then the most recent clamped
  -- update; if every copy is flagged the least implausible date wins; _dlt_id breaks
  -- remaining ties (it is stored in bronze, so the winner is always the same row)
  SELECT *
  FROM flagged
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_ts, customer_id
    ORDER BY
      is_future_last_updated ASC,
      effective_updated_at DESC,
      last_updated ASC,
      _dlt_id ASC
  ) = 1
),

with_change AS (
  -- A new version starts only when a business attribute changes versus the previous photo.
  -- The comparison is explicit, one line per attribute: adding or deleting a column is a
  -- single visible edit here, and nothing silently joins or leaves the comparison.
  -- last_updated, the flags, snapshot_ts and the _ metadata are deliberately absent, so a
  -- changed timestamp alone never opens a new version.
  SELECT
    *,
    (
      LAG(customer_id) OVER previous_photo IS NULL -- customer's first photo
      OR document_number IS DISTINCT FROM LAG(document_number) OVER previous_photo
      OR document_type IS DISTINCT FROM LAG(document_type) OVER previous_photo
      OR first_name IS DISTINCT FROM LAG(first_name) OVER previous_photo
      OR last_name IS DISTINCT FROM LAG(last_name) OVER previous_photo
      OR date_of_birth IS DISTINCT FROM LAG(date_of_birth) OVER previous_photo
      OR gender IS DISTINCT FROM LAG(gender) OVER previous_photo
      OR email IS DISTINCT FROM LAG(email) OVER previous_photo
      OR mobile_phone IS DISTINCT FROM LAG(mobile_phone) OVER previous_photo
      OR landline_phone IS DISTINCT FROM LAG(landline_phone) OVER previous_photo
      OR address IS DISTINCT FROM LAG(address) OVER previous_photo
      OR city IS DISTINCT FROM LAG(city) OVER previous_photo
      OR state IS DISTINCT FROM LAG(state) OVER previous_photo
      OR country IS DISTINCT FROM LAG(country) OVER previous_photo
      OR postal_code IS DISTINCT FROM LAG(postal_code) OVER previous_photo
      OR detected_accent IS DISTINCT FROM LAG(detected_accent) OVER previous_photo
      OR segment IS DISTINCT FROM LAG(segment) OVER previous_photo
      OR credit_score IS DISTINCT FROM LAG(credit_score) OVER previous_photo
      OR estimated_monthly_income IS DISTINCT FROM LAG(estimated_monthly_income) OVER previous_photo
      OR occupation IS DISTINCT FROM LAG(occupation) OVER previous_photo
      OR marital_status IS DISTINCT FROM LAG(marital_status) OVER previous_photo
      OR education_level IS DISTINCT FROM LAG(education_level) OVER previous_photo
      OR registration_branch_id IS DISTINCT FROM LAG(registration_branch_id) OVER previous_photo
      OR customer_status IS DISTINCT FROM LAG(customer_status) OVER previous_photo
      OR accepts_marketing IS DISTINCT FROM LAG(accepts_marketing) OVER previous_photo
      OR registration_date IS DISTINCT FROM LAG(registration_date) OVER previous_photo
    )::INTEGER AS is_new_version
  FROM deduplicated
  WINDOW previous_photo AS (PARTITION BY customer_id ORDER BY snapshot_ts)
),

with_version AS (
  SELECT
    *,
    SUM(is_new_version) OVER (PARTITION BY customer_id ORDER BY snapshot_ts) AS version_number
  FROM with_change
),

versions AS (
  -- Keep the latest photo of each version, so the version shows the latest metadata and flags
  SELECT
    *,
    MIN(snapshot_ts) OVER (PARTITION BY customer_id, version_number) AS version_snapshot_ts
  FROM with_version
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id, version_number ORDER BY snapshot_ts DESC
  ) = 1
),

validity AS (
  SELECT
    *,
    -- Validity follows snapshot_ts, never last_updated. Only a first version registered
    -- on or before its photo is backdated to the registration date
    CASE
      WHEN version_number = 1 AND last_updated::DATE <= version_snapshot_ts
        THEN last_updated::DATE
      ELSE version_snapshot_ts
    END AS valid_from,
    LEAD(version_snapshot_ts) OVER (
      PARTITION BY customer_id ORDER BY version_number
    ) AS valid_to
  FROM versions
)

SELECT
  customer_id,
  document_number,
  document_type,
  first_name,
  last_name,
  date_of_birth,
  gender,
  email,
  mobile_phone,
  landline_phone,
  address,
  city,
  state,
  country,
  postal_code,
  detected_accent,
  segment,
  credit_score,
  estimated_monthly_income,
  occupation,
  marital_status,
  education_level,
  registration_branch_id,
  customer_status,
  accepts_marketing,
  registration_date,
  last_updated,
  is_future_last_updated,
  is_future_registration,
  version_number,
  valid_from,
  valid_to,
  valid_to IS NULL AS is_current,
  snapshot_ts,
  _dlt_load_id,
  _source_file
FROM validity