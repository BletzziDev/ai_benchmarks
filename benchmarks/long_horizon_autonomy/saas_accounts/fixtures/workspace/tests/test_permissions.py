from acctsvc import orgs, permissions, users


def test_owner_can_everything(conn, org):
    for action in ("org.read", "org.update", "org.delete", "members.manage", "billing.read", "billing.manage"):
        assert permissions.can(conn, org["owner"], org["id"], action)


def test_member_read_only(conn, org):
    u = users.create_user(conn, "m@example.com", "Mem Ber")
    orgs.add_member(conn, org["id"], u, "member")
    assert permissions.can(conn, u, org["id"], "org.read")
    assert not permissions.can(conn, u, org["id"], "org.update")


def test_non_member_and_unknown_action_denied(conn, org):
    stranger = users.create_user(conn, "s@example.com", "Stran Ger")
    assert not permissions.can(conn, stranger, org["id"], "org.read")
    assert not permissions.can(conn, org["owner"], org["id"], "org.transmogrify")


def test_deactivated_user_has_no_permissions(conn, org):
    users.deactivate_user(conn, org["owner"])
    assert not permissions.can(conn, org["owner"], org["id"], "org.read")
