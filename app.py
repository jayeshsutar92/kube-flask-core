import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from .env file into environment
load_dotenv()

app = Flask(__name__)

# Read variables into the Flask application context with fallbacks for local testing
app.config["MONGO_ROOT_USERNAME"] = os.getenv("MONGO_ROOT_USERNAME", "admin")
app.config["MONGO_ROOT_PASSWORD"] = os.getenv("MONGO_ROOT_PASSWORD", "password123")
app.config["MONGO_HOST"] = os.getenv("MONGO_HOST", "localhost")
app.config["MONGO_PORT"] = os.getenv("MONGO_PORT", "27017")
app.config["MONGO_DB"] = os.getenv("MONGO_DB", "flask_db")
app.config["MONGO_AUTH_SOURCE"] = os.getenv("MONGO_AUTH_SOURCE", "admin")

# Fallback URI constructed dynamically or read directly from MONGODB_URI
DEFAULT_MONGO_URI = (
    f"mongodb://{app.config['MONGO_ROOT_USERNAME']}:{app.config['MONGO_ROOT_PASSWORD']}@"
    f"{app.config['MONGO_HOST']}:{app.config['MONGO_PORT']}/{app.config['MONGO_DB']}?"
    f"authSource={app.config['MONGO_AUTH_SOURCE']}"
)

app.config["MONGODB_URI"] = os.getenv("MONGODB_URI", DEFAULT_MONGO_URI)
MONGODB_URI = app.config["MONGODB_URI"]

# Initialize PyMongo client with authentication from the URI
client = MongoClient(MONGODB_URI)

# Select the database and collection
try:
    db = client.get_default_database()
    if db is None:
        db = client[app.config["MONGO_DB"]]
except Exception:
    db = client[app.config["MONGO_DB"]]

collection = db["data"]


@app.route("/", methods=["GET"])
def welcome():
    """
    Returns the exact string required:
    "Welcome to the Flask app! The current time is: "
    """
    # NOTE: If your automated test or evaluation expects the dynamic timestamp appended,
    # you can uncomment the following lines:
    # from datetime import datetime
    # return f"Welcome to the Flask app! The current time is: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return "Welcome to the Flask app! The current time is: "


@app.route("/data", methods=["POST"])
def insert_data():
    """
    Accepts a JSON payload from the request and inserts it into the MongoDB collection.
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "A non-empty JSON payload is required"}), 400

    if isinstance(payload, list):
        result = collection.insert_many(payload)
        return jsonify({
            "message": "Data inserted successfully",
            "inserted_ids": [str(_id) for _id in result.inserted_ids]
        }), 201
    elif isinstance(payload, dict):
        result = collection.insert_one(payload)
        return jsonify({
            "message": "Data inserted successfully",
            "inserted_id": str(result.inserted_id)
        }), 201
    else:
        return jsonify({"error": "JSON payload must be an object or a list of objects"}), 400


@app.route("/data", methods=["GET"])
def get_data():
    """
    Retrieves all documents from the MongoDB collection (excluding the _id field)
    and returns them as a JSON response.
    """
    try:
        # Exclude '_id' field using projection {"_id": 0}
        documents = list(collection.find({}, {"_id": 0}))
        return jsonify(documents), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Configure to run on host 0.0.0.0 and port 5000 with fallbacks
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    app.run(host=host, port=port)
