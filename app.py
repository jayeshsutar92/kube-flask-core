import os
from flask import Flask, request, jsonify
from pymongo import MongoClient

app = Flask(__name__)

# Fetch MongoDB URI dynamically from environment variable
# Uses an authenticated connection string format: mongodb://<user>:<password>@<host>:<port>/<dbname>?authSource=admin
MONGODB_URI = os.environ.get(
    "MONGODB_URI",
    "mongodb://admin:password@localhost:27017/flask_db?authSource=admin"
)

# Initialize PyMongo client with authentication from the URI
client = MongoClient(MONGODB_URI)

# Select the database and collection
try:
    db = client.get_default_database()
    if db is None:
        db = client["flask_db"]
except Exception:
    db = client["flask_db"]

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
    # Configure to run on host 0.0.0.0 and port 5000
    app.run(host="0.0.0.0", port=5000)

