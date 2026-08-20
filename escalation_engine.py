import sqlite3

DB_PATH = "eldercare.db"


def decide_escalation(anomaly_score, anomaly_level):
    """
    Convert an anomaly classification into an action.

    This is intentionally deterministic and explainable,
    which is useful for a hackathon demo.
    """

    if anomaly_level == "normal":
        return {
            "level": "none",
            "action": "No escalation required."
        }

    elif anomaly_level == "low":
        return {
            "level": "low",
            "action": "Continue monitoring the elder."
        }

    elif anomaly_level == "medium":
        return {
            "level": "medium",
            "action": "Notify the designated caregiver for a wellness check."
        }

    elif anomaly_level == "high":
        return {
            "level": "high",
            "action": "Urgent caregiver notification and immediate wellness check recommended."
        }

    raise ValueError(
        f"Unknown anomaly level: {anomaly_level}"
    )


def save_escalation(conn, anomaly_id, decision):
    """
    Store the escalation decision in SQLite.
    """

    cursor = conn.execute(
        """
        INSERT INTO escalations (
            anomaly_id,
            escalation_level,
            action
        )
        VALUES (?, ?, ?)
        """,
        (
            anomaly_id,
            decision["level"],
            decision["action"]
        )
    )

    conn.commit()

    return cursor.lastrowid


def get_latest_anomaly(conn):
    """
    Get the most recent anomaly event.
    """

    return conn.execute(
        """
        SELECT
            id,
            check_in_id,
            anomaly_score,
            is_anomaly,
            reason
        FROM anomaly_events
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def main():

    conn = sqlite3.connect(DB_PATH)

    anomaly = get_latest_anomaly(conn)

    if anomaly is None:
        raise ValueError(
            "No anomaly event found. "
            "Run anomaly_engine.py first."
        )

    (
        anomaly_id,
        check_in_id,
        anomaly_score,
        is_anomaly,
        reason
    ) = anomaly

    # Recreate the classification from the stored score.
    if anomaly_score >= 0.70:
        anomaly_level = "high"

    elif anomaly_score >= 0.50:
        anomaly_level = "medium"

    elif anomaly_score >= 0.30:
        anomaly_level = "low"

    else:
        anomaly_level = "normal"

    decision = decide_escalation(
        anomaly_score,
        anomaly_level
    )

    escalation_id = save_escalation(
        conn,
        anomaly_id,
        decision
    )

    print("\n" + "=" * 65)
    print("ESCALATION DECISION")
    print("=" * 65)

    print(f"\nAnomaly ID : {anomaly_id}")
    print(f"Check-in ID: {check_in_id}")
    print(f"Score      : {anomaly_score:.3f}")
    print(f"Level      : {anomaly_level.upper()}")

    print("\nReason:")
    print(reason)

    print("\nDecision:")
    print(f"  Escalation level: {decision['level']}")
    print(f"  Action: {decision['action']}")

    print(f"\nSaved escalation ID: {escalation_id}")

    print("\n" + "=" * 65)

    conn.close()


if __name__ == "__main__":
    main()