import pytest


@pytest.fixture
def valid_email_context():
    return {
        "sender": "hacker@evil.com",
        "subject": "Urgent Invoice",
        "body_text": "Please open the attached PDF."
    }
