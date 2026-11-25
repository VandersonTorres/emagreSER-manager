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

TRICKY_TEXT = 'D\'Avila \\ barra\nnova linha; ponto e vírgula, ção 😀 "aspas" -- :var \\q'
FORMULAS = ("=1+1", "+1", "-1", "@SUM(A1)", "\tcmd", "\rcmd")
SECRETS = {
    "password": "hash-secret-value-0001",  # pragma: allowlist secret
    "fs_uniquifier": "uniquifier-secret-value-0002",
    "fs_webauthn_user_handle": "webauthn-secret-value-0003",
    "tf_totp_secret": "totp-secret-value-0004",  # pragma: allowlist secret
    "us_totp_secrets": "unified-totp-secret-value-0005",  # pragma: allowlist secret
}
RECOVERY_CODES = ["recovery-secret-0006", "recovery-secret-0007"]
ALEMBIC_REVISION = "fb739ba57804"  # pragma: allowlist secret
