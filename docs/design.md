# Design

This document describes the design of the Flask server and how data moves through its layers. A request follows one path:

**app.py → TeeTimeApp → ClubStorage**

1. **API** (`app.py`) — handles HTTP: parse requests, call `TeeTimeApp`, return responses.
2. **Application** (`TeeTimeApp`) — handles business logic: the rules and workflows of the country club (listing tee times, listing members, adding a member, booking a player).
3. **DB** (`ClubStorage`) — interacts with MySQL: turn application requests into SQL and turn rows into data the application can use.

`ClubStorage` reads and writes the tables in `scripts/schema.sql`. The application never sees raw rows. The API never talks to MySQL.


## Tables

Members, tee times, and bookings are three InnoDB tables. A player's name lives on `members`. A booking points at a member and a tee time.

### members

| Column | Type | Constraints |
|--------|------|-------------|
| id | `VARCHAR(50)` | `PRIMARY KEY` |
| name | `VARCHAR(100)` | `NOT NULL` |
| phone | `VARCHAR(20)` | `NOT NULL` |

A member id is eight hex characters, such as `a1b2c3d4`. `TeeTimeApp.add_member` generates that id and stores it in `members.id`.

```text
id        name              phone
a1b2c3d4  William Hargrove  (610) 332-1044
```

### tee_times

| Column | Type | Constraints |
|--------|------|-------------|
| id | `INT` | `PRIMARY KEY AUTO_INCREMENT` |
| slot_date | `DATE` | `NOT NULL` |
| slot_time | `TIME` | `NOT NULL` |

`uq_slot` is unique on (`slot_date`, `slot_time`). The integer `id` stays inside the database. The public slot id is the date and time joined as `2026-09-19T07:00:00`.

```text
id  slot_date   slot_time
52  2026-09-19  07:00:00
```

### bookings

| Column | Type | Constraints |
|--------|------|-------------|
| id | `INT` | `PRIMARY KEY AUTO_INCREMENT` |
| tee_time_id | `INT` | `NOT NULL`, foreign key to `tee_times(id)` `ON DELETE CASCADE` |
| member_id | `VARCHAR(50)` | `NOT NULL`, foreign key to `members(id)` `ON DELETE CASCADE` |
| player_position | `INT` | `NOT NULL`, `CHECK (player_position BETWEEN 1 AND 4)` |

`uq_booking_position` is unique on (`tee_time_id`, `player_position`). `uq_booking_member` is unique on (`tee_time_id`, `member_id`). A slot holds at most four players, each position once, and each member once.

```text
tee_time_id  member_id  player_position
52           a1b2c3d4   1
52           e5f6g7h8   2
```

An open slot is a `tee_times` row with no bookings, or one of the sixteen default times with no row yet. A full slot has `player_position` values 1 through 4.


## Data representations

`ClubStorage` returns `MemberData` and `TeeTimeData`. `TeeTimeApp` picks the fields for the request. `app.py` turns that into HTTP.

### Stored records

`ClubStorage` maps `members` rows to **`MemberData`**. It maps a `tee_times` row plus its `bookings` (joined to `members` for the name) to **`TeeTimeData`**. Dates are `YYYY-MM-DD`. Times are `HH:MM`. Players are in `player_position` order.

```python
MemberData(
    id="a1b2c3d4",
    name="William Hargrove",
    phone="(610) 332-1044",
)
```

```python
TeeTimeData(
    date="2026-09-19",
    time="07:00",
    players=(
        PlayerData(number=1, member_id="a1b2c3d4", name="William Hargrove"),
        PlayerData(number=2, member_id="e5f6g7h8", name="Margaret Ashford"),
    ),
)
```

List members: every `members` row, sorted by name, then id. List a day: `tee_times` for that date, then the sixteen default times from 07:00 through 14:30, every 30 minutes. A default time with no row is an empty slot. Add member: insert a new eight-hex id. Load one slot: match `slot_date` and `slot_time`. Book: insert a `bookings` row, creating the `tee_times` row when that date and time are not stored yet.


### Member view

Name and phone. **`MemberView`**:

```python
MemberView(
    id="a1b2c3d4",
    name="William Hargrove",
    phone="(610) 332-1044",
)
```


### Tee time slot

A card grid. Each card is the time and a 4-mark fullness indicator. Click a card with `player_count` under 4 to book it, when the slot has not started yet. A full card and a past slot are not clickable. Reserved bookings, past and upcoming, are a separate list. **`TeeTimeSlot`**:

```python
TeeTimeSlot(
    id="2026-09-19T07:00:00",
    date="2026-09-19",
    time="07:00",
    player_names=("William Hargrove", "Margaret Ashford"),
    player_count=2,
    bookable=True,
)
```

Bookable when `player_count < 4` and the slot's start is still ahead of the club clock. Open: no names, `player_count` 0.

### Tee time booking view

`GET /tee-times/{slotId}` (and the same JSON after `POST .../bookings`) is what the book page loads. It sends two lists: who is already playing, then who can still be picked.

```python
TeeTimeView(
    id="2026-09-19T07:00:00",
    date="2026-09-19",
    time="07:00",
    players=(
        PlayerData(number=1, member_id="a1b2c3d4", name="William Hargrove"),
        PlayerData(number=2, member_id="e5f6g7h8", name="Margaret Ashford"),
    ),
    player_count=2,
    bookable=True,
    available_members=(
        MemberView(id="c4e91a26", name="Charles Beaumont", phone="(610) 691-4482"),
        MemberView(id="d5f02b37", name="Eleanor Whitfield", phone="(610) 258-7731"),
    ),
)
```

`available_members` is the roster minus anyone already in `players`. The book page shows booked names as read-only rows and fills the empty rows from `available_members`.


## Sample data

`scripts/seed-data.sql` loads twelve members, tee times for Sep 14–20, 2026, and their bookings.

| Use case | Rows |
|----------|------|
| List / add members | twelve `members` rows below |
| Open (`0/4`) | `2026-09-14` `08:00:00`, no bookings |
| One player | `2026-09-14` `08:10:00`, Thomas Langley |
| Two players | `2026-09-19` `07:00:00`, William Hargrove, Margaret Ashford |
| Three players | `2026-09-15` `08:00:00`, Priya Shah, Robert Vance, Diana Cole |
| Full (`4/4`) | `2026-09-16` `07:00:00`, William Hargrove, Margaret Ashford, Charles Beaumont, Eleanor Whitfield |

| id | Name | Phone |
|----|------|-------|
| `a1b2c3d4` | William Hargrove | (610) 332-1044 |
| `e5f6g7h8` | Margaret Ashford | (610) 867-2210 |
| `c4e91a26` | Charles Beaumont | (610) 691-4482 |
| `d5f02b37` | Eleanor Whitfield | (610) 258-7731 |
| `e6013c48` | Thomas Langley | (484) 821-0095 |
| `f7124d59` | James Whitaker | (610) 974-3360 |
| `08235e6a` | Helen Cho | (610) 419-8827 |
| `19346f7b` | Robert Vance | (484) 635-1108 |
| `2a45708c` | Priya Shah | (610) 746-2294 |
| `3b56819d` | Arthur Quinn | (610) 882-5401 |
| `4c6792ae` | Diana Cole | (484) 201-6673 |
| `5d78a3bf` | Frank Moretti | (610) 317-0946 |
