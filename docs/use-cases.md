# Use cases

The site lists tee times, books an open slot for a member, and lists and adds members. These cases are the behavior to build and test.

| ID | Use case | Actor | Writes |
|----|----------|-------|--------|
| [UC-1](#uc-1-browse-tee-times) | Browse tee times | Site user | No |
| [UC-2](#uc-2-book-a-tee-time) | Book a tee time | Site user | Yes |
| [UC-3](#uc-3-view-members) | View members | Site user | No |
| [UC-4](#uc-4-add-a-member) | Add a member | Site user | Yes |
| [UC-5](#uc-5-health) | Health | Tests / ops | No |

## UC-1 Browse tee times

**Actor:** Someone using the site.

### Happy path

1. Open the times page.
2. The app loads all tee times.
3. Each row shows the date, the time, and the status: **open**, or **booked** with the member's name.
4. Open slots can be selected.

### Other outcomes

| Situation | Result |
|-----------|--------|
| No tee times | Empty message. This is not an error. |
| Bad URL | Not-found page. |
| Database down | Unavailable. An empty list is not shown in place of the failure. |

**After:** Nothing is written.

## UC-2 Book a tee time

**Actor:** Someone using the site.

### Happy path

1. Select an open time with fewer than four players.
2. Choose a member who is not already on that time.
3. Confirm **Book**.
4. The app checks that the slot still has fewer than four players and that the member is not already listed, then appends the member.
5. The count goes up by one and the name appears. A slot that now has four players is no longer selectable.
6. A reload still shows the group.

### Other outcomes

| Situation | Result |
|-----------|--------|
| No slot, or no member | Nothing written. |
| Unknown member or unknown slot | 404. Nothing written. |
| Slot already 4/4 (race or double-submit) | “foursome full”. Nothing written. |
| Member already on this time | “already booked on this slot”. Nothing written. |
| Database down on read or write | 503. The slot is unchanged. The member is shown as booked only after the write succeeds. |

**After (success):** Exactly one member was added to that tee time. Other tee times are unchanged.

## UC-3 View members

**Actor:** Someone using the site.

### Happy path

1. Open the members page.
2. The list shows each member's name and contact, in a stable order.
3. The add-member form is on the same page.

### Other outcomes

| Situation | Result |
|-----------|--------|
| No members | “No members”. The add form stays on the page. Booking fails until a member exists ([UC-4](#uc-4-add-a-member)). |
| Bad URL | Not-found page. |
| Database down | 503. |

**After:** Nothing is written.

## UC-4 Add a member

**Actor:** Someone using the site.

### Happy path

1. Fill in a name and a contact. Contact is an email or a phone; one of them is required.
2. Submit.
3. The app validates the input, stores the member, and returns an id.
4. The list updates and the form clears.
5. The new member appears in the booking picker.

### Other outcomes

| Situation | Result |
|-----------|--------|
| Blank or missing name | Nothing written. |
| Name too long | Nothing written. |
| Bad email | Nothing written. |
| Duplicate email (when email is unique) | Nothing written. |
| Database down | 503. The roster is unchanged. |

**After (success):** One new member exists. Tee times are unchanged.

## UC-5 Health

**Actor:** Tests or operations. `GET /health`.

### Happy path

The database and its table are reachable. Respond **200** with `{"status":"ok"}`.

### Other outcomes

| Situation | Result |
|-----------|--------|
| Caller error | None. |
| Database or table missing | **503** `{"status":"unavailable"}`. |
