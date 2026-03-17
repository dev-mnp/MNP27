


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "hypopg" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "index_advisor" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."is_admin"() RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM app_users
    WHERE id = auth.uid() AND role = 'admin'
  );
END;
$$;


ALTER FUNCTION "public"."is_admin"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_editor"() RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM app_users
    WHERE id = auth.uid() AND role IN ('admin', 'editor')
  );
END;
$$;


ALTER FUNCTION "public"."is_editor"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_app_users_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_app_users_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_order_entries_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_order_entries_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."app_users" (
    "id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "name" "text",
    "first_name" "text",
    "last_name" "text",
    "role" "text" DEFAULT 'viewer'::"text" NOT NULL,
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "app_users_role_check" CHECK (("role" = ANY (ARRAY['admin'::"text", 'editor'::"text", 'viewer'::"text"]))),
    CONSTRAINT "app_users_status_check" CHECK (("status" = ANY (ARRAY['active'::"text", 'inactive'::"text"])))
);


ALTER TABLE "public"."app_users" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."articles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "article_name" "text" NOT NULL,
    "cost_per_unit" numeric DEFAULT 0 NOT NULL,
    "item_type" "text" NOT NULL,
    "category" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "comments" "text",
    "article_name_tk" "text",
    "master_category" "text",
    "combo" boolean DEFAULT false NOT NULL,
    CONSTRAINT "articles_item_type_check" CHECK (("item_type" = ANY (ARRAY['Article'::"text", 'Aid'::"text", 'Project'::"text"])))
);


ALTER TABLE "public"."articles" OWNER TO "postgres";


COMMENT ON TABLE "public"."articles" IS 'Master catalog of articles and aids available for distribution';



COMMENT ON COLUMN "public"."articles"."article_name_tk" IS 'Article name for Tokens';



COMMENT ON COLUMN "public"."articles"."combo" IS 'Marks split/combo articles created for order management; typically inactive';



CREATE TABLE IF NOT EXISTS "public"."audit_logs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "action_type" "text" NOT NULL,
    "entity_type" "text" NOT NULL,
    "entity_id" "text",
    "details" "jsonb" DEFAULT '{}'::"jsonb",
    "ip_address" "text",
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "audit_logs_action_type_check" CHECK (("action_type" = ANY (ARRAY['CREATE'::"text", 'UPDATE'::"text", 'DELETE'::"text", 'LOGIN'::"text", 'LOGOUT'::"text", 'EXPORT'::"text", 'STATUS_CHANGE'::"text"])))
);


ALTER TABLE "public"."audit_logs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."district_beneficiary_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "district_id" "uuid" NOT NULL,
    "application_number" "text",
    "article_id" "uuid" NOT NULL,
    "quantity" integer DEFAULT 1 NOT NULL,
    "total_amount" numeric DEFAULT 0 NOT NULL,
    "notes" "text",
    "status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "article_cost_per_unit" numeric DEFAULT 0 NOT NULL,
    "fund_request_id" "uuid",
    CONSTRAINT "district_beneficiary_entries_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'approved'::"text", 'rejected'::"text", 'completed'::"text"])))
);


ALTER TABLE "public"."district_beneficiary_entries" OWNER TO "postgres";


COMMENT ON TABLE "public"."district_beneficiary_entries" IS 'District beneficiary entries/requests';



CREATE TABLE IF NOT EXISTS "public"."district_master" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "district_name" "text" NOT NULL,
    "allotted_budget" numeric DEFAULT 0 NOT NULL,
    "president_name" "text" NOT NULL,
    "mobile_number" "text" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "application_number" "text" NOT NULL
);


ALTER TABLE "public"."district_master" OWNER TO "postgres";


COMMENT ON TABLE "public"."district_master" IS 'Master data of districts with president information and allotted budgets';



COMMENT ON COLUMN "public"."district_master"."application_number" IS 'series number for districts';



CREATE OR REPLACE VIEW "public"."district_beneficiary_summary" AS
 SELECT "dbe"."id",
    "dbe"."application_number",
    "dm"."district_name",
    "a"."article_name",
    "a"."cost_per_unit",
    "a"."item_type",
    "a"."category",
    "dbe"."quantity",
    "dbe"."total_amount",
    "dbe"."status",
    "dbe"."notes",
    "dbe"."created_at",
    "dbe"."updated_at"
   FROM (("public"."district_beneficiary_entries" "dbe"
     JOIN "public"."district_master" "dm" ON (("dbe"."district_id" = "dm"."id")))
     JOIN "public"."articles" "a" ON (("dbe"."article_id" = "a"."id")));


ALTER VIEW "public"."district_beneficiary_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."district_beneficiary_summary" IS 'District entries with article and district names joined';



