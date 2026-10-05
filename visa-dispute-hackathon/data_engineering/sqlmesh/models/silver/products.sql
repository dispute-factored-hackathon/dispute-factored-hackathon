MODEL (
  name silver.products,
  kind FULL,
  grain (product_id, valid_from),
  dialect duckdb
);

-- Monthly-snapshot dimension, same pattern as silver.customers: rebuilds the whole
-- product history from every photo in bronze on each run. Sorting by snapshot_ts makes
-- the result independent of the order the photos were loaded in.
--
-- Every business column drives versions, including balances and activity counters
-- (current_balance, days_past_due, last_transaction_date): a product whose balance
-- moved between photos gets a new version. Only last_updated, the flags, snapshot_ts
-- and the _ metadata are excluded.
WITH source AS (
  -- Latest load per photo (re-deliveries append a new load; the newest one wins)
  SELECT *
  FROM bronze.products AS p
  WHERE @LATEST_LOAD(p, 'bronze.products', snapshot_ts)
),

typed AS (
  SELECT
    TRIM(product_id) AS product_id,
    TRIM(customer_id) AS customer_id,
    TRIM(product_number) AS product_number,
    TRIM(opening_branch_id) AS opening_branch_id,

    -- product_type arrives in a mix of English and Spanish; the Spanish variants are
    -- translated to their English equivalent before normalizing
    @NORMALIZE_STRING(
      CASE TRIM(product_type)
        WHEN 'Cuenta Ahorro' THEN 'Savings Account'
        WHEN 'Cuenta Corriente' THEN 'Checking Account'
        WHEN 'Inversión' THEN 'Investment'
        WHEN 'Préstamo Hipotecario' THEN 'Mortgage'
        WHEN 'Préstamo Personal' THEN 'Personal Loan'
        WHEN 'Seguro' THEN 'Insurance'
        WHEN 'Tarjeta Crédito' THEN 'Credit Card'
        WHEN 'Tarjeta Débito' THEN 'Debit Card'
        ELSE TRIM(product_type)
      END
    ) AS product_type,

    @NORMALIZE_STRING(currency) AS currency,
    @NORMALIZE_STRING(product_status) AS product_status,
    @NORMALIZE_STRING(opening_channel) AS opening_channel,

    TRY_CAST(TRIM(credit_limit) AS DECIMAL(15,2)) AS credit_limit,
    TRY_CAST(TRIM(interest_rate) AS DECIMAL(5,2)) AS interest_rate,
    TRY_CAST(TRIM(opening_date) AS DATE) AS opening_date,
    TRY_CAST(TRIM(expiration_date) AS DATE) AS expiration_date,
    TRY_CAST(TRIM(has_linked_app) AS BOOLEAN) AS has_linked_app,

    TRY_CAST(TRIM(current_balance) AS DECIMAL(15,2)) AS current_balance,
    TRY_CAST(TRIM(days_past_due) AS UINTEGER) AS days_past_due,
    TRY_CAST(TRIM(last_transaction_date) AS TIMESTAMP) AS last_transaction_date,

    TRY_CAST(TRIM(last_updated) AS TIMESTAMP) AS last_updated,
    snapshot_ts,
    _dlt_load_id,
    _dlt_id,
    _source_file
  FROM source
  WHERE TRIM(product_id) IS NOT NULL
),

flagged AS (
  -- Flags are computed against each row's own snapshot, date to date, so a same-day
  -- update on the snapshot date is NOT considered future. Impossible dates are kept
  -- and flagged, never dropped or imputed
  SELECT
    *,
    last_updated::DATE > snapshot_ts AS is_future_last_updated,
    COALESCE(opening_date > snapshot_ts, FALSE) AS is_future_opening,
    last_transaction_date::DATE > snapshot_ts AS is_future_last_transaction,
    COALESCE(expiration_date < opening_date, FALSE) AS is_invalid_expiration,
    -- Clamp impossible timestamps to the end of the snapshot day, for ranking only
    LEAST(last_updated, (snapshot_ts + 1)::TIMESTAMP - INTERVAL 1 MICROSECOND) AS effective_updated_at
  FROM typed
),

