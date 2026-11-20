import psycopg2
from app.core.config import settings

def get_connection_db():
    conn = psycopg2.connect(
        host = settings.DB_HOST,
        port = settings.DB_PORT,
        dbname = settings.DB_NAME,
        user = settings.DB_USER,
        password = settings.DB_PASSWORD,
    )
    return conn

if __name__ == "__main__":
    conn = get_connection_db()
    print("Connected to PostgreSQL")
