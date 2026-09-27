DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS tee_times;
DROP TABLE IF EXISTS members;

CREATE TABLE members (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL
);


CREATE TABLE tee_times (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slot_date DATE NOT NULL,
    slot_time TIME NOT NULL,
    UNIQUE (slot_date, slot_time)
);


CREATE TABLE bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tee_time_id INT NOT NULL,
    member_id VARCHAR(50) NOT NULL,
    player_position INT NOT NULL CHECK (player_position BETWEEN 1 AND 4),
    FOREIGN KEY (tee_time_id) REFERENCES tee_times(id) ON DELETE CASCADE,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    UNIQUE (tee_time_id, player_position), 
    UNIQUE (tee_time_id, member_id)   
);

