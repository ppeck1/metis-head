from metis_head.governance import classify_intent


def test_email_read_is_not_misclassified_as_write():
    policy = classify_intent("search my email for the receipt")
    assert policy.action_class == "retrieve"
    assert policy.requires_approval is False


def test_email_send_remains_external_action():
    policy = classify_intent("send an email to Alex")
    assert policy.action_class == "external_action"
    assert policy.requires_approval is True
