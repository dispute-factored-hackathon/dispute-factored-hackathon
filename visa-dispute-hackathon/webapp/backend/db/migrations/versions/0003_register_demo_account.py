"""Add the atomic demo-account registration operation.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.register_demo_account(customer_data jsonb, product_data jsonb)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            phone_digits text;
            previous_customer_id text;
        BEGIN
            IF customer_data->>'customer_id' NOT LIKE 'CLI-DEMO-%'
               OR customer_data->>'document_type' <> 'FACTORED_ID'
               OR product_data->>'product_id' NOT LIKE 'PRD-DEMO-%'
               OR product_data->>'customer_id' <> customer_data->>'customer_id' THEN
                RAISE EXCEPTION 'Invalid demo account registration.';
            END IF;

            phone_digits := regexp_replace(
                COALESCE(customer_data->>'mobile_phone', ''),
                '[^0-9]',
                '',
                'g'
            );
            IF phone_digits <> '' THEN
                PERFORM pg_advisory_xact_lock(hashtextextended(phone_digits, 0));
                SELECT customer_id
                  INTO previous_customer_id
                  FROM public.customers
                 WHERE regexp_replace(COALESCE(mobile_phone, ''), '[^0-9]', '', 'g') = phone_digits
                 FOR UPDATE;
            END IF;

            IF previous_customer_id IS NOT NULL THEN
                DELETE FROM public.satisfaction_surveys WHERE customer_id = previous_customer_id;
                DELETE FROM public.call_transcripts WHERE customer_id = previous_customer_id;
                DELETE FROM public.call_center_interactions WHERE customer_id = previous_customer_id;
                DELETE FROM public.complaints WHERE customer_id = previous_customer_id;
                DELETE FROM public.transactions WHERE customer_id = previous_customer_id;
                DELETE FROM public.products WHERE customer_id = previous_customer_id;
                DELETE FROM public.sessions WHERE customer_id = previous_customer_id;
                DELETE FROM public.customers WHERE customer_id = previous_customer_id;
            END IF;

            INSERT INTO public.customers (
                customer_id, document_number, document_type, first_name, last_name,
                search_name, date_of_birth, gender, mobile_phone, city, state, country,
                detected_accent, segment, registration_date, registration_branch_id,
                customer_status, preferred_locale, onboarding_completed, tutorial_version,
                tutorial_status, tutorial_last_completed_step, last_updated
            ) VALUES (
                customer_data->>'customer_id', customer_data->>'document_number',
                customer_data->>'document_type', customer_data->>'first_name',
                customer_data->>'last_name', customer_data->>'search_name',
                (customer_data->>'date_of_birth')::date, customer_data->>'gender',
                NULLIF(customer_data->>'mobile_phone', ''), customer_data->>'city',
                customer_data->>'state', customer_data->>'country',
                customer_data->>'detected_accent', customer_data->>'segment',
                (customer_data->>'registration_date')::timestamptz,
                (customer_data->>'registration_branch_id')::integer,
                customer_data->>'customer_status', NULLIF(customer_data->>'preferred_locale', ''),
                (customer_data->>'onboarding_completed')::boolean,
                (customer_data->>'tutorial_version')::integer,
                customer_data->>'tutorial_status',
                NULLIF(customer_data->>'tutorial_last_completed_step', ''),
                (customer_data->>'last_updated')::timestamptz
            );

            INSERT INTO public.products (
                product_id, customer_id, product_type, product_number, currency,
                current_balance, credit_limit, opening_date, opening_branch_id,
                product_status, opening_channel, has_linked_app, last_updated
            ) VALUES (
                product_data->>'product_id', product_data->>'customer_id',
                product_data->>'product_type', product_data->>'product_number',
                product_data->>'currency', (product_data->>'current_balance')::numeric,
                (product_data->>'credit_limit')::numeric,
                (product_data->>'opening_date')::date,
                (product_data->>'opening_branch_id')::integer,
                product_data->>'product_status', product_data->>'opening_channel',
                (product_data->>'has_linked_app')::boolean,
                (product_data->>'last_updated')::timestamptz
            );
        END;
        $$;

        REVOKE ALL ON FUNCTION public.register_demo_account(jsonb, jsonb) FROM PUBLIC;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION public.register_demo_account(jsonb, jsonb)")
