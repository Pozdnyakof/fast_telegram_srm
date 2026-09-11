"""Tests for building membership journal entries from Telegram updates.

The sheet shows the client what they want to see, with its own skip
rules. The journal is different: it records every membership change as
it happened, so that it can confirm who invited whom and tell who stayed.

That is why its rules are stricter: a join is a move from outside to
inside, not any update that ends with status "member". A demoted
administrator did not join anything.
"""

from datetime import datetime, timezone

from app.services.journal import event_from_join_request, event_from_member_update

_WHEN = datetime(2026, 9, 10, 15, 1, 38, tzinfo=timezone.utc)


class _User:
    def __init__(self, user_id, full_name="Anna P", username=None):
        self.id = user_id
        self.full_name = full_name
        self.username = username


class _Member:
    def __init__(self, status, user=None):
        self.status = status
        self.user = user


class _Chat:
    def __init__(self, type_="channel"):
        self.id = -1003158922677
        self.type = type_
        self.title = "Хоккей в плюсе | VIP"


class _Invite:
    def __init__(self, invite_link="https://t.me/+abc", name="Promo"):
        self.invite_link = invite_link
        self.name = name


class _MemberUpdate:
    def __init__(self, old, new, user, actor, invite=None, chat=None):
        self.chat = chat or _Chat()
        self.old_chat_member = _Member(old, user) if old else None
        self.new_chat_member = _Member(new, user)
        self.from_user = actor
        self.invite_link = invite
        self.date = _WHEN


class _Request:
    def __init__(self, user, invite=None):
        self.chat = _Chat()
        self.from_user = user
        self.invite_link = invite
        self.date = _WHEN


class _RawUpdate:
    def __init__(self, update_id=155191255):
        self.update_id = update_id


_PERSON = _User(7175828896, "настькин я", "daneksosol")
_OUR_ACCOUNT = _User(8421258155, "Xbdcnh")


def test_a_person_added_by_our_account_is_a_join_with_that_actor():
    """The event the whole integration exists for: who added whom.

    `from_user` is whoever caused the change. When a person is added,
    that is not them but the one who added them, and this is how
    Telegram itself confirms who made the invite.
    """
    update = _MemberUpdate("left", "member", _PERSON, actor=_OUR_ACCOUNT)

    event = event_from_member_update(update, _RawUpdate())

    assert event is not None
    assert event["event"] == "join"
    assert event["user_id"] == 7175828896
    assert event["actor_id"] == 8421258155
    assert event["update_id"] == 155191255
    assert event["chat_id"] == -1003158922677


def test_a_person_joining_by_link_is_their_own_actor():
    update = _MemberUpdate(
        "left", "member", _PERSON, actor=_PERSON, invite=_Invite(),
    )

    event = event_from_member_update(update, _RawUpdate())

    assert event["actor_id"] == event["user_id"]
    assert event["invite_link"] == "https://t.me/+abc"
    assert event["invite_name"] == "Promo"


def test_the_username_is_kept_as_telegram_gives_it():
    """The sheet shows "@name"; the journal keeps the raw value to match on."""
    update = _MemberUpdate("left", "member", _PERSON, actor=_PERSON)

    assert event_from_member_update(update, _RawUpdate())["username"] == "daneksosol"


def test_a_first_ever_membership_counts_as_a_join():
    """There may be no previous status at all; that is a join too."""
    update = _MemberUpdate(None, "member", _PERSON, actor=_PERSON)

    assert event_from_member_update(update, _RawUpdate())["event"] == "join"


def test_coming_back_after_a_ban_is_a_join():
    update = _MemberUpdate("kicked", "member", _PERSON, actor=_OUR_ACCOUNT)

    assert event_from_member_update(update, _RawUpdate())["event"] == "join"


def test_leaving_on_ones_own_is_recorded_as_left():
    update = _MemberUpdate("member", "left", _PERSON, actor=_PERSON)

    assert event_from_member_update(update, _RawUpdate())["event"] == "left"


def test_being_removed_is_recorded_as_kicked_not_left():
    """Leaving and being removed are different signals for retention."""
    update = _MemberUpdate("member", "kicked", _PERSON, actor=_OUR_ACCOUNT)

    assert event_from_member_update(update, _RawUpdate())["event"] == "kicked"


def test_a_demoted_administrator_is_not_a_join():
    """Ends with "member", but the person was inside all along."""
    update = _MemberUpdate("administrator", "member", _PERSON, actor=_PERSON)

    assert event_from_member_update(update, _RawUpdate()) is None


def test_a_promotion_is_not_a_membership_change():
    update = _MemberUpdate("member", "administrator", _PERSON, actor=_PERSON)

    assert event_from_member_update(update, _RawUpdate()) is None


def test_lifting_a_ban_is_not_a_membership_change():
    """Kicked to left: still outside, nobody came or went."""
    update = _MemberUpdate("kicked", "left", _PERSON, actor=_OUR_ACCOUNT)

    assert event_from_member_update(update, _RawUpdate()) is None


def test_without_the_raw_update_there_is_no_idempotency_key():
    """Without update_id a replayed update would be written twice."""
    update = _MemberUpdate("left", "member", _PERSON, actor=_OUR_ACCOUNT)

    assert event_from_member_update(update, None) is None


def test_only_channels_and_supergroups_are_journaled():
    """The bot serves channels; other chats are skipped by the sheet too."""
    update = _MemberUpdate(
        "left", "member", _PERSON, actor=_PERSON, chat=_Chat(type_="group"),
    )

    assert event_from_member_update(update, _RawUpdate()) is None


def test_a_join_request_is_recorded_with_the_requester_as_actor():
    request = _Request(_PERSON, invite=_Invite(name="(request)"))

    event = event_from_join_request(request, _RawUpdate(155191300))

    assert event is not None
    assert event["event"] == "request"
    assert event["user_id"] == event["actor_id"] == 7175828896
    assert event["update_id"] == 155191300


def test_the_moment_survives_a_round_trip_through_text():
    """Entries wait in the outbox as JSON, so the time travels as text."""
    update = _MemberUpdate("left", "member", _PERSON, actor=_OUR_ACCOUNT)

    event = event_from_member_update(update, _RawUpdate())

    assert datetime.fromisoformat(event["occurred_at"]) == _WHEN
