MODEL (
  name silver.service_agents,
  kind FULL,
  grain (agent_id, valid_from),
  dialect duckdb
);

-- Monthly-snapshot dimension, same pattern as silver.customers: rebuilds the whole
-- agent history from every photo in bronze on each run. Sorting by snapshot_ts makes
-- the result independent of the order the photos were loaded in.
--
-- There is no last_updated column in the source, so snapshot_ts is the only driver of
-- validity and of the within-photo dedup order.
--
-- avg_csat and total_monthly_interactions take part in change detection: they are part
-- of the agent's monthly state, so a month where a metric moves opens a new version and
-- the history keeps the metric each version was observed with.
--
-- employee_code is NOT a reliable key: the same code can be reused across different
-- agent_id values. It is kept and exposed through has_duplicated_employee_code, a
-- per-photo flag. agent_id is the only business key.
WITH source AS (
  -- Latest load per photo (re-deliveries append a new load; the newest one wins)
  SELECT *
  FROM bronze.service_agents AS a
  WHERE @LATEST_LOAD(a, 'bronze.service_agents', snapshot_ts)
),

typed AS (
  SELECT
    TRIM(agent_id) AS agent_id,
    TRIM(employee_code) AS employee_code,
    @NORMALIZE_STRING(first_name) AS first_name,
    @NORMALIZE_STRING(last_name) AS last_name,
    -- Email is lowercased, so a re-delivery that only changes its casing opens no version
    LOWER(TRIM(email)) AS email,
    NULLIF(TRIM(phone), '') AS phone,
    @NORMALIZE_STRING(native_accent) AS native_accent,
    @NORMALIZE_STRING(country_of_origin) AS country_of_origin,
    NULLIF(TRIM(assigned_branch_id), '') AS assigned_branch_id,
    @NORMALIZE_STRING(agent_type) AS agent_type,
    @NORMALIZE_STRING(experience_level) AS experience_level,
    @NORMALIZE_STRING(agent_status) AS agent_status,
    @NORMALIZE_STRING(work_shift) AS work_shift,

    -- Comma-separated list to array, with the Spanish language names translated.
    -- The macro runs on the whole string before the split: macros are not expanded
    -- inside a lambda, so the lambda only trims and translates.
    CASE
      WHEN NULLIF(TRIM(languages), '') IS NULL THEN NULL
      ELSE LIST_TRANSFORM(
        STRING_SPLIT(@NORMALIZE_STRING(languages), ','),
        x -> CASE TRIM(x)
          WHEN 'ESPANOL' THEN 'SPANISH'
          WHEN 'INGLES' THEN 'ENGLISH'
          WHEN 'PORTUGUES' THEN 'PORTUGUESE'
          ELSE TRIM(x)
        END
      )
    END AS languages,

    -- Spanish specialties translated to English; unknown values are only normalized
    NULLIF(
      CASE @NORMALIZE_STRING(specialty)
        WHEN 'PRESTAMOS' THEN 'LOANS'
        WHEN 'TARJETAS' THEN 'CARDS'
        WHEN 'TARJETAS DE CREDITO' THEN 'CREDIT CARDS'
        WHEN 'INVERSIONES' THEN 'INVESTMENTS'
        WHEN 'SEGUROS' THEN 'INSURANCE'
        WHEN 'HIPOTECAS' THEN 'MORTGAGES'
        WHEN 'CUENTAS' THEN 'ACCOUNTS'
        WHEN 'FRAUDE' THEN 'FRAUD'
        WHEN 'COBRANZAS' THEN 'COLLECTIONS'
        WHEN 'BANCA DIGITAL' THEN 'DIGITAL BANKING'
        WHEN 'BANCA EMPRESARIAL' THEN 'BUSINESS BANKING'
        WHEN 'ATENCION GENERAL' THEN 'GENERAL SUPPORT'
        ELSE @NORMALIZE_STRING(specialty)
      END,
      ''
    ) AS specialty,

    TRY_CAST(TRIM(hire_date) AS DATE) AS hire_date,
    TRY_CAST(TRIM(avg_csat) AS DECIMAL(3,2)) AS avg_csat,
    TRY_CAST(TRIM(total_monthly_interactions) AS USMALLINT) AS total_monthly_interactions,
    snapshot_ts,
    _dlt_load_id,
    _dlt_id,
    _source_file
  FROM source
  WHERE TRIM(agent_id) IS NOT NULL
),

flagged AS (
  -- Flags are computed against each row's own snapshot, date to date, so an agent
  -- hired on the snapshot date is NOT considered future. Rows are kept, never imputed
  SELECT
    *,
    COALESCE(hire_date > snapshot_ts, FALSE) AS is_future_hire
  FROM typed
),

