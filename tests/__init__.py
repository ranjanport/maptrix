import unittest

from maptrix.tileid import PackedTileId
from maptrix.libmath import Coord2PointXY, MortonCode, Position, CoordinateMath


class TestLibMethods(unittest.TestCase):
    # To add a test case, add a method with the prefix test_

    test_cases = [
        {
            "name": "Eiffel Tower",
            "lon": 2.2945,
            "lat": 48.858222,
            "expected": (27374451, 582901293)
        },
        {
            "name": "Statue of Liberty",
            "lon": -74.044444,
            "lat": 40.689167,
            "expected": (-883384626, 485440671)
        },
        {
            "name": "Sugarloaf Mountain",
            "lon": -43.157444,
            "lat": -22.948658,
            "expected": (-514888362, -273788154)
        },
        {
            "name": "Sydney Opera House",
            "lon": 151.214189,
            "lat": -33.857529,
            "expected": (1804055545, -403936054)
        },
        {
            "name": "Near the Millenium Dome (O₂)",
            "lon": 0.0,
            "lat": 51.503,
            "expected": (0, 614454724)
        },
        {
            "name": "Near Quito",
            "lon": -78.45,
            "lat": 0.0,
            "expected": (-935944956, 0)
        }
    ]

    def test_to_nds_coordinates(self):
        # Test cases with expected NDS coordinates from the table
        print("-----------------------------")
        print("Testing Position to NDS conversion")

        for case in self.test_cases:
            position = Position(lon=case["lon"], lat=case["lat"])
            result = position.to_nds_coordinates()

            # Test that result is a tuple
            assert isinstance(result, tuple), f"{case['name']}: Expected tuple, got {type(result)}"

            # Test that tuple has exactly 2 elements
            assert len(result) == 2, f"{case['name']}: Expected tuple of length 2, got {len(result)}"

            # Test that both elements are integers
            assert isinstance(result[0], int), f"{case['name']}: x-coordinate should be int, got {type(result[0])}"
            assert isinstance(result[1], int), f"{case['name']}: y-coordinate should be int, got {type(result[1])}"

            # Test the actual values match expected
            assert result == case["expected"], f"{case['name']}: Expected {case['expected']}, got {result}"
            print("Passed: ", case["name"], "-> NDS Coordinates: ", result)

    def test_wgs2nds_with_coord2pointxy(self):
        print("-----------------------------")
        print("Testing WGS to NDS conversion")

        for case in self.test_cases:
            # Convert WGS to NDS coordinates
            result = CoordinateMath().WGS2NDS(Coord2PointXY(
                long=case["lon"], lat=case["lat"]
            ))

            # Create expected point
            expected_point = Coord2PointXY(
                long=case["expected"][0], lat=case["expected"][1]
            )

            # Test that result matches expected
            assert result.long == expected_point.long, \
                f"{case['name']}: Expected x-coordinate {expected_point.long}, got {result.long}"
            assert result.lat == expected_point.lat, \
                f"{case['name']}: Expected y-coordinate {expected_point.lat}, got {result.lat}"

            print("Passed: ", case["name"], "-> NDS Coordinates: ", result,)

    def test_nds2wgs_with_coord2pointxy(self):
        print("-----------------------------")
        print("Testing NDS to WGS conversion")
        # Test cases with expected WGS coordinates from the table
        test_cases = [
            {
                "name": "Eiffel Tower",
                "input": Coord2PointXY(long=27374451, lat=582901293),
                "expected": Coord2PointXY(long=2.2945, lat=48.858222)
            },
            {
                "name": "Statue of Liberty",
                "input": Coord2PointXY(long=-883384626, lat=485440671),
                "expected": Coord2PointXY(long=-74.044444, lat=40.689167)
            },
            {
                "name": "Sugarloaf Mountain",
                "input": Coord2PointXY(long=-514888362, lat=-273788154),
                "expected": Coord2PointXY(long=-43.157444, lat=-22.948658)
            },
            {
                "name": "Sydney Opera House",
                "input": Coord2PointXY(long=1804055545, lat=-403936054),
                "expected": Coord2PointXY(long=151.214189, lat=-33.857529)
            },
            {
                "name": "Near the Millenium Dome (O₂)",
                "input": Coord2PointXY(long=0, lat=614454724),
                "expected": Coord2PointXY(long=0.0, lat=51.503)
            },
            {
                "name": "Near Quito",
                "input": Coord2PointXY(long=-935944956, lat=0),
                "expected": Coord2PointXY(long=-78.45, lat=0.0)
            }
        ]

        for case in test_cases:
            # Convert NDS to WGS coordinates
            result = CoordinateMath().NDS2WGS(case["input"])

            # Verify result type
            assert isinstance(result, Coord2PointXY), \
                f"{case['name']}: Expected Coord2PointXY, got {type(result)}"

            # Verify coordinates are floats (with tolerance for floating point)
            assert isinstance(result.long, float), \
                f"{case['name']}: long should be float, got {type(result.long)}"
            assert isinstance(result.lat, float), \
                f"{case['name']}: lat should be float, got {type(result.lat)}"

            # Verify values with tolerance (due to floating point precision)
            tolerance = 0.0001
            assert abs(result.long - case["expected"].long) < tolerance, \
                f"{case['name']}: Expected long={case['expected'].long}, got {result.long}"
            assert abs(result.lat - case["expected"].lat) < tolerance, \
                f"{case['name']}: Expected lat={case['expected'].lat}, got {result.lat}"

            print("Passed: ", case["name"], "-> WGS Coordinates: ", result)

    def test_decode_morton_code(self):
        print("-----------------------------")
        print("Testing decode morton code")

        # Test cases as structured data
        test_cases = [
            {
                "mcode": 519168122092038698,
                "wgs": (77.16796875, 28.55417418912454)
            },
            {
                "mcode": 579221254078012839,
                "wgs": (2.2945, 48.858222)
            },
            {
                "mcode": 5973384896724652798,
                "wgs": (-74.044444, 40.689167)
            },
            {
                "mcode": 8983442095026671932,
                "wgs": (-43.157444, -22.948658)
            },
            {
                "mcode": 4354955230616876489,
                "wgs": (151.214189, -33.857529)
            },
            {
                "mcode": 585611620934393888,
                "wgs": (0.0, 51.503)
            },
            {
                "mcode": 5782627506097029136,
                "wgs": (-78.45, 0.0)
            }
        ]

        for i, case in enumerate(test_cases, 1):
            with self.subTest(f"Test case {i}"):
                mcode = MortonCode(case["mcode"])
                x, y = mcode.to_nds_coordinates()

                # Convert both paths to WGS84 for comparison
                result_wgs = Coord2PointXY(long=x, lat=y).to_wgs84_coordinate
                expected_wgs = Coord2PointXY(
                    long=case["wgs"][0], lat=case["wgs"][1]
                ).to_nds_coordinate.to_wgs84_coordinate

                self.assertEqual(result_wgs, expected_wgs)
            print("Passed: ", mcode, "-> WGS Coordinates: ", result_wgs)

    def test_get_tile_id_from_wgs84(self):
        print("-----------------------------")
        print("Testing get tile id from wgs84")
        nds_coord = Coord2PointXY(
            long=77.158708, lat=28.556217
        ).to_nds_coordinate
        mcode = MortonCode(MortonCode.from_nds_coordinates(nds_coord.long, nds_coord.lat))
        tile = PackedTileId.from_morton_and_level(mcode, 13)
        self.assertEqual(tile.value, 544425759)
        print("Passed: test_get_tile_id_from_wgs84")

    def test_coord2tile(self):
        print("-----------------------------")
        print("Testing coord2tile")
        c = Coord2PointXY(long=77.158708, lat=28.556217)
        self.assertEqual(c.get_tile_id(), 544425759)
        print("Passed: test_coord2tileId")




if __name__ == "__main__":
    unittest.main()
