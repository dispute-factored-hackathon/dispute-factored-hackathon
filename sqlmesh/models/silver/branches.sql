MODEL (
  NAME silver.branches,
  KIND FULL,
  COLUMNS (
    branch_id VARCHAR(20) NOT NULL,
    branch_code VARCHAR(20) NOT NULL,
    branch_name VARCHAR(100) NOT NULL,
    branch_type VARCHAR(20) NOT NULL,
    address VARCHAR(200) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    country VARCHAR(50) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    geographic_zone VARCHAR(20) NOT NULL,
    phone VARCHAR(30),
    email VARCHAR(100),
    opening_time TIME NOT NULL,
    closing_time TIME NOT NULL,
    has_atms BOOLEAN NOT NULL,
    atm_count UTINYINT,
    has_teller_windows BOOLEAN NOT NULL,
    teller_window_count UTINYINT,
    branch_location POINT_2D NOT NULL,
    branch_opening_date DATE NOT NULL,
    branch_status VARCHAR(30) NOT NULL,
    is_future_opening BOOLEAN NOT NULL,
    version_number INTEGER NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN NOT NULL,
    snapshot_ts DATE NOT NULL,
    _source_file VARCHAR(255) NOT NULL,
    _dlt_load_id VARCHAR(64) NOT NULL,
    _dlt_id VARCHAR(64) NOT NULL,
    _processed_at TIMESTAMP WITH TIME ZONE NOT NULL
  ),
  GRAIN (branch_id, valid_from)
);

-- SCD2 dimension. KIND FULL rebuilds the whole history from every photo on each
-- run, so the result is deterministic and independent of the order the photos
-- were loaded in -- a late backfill of an older photo lands in the right place.
-- The gateway is chosen at plan time (--gateway), so the model does not pin one.
--
-- Validity is driven by snapshot_ts, the business date of the photo, never by a
-- column from the source: one row per branch per version, not per photo.
-- branch_code is NOT declared UNIQUE: every version of a branch repeats it.

WITH staged_data AS (
  SELECT
    -- Clean identifier keys
    TRIM(branch_id) AS branch_id,
    TRIM(branch_code) AS branch_code,

    -- Descriptive text fields (English-only, normalized for casing/accents)
    @NORMALIZE_STRING(branch_name) AS branch_name,
    @NORMALIZE_STRING(branch_type) AS branch_type,
    @NORMALIZE_STRING(address) AS address,
    @NORMALIZE_STRING(city) AS city,
    @NORMALIZE_STRING(state) AS state,
    @NORMALIZE_STRING(country) AS country,
    TRIM(postal_code) AS postal_code,

    -- geographic_zone arrives in a mix of English and Spanish; translate the
    -- Spanish variants to their English equivalent. @NORMALIZE_STRING is a
    -- SQLMesh macro, so it's applied afterwards, in the next CTE.
    CASE TRIM(geographic_zone)
      WHEN 'Urbana' THEN 'Urban'
      WHEN 'Suburbana' THEN 'Suburban'
      ELSE TRIM(geographic_zone)
    END AS geographic_zone,

    -- Contact fields (nullable). Email is lowercased rather than uppercased, so
    -- a re-delivery that only changes its casing does not open a new version.
    NULLIF(TRIM(phone), '') AS phone,
    NULLIF(LOWER(TRIM(email)), '') AS email,

    -- Opening hours as TIME
    TRY_CAST(TRIM(opening_time) AS TIME) AS opening_time,
    TRY_CAST(TRIM(closing_time) AS TIME) AS closing_time,

    -- Boolean flags and non-negative counts
    TRY_CAST(TRIM(has_atms) AS BOOLEAN) AS has_atms,
    TRY_CAST(TRIM(atm_count) AS UTINYINT) AS atm_count,
    TRY_CAST(TRIM(has_teller_windows) AS BOOLEAN) AS has_teller_windows,
    TRY_CAST(TRIM(teller_window_count) AS UTINYINT) AS teller_window_count,

    -- Geolocation. The point is assembled at the end, from these two values:
    -- change detection compares the numbers, not the geometry.
    TRY_CAST(TRIM(latitude) AS DECIMAL(10, 7)) AS latitude,
    TRY_CAST(TRIM(longitude) AS DECIMAL(10, 7)) AS longitude,

    -- Dates and status
    TRY_CAST(TRIM(branch_opening_date) AS DATE) AS branch_opening_date,
    @NORMALIZE_STRING(branch_status) AS branch_status,

    -- Business date of the photo, stamped at load time from --snapshot-date
    b.snapshot_ts,
    TRIM(_source_file) AS _source_file,
    _dlt_load_id,
    _dlt_id
  FROM bronze.branches AS b
  WHERE
    TRIM(branch_id) IS NOT NULL
    -- Bronze is append-only: a re-delivered photo adds a new load and the newest one wins
    AND @LATEST_LOAD(b, 'bronze.branches', snapshot_ts)
),

flagged AS (
  SELECT
    * EXCLUDE (geographic_zone),
    @NORMALIZE_STRING(geographic_zone) AS geographic_zone,

    -- Impossible dates are kept and flagged, never dropped or imputed.
    -- Date to date: a branch opening on the photo's own day is valid.
    COALESCE(branch_opening_date > snapshot_ts, FALSE) AS is_future_opening
  FROM staged_data
),

