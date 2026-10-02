import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import date

logging.basicConfig(
    filename="library.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)

PHONE_RE = re.compile(r"^\+998\d{9}$")
MIN_YEAR = 1000


class LibraryError(Exception):
    """Biznes-mantiq xatolari (foydalanuvchiga ko'rsatiladi)."""


class Book:
    def __init__(self, title, author, year, status="bor", id=None):
        self.id = id
        self.title = title
        self.author = author
        self.year = year
        self.status = status  


class Member:
    def __init__(self, name, phone, id=None):
        self.id = id
        self.name = name
        self.phone = phone


class Library:
    def __init__(self, db_name="library.db"):
        self.db_name = db_name
        self.init_db()

    @contextmanager
    def connect(self):
        """Ulanishni ochadi, muvaffaqiyatda commit, xatoda rollback, oxirida yopadi."""
        conn = sqlite3.connect(self.db_name)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """Dastur birinchi marta ishga tushganda jadvallarni yaratadi."""
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    year INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rentals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL UNIQUE,
                    member_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES books(id),
                    FOREIGN KEY (member_id) REFERENCES members(id)
                )
            """)

    _BOOK_SELECT = """
        SELECT b.id, b.title, b.author, b.year,
               CASE WHEN r.id IS NULL THEN 'bor' ELSE 'berilgan' END
        FROM books b
        LEFT JOIN rentals r ON r.book_id = b.id
    """

    @staticmethod
    def _row_to_book(row):
        return Book(id=row[0], title=row[1], author=row[2], year=row[3], status=row[4])

    def add_book(self, book: Book):
        if not book.title or not book.author:
            raise LibraryError("Kitob nomi va muallifi bo'sh bo'lishi mumkin emas!")
        current_year = date.today().year
        if not (MIN_YEAR <= book.year <= current_year):
            raise LibraryError(f"Yil {MIN_YEAR} dan {current_year} gacha bo'lishi kerak!")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO books (title, author, year) VALUES (?, ?, ?)",
                (book.title, book.author, book.year),
            )

    def get_all_books(self):
        with self.connect() as conn:
            rows = conn.execute(self._BOOK_SELECT + " ORDER BY b.id").fetchall()
        return [self._row_to_book(r) for r in rows]

    def search_books(self, query):
        q = query.casefold()
        return [
            b for b in self.get_all_books()
            if q in b.title.casefold() or q in b.author.casefold()
        ]

    def get_book_status(self, book_id):
        """Kitob holatini ('bor'/'berilgan') qaytaradi, kitob yo'q bo'lsa None."""
        with self.connect() as conn:
            row = conn.execute(
                self._BOOK_SELECT + " WHERE b.id = ?", (book_id,)
            ).fetchone()
        return row[4] if row else None

    # ---------- A'zolar ----------

    def add_member(self, member: Member):
        if not member.name:
            raise LibraryError("Ism kiritilishi shart!")
        phone = re.sub(r"[\s\-()]", "", member.phone)
        if not PHONE_RE.match(phone):
            raise LibraryError("Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak!")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO members (name, phone) VALUES (?, ?)",
                (member.name, phone),
            )

    def member_exists(self, member_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM members WHERE id = ?", (member_id,)
            ).fetchone()
        return row is not None

    # ---------- Ijara ----------

    def rent_book(self, book_id, member_id):
        status = self.get_book_status(book_id)
        if status is None:
            raise LibraryError("Bunday ID li kitob mavjud emas!")
        if not self.member_exists(member_id):
            raise LibraryError("Bunday ID li a'zo mavjud emas!")
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO rentals (book_id, member_id) VALUES (?, ?)",
                    (book_id, member_id),
                )
        except sqlite3.IntegrityError:
            raise LibraryError("Bu kitob allaqachon birovga berilgan!")

    def return_book(self, book_id):
        status = self.get_book_status(book_id)
        if status is None:
            raise LibraryError("Bunday ID li kitob mavjud emas!")
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM rentals WHERE book_id = ?", (book_id,))
            if cur.rowcount == 0:
                raise LibraryError("Bu kitob ijaraga berilmagan, u kutubxonada turibdi.")

    def get_rented_books_with_members(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT b.id, b.title, m.name
                FROM rentals r
                JOIN books b ON r.book_id = b.id
                JOIN members m ON r.member_id = m.id
                ORDER BY b.id
            """).fetchall()