CREATE OR REPLACE VIEW "public"."district_budget_utilization" AS
 SELECT "dm"."id",
    "dm"."district_name",
    "dm"."allotted_budget",
    COALESCE("sum"("dbe"."total_amount"), (0)::numeric) AS "total_spent",
    ("dm"."allotted_budget" - COALESCE("sum"("dbe"."total_amount"), (0)::numeric)) AS "remaining_budget",
        CASE
            WHEN ("dm"."allotted_budget" > (0)::numeric) THEN "round"(((COALESCE("sum"("dbe"."total_amount"), (0)::numeric) / "dm"."allotted_budget") * (100)::numeric), 2)
            ELSE (0)::numeric
        END AS "utilization_percentage",
    "dm"."president_name",
    "dm"."mobile_number",
    "dm"."is_active"
   FROM ("public"."district_master" "dm"
     LEFT JOIN "public"."district_beneficiary_entries" "dbe" ON ((("dm"."id" = "dbe"."district_id") AND ("dbe"."status" = ANY (ARRAY['approved'::"text", 'completed'::"text"])))))
  GROUP BY "dm"."id", "dm"."district_name", "dm"."allotted_budget", "dm"."president_name", "dm"."mobile_number", "dm"."is_active";


ALTER VIEW "public"."district_budget_utilization" OWNER TO "postgres";


COMMENT ON VIEW "public"."district_budget_utilization" IS 'District master with total spent and remaining budget';



CREATE TABLE IF NOT EXISTS "public"."fund_request" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "fund_request_type" "text" NOT NULL,
    "fund_request_number" "text" NOT NULL,
    "status" "text" DEFAULT 'draft'::"text",
    "total_amount" numeric DEFAULT 0 NOT NULL,
    "aid_type" "text",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "gst_number" "text",
    "supplier_name" "text",
    "supplier_address" "text",
    "supplier_city" "text",
    "supplier_state" "text",
    "supplier_pincode" "text",
    "purchase_order_number" "text",
    CONSTRAINT "fund_request_fund_request_type_check" CHECK (("fund_request_type" = ANY (ARRAY['Aid'::"text", 'Article'::"text"]))),
    CONSTRAINT "fund_request_status_check" CHECK (("status" = ANY (ARRAY['draft'::"text", 'submitted'::"text", 'approved'::"text", 'rejected'::"text", 'completed'::"text"])))
);


ALTER TABLE "public"."fund_request" OWNER TO "postgres";


COMMENT ON TABLE "public"."fund_request" IS 'Main table for fund request records supporting both Aid and Article types';



COMMENT ON COLUMN "public"."fund_request"."gst_number" IS 'GST number for Article type fund requests (applies to all articles)';



COMMENT ON COLUMN "public"."fund_request"."supplier_name" IS 'Supplier name for Article type fund requests';



COMMENT ON COLUMN "public"."fund_request"."supplier_address" IS 'Supplier address for Article type fund requests';



COMMENT ON COLUMN "public"."fund_request"."supplier_city" IS 'Supplier city for Article type fund requests';



COMMENT ON COLUMN "public"."fund_request"."supplier_state" IS 'Supplier state for Article type fund requests';



COMMENT ON COLUMN "public"."fund_request"."supplier_pincode" IS 'Supplier pincode for Article type fund requests';



CREATE TABLE IF NOT EXISTS "public"."fund_request_articles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "fund_request_id" "uuid" NOT NULL,
    "article_id" "uuid" NOT NULL,
    "sl_no" integer,
    "beneficiary" "text",
    "article_name" "text" NOT NULL,
    "gst_no" "text",
    "quantity" integer DEFAULT 1 NOT NULL,
    "unit_price" numeric DEFAULT 0 NOT NULL,
    "price_including_gst" numeric DEFAULT 0 NOT NULL,
    "value" numeric DEFAULT 0 NOT NULL,
    "cumulative" numeric DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "cheque_in_favour" "text",
    "cheque_no" "text",
    "supplier_article_name" "text",
    "description" "text"
);


ALTER TABLE "public"."fund_request_articles" OWNER TO "postgres";


COMMENT ON TABLE "public"."fund_request_articles" IS 'Articles for Article type fund requests (multiple articles per fund request)';



COMMENT ON COLUMN "public"."fund_request_articles"."cheque_in_favour" IS 'Cheque in favour for Article fund request';



COMMENT ON COLUMN "public"."fund_request_articles"."cheque_no" IS 'Cheque serial number for Article fund request';



COMMENT ON COLUMN "public"."fund_request_articles"."supplier_article_name" IS 'Supplier article name (used for purchase order)';



CREATE TABLE IF NOT EXISTS "public"."fund_request_documents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "fund_request_id" "uuid" NOT NULL,
    "document_type" "text" NOT NULL,
    "file_path" "text",
    "file_name" "text" NOT NULL,
    "generated_at" timestamp with time zone DEFAULT "now"(),
    "generated_by" "uuid",
    CONSTRAINT "fund_request_documents_document_type_check" CHECK (("document_type" = ANY (ARRAY['fund_request'::"text", 'purchase_order'::"text"])))
);


ALTER TABLE "public"."fund_request_documents" OWNER TO "postgres";


COMMENT ON TABLE "public"."fund_request_documents" IS 'Metadata for generated fund request and purchase order documents';



