DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS tee_times;
DROP TABLE IF EXISTS members;

CREATE TABLE members (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL
) ENGINE=InnoDB;


CREATE TABLE tee_times (
    id INT PRIMARY KEY AUTO_INCREMENT,
    slot_date DATE NOT NULL,
    slot_time TIME NOT NULL,
    CONSTRAINT uq_slot UNIQUE (slot_date, slot_time)
) ENGINE=InnoDB;


CREATE TABLE bookings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    tee_time_id INT NOT NULL,
    member_id VARCHAR(50) NOT NULL,
    player_position INT NOT NULL,
    CONSTRAINT chk_player_position CHECK (player_position BETWEEN 1 AND 4),
    CONSTRAINT fk_booking_tee_time FOREIGN KEY (tee_time_id) REFERENCES tee_times(id) ON DELETE CASCADE,
    CONSTRAINT fk_booking_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    CONSTRAINT uq_booking_position UNIQUE (tee_time_id, player_position),
    CONSTRAINT uq_booking_member UNIQUE (tee_time_id, member_id)
) ENGINE=InnoDB;