deduplicated AS (
  -- One row per photo and agent. There is no last_updated to rank by, so trustworthy
  -- dates come first and _dlt_id breaks the remaining ties (it is stored in bronze,
  -- so the winner is always the same row across rebuilds)
  SELECT *
  FROM flagged
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot_ts, agent_id
    ORDER BY
      is_future_hire ASC,
      _dlt_id ASC
  ) = 1
),

code_checked AS (
  -- One row per agent per photo after the dedup above, so counting rows per
  -- employee_code counts the distinct agent_ids that share it. Computed in its own
  -- step because a window in the dedup SELECT would still see the discarded copies
  SELECT
    *,
    COUNT(*) OVER (PARTITION BY snapshot_ts, employee_code) > 1 AS has_duplicated_employee_code
  FROM deduplicated
),

with_change AS (
  -- A new version starts only when a business attribute changes versus the previous photo.
  -- The comparison is explicit, one line per attribute: adding or deleting a column is a
  -- single visible edit here, and nothing silently joins or leaves the comparison.
  -- The flags, snapshot_ts and the _ metadata are deliberately absent, so a re-delivery
  -- of unchanged data never opens a new version.
  SELECT
    *,
    (
      LAG(agent_id) OVER previous_photo IS NULL -- agent's first photo
      OR employee_code IS DISTINCT FROM LAG(employee_code) OVER previous_photo
      OR first_name IS DISTINCT FROM LAG(first_name) OVER previous_photo
      OR last_name IS DISTINCT FROM LAG(last_name) OVER previous_photo
      OR email IS DISTINCT FROM LAG(email) OVER previous_photo
      OR phone IS DISTINCT FROM LAG(phone) OVER previous_photo
      OR native_accent IS DISTINCT FROM LAG(native_accent) OVER previous_photo
      OR country_of_origin IS DISTINCT FROM LAG(country_of_origin) OVER previous_photo
      OR assigned_branch_id IS DISTINCT FROM LAG(assigned_branch_id) OVER previous_photo
      OR agent_type IS DISTINCT FROM LAG(agent_type) OVER previous_photo
      OR experience_level IS DISTINCT FROM LAG(experience_level) OVER previous_photo
      OR languages IS DISTINCT FROM LAG(languages) OVER previous_photo
      OR specialty IS DISTINCT FROM LAG(specialty) OVER previous_photo
      OR hire_date IS DISTINCT FROM LAG(hire_date) OVER previous_photo
      OR avg_csat IS DISTINCT FROM LAG(avg_csat) OVER previous_photo
      OR total_monthly_interactions IS DISTINCT FROM LAG(total_monthly_interactions) OVER previous_photo
      OR agent_status IS DISTINCT FROM LAG(agent_status) OVER previous_photo
      OR work_shift IS DISTINCT FROM LAG(work_shift) OVER previous_photo
    )::INTEGER AS is_new_version
  FROM code_checked
  WINDOW previous_photo AS (PARTITION BY agent_id ORDER BY snapshot_ts)
),

with_version AS (
  SELECT
    *,
    SUM(is_new_version) OVER (PARTITION BY agent_id ORDER BY snapshot_ts)::INTEGER AS version_number
  FROM with_change
),

versions AS (
  -- Keep the latest photo of each version, so the version shows the latest flags
  SELECT
    *,
    MIN(snapshot_ts) OVER (PARTITION BY agent_id, version_number) AS version_snapshot_ts
  FROM with_version
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY agent_id, version_number ORDER BY snapshot_ts DESC
  ) = 1
),

validity AS (
  SELECT
    *,
    -- Validity follows snapshot_ts. Only a first version hired on or before its photo
    -- is backdated to the hire date, which is real history predating the first photo
    CASE
      WHEN version_number = 1 AND hire_date <= version_snapshot_ts
        THEN hire_date
      ELSE version_snapshot_ts
    END AS valid_from,
    LEAD(version_snapshot_ts) OVER (
      PARTITION BY agent_id ORDER BY version_number
    ) AS valid_to
  FROM versions
)

SELECT
  agent_id,
  employee_code,
  has_duplicated_employee_code,
  first_name,
  last_name,
  email,
  phone,
  native_accent,
  country_of_origin,
  assigned_branch_id,
  agent_type,
  experience_level,
  languages,
  specialty,
  hire_date,
  avg_csat,
  total_monthly_interactions,
  agent_status,
  work_shift,
  is_future_hire,
  version_number,
  valid_from,
  valid_to,
  valid_to IS NULL AS is_current,
  snapshot_ts,
  _dlt_load_id,
  _source_file
FROM validity