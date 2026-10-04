from edusync.shared.infrastructure.security import hash_password, verify_password

def test_argon2_password_hashing():
    h = hash_password("motdepasse-solide")
    assert h != "motdepasse-solide"
    assert verify_password("motdepasse-solide", h)
    assert not verify_password("mauvais", h)