deduplicated AS (
  -- Guard against source duplicates: one row per branch WITHIN each photo.
  -- _processed_at is a single CURRENT_TIMESTAMP per load, so it cannot break ties
  -- here; prefer trustworthy rows, then fall back to _dlt_id so the winner is
  -- deterministic across rebuilds.
  SELECT *
  FROM flagged
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_ts, branch_id
    ORDER BY
      is_future_opening ASC,
      _dlt_id ASC
  ) = 1
),

change_detection AS (
  -- A new version opens on a branch's first photo, or when any business attribute
  -- differs from the previous photo. The comparison is explicit, one line per
  -- attribute: adding or deleting a column is a single visible edit here, and
  -- nothing silently joins or leaves the comparison.
  -- snapshot_ts, the flag and the _ metadata are deliberately absent, so a new
  -- delivery of unchanged data never opens a version.
  -- IS DISTINCT FROM never returns NULL, so this chain is always TRUE or FALSE
  -- and needs no CASE to guard against three-valued logic.
  SELECT
    *,
    (
      LAG(snapshot_ts) OVER previous_photo IS NULL
      OR branch_code IS DISTINCT FROM LAG(branch_code) OVER previous_photo
      OR branch_name IS DISTINCT FROM LAG(branch_name) OVER previous_photo
      OR branch_type IS DISTINCT FROM LAG(branch_type) OVER previous_photo
      OR address IS DISTINCT FROM LAG(address) OVER previous_photo
      OR city IS DISTINCT FROM LAG(city) OVER previous_photo
      OR state IS DISTINCT FROM LAG(state) OVER previous_photo
      OR country IS DISTINCT FROM LAG(country) OVER previous_photo
      OR postal_code IS DISTINCT FROM LAG(postal_code) OVER previous_photo
      OR geographic_zone IS DISTINCT FROM LAG(geographic_zone) OVER previous_photo
      OR phone IS DISTINCT FROM LAG(phone) OVER previous_photo
      OR email IS DISTINCT FROM LAG(email) OVER previous_photo
      OR opening_time IS DISTINCT FROM LAG(opening_time) OVER previous_photo
      OR closing_time IS DISTINCT FROM LAG(closing_time) OVER previous_photo
      OR has_atms IS DISTINCT FROM LAG(has_atms) OVER previous_photo
      OR atm_count IS DISTINCT FROM LAG(atm_count) OVER previous_photo
      OR has_teller_windows IS DISTINCT FROM LAG(has_teller_windows) OVER previous_photo
      OR teller_window_count IS DISTINCT FROM LAG(teller_window_count) OVER previous_photo
      OR latitude IS DISTINCT FROM LAG(latitude) OVER previous_photo
      OR longitude IS DISTINCT FROM LAG(longitude) OVER previous_photo
      OR branch_opening_date IS DISTINCT FROM LAG(branch_opening_date) OVER previous_photo
      OR branch_status IS DISTINCT FROM LAG(branch_status) OVER previous_photo
    ) AS is_new_version
  FROM deduplicated
  WINDOW previous_photo AS (PARTITION BY branch_id ORDER BY snapshot_ts)
),

versioned AS (
  SELECT
    *,
    SUM(is_new_version::INTEGER) OVER (
      PARTITION BY branch_id
      ORDER BY snapshot_ts
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )::INTEGER AS version_number
  FROM change_detection
),

one_row_per_version AS (
  -- One row per version, taken from its most recent photo, so the row carries the
  -- latest metadata and flag. first_seen_snapshot_ts is the photo that opened it.
  SELECT
    *,
    MIN(snapshot_ts) OVER (PARTITION BY branch_id, version_number) AS first_seen_snapshot_ts
  FROM versioned
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY branch_id, version_number
    ORDER BY snapshot_ts DESC
  ) = 1
),

history AS (
  SELECT
    *,
    -- The first version is backdated to the branch's opening date, which is real
    -- history that predates the first photo. An opening date after the photo is
    -- not trustworthy, so that version starts at the photo instead of backdating.
    CASE
      WHEN version_number = 1 AND branch_opening_date <= first_seen_snapshot_ts
        THEN branch_opening_date
      ELSE first_seen_snapshot_ts
    END AS valid_from,

    -- A version ends where the next one opens; the newest version stays open.
    LEAD(first_seen_snapshot_ts) OVER (
      PARTITION BY branch_id
      ORDER BY version_number
    ) AS valid_to
  FROM one_row_per_version
)

SELECT
  branch_id,
  branch_code,
  branch_name,
  branch_type,
  address,
  city,
  state,
  country,
  postal_code,
  geographic_zone,
  phone,
  email,
  opening_time,
  closing_time,
  has_atms,
  atm_count,
  has_teller_windows,
  teller_window_count,
  -- Single geographic point built from the validated lat/long pair, same
  -- pattern as silver.transactions.transaction_location.
  ST_POINT(longitude, latitude)::POINT_2D AS branch_location,
  branch_opening_date,
  branch_status,
  is_future_opening,
  version_number,
  valid_from,
  valid_to,
  valid_to IS NULL AS is_current,
  snapshot_ts,
  _source_file,
  _dlt_load_id,
  _dlt_id,
  @NOW_IN_BOGOTA_TZ() AS _processed_at
FROM history;