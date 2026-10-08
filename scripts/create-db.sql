-- Run as root before scripts/schema.sql. Creates the app database and the
-- account the app uses over TCP (127.0.0.1) and over the local socket.
CREATE DATABASE IF NOT EXISTS tee_time;
CREATE USER IF NOT EXISTS 'tee_time'@'localhost' IDENTIFIED BY 'tee_time';
CREATE USER IF NOT EXISTS 'tee_time'@'127.0.0.1' IDENTIFIED BY 'tee_time';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'localhost';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'127.0.0.1';
FLUSH PRIVILEGES;
