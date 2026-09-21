# Phase 12 disposable production-stack environment
# Uses the public schema of the dev database; the audit script
# creates and drops its own isolated schema internally.
# DATABASE_URL (with credentials) intentionally NOT stored here:
# the orchestrator loads it from backend/.env (gitignored). Never put
# a database password in this script file.
# export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME'
export JWT_SECRET_KEY='phase12-jwt-secret-32-bytes-or-more-validation-aaaaaa'
export SECRET_KEY='phase12-flask-secret-32-bytes-or-more-validation-bbbbbb'
export FRONTEND_URL='http://localhost:5173'
export FLASK_ENV='production'
export TRUSTED_PROXY_COUNT='1'
export CORS_ALLOWED_ORIGINS='http://localhost:5173,http://localhost:8080'
export LOG_JSON='true'
export LOG_LEVEL='INFO'
export RATE_LIMIT_ENABLED='true'
export LIMITER_STORAGE_URL='memory://'
export REPORT_OUTPUT_DIRECTORY='C:/tmp/phase12_reports'
export UPLOAD_FOLDER='C:/tmp/phase12_uploads'
export LLM_PROVIDER='deterministic'
export SENTIMENT_ENGINE='vader'