deduplicated AS (
  -- One row per photo and product: trustworthy dates first, then the most recent clamped
  -- update; if every copy is flagged the least implausible date wins; _dlt_id breaks
  -- remaining ties (it is stored in bronze, so the winner is always the same row)
  SELECT *
  FROM flagged
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_ts, product_id
    ORDER BY
      is_future_last_updated ASC,
      effective_updated_at DESC,
      last_updated ASC,
      _dlt_id ASC
  ) = 1
),

with_change AS (
  -- A new version starts when any business attribute changes versus the previous photo.
  -- The comparison is explicit, one line per attribute: adding or deleting a column is a
  -- single visible edit here, and nothing silently joins or leaves the comparison.
  -- last_updated, the flags, snapshot_ts and the _ metadata are deliberately absent, so
  -- a changed timestamp alone never opens a new version.
  SELECT
    *,
    (
      LAG(product_id) OVER previous_photo IS NULL -- product's first photo
      OR customer_id IS DISTINCT FROM LAG(customer_id) OVER previous_photo
      OR product_type IS DISTINCT FROM LAG(product_type) OVER previous_photo
      OR product_number IS DISTINCT FROM LAG(product_number) OVER previous_photo
      OR currency IS DISTINCT FROM LAG(currency) OVER previous_photo
      OR credit_limit IS DISTINCT FROM LAG(credit_limit) OVER previous_photo
      OR interest_rate IS DISTINCT FROM LAG(interest_rate) OVER previous_photo
      OR opening_date IS DISTINCT FROM LAG(opening_date) OVER previous_photo
      OR expiration_date IS DISTINCT FROM LAG(expiration_date) OVER previous_photo
      OR opening_branch_id IS DISTINCT FROM LAG(opening_branch_id) OVER previous_photo
      OR product_status IS DISTINCT FROM LAG(product_status) OVER previous_photo
      OR opening_channel IS DISTINCT FROM LAG(opening_channel) OVER previous_photo
      OR has_linked_app IS DISTINCT FROM LAG(has_linked_app) OVER previous_photo
      OR current_balance IS DISTINCT FROM LAG(current_balance) OVER previous_photo
      OR days_past_due IS DISTINCT FROM LAG(days_past_due) OVER previous_photo
      OR last_transaction_date IS DISTINCT FROM LAG(last_transaction_date) OVER previous_photo
    )::INTEGER AS is_new_version
  FROM deduplicated
  WINDOW previous_photo AS (PARTITION BY product_id ORDER BY snapshot_ts)
),

with_version AS (
  SELECT
    *,
    SUM(is_new_version) OVER (PARTITION BY product_id ORDER BY snapshot_ts)::INTEGER AS version_number
  FROM with_change
),

versions AS (
  -- Keep the latest photo of each version, so the version shows the latest metadata and flags
  SELECT
    *,
    MIN(snapshot_ts) OVER (PARTITION BY product_id, version_number) AS version_snapshot_ts
  FROM with_version
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY product_id, version_number ORDER BY snapshot_ts DESC
  ) = 1
),

validity AS (
  SELECT
    *,
    -- Validity follows snapshot_ts, never last_updated. Only a first version opened on
    -- or before its photo is backdated to the opening date, which is real history that
    -- predates the first photo
    CASE
      WHEN version_number = 1 AND opening_date <= version_snapshot_ts
        THEN opening_date
      ELSE version_snapshot_ts
    END AS valid_from,
    LEAD(version_snapshot_ts) OVER (
      PARTITION BY product_id ORDER BY version_number
    ) AS valid_to
  FROM versions
)

SELECT
  product_id,
  customer_id,
  product_type,
  product_number,
  currency,
  current_balance,
  credit_limit,
  interest_rate,
  opening_date,
  expiration_date,
  opening_branch_id,
  product_status,
  opening_channel,
  has_linked_app,
  days_past_due,
  last_transaction_date,
  last_updated,
  is_future_last_updated,
  is_future_opening,
  is_future_last_transaction,
  is_invalid_expiration,
  version_number,
  valid_from,
  valid_to,
  valid_to IS NULL AS is_current,
  snapshot_ts,
  _dlt_load_id,
  _source_file
FROM validity