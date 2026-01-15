import unittest
import os
from app.utils.security import hash_password, verify_password


class TestSecurity(unittest.TestCase):
    def test_hashing(self):
        password = "mi_password_seguro"
        hashed = hash_password(password)

        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("incorrecto", hashed))
        self.assertNotEqual(password, hashed)


if __name__ == "__main__":
    unittest.main()
