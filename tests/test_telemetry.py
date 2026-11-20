from custom_components.kickrvent.telemetry import Snapshot, Telemetry


def test_one_day_idle_does_not_publish_a_timestamp_every_packet():
    telemetry = Telemetry()
    updates = []
    for second in range(86400):
        telemetry.ingest({"speed": 0, "power": 0, "cadence": 0}, second)
        if (snapshot := telemetry.publish(second, True)) is not None:
            updates.append(snapshot)
    assert updates == [Snapshot(True, False, 0, 0, 0)]
    assert len(telemetry.values) == 3


def test_high_rate_stream_bounded_and_latest_sample_is_not_lost():
    telemetry = Telemetry(interval=5)
    updates = []
    for i in range(601):  # 10 Hz, one minute
        now = i / 10
        telemetry.ingest({"power": i}, now)
        if (snapshot := telemetry.publish(now, True)) is not None:
            updates.append(snapshot)
    assert len(updates) == 13
    assert updates[-1].power == 600
    assert len(telemetry.values) == 1


def test_idle_transition_preserves_final_zero_and_wakes():
    telemetry = Telemetry()
    telemetry.ingest({"power": 220}, 0)
    assert telemetry.publish(0, True).active
    telemetry.ingest({"power": 0}, 1)
    assert telemetry.publish(1, True) is None
    assert telemetry.publish(5, True).power == 0
    assert telemetry.publish(15, True).active is False
    telemetry.ingest({"power": 240}, 20)
    assert telemetry.publish(20, True).active is True


def test_per_field_freshness_partial_packets_disconnect_and_new_session():
    telemetry = Telemetry(stale_after=30)
    telemetry.ingest({"power": 220, "speed": 30}, 0)
    telemetry.publish(0, True)
    telemetry.ingest({"power": 210}, 29)
    telemetry.publish(29, True)
    stale = telemetry.publish(30, True)
    assert stale.speed is None
    assert stale.power == 210
    telemetry.reset()
    assert telemetry.publish(31, False) == Snapshot()
    assert telemetry.publish(32, True) == Snapshot(connected=True)
    assert telemetry.snapshot(33, True).power is None


def test_rounding_and_no_force_update():
    telemetry = Telemetry()
    telemetry.ingest({"speed": 30.001, "power": 200}, 0)
    telemetry.publish(0, True)
    for second in range(1, 10):
        telemetry.ingest({"speed": 30.009, "power": 200}, second)
        assert telemetry.publish(second, True) is None
