BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.ea_events
    ADD COLUMN IF NOT EXISTS account_login BIGINT,
    ADD COLUMN IF NOT EXISTS account_environment TEXT;

UPDATE public.ea_events
SET account_login =
    CASE
        WHEN COALESCE(raw_payload->>'account_login', '') ~ '^[0-9]+$'
        THEN (raw_payload->>'account_login')::BIGINT
        ELSE account_login
    END
WHERE account_login IS NULL
  AND raw_payload IS NOT NULL;

UPDATE public.ea_events
SET account_environment = raw_payload->>'account_environment'
WHERE account_environment IS NULL
  AND raw_payload IS NOT NULL
  AND NULLIF(raw_payload->>'account_environment', '') IS NOT NULL;

COMMIT;
