CREATE TABLE IF NOT EXISTS movies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    caption TEXT,
    org_links TEXT
);

CREATE TABLE IF NOT EXISTS series (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    movie_descrp TEXT,
    links TEXT,
    org_links TEXT
);

CREATE TABLE IF NOT EXISTS ongoing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    serieslink TEXT,
    episodelinks TEXT
);

CREATE TABLE IF NOT EXISTS zip (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url TEXT,
    links TEXT,
    org_links TEXT
);