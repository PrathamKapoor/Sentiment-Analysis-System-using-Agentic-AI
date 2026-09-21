import os

from dotenv import load_dotenv

# Match the Flask CLI's behavior: load backend/.env before the app
# factory reads configuration, so `python run.py` and
# `flask --app run.py run` see the same environment.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
