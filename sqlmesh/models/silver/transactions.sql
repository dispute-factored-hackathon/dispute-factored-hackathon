MODEL (
  NAME silver.transactions,
  KIND INCREMENTAL_BY_TIME_RANGE (
    time_column process_date,
    lookback 3
  ),
  COLUMNS (
    transaction_id VARCHAR(30) PRIMARY KEY,
    transaction_date TIMESTAMP NOT NULL,
    process_date DATE NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    transaction_category VARCHAR(50),
    amount DECIMAL(15, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount_usd DECIMAL(15, 2),
    channel VARCHAR(30) NOT NULL,
    branch_id VARCHAR(20),
    merchant_name VARCHAR(150),
    merchant_category VARCHAR(50),
    transaction_country VARCHAR(50) NOT NULL,
    transaction_city VARCHAR(100),
    transaction_status VARCHAR(20) NOT NULL,
    response_code VARCHAR(10),
    is_fraud BOOLEAN NOT NULL,
    fraud_score DECIMAL(5, 2),
    transaction_location POINT_2D NOT NULL,
    is_future_transaction BOOLEAN NOT NULL,
    _source_file VARCHAR(255) NOT NULL,
    _dlt_load_id VARCHAR(64) NOT NULL,
    _dlt_id VARCHAR(64) NOT NULL,
    _processed_at TIMESTAMP WITH TIME ZONE NOT NULL
  ),
  START '2023-06-17',
  CRON '@daily',
  GRAIN (transaction_id)
);

WITH staged_data AS (
  SELECT
    -- Clean and cast identifier keys
    TRIM(transaction_id) AS transaction_id,
    TRY_CAST(transaction_date AS TIMESTAMP) AS transaction_date,
    -- Already a DATE in bronze: it comes from the partition folder, not from the CSV
    process_date,
    TRIM(product_id) AS product_id,
    TRIM(customer_id) AS customer_id,
    
    -- Clean accents and normalize text fields
    @NORMALIZE_STRING(transaction_type) AS transaction_type,
    NULLIF(@NORMALIZE_STRING(transaction_category), '') AS transaction_category,
    
    -- Numerical and financial metrics
    TRY_CAST(amount AS DECIMAL(15, 2)) AS amount,
    UPPER(TRIM(currency)) AS currency,
    TRY_CAST(amount_usd AS DECIMAL(15, 2)) AS amount_usd,
    
    -- Channels and locations
    @NORMALIZE_STRING(channel) AS channel,
    NULLIF(TRIM(branch_id), '') AS branch_id,
    NULLIF(@NORMALIZE_STRING(merchant_name), '') AS merchant_name,
    NULLIF(@NORMALIZE_STRING(merchant_category), '') AS merchant_category,
    @NORMALIZE_STRING(transaction_country) AS transaction_country,
    NULLIF(@NORMALIZE_STRING(transaction_city), '') AS transaction_city,
    
    -- Status and validation flags
    @NORMALIZE_STRING(transaction_status) AS transaction_status,
    NULLIF(UPPER(TRIM(response_code)), '') AS response_code,
    TRY_CAST(is_fraud AS BOOLEAN) AS is_fraud,
    TRY_CAST(fraud_score AS DECIMAL(5, 2)) AS fraud_score,
    -- ST_POINT takes (x, y) = (longitude, latitude)
    ST_POINT(TRY_CAST(longitude AS DECIMAL(10, 7)), TRY_CAST(latitude AS DECIMAL(10, 7))) AS transaction_location,

    -- Flag, never drop: a transaction cannot happen after the day it was recorded.
    -- Compared date to date so a same-day transaction is not flagged.
    COALESCE(TRY_CAST(transaction_date AS TIMESTAMP)::DATE > process_date, FALSE) AS is_future_transaction,

    -- Lineage
    _source_file,
    _dlt_load_id,
    _dlt_id
  FROM bronze.transactions AS b
  WHERE
    -- Bronze is append-only: a replayed day keeps its older loads. Only the newest
    -- load of each day counts, so rows removed upstream do not linger in silver.
    @LATEST_LOAD(b, 'bronze.transactions', process_date)
    AND process_date BETWEEN @start_date AND @end_date
    AND TRIM(transaction_id) IS NOT NULL
  -- The source injects ~2 % duplicates; _dlt_id is the deterministic tie-break
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TRIM(transaction_id)
    ORDER BY TRY_CAST(transaction_date AS TIMESTAMP) DESC, _dlt_id
  ) = 1
)

SELECT
  transaction_id,
  transaction_date,
  process_date,
  product_id,
  customer_id,
  transaction_type,
  transaction_category,
  amount,
  currency,
  amount_usd,
  channel,
  branch_id,
  merchant_name,
  merchant_category,
  transaction_country,
  transaction_city,
  transaction_status,
  response_code,
  is_fraud,
  fraud_score,
  transaction_location,
  is_future_transaction,
  _source_file,
  _dlt_load_id,
  _dlt_id,
  @NOW_IN_BOGOTA_TZ() AS _processed_at
FROM staged_data;