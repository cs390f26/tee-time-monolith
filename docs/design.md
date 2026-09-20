# Design

This document describes the design of the Flask server and how data moves through its various layers.  The web API and database are *delivery mechanisms for the core application, and there is one layer for each:

1. **API** — handles HTTP: parse requests, call the application, return responses.
2. **Application** — handles business logic: the rules and workflows of the country club (listing tee times, listing members, adding a member).
3. **DB** — interacts with the database: turn application requests into DynamoDB operations and turn DynamoDB results into data the application can use.



## Data representations

Members and tee times live in one table (`Club`).  The database layer returns the full item.  The application layer picks the fields for the request.  The API layer turns that into HTTP.

### Database Representation

Members and tee times are separate items.  `itemType` tells them apart.

- Member id: `MEMBER#` + eight hex characters
- Tee time id: `SLOT#YYYY-MM-DD#HH:MM` (club-local, 24-hour)

```json
{
  "itemId": "MEMBER#a1b2c3d4",
  "itemType": "member",
  "name": "William Hargrove",
  "phone": "(610) 332-1044"
}
```

```json
{
  "itemId": "SLOT#2026-09-19#07:00",
  "itemType": "teeTime",
  "date": "2026-09-19",
  "time": "07:00",
  "players": {
    "1": { "memberId": "a1b2c3d4", "name": "William Hargrove" },
    "2": { "memberId": "e5f6g7h8", "name": "Margaret Ashford" }
  }
}
```

Players store `memberId` and `name`.  Open: `"players": {}`.  Full: keys `"1"`–`"4"`.  Max four players.  Every scheduled slot is stored, including open ones.



### Raw Query Result

**`MemberData`** and **`TeeTimeData`** match the database (snake_case in Python):

```python
MemberData(
    item_id="MEMBER#a1b2c3d4",
    item_type="member",
    name="William Hargrove",
    phone="(610) 332-1044",
)
```

```python
TeeTimeData(
    item_id="SLOT#2026-09-19#07:00",
    item_type="teeTime",
    date="2026-09-19",
    time="07:00",
    players=[
        {"number": 1, "member_id": "a1b2c3d4", "name": "William Hargrove"},
        {"number": 2, "member_id": "e5f6g7h8", "name": "Margaret Ashford"},
    ],
)
```

List members: keep `itemType == member`, sort by name.  List a week: keep `itemType == teeTime` and dates in range, sort by date then time.  Add member: new `MEMBER#` id.  Load one slot: `SLOT#` id.


### Member View

Name and phone.  **`MemberView`**:

```python
MemberView(
    id="a1b2c3d4",
    name="William Hargrove",
    phone="(610) 332-1044",
)
```



### Tee Time Slot

Time, player names (or open), `player_count` / 4, and whether it is bookable.  **`TeeTimeSlot`**:

```python
TeeTimeSlot(
    date="2026-09-19",
    time="07:00",
    player_names=["William Hargrove", "Margaret Ashford"],
    player_count=2,
    bookable=True,
)
```

Bookable when `player_count < 4`.  Open: no names, `player_count` 0.



## Sample data

`data/sample-data.json` — same item shapes.  Twelve members and every slot for Sep 14–20, 2026.

| Use case | Item |
|----------|------|
| List / add members | twelve `MEMBER#` items below |
| Open (`0/4`) | `SLOT#2026-09-14#08:00` |
| One player | `SLOT#2026-09-14#08:10` Thomas Langley |
| Two players | `SLOT#2026-09-19#07:00` William Hargrove, Margaret Ashford |
| Three players | `SLOT#2026-09-15#08:00` Priya Shah, Robert Vance, Diana Cole |
| Full (`4/4`) | `SLOT#2026-09-16#07:00` William Hargrove, Margaret Ashford, Charles Beaumont, Eleanor Whitfield |

| itemId | Name | Phone |
|--------|------|-------|
| `MEMBER#a1b2c3d4` | William Hargrove | (610) 332-1044 |
| `MEMBER#e5f6g7h8` | Margaret Ashford | (610) 867-2210 |
| `MEMBER#c4e91a26` | Charles Beaumont | (610) 691-4482 |
| `MEMBER#d5f02b37` | Eleanor Whitfield | (610) 258-7731 |
| `MEMBER#e6013c48` | Thomas Langley | (484) 821-0095 |
| `MEMBER#f7124d59` | James Whitaker | (610) 974-3360 |
| `MEMBER#08235e6a` | Helen Cho | (610) 419-8827 |
| `MEMBER#19346f7b` | Robert Vance | (484) 635-1108 |
| `MEMBER#2a45708c` | Priya Shah | (610) 746-2294 |
| `MEMBER#3b56819d` | Arthur Quinn | (610) 882-5401 |
| `MEMBER#4c6792ae` | Diana Cole | (484) 201-6673 |
| `MEMBER#5d78a3bf` | Frank Moretti | (610) 317-0946 |
