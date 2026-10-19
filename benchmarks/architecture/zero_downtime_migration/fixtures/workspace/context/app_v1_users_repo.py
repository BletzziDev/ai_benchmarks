"""accounts-api v1 — data access for users (excerpt)."""


class UsersRepo:
    def __init__(self, db):
        self.db = db

    def get(self, user_id: int) -> dict:
        row = self.db.fetch_one("SELECT id, email, name FROM users WHERE id = %s", (user_id,))
        return {"id": row[0], "email": row[1], "display_name": row[2]}

    def create(self, user_id: int, email: str, name: str) -> None:
        self.db.execute("INSERT INTO users (id, email, name) VALUES (%s, %s, %s)", (user_id, email, name))

    def rename(self, user_id: int, name: str) -> None:
        self.db.execute("UPDATE users SET name = %s WHERE id = %s", (name, user_id))