CREATE TABLE IF NOT EXISTS "public"."fund_request_recipients" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "fund_request_id" "uuid" NOT NULL,
    "beneficiary_type" "text",
    "beneficiary" "text",
    "recipient_name" "text" NOT NULL,
    "name_of_beneficiary" "text",
    "name_of_institution" "text",
    "details" "text",
    "fund_requested" numeric DEFAULT 0 NOT NULL,
    "aadhar_number" "text",
    "address" "text",
    "cheque_in_favour" "text",
    "cheque_no" "text",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "district_name" "text",
    CONSTRAINT "fund_request_recipients_beneficiary_type_check" CHECK (("beneficiary_type" = ANY (ARRAY['District'::"text", 'Public'::"text", 'Institutions'::"text", 'Others'::"text"])))
);


ALTER TABLE "public"."fund_request_recipients" OWNER TO "postgres";


COMMENT ON TABLE "public"."fund_request_recipients" IS 'Recipients for Aid type fund requests (multiple recipients per fund request)';



COMMENT ON COLUMN "public"."fund_request_recipients"."district_name" IS 'Name of the district for District type beneficiaries';



CREATE OR REPLACE VIEW "public"."fund_request_summary" AS
 SELECT "fr"."id",
    "fr"."fund_request_type",
    "fr"."fund_request_number",
    "fr"."status",
    "fr"."total_amount",
    "fr"."aid_type",
    "fr"."created_at",
    "fr"."updated_at",
    "count"(DISTINCT "frr"."id") AS "recipient_count",
    "count"(DISTINCT "fra"."id") AS "article_count"
   FROM (("public"."fund_request" "fr"
     LEFT JOIN "public"."fund_request_recipients" "frr" ON (("fr"."id" = "frr"."fund_request_id")))
     LEFT JOIN "public"."fund_request_articles" "fra" ON (("fr"."id" = "fra"."fund_request_id")))
  GROUP BY "fr"."id", "fr"."fund_request_type", "fr"."fund_request_number", "fr"."status", "fr"."total_amount", "fr"."aid_type", "fr"."created_at", "fr"."updated_at";


ALTER VIEW "public"."fund_request_summary" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."institutions_beneficiary_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "institution_name" "text" NOT NULL,
    "institution_type" "text" NOT NULL,
    "application_number" "text",
    "address" "text",
    "mobile" "text",
    "article_id" "uuid" NOT NULL,
    "quantity" integer DEFAULT 1 NOT NULL,
    "article_cost_per_unit" numeric,
    "total_amount" numeric DEFAULT 0 NOT NULL,
    "notes" "text",
    "status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "fund_request_id" "uuid",
    CONSTRAINT "institutions_beneficiary_entries_institution_type_check" CHECK (("institution_type" = ANY (ARRAY['institutions'::"text", 'others'::"text"]))),
    CONSTRAINT "institutions_beneficiary_entries_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'approved'::"text", 'rejected'::"text", 'completed'::"text"])))
);


ALTER TABLE "public"."institutions_beneficiary_entries" OWNER TO "postgres";


COMMENT ON TABLE "public"."institutions_beneficiary_entries" IS 'Institutions and others beneficiary entries with multiple articles per application';



CREATE TABLE IF NOT EXISTS "public"."order_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "article_id" "uuid" NOT NULL,
    "quantity_ordered" integer DEFAULT 1 NOT NULL,
    "order_date" "date" DEFAULT CURRENT_DATE NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "supplier_name" "text",
    "supplier_contact" "text",
    "unit_price" numeric,
    "total_amount" numeric DEFAULT 0 NOT NULL,
    "expected_delivery_date" "date",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "fund_request_id" "uuid",
    CONSTRAINT "order_entries_quantity_ordered_check" CHECK (("quantity_ordered" > 0)),
    CONSTRAINT "order_entries_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'ordered'::"text", 'received'::"text", 'cancelled'::"text"])))
);


ALTER TABLE "public"."order_entries" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."public_beneficiary_entries" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "application_number" "text",
    "name" "text" NOT NULL,
    "aadhar_number" "text" NOT NULL,
    "is_handicapped" boolean DEFAULT false,
    "address" "text",
    "mobile" "text",
    "article_id" "uuid" NOT NULL,
    "quantity" integer DEFAULT 1 NOT NULL,
    "total_amount" numeric DEFAULT 0 NOT NULL,
    "notes" "text",
    "status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "fund_request_id" "uuid",
    "gender" "text",
    "female_status" "text",
    CONSTRAINT "public_beneficiary_entries_female_status_check" CHECK (("female_status" = ANY (ARRAY['Single Mother'::"text", 'Widow'::"text", 'Married'::"text", 'Unmarried'::"text"]))),
    CONSTRAINT "public_beneficiary_entries_gender_check" CHECK (("gender" = ANY (ARRAY['Male'::"text", 'Female'::"text", 'Transgender'::"text"]))),
    CONSTRAINT "public_beneficiary_entries_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'approved'::"text", 'rejected'::"text", 'completed'::"text"])))
);


ALTER TABLE "public"."public_beneficiary_entries" OWNER TO "postgres";


COMMENT ON TABLE "public"."public_beneficiary_entries" IS 'Public (individual) beneficiary entries';



