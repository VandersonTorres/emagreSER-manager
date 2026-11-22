"""Fake seed data constants shared by the conftests and the tests."""

TEST_PASSWORD = "test-password-123"  # pragma: allowlist secret

ROLES = ("admin", "secretary", "nutritionist")
EMAILS = {
    "admin": "admin@test.local",
    "secretary": "secretary@test.local",  # pragma: allowlist secret
    "nutritionist": "nutritionist@test.local",
}
NUTRITIONIST_USERNAME = "Nutri Teste"

FIXTURE_DIET_URL = "https://fixtures.test/diet-a4.pdf"
