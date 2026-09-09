import os
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

@app.route("/register", methods=["POST"])
def register():
    """Body: {"discord_id": 123456789, "team_id": 2093872}
    Inserts, or updates team_id if this discord_id is already registered."""
    data = request.get_json()
    discord_id = data.get("discord_id")
    team_id = data.get("team_id")

    if discord_id is None or team_id is None:
        return jsonify({"error": "discord_id and team_id are required"}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_teams (discord_id, team_id)
        VALUES (%s, %s)
        ON CONFLICT (discord_id) DO UPDATE SET team_id = EXCLUDED.team_id
    """, (discord_id, team_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"discord_id": discord_id, "team_id": team_id}), 200

@app.route("/users/<int:discord_id>", methods=["GET"])
def get_user(discord_id):
    """Returns {"discord_id": ..., "team_id": ...} or 404 if not registered."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM user_teams WHERE discord_id = %s", (discord_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is None:
        return jsonify({"error": "not registered"}), 404
    return jsonify(row), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)