CREATE OR REPLACE VIEW "public"."order_requirement_view" AS
 SELECT "a"."article_name" AS "REQUESTED ARTICLE",
    COALESCE("d"."district_count", (0)::bigint) AS "District",
    COALESCE("i"."institution_count", (0)::bigint) AS "Institution",
    COALESCE("o"."others_count", (0)::bigint) AS "Others",
    COALESCE("p"."public_count", (0)::bigint) AS "Public",
    (((COALESCE("d"."district_count", (0)::bigint) + COALESCE("i"."institution_count", (0)::bigint)) + COALESCE("o"."others_count", (0)::bigint)) + COALESCE("p"."public_count", (0)::bigint)) AS "Total",
    0 AS "Ordered Quantity",
    0 AS "Remaining Quantity"
   FROM (((("public"."articles" "a"
     LEFT JOIN ( SELECT "district_beneficiary_entries"."article_id",
            "sum"("district_beneficiary_entries"."quantity") AS "district_count"
           FROM "public"."district_beneficiary_entries"
          GROUP BY "district_beneficiary_entries"."article_id") "d" ON (("a"."id" = "d"."article_id")))
     LEFT JOIN ( SELECT "public_beneficiary_entries"."article_id",
            "sum"("public_beneficiary_entries"."quantity") AS "public_count"
           FROM "public"."public_beneficiary_entries"
          GROUP BY "public_beneficiary_entries"."article_id") "p" ON (("a"."id" = "p"."article_id")))
     LEFT JOIN ( SELECT "district_beneficiary_entries"."article_id",
            "sum"("district_beneficiary_entries"."quantity") AS "institution_count"
           FROM "public"."district_beneficiary_entries"
          WHERE ("district_beneficiary_entries"."status" = 'approved'::"text")
          GROUP BY "district_beneficiary_entries"."article_id") "i" ON (("a"."id" = "i"."article_id")))
     LEFT JOIN ( SELECT "district_beneficiary_entries"."article_id",
            "sum"("district_beneficiary_entries"."quantity") AS "others_count"
           FROM "public"."district_beneficiary_entries"
          WHERE ("district_beneficiary_entries"."status" = 'approved'::"text")
          GROUP BY "district_beneficiary_entries"."article_id") "o" ON (("a"."id" = "o"."article_id")))
  WHERE ("a"."is_active" = true)
  ORDER BY "a"."article_name";


ALTER VIEW "public"."order_requirement_view" OWNER TO "postgres";


COMMENT ON VIEW "public"."order_requirement_view" IS 'Article-wise summary by beneficiary type matching Order Requirement format';



CREATE TABLE IF NOT EXISTS "public"."public_beneficiary_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "aadhar_number" "text" NOT NULL,
    "name" "text" NOT NULL,
    "year" integer NOT NULL,
    "article_name" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "application_number" "text",
    "comments" "text",
    "is_handicapped" boolean,
    "address" "text",
    "mobile" "text",
    "aadhar_number_sp" "text",
    "is_selected" boolean,
    "category" "text"
);


ALTER TABLE "public"."public_beneficiary_history" OWNER TO "postgres";


COMMENT ON TABLE "public"."public_beneficiary_history" IS 'Historical data of public beneficiaries for Aadhar-based validation (read-only reference)';



COMMENT ON COLUMN "public"."public_beneficiary_history"."application_number" IS 'Application number from historical records';



COMMENT ON COLUMN "public"."public_beneficiary_history"."comments" IS 'Comments or notes from historical records';



COMMENT ON COLUMN "public"."public_beneficiary_history"."is_handicapped" IS 'Whether the beneficiary is handicapped';



COMMENT ON COLUMN "public"."public_beneficiary_history"."address" IS 'Address of the beneficiary';



COMMENT ON COLUMN "public"."public_beneficiary_history"."mobile" IS 'Mobile number of the beneficiary';



COMMENT ON COLUMN "public"."public_beneficiary_history"."aadhar_number_sp" IS 'Aadhar Number with Spaces';



COMMENT ON COLUMN "public"."public_beneficiary_history"."is_selected" IS 'Selected status';



COMMENT ON COLUMN "public"."public_beneficiary_history"."category" IS 'Category of beneficiary';



CREATE OR REPLACE VIEW "public"."public_beneficiary_summary" AS
 SELECT "pbe"."id",
    "pbe"."application_number",
    "pbe"."name",
    "pbe"."aadhar_number",
    "pbe"."is_handicapped",
    "pbe"."address",
    "pbe"."mobile",
    "a"."article_name",
    "a"."cost_per_unit",
    "a"."item_type",
    "a"."category",
    "pbe"."quantity",
    "pbe"."total_amount",
    "pbe"."status",
    "pbe"."notes",
    "pbe"."created_at",
    "pbe"."updated_at"
   FROM ("public"."public_beneficiary_entries" "pbe"
     JOIN "public"."articles" "a" ON (("pbe"."article_id" = "a"."id")));


ALTER VIEW "public"."public_beneficiary_summary" OWNER TO "postgres";


COMMENT ON VIEW "public"."public_beneficiary_summary" IS 'Public entries with article names joined';



