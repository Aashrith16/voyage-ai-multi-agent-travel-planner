import unittest

from demos.demo_weather_service import format_measurement


class WeatherServiceDemoSafetyTests(unittest.TestCase):
    def test_missing_measurements_are_reported_without_numeric_formatting(self):
        self.assertEqual(format_measurement(None, "°C"), "Unavailable")

    def test_available_measurements_keep_one_decimal_place(self):
        self.assertEqual(format_measurement(19.25, "°C"), "19.2 °C")


if __name__ == "__main__":
    unittest.main()
