import unittest
from pathlib import Path

from tr2 import Tr2

import hashlib


class TR2Tests(unittest.TestCase):
    def test_read_misc_tr2_and_write_it_back_validate(self):
        project_root = Path(__file__).resolve().parent.parent
        original_path = project_root / "tr2" / "Misc.tr2"
        copied_path = project_root / "tr2" / "Misc_copy.tr2"

        # Read the original file and get its hash.
        original_tr2 = Tr2(original_path)
        original_hash = self.get_file_hash(original_path)

        # Write it back out to a new file.
        original_tr2.save(copied_path)

        # Read the new file and get its hash.
        copied_tr2 = Tr2(copied_path)
        copied_hash = self.get_file_hash(copied_path)

        # Compare the hashes to ensure they are identical.
        self.assertEqual(original_hash, copied_hash, "The original and copied TR2 files do not match.")

        # Clean up the copied file after the test.
        copied_path.unlink()

    @staticmethod
    def get_file_hash(filename: Path) -> str:
        """Calculate the SHA-256 hash of a file.

        Args:
            filename (Path): The path to the file.

        Returns:
            str: The hexadecimal representation of the hash.
        """
        with open(filename, 'rb') as f:
            file_data = f.read()
            return hashlib.sha256(file_data).hexdigest()