ALTER TABLE ONLY "public"."app_users"
    ADD CONSTRAINT "app_users_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."app_users"
    ADD CONSTRAINT "app_users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."articles"
    ADD CONSTRAINT "articles_article_name_key" UNIQUE ("article_name");



ALTER TABLE ONLY "public"."articles"
    ADD CONSTRAINT "articles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."district_beneficiary_entries"
    ADD CONSTRAINT "district_beneficiary_entries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."district_master"
    ADD CONSTRAINT "district_master_district_name_key" UNIQUE ("district_name");



ALTER TABLE ONLY "public"."district_master"
    ADD CONSTRAINT "district_master_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fund_request_articles"
    ADD CONSTRAINT "fund_request_articles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fund_request_documents"
    ADD CONSTRAINT "fund_request_documents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fund_request"
    ADD CONSTRAINT "fund_request_fund_request_number_key" UNIQUE ("fund_request_number");



ALTER TABLE ONLY "public"."fund_request"
    ADD CONSTRAINT "fund_request_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fund_request_recipients"
    ADD CONSTRAINT "fund_request_recipients_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."institutions_beneficiary_entries"
    ADD CONSTRAINT "institutions_beneficiary_entries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."order_entries"
    ADD CONSTRAINT "order_entries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."public_beneficiary_entries"
    ADD CONSTRAINT "public_beneficiary_entries_application_number_key" UNIQUE ("application_number");



ALTER TABLE ONLY "public"."public_beneficiary_entries"
    ADD CONSTRAINT "public_beneficiary_entries_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."public_beneficiary_history"
    ADD CONSTRAINT "public_beneficiary_history_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_app_users_email" ON "public"."app_users" USING "btree" ("email");



CREATE INDEX "idx_app_users_role" ON "public"."app_users" USING "btree" ("role");



CREATE INDEX "idx_app_users_status" ON "public"."app_users" USING "btree" ("status");



CREATE INDEX "idx_articles_article_name" ON "public"."articles" USING "btree" ("article_name");



CREATE INDEX "idx_articles_is_active" ON "public"."articles" USING "btree" ("is_active");



CREATE INDEX "idx_articles_item_type" ON "public"."articles" USING "btree" ("item_type");



CREATE INDEX "idx_articles_item_type_active" ON "public"."articles" USING "btree" ("item_type", "is_active");



CREATE INDEX "idx_audit_logs_action_type" ON "public"."audit_logs" USING "btree" ("action_type");



CREATE INDEX "idx_audit_logs_created_at" ON "public"."audit_logs" USING "btree" ("created_at");



CREATE INDEX "idx_audit_logs_entity" ON "public"."audit_logs" USING "btree" ("entity_type", "entity_id");



CREATE INDEX "idx_audit_logs_entity_id" ON "public"."audit_logs" USING "btree" ("entity_id");



CREATE INDEX "idx_audit_logs_entity_type" ON "public"."audit_logs" USING "btree" ("entity_type");



CREATE INDEX "idx_audit_logs_user_action" ON "public"."audit_logs" USING "btree" ("user_id", "action_type");



CREATE INDEX "idx_audit_logs_user_id" ON "public"."audit_logs" USING "btree" ("user_id");



CREATE INDEX "idx_district_beneficiary_application_number" ON "public"."district_beneficiary_entries" USING "btree" ("application_number");



CREATE INDEX "idx_district_beneficiary_article_id" ON "public"."district_beneficiary_entries" USING "btree" ("article_id");



CREATE INDEX "idx_district_beneficiary_district_id" ON "public"."district_beneficiary_entries" USING "btree" ("district_id");



CREATE INDEX "idx_district_beneficiary_district_status" ON "public"."district_beneficiary_entries" USING "btree" ("district_id", "status");



CREATE INDEX "idx_district_beneficiary_entries_district_article" ON "public"."district_beneficiary_entries" USING "btree" ("district_id", "article_id", "created_at" DESC);



CREATE INDEX "idx_district_beneficiary_fund_request_id" ON "public"."district_beneficiary_entries" USING "btree" ("fund_request_id");



CREATE INDEX "idx_district_beneficiary_status" ON "public"."district_beneficiary_entries" USING "btree" ("status");



CREATE INDEX "idx_district_master_district_name" ON "public"."district_master" USING "btree" ("district_name");



CREATE INDEX "idx_district_master_is_active" ON "public"."district_master" USING "btree" ("is_active");



CREATE INDEX "idx_fund_request_aid_type" ON "public"."fund_request" USING "btree" ("aid_type");



CREATE INDEX "idx_fund_request_articles_article_id" ON "public"."fund_request_articles" USING "btree" ("article_id");



CREATE INDEX "idx_fund_request_articles_fund_request_id" ON "public"."fund_request_articles" USING "btree" ("fund_request_id");



CREATE INDEX "idx_fund_request_created_at" ON "public"."fund_request" USING "btree" ("created_at");



CREATE INDEX "idx_fund_request_documents_fund_request_id" ON "public"."fund_request_documents" USING "btree" ("fund_request_id");



CREATE INDEX "idx_fund_request_documents_type" ON "public"."fund_request_documents" USING "btree" ("document_type");



