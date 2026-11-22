# Backend verification

From the `backend` directory, run the normal deterministic suite with:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Runnable examples live in `demos/` and are not part of test discovery. Their
module-level code runs only when invoked as scripts. Examples that contact a
provider or public routing/geocoding service require:

```powershell
$env:VOYAGEAI_RUN_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe demos\demo_weather_service.py
```

The optional integration suite is also inert unless explicitly enabled:

```powershell
$env:VOYAGEAI_RUN_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest integration_smoke_tests -v
```

The complete-trip smoke test requires the additional
`VOYAGEAI_RUN_FULL_LIVE_TRIP=1` opt-in because it performs multiple provider
and geocoding calls. Do not set either live-test variable during normal CI.
