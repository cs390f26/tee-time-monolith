from tee_time.types import MemberData, MemberView, PlayerData, TeeTimeData, TeeTimeView


def make_sample_member():
    return MemberView(id="mem_01", name="Alice Smith", phone="555-0100")


def make_sample_slot():
    return TeeTimeData(
        date="2026-09-19",
        time="07:00",
        players=(PlayerData(number=1, member_id="mem_01", name="Alice Smith"),),
    )


def make_sample_slot_view():
    return TeeTimeView(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        players=(PlayerData(number=1, member_id="mem_01", name="Alice Smith"),),
        player_count=1,
        bookable=True,
        available_members=(
            MemberView(id="mem_02", name="Bob Jones", phone="555-0199"),
        ),
    )