CREATE INDEX "idx_fund_request_number" ON "public"."fund_request" USING "btree" ("fund_request_number");



CREATE INDEX "idx_fund_request_purchase_order_number" ON "public"."fund_request" USING "btree" ("purchase_order_number");



CREATE INDEX "idx_fund_request_recipients_beneficiary_type" ON "public"."fund_request_recipients" USING "btree" ("beneficiary_type");



CREATE INDEX "idx_fund_request_recipients_fund_request_id" ON "public"."fund_request_recipients" USING "btree" ("fund_request_id");



CREATE INDEX "idx_fund_request_status" ON "public"."fund_request" USING "btree" ("status");



CREATE INDEX "idx_fund_request_type" ON "public"."fund_request" USING "btree" ("fund_request_type");



CREATE INDEX "idx_fund_request_type_status" ON "public"."fund_request" USING "btree" ("fund_request_type", "status");



CREATE INDEX "idx_institution_beneficiary_fund_request_id" ON "public"."institutions_beneficiary_entries" USING "btree" ("fund_request_id");



CREATE INDEX "idx_institutions_beneficiary_entries_application_number" ON "public"."institutions_beneficiary_entries" USING "btree" ("application_number");



CREATE INDEX "idx_institutions_beneficiary_entries_article_id" ON "public"."institutions_beneficiary_entries" USING "btree" ("article_id");



CREATE INDEX "idx_institutions_beneficiary_entries_created_at" ON "public"."institutions_beneficiary_entries" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_institutions_beneficiary_entries_institution_name" ON "public"."institutions_beneficiary_entries" USING "btree" ("institution_name");



CREATE INDEX "idx_institutions_beneficiary_entries_institution_type" ON "public"."institutions_beneficiary_entries" USING "btree" ("institution_type");



CREATE INDEX "idx_order_entries_article_id" ON "public"."order_entries" USING "btree" ("article_id");



CREATE INDEX "idx_order_entries_article_status" ON "public"."order_entries" USING "btree" ("article_id", "status");



CREATE INDEX "idx_order_entries_fund_request_id" ON "public"."order_entries" USING "btree" ("fund_request_id");



CREATE INDEX "idx_order_entries_order_date" ON "public"."order_entries" USING "btree" ("order_date");



CREATE INDEX "idx_order_entries_status" ON "public"."order_entries" USING "btree" ("status");



CREATE INDEX "idx_public_beneficiary_aadhar" ON "public"."public_beneficiary_entries" USING "btree" ("aadhar_number");



CREATE INDEX "idx_public_beneficiary_application_number" ON "public"."public_beneficiary_entries" USING "btree" ("application_number");



CREATE INDEX "idx_public_beneficiary_article_id" ON "public"."public_beneficiary_entries" USING "btree" ("article_id");



CREATE INDEX "idx_public_beneficiary_female_status" ON "public"."public_beneficiary_entries" USING "btree" ("female_status");



CREATE INDEX "idx_public_beneficiary_fund_request_id" ON "public"."public_beneficiary_entries" USING "btree" ("fund_request_id");



CREATE INDEX "idx_public_beneficiary_gender" ON "public"."public_beneficiary_entries" USING "btree" ("gender");



CREATE INDEX "idx_public_beneficiary_status" ON "public"."public_beneficiary_entries" USING "btree" ("status");



CREATE INDEX "idx_public_history_aadhar" ON "public"."public_beneficiary_history" USING "btree" ("aadhar_number");



CREATE INDEX "idx_public_history_aadhar_year" ON "public"."public_beneficiary_history" USING "btree" ("aadhar_number", "year");



CREATE INDEX "public_beneficiary_history_comments_idx" ON "public"."public_beneficiary_history" USING "btree" ("comments");



CREATE INDEX "public_beneficiary_history_is_handicapped_idx" ON "public"."public_beneficiary_history" USING "btree" ("is_handicapped");



CREATE INDEX "public_beneficiary_history_is_selected_idx" ON "public"."public_beneficiary_history" USING "btree" ("is_selected");



CREATE OR REPLACE TRIGGER "trigger_update_app_users_updated_at" BEFORE UPDATE ON "public"."app_users" FOR EACH ROW EXECUTE FUNCTION "public"."update_app_users_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_order_entries_updated_at" BEFORE UPDATE ON "public"."order_entries" FOR EACH ROW EXECUTE FUNCTION "public"."update_order_entries_updated_at"();



