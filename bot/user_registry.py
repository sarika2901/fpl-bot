import os
import psycopg2

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def register_user(discord_user_id, team_id):
    """Registers or updates a user's FPL team ID directly in Postgres."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_teams (discord_id, team_id)
        VALUES (%s, %s)
        ON CONFLICT (discord_id) DO UPDATE SET team_id = EXCLUDED.team_id
    """, (discord_user_id, team_id))
    conn.commit()
    cur.close()
    conn.close()

def get_registered_team(discord_user_id):
    """Returns the registered team_id for a discord_user_id, or None if not registered."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT team_id FROM user_teams WHERE discord_id = %s", (discord_user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None