def read_int(prompt):
    try:
        return int(input(prompt).strip())
    except ValueError:
        raise LibraryError("Raqam o'rniga harf yoki noto'g'ri format kiritildi!")


def print_menu():
    print("\n=== KUTUBXONA MENYUSI ===")
    print("1. Kitob qo'shish")
    print("2. Barcha kitoblar")
    print("3. Kitob qidirish")
    print("4. A'zo qo'shish")
    print("5. Kitob berish")
    print("6. Kitobni qaytarish")
    print("7. Kimda qaysi kitob bor")
    print("0. Chiqish")


def print_book(b):
    print(f"ID: {b.id} | Nomi: {b.title} | Muallifi: {b.author} | Yili: {b.year} | Holati: {b.status}")


def main():
    library = Library()

    while True:
        print_menu()
        choice = input("Tanlovingizni kiriting: ").strip()

        try:
            if choice == "1":
                title = input("Kitob nomi: ").strip()
                author = input("Muallifi: ").strip()
                year = read_int("Chop etilgan yili: ")
                library.add_book(Book(title, author, year))
                print("Muvaffaqiyatli qo'shildi!")

            elif choice == "2":
                books = library.get_all_books()
                if not books:
                    print("Kutubxonada hozircha kitoblar yo'q.")
                else:
                    print("\n--- BARCHA KITOBLAR ---")
                    for b in books:
                        print_book(b)

            elif choice == "3":
                query = input("Qidirilayotgan kitob nomi yoki muallifini kiriting: ").strip()
                if not query:
                    raise LibraryError("Qidiruv matni bo'sh bo'lmasligi kerak.")
                results = library.search_books(query)
                if not results:
                    print("Hech qanday kitob topilmadi.")
                else:
                    print(f"\n--- TOPILGAN KITOBLAR ({len(results)} ta) ---")
                    for b in results:
                        print_book(b)

            elif choice == "4":
                name = input("A'zoning ismi: ").strip()
                phone = input("Telefon raqami (+998XXXXXXXXX): ").strip()
                library.add_member(Member(name, phone))
                print("Yangi a'zo muvaffaqiyatli qo'shildi!")

            elif choice == "5":
                book_id = read_int("Kitob ID sini kiriting: ")
                member_id = read_int("A'zo ID sini kiriting: ")
                library.rent_book(book_id, member_id)
                print("Kitob a'zoga muvaffaqiyatli berildi!")

            elif choice == "6":
                book_id = read_int("Qaytariladigan kitob ID sini kiriting: ")
                library.return_book(book_id)
                print("Kitob muvaffaqiyatli qaytarildi!")

            elif choice == "7":
                rentals = library.get_rented_books_with_members()
                if not rentals:
                    print("Hozircha hech kim kitob olmagan.")
                else:
                    print("\n--- IJARADAGI KITOBLAR ---")
                    for book_id, title, member_name in rentals:
                        print(f"Kitob ID: {book_id} | Nomi: '{title}' -> Kimda: {member_name}")

            elif choice == "0":
                print("Dastur tugatildi. Xayr!")
                break

            else:
                print("Xato: Noto'g'ri menyu tanlandi. 0 dan 7 gacha raqam kiriting.")

        except LibraryError as e:
            print(f"Xato: {e}")
        except Exception:
            logging.exception("Kutilmagan xatolik")
            print("Kutilmagan xatolik yuz berdi (library.log ga yozildi). Menyuga qaytilmoqda...")


if __name__ == "__main__":
    main()