CREATE OR REPLACE TRIGGER "update_articles_updated_at" BEFORE UPDATE ON "public"."articles" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_district_beneficiary_updated_at" BEFORE UPDATE ON "public"."district_beneficiary_entries" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_district_master_updated_at" BEFORE UPDATE ON "public"."district_master" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_fund_request_updated_at" BEFORE UPDATE ON "public"."fund_request" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_public_beneficiary_updated_at" BEFORE UPDATE ON "public"."public_beneficiary_entries" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."app_users"
    ADD CONSTRAINT "app_users_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."app_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."district_beneficiary_entries"
    ADD CONSTRAINT "district_beneficiary_entries_article_id_fkey" FOREIGN KEY ("article_id") REFERENCES "public"."articles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."district_beneficiary_entries"
    ADD CONSTRAINT "district_beneficiary_entries_district_id_fkey" FOREIGN KEY ("district_id") REFERENCES "public"."district_master"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."district_beneficiary_entries"
    ADD CONSTRAINT "district_beneficiary_entries_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."fund_request_articles"
    ADD CONSTRAINT "fund_request_articles_article_id_fkey" FOREIGN KEY ("article_id") REFERENCES "public"."articles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."fund_request_articles"
    ADD CONSTRAINT "fund_request_articles_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."fund_request_documents"
    ADD CONSTRAINT "fund_request_documents_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."fund_request_recipients"
    ADD CONSTRAINT "fund_request_recipients_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."institutions_beneficiary_entries"
    ADD CONSTRAINT "institutions_beneficiary_entries_article_id_fkey" FOREIGN KEY ("article_id") REFERENCES "public"."articles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."institutions_beneficiary_entries"
    ADD CONSTRAINT "institutions_beneficiary_entries_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."order_entries"
    ADD CONSTRAINT "order_entries_article_id_fkey" FOREIGN KEY ("article_id") REFERENCES "public"."articles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."order_entries"
    ADD CONSTRAINT "order_entries_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."public_beneficiary_entries"
    ADD CONSTRAINT "public_beneficiary_entries_article_id_fkey" FOREIGN KEY ("article_id") REFERENCES "public"."articles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."public_beneficiary_entries"
    ADD CONSTRAINT "public_beneficiary_entries_fund_request_id_fkey" FOREIGN KEY ("fund_request_id") REFERENCES "public"."fund_request"("id") ON DELETE SET NULL;



CREATE POLICY "Admins can do everything on articles" ON "public"."articles" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on district_master" ON "public"."district_master" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on fund_request" ON "public"."fund_request" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on fund_request_articles" ON "public"."fund_request_articles" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on fund_request_documents" ON "public"."fund_request_documents" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on fund_request_recipients" ON "public"."fund_request_recipients" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can do everything on public_beneficiary_history" ON "public"."public_beneficiary_history" USING ("public"."is_admin"()) WITH CHECK ("public"."is_admin"());



CREATE POLICY "Allow all operations on app_users" ON "public"."app_users" USING (true) WITH CHECK (true);



CREATE POLICY "Allow all operations on audit_logs" ON "public"."audit_logs" USING (true) WITH CHECK (true);



CREATE POLICY "Allow all operations on district_beneficiary_entries" ON "public"."district_beneficiary_entries" USING (true) WITH CHECK (true);



CREATE POLICY "Allow all operations on institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" USING (true) WITH CHECK (true);



CREATE POLICY "Allow all operations on order_entries" ON "public"."order_entries" USING (true) WITH CHECK (true);



CREATE POLICY "Allow all operations on public_beneficiary_entries" ON "public"."public_beneficiary_entries" USING (true) WITH CHECK (true);



CREATE POLICY "Editors can delete fund_request" ON "public"."fund_request" FOR DELETE USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can delete fund_request_articles" ON "public"."fund_request_articles" FOR DELETE USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can insert fund_request" ON "public"."fund_request" FOR INSERT WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can insert fund_request_articles" ON "public"."fund_request_articles" FOR INSERT WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can insert fund_request_documents" ON "public"."fund_request_documents" FOR INSERT WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can insert fund_request_recipients" ON "public"."fund_request_recipients" FOR INSERT WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can insert institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" FOR INSERT WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can modify fund_request" ON "public"."fund_request" FOR UPDATE USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can modify fund_request_articles" ON "public"."fund_request_articles" FOR UPDATE USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can modify fund_request_documents" ON "public"."fund_request_documents" FOR UPDATE USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can modify fund_request_recipients" ON "public"."fund_request_recipients" FOR UPDATE USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can read institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select and modify articles" ON "public"."articles" USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select and modify fund_request_recipients" ON "public"."fund_request_recipients" FOR DELETE USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select fund_request" ON "public"."fund_request" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select fund_request_articles" ON "public"."fund_request_articles" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select fund_request_documents" ON "public"."fund_request_documents" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select fund_request_recipients" ON "public"."fund_request_recipients" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can select public_beneficiary_history" ON "public"."public_beneficiary_history" FOR SELECT USING (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Editors can update institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" FOR UPDATE USING (("public"."is_editor"() OR "public"."is_admin"())) WITH CHECK (("public"."is_editor"() OR "public"."is_admin"()));



CREATE POLICY "Viewers can select articles" ON "public"."articles" FOR SELECT USING (true);



CREATE POLICY "Viewers can select district_master" ON "public"."district_master" FOR SELECT USING (true);



CREATE POLICY "Viewers can select fund_request" ON "public"."fund_request" FOR SELECT USING (true);



CREATE POLICY "Viewers can select fund_request_articles" ON "public"."fund_request_articles" FOR SELECT USING (true);



CREATE POLICY "Viewers can select fund_request_documents" ON "public"."fund_request_documents" FOR SELECT USING (true);



