from healthos.integrations import CSVObservationImporter, GPXImporter, HealthConnectContract, fit_adapter_status
from healthos.storage import LocalObservationStore


def test_health_connect_contract_normalizes_record():
    obs = HealthConnectContract.normalize(
        {
            "metric": "resting_hr",
            "value": 60,
            "unit": "bpm",
            "observed_at": "2027-03-01T08:00:00+00:00",
            "source_id": "synthetic-health-connect",
            "source_type": "HEALTH_CONNECT",
            "quality": "device",
        }
    )
    assert obs.metric == "resting_hr"
    assert obs.source_type == "HEALTH_CONNECT"


def test_gpx_import_and_local_store_roundtrip():
    gpx = (
        b'<?xml version="1.0"?>'
        b'<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
        b"<trk><trkseg>"
        b'<trkpt lat="0.1000" lon="0.1000"><time>2027-03-01T12:00:00Z</time></trkpt>'
        b'<trkpt lat="0.1010" lon="0.1010"><time>2027-03-01T12:01:00Z</time></trkpt>'
        b"</trkseg></trk></gpx>"
    )
    observations = GPXImporter().parse(gpx)
    assert len(observations) == 2
    store = LocalObservationStore()
    store.append(observations)
    assert store.count() == 2


def test_csv_import():
    csv_text = "metric,value,unit,observed_at\nweight,82.0,kg,2027-03-01T07:00:00+00:00\n"
    observations = CSVObservationImporter().parse(csv_text)
    assert observations[0].value == 82.0


def test_fitdecode_selected_over_fitparse():
    status = fit_adapter_status()
    assert status["selected_library"] == "fitdecode"


def test_local_store_is_idempotent_by_observation_id():
    obs = HealthConnectContract.normalize(
        {
            "metric": "weight",
            "value": 82,
            "unit": "kg",
            "observed_at": "2027-03-01T08:00:00+00:00",
            "source_id": "synthetic-hc",
            "source_type": "HEALTH_CONNECT",
        }
    )
    store = LocalObservationStore()
    assert store.append([obs]) == 1
    assert store.append([obs]) == 0
    assert store.count() == 1
