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


def insert_series(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    description: str,
    captions: str,
    direct_links: str,
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO series (image_url, movie_descrp, links, org_links) VALUES (%s, %s, %s, %s)",
        (image_url, description, captions, direct_links),
    )
    connection.commit()
    cursor.close()
    log.info("Inserted series: %s", image_url)


def insert_ongoing(
    connection: mysql.connector.MySQLConnection,
    series_link: str,
    episode_links: str,
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO ongoing (serieslink, episodelinks) VALUES (%s, %s)",
        (series_link, episode_links),
    )
    connection.commit()
    cursor.close()
    log.info("Inserted ongoing series: %s", series_link)


def insert_movie(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    caption: str,
    direct_links: str,
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO movies (image_url, caption, org_links) VALUES (%s, %s, %s)",
        (image_url, caption, direct_links),
    )
    connection.commit()
    cursor.close()
    log.info("Inserted movie: %s", image_url)


def insert_zip(
    connection: mysql.connector.MySQLConnection,
    image_url: str,
    caption: str,
    direct_links: str,
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO zip (image_url, links, org_links) VALUES (%s, %s, %s)",
        (image_url, caption, direct_links),
    )
    connection.commit()
    cursor.close()
    log.info("Inserted zip: %s", image_url)
