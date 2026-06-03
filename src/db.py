from __future__ import annotations

import logging

import mysql.connector

log = logging.getLogger(__name__)


def get_connection(db_params: dict) -> mysql.connector.MySQLConnection:
    """Create a new MySQL connection from the given params."""
    return mysql.connector.connect(**db_params)


def load_existing_images(connection: mysql.connector.MySQLConnection) -> list[str]:
    """Load all image URLs already stored in the movies and series tables."""
    cursor = connection.cursor()
    images: list[str] = []
    for table in ("series", "movies"):
        cursor.execute(f"SELECT image_url FROM {table}")  # noqa: S608
        for row in cursor.fetchall():
            images.append(row[0])
    cursor.close()
    return images


def delete_rows_by_image(connection: mysql.connector.MySQLConnection, image_url: str) -> int:
    """Delete every stored row for a poster image. Returns rows removed."""
    cursor = connection.cursor()
    removed = 0
    for table in ("series", "movies", "zip"):
        cursor.execute(f"DELETE FROM {table} WHERE image_url = %s", (image_url,))  # noqa: S608
        removed += cursor.rowcount
    connection.commit()
    cursor.close()
    log.info("Deleted %d dead rows for %s", removed, image_url[:80])
    return removed


def fetch_stored_links(
    connection: mysql.connector.MySQLConnection, image_url: str
) -> list[tuple[str, str, str]]:
    """Fetch stored rows for a poster image as (table, captions, links) triples.

    `captions` is the human-readable column (series.links, movies.caption,
    zip.links), `links` the newline-joined direct links (org_links).
    Empty when the title was never scraped.
    """
    cursor = connection.cursor()
    rows: list[tuple[str, str, str]] = []
    for table, caption_column in (
        ("series", "links"),
        ("movies", "caption"),
        ("zip", "links"),
    ):
        cursor.execute(
            f"SELECT {caption_column}, org_links FROM {table} WHERE image_url = %s",  # noqa: S608
            (image_url,),
        )
        for captions, links in cursor.fetchall():
            if links:
                rows.append((table, captions or "", links))
    cursor.close()
    return rows


def insert_series(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    description: str,
    captions: str,
    direct_links: str,
) -> int:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO series (image_url, movie_descrp, links, org_links) VALUES (%s, %s, %s, %s)",
        (image_url, description, captions, direct_links),
    )
    connection.commit()
    row_id = cursor.lastrowid
    cursor.close()
    log.debug("Inserted series row %s", row_id)
    return row_id


def insert_ongoing(
    connection: mysql.connector.MySQLConnection,
    series_link: str,
    episode_links: str,
) -> int:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO ongoing (serieslink, episodelinks) VALUES (%s, %s)",
        (series_link, episode_links),
    )
    connection.commit()
    row_id = cursor.lastrowid
    cursor.close()
    log.debug("Inserted ongoing row %s", row_id)
    return row_id


def insert_movie(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    caption: str,
    direct_links: str,
) -> int:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO movies (image_url, caption, org_links) VALUES (%s, %s, %s)",
        (image_url, caption, direct_links),
    )
    connection.commit()
    row_id = cursor.lastrowid
    cursor.close()
    log.debug("Inserted movie row %s", row_id)
    return row_id


def insert_zip(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    caption: str,
    direct_links: str,
) -> int:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO zip (image_url, links, org_links) VALUES (%s, %s, %s)",
        (image_url, caption, direct_links),
    )
    connection.commit()
    row_id = cursor.lastrowid
    cursor.close()
    log.debug("Inserted zip row %s", row_id)
    return row_id