CREATE POLICY "Viewers can select fund_request_recipients" ON "public"."fund_request_recipients" FOR SELECT USING (true);



CREATE POLICY "Viewers can select institutions_beneficiary_entries" ON "public"."institutions_beneficiary_entries" FOR SELECT USING (true);



CREATE POLICY "Viewers can select public_beneficiary_history" ON "public"."public_beneficiary_history" FOR SELECT USING (true);



ALTER TABLE "public"."app_users" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."articles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."audit_logs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."district_beneficiary_entries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."district_master" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."fund_request" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."fund_request_articles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."fund_request_documents" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."fund_request_recipients" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."institutions_beneficiary_entries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."order_entries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."public_beneficiary_entries" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."public_beneficiary_history" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";





























































































































































































GRANT ALL ON FUNCTION "public"."is_admin"() TO "anon";
GRANT ALL ON FUNCTION "public"."is_admin"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_admin"() TO "service_role";



GRANT ALL ON FUNCTION "public"."is_editor"() TO "anon";
GRANT ALL ON FUNCTION "public"."is_editor"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_editor"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_app_users_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_app_users_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_app_users_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_order_entries_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_order_entries_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_order_entries_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";
























GRANT ALL ON TABLE "public"."app_users" TO "anon";
GRANT ALL ON TABLE "public"."app_users" TO "authenticated";
GRANT ALL ON TABLE "public"."app_users" TO "service_role";



GRANT ALL ON TABLE "public"."articles" TO "anon";
GRANT ALL ON TABLE "public"."articles" TO "authenticated";
GRANT ALL ON TABLE "public"."articles" TO "service_role";



GRANT ALL ON TABLE "public"."audit_logs" TO "anon";
GRANT ALL ON TABLE "public"."audit_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_logs" TO "service_role";



GRANT ALL ON TABLE "public"."district_beneficiary_entries" TO "anon";
GRANT ALL ON TABLE "public"."district_beneficiary_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."district_beneficiary_entries" TO "service_role";



GRANT ALL ON TABLE "public"."district_master" TO "anon";
GRANT ALL ON TABLE "public"."district_master" TO "authenticated";
GRANT ALL ON TABLE "public"."district_master" TO "service_role";



GRANT ALL ON TABLE "public"."district_beneficiary_summary" TO "anon";
GRANT ALL ON TABLE "public"."district_beneficiary_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."district_beneficiary_summary" TO "service_role";



GRANT ALL ON TABLE "public"."district_budget_utilization" TO "anon";
GRANT ALL ON TABLE "public"."district_budget_utilization" TO "authenticated";
GRANT ALL ON TABLE "public"."district_budget_utilization" TO "service_role";



GRANT ALL ON TABLE "public"."fund_request" TO "anon";
GRANT ALL ON TABLE "public"."fund_request" TO "authenticated";
GRANT ALL ON TABLE "public"."fund_request" TO "service_role";



GRANT ALL ON TABLE "public"."fund_request_articles" TO "anon";
GRANT ALL ON TABLE "public"."fund_request_articles" TO "authenticated";
GRANT ALL ON TABLE "public"."fund_request_articles" TO "service_role";



GRANT ALL ON TABLE "public"."fund_request_documents" TO "anon";
GRANT ALL ON TABLE "public"."fund_request_documents" TO "authenticated";
GRANT ALL ON TABLE "public"."fund_request_documents" TO "service_role";



GRANT ALL ON TABLE "public"."fund_request_recipients" TO "anon";
GRANT ALL ON TABLE "public"."fund_request_recipients" TO "authenticated";
GRANT ALL ON TABLE "public"."fund_request_recipients" TO "service_role";



GRANT ALL ON TABLE "public"."fund_request_summary" TO "anon";
GRANT ALL ON TABLE "public"."fund_request_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."fund_request_summary" TO "service_role";



GRANT ALL ON TABLE "public"."institutions_beneficiary_entries" TO "anon";
GRANT ALL ON TABLE "public"."institutions_beneficiary_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."institutions_beneficiary_entries" TO "service_role";



GRANT ALL ON TABLE "public"."order_entries" TO "anon";
GRANT ALL ON TABLE "public"."order_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."order_entries" TO "service_role";



GRANT ALL ON TABLE "public"."public_beneficiary_entries" TO "anon";
GRANT ALL ON TABLE "public"."public_beneficiary_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."public_beneficiary_entries" TO "service_role";



GRANT ALL ON TABLE "public"."order_requirement_view" TO "anon";
GRANT ALL ON TABLE "public"."order_requirement_view" TO "authenticated";
GRANT ALL ON TABLE "public"."order_requirement_view" TO "service_role";



GRANT ALL ON TABLE "public"."public_beneficiary_history" TO "anon";
GRANT ALL ON TABLE "public"."public_beneficiary_history" TO "authenticated";
GRANT ALL ON TABLE "public"."public_beneficiary_history" TO "service_role";



GRANT ALL ON TABLE "public"."public_beneficiary_summary" TO "anon";
GRANT ALL ON TABLE "public"."public_beneficiary_summary" TO "authenticated";
GRANT ALL ON TABLE "public"."public_beneficiary_summary" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































