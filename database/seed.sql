-- Plain-SQL equivalent of `flask seed` (see database/README.md).
-- Requires the pgcrypto extension for gen_random_uuid().
-- Safe to re-run: every insert is guarded with ON CONFLICT DO NOTHING.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Fixed permission catalogue
INSERT INTO permissions (id, code, description) VALUES
  (gen_random_uuid(), 'create_project', 'Create a project'),
  (gen_random_uuid(), 'edit_project', 'Edit, archive, or delete a project'),
  (gen_random_uuid(), 'delete_project', 'Delete a project'),
  (gen_random_uuid(), 'upload_dataset', 'Upload a dataset'),
  (gen_random_uuid(), 'manage_data_sources', 'Add, edit, enable, or disable data sources'),
  (gen_random_uuid(), 'view_reviews', 'View reviews and analysis results'),
  (gen_random_uuid(), 'correct_sentiment', 'Correct a review''s sentiment label'),
  (gen_random_uuid(), 'generate_report', 'Generate, download, or delete reports'),
  (gen_random_uuid(), 'manage_alerts', 'Create, edit, or resolve alert rules'),
  (gen_random_uuid(), 'manage_users', 'Invite, edit, activate/deactivate, or remove users'),
  (gen_random_uuid(), 'manage_roles', 'Create, edit, or delete roles and assign permissions'),
  (gen_random_uuid(), 'approve_ai_output', 'Approve AI-generated summaries and recommendations')
ON CONFLICT (code) DO NOTHING;

-- Built-in roles (organisation_id = NULL)
INSERT INTO roles (id, organisation_id, name, is_custom, created_at, updated_at) VALUES
  (gen_random_uuid(), NULL, 'Organisation Owner', false, now(), now()),
  (gen_random_uuid(), NULL, 'Organisation Administrator', false, now(), now()),
  (gen_random_uuid(), NULL, 'Project Manager', false, now(), now()),
  (gen_random_uuid(), NULL, 'Analyst', false, now(), now()),
  (gen_random_uuid(), NULL, 'Data Collector', false, now(), now()),
  (gen_random_uuid(), NULL, 'Viewer', false, now(), now())
ON CONFLICT (organisation_id, name) DO NOTHING;

-- Owner and Administrator: every permission
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.organisation_id IS NULL AND r.name IN ('Organisation Owner', 'Organisation Administrator')
ON CONFLICT DO NOTHING;

-- Project Manager
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN (
  'create_project', 'edit_project', 'upload_dataset', 'manage_data_sources',
  'view_reviews', 'correct_sentiment', 'generate_report', 'manage_alerts', 'approve_ai_output'
)
WHERE r.organisation_id IS NULL AND r.name = 'Project Manager'
ON CONFLICT DO NOTHING;

-- Analyst
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN (
  'upload_dataset', 'view_reviews', 'correct_sentiment', 'generate_report', 'manage_alerts'
)
WHERE r.organisation_id IS NULL AND r.name = 'Analyst'
ON CONFLICT DO NOTHING;

-- Data Collector
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN (
  'upload_dataset', 'manage_data_sources', 'view_reviews'
)
WHERE r.organisation_id IS NULL AND r.name = 'Data Collector'
ON CONFLICT DO NOTHING;

-- Viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = 'view_reviews'
WHERE r.organisation_id IS NULL AND r.name = 'Viewer'
ON CONFLICT DO NOTHING;
