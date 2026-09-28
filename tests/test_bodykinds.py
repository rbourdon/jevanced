import unittest

from jevanced.bodykinds import parse_mobtypes

SAMPLE = """# Animation types for animation lookups\t\t
# ID\tTYPE\tFLAGS
1\tMONSTER\t0
17\tMONSTER\t0
205\tANIMAL\t0
150\tSEA_MONSTER\t0
400\tHUMAN\t20000
987\tEQUIPMENT\t0
UOSA stuff that isn't a row
"""


class ParseTest(unittest.TestCase):
    def test_reads_creature_types_and_skips_the_rest(self):
        self.assertEqual(parse_mobtypes(SAMPLE), {
            1: "monster", 17: "monster", 205: "animal", 150: "sea monster", 400: "human"})


if __name__ == "__main__":
    unittest.main()
