
long_init_query = """CREATE DATABASE moviemod;

USE moviemod;

CREATE TABLE movies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    caption TEXT,
    org_links TEXT
);

CREATE TABLE series (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    movie_descrp TEXT,
    links TEXT,
    org_links TEXT
);

CREATE TABLE ongoing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    serieslink TEXT,
    episodelinks TEXT
);

CREATE TABLE zip (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    links TEXT,
    org_links TEXT
);"""
