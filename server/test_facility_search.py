import unittest
from unittest.mock import patch
from urllib import parse

from server import api_server


class FacilitySearchTests(unittest.TestCase):
    def test_park_search_is_separate_from_crowded_general_results(self):
        calls = []

        def fake_page(url):
            query = parse.parse_qs(parse.urlparse(url).query)
            calls.append(query)
            if query["types"][0] == api_server.FACILITY_PARK_TYPES:
                return {"status": "1", "pois": [{
                    "id": "park-1", "name": "测试公园", "typecode": "110101",
                    "location": "118.790000,32.050000", "distance": "300",
                }]}
            return {"status": "1", "pois": [{
                "id": f"shop-{query['page'][0]}-{i}", "name": "商店", "typecode": "060000",
                "location": "118.790000,32.050000", "distance": "100",
            } for i in range(20)]}

        with patch.object(api_server, "facility_amap_key", return_value="test-key"), \
                patch.object(api_server, "request_facility_page", side_effect=fake_page):
            pois, pages, message = api_server.fetch_around_pois(118.79, 32.05)

        self.assertEqual(message, "")
        self.assertEqual(len(pages), 4)
        self.assertEqual(len(pois), 61)
        self.assertEqual(next(item for item in api_server.build_poi_summary(pois) if item["key"] == "park")["count"], 1)
        self.assertEqual(calls[-1]["types"], ["110100"])
        self.assertEqual(calls[-1]["location"], ["118.790000,32.050000"])

    def test_api_failure_is_not_reported_as_no_facilities(self):
        with patch.object(api_server, "facility_amap_key", return_value="test-key"), \
                patch.object(api_server, "request_facility_page", return_value={
                    "status": "0", "infocode": "10004", "info": "ACCESS_TOO_FREQUENT",
                }):
            pois, _, message = api_server.fetch_around_pois(118.79, 32.05)

        self.assertEqual(pois, [])
        self.assertIn("ACCESS_TOO_FREQUENT", message)


if __name__ == "__main__":
    unittest.main()
