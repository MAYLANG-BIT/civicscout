CREATE DATABASE IF NOT EXISTS civicscout_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE civicscout_db;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('scout', 'lgu') NOT NULL DEFAULT 'scout',
    barangay VARCHAR(100) NOT NULL DEFAULT 'Brgy. Batia',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reports (
    id BIGINT PRIMARY KEY,
    scout_email VARCHAR(150) NOT NULL,
    scout_name VARCHAR(100) NOT NULL,
    barangay VARCHAR(100) NOT NULL,
    category ENUM('Pothole', 'Uncollected Trash', 'Busted Streetlight', 'Damaged Drainage') NOT NULL,
    description TEXT NOT NULL,
    image LONGTEXT,
    lat DECIMAL(10, 7) NOT NULL,
    lng DECIMAL(10, 7) NOT NULL,
    status ENUM('Reported', 'Verified', 'In Progress', 'Resolved', 'Duplicate', 'Rejected/Invalid') DEFAULT 'Reported',
    dispatched_unit VARCHAR(150),
    ai_flagged BOOLEAN DEFAULT FALSE,
    confirmations INT DEFAULT 1,
    confirmed_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scout_email) REFERENCES users(email) ON DELETE CASCADE
);