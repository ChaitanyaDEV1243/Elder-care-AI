import sqlite3
from datetime import date, timedelta

DB_PATH = "eldercare.db"


def insert_checkin(
    conn,
    person_id,
    check_date,
    latency,
    sentiment,
    morning_med,
    evening_med,
    call_answered
):
    cursor = conn.execute(
        """
        INSERT INTO check_ins (
            person_id,
            check_in_date,
            response_latency_seconds,
            sentiment_score,
            medication_morning_confirmed,
            medication_evening_confirmed,
            call_answered
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            person_id,
            check_date.isoformat(),
            latency,
            sentiment,
            morning_med,
            evening_med,
            call_answered
        )
    )

    return cursor.lastrowid


def insert_call_attempt(
    conn,
    check_in_id,
    attempt_number,
    answered,
    latency
):
    conn.execute(
        """
        INSERT INTO call_attempts (
            check_in_id,
            attempt_number,
            answered,
            response_latency_seconds
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            check_in_id,
            attempt_number,
            answered,
            latency
        )
    )


def main():

    conn = sqlite3.connect(DB_PATH)

    # -----------------------------------------------------
    # CREATE RAM PRAKASH VERMA
    # -----------------------------------------------------

    cursor = conn.execute(
        """
        INSERT INTO persons (
            full_name,
            age,
            notes
        )
        VALUES (?, ?, ?)
        """,
        (
            "Ram Prakash Verma",
            68,
            "Synthetic persona. Takes BP medication morning and evening."
        )
    )

    person_id = cursor.lastrowid

    # -----------------------------------------------------
    # DAYS 1-11: NORMAL BASELINE
    # -----------------------------------------------------

    baseline = [
        (8.2, 0.42),
        (7.6, 0.47),
        (8.8, 0.39),
        (7.9, 0.44),
        (9.1, 0.35),
        (8.4, 0.41),
        (7.7, 0.46),
        (8.9, 0.38),
        (8.1, 0.43),
        (9.3, 0.36),
        (8.5, 0.40),
    ]

    start_date = date.today() - timedelta(days=13)

    for day_number, (latency, sentiment) in enumerate(
        baseline,
        start=1
    ):

        check_date = start_date + timedelta(days=day_number - 1)

        check_id = insert_checkin(
            conn,
            person_id,
            check_date,
            latency,
            sentiment,
            1,
            1,
            1
        )

        insert_call_attempt(
            conn,
            check_id,
            1,
            1,
            latency
        )

    # -----------------------------------------------------
    # DAY 12: MISSED EVENING MEDICATION
    # -----------------------------------------------------

    check_date = start_date + timedelta(days=11)

    check_id = insert_checkin(
        conn,
        person_id,
        check_date,
        9.0,
        0.37,
        1,
        0,       # evening medication missed
        1
    )

    insert_call_attempt(
        conn,
        check_id,
        1,
        1,
        9.0
    )

    # -----------------------------------------------------
    # DAY 13: CALL MISSED -> RETRY SUCCESSFUL
    # -----------------------------------------------------

    check_date = start_date + timedelta(days=12)

    check_id = insert_checkin(
        conn,
        person_id,
        check_date,
        9.4,
        0.32,
        1,
        1,
        1
    )

    # First attempt: unanswered
    insert_call_attempt(
        conn,
        check_id,
        1,
        0,
        None
    )

    # Second attempt: answered
    insert_call_attempt(
        conn,
        check_id,
        2,
        1,
        9.4
    )

    # -----------------------------------------------------
    # DAY 14: FLAGGED ANOMALY
    # -----------------------------------------------------

    check_date = start_date + timedelta(days=13)

    check_id = insert_checkin(
        conn,
        person_id,
        check_date,
        18.2,      # approximately double normal latency
        -0.42,     # significant mood drop
        1,
        1,
        1
    )

    insert_call_attempt(
        conn,
        check_id,
        1,
        1,
        18.2
    )

    conn.commit()

    # -----------------------------------------------------
    # DISPLAY DATASET
    # -----------------------------------------------------

    print("\n" + "=" * 75)
    print("ELDER-CARE SYNTHETIC DATASET")
    print("=" * 75)

    print(f"Persona ID : {person_id}")
    print("Name       : Ram Prakash Verma")
    print("Age        : 68")
    print("Medication : BP medication")

    print("\n14-DAY CHECK-IN HISTORY")
    print("-" * 75)

    rows = conn.execute(
        """
        SELECT
            check_in_date,
            response_latency_seconds,
            sentiment_score,
            medication_morning_confirmed,
            medication_evening_confirmed,
            call_answered
        FROM check_ins
        WHERE person_id = ?
        ORDER BY check_in_date
        """,
        (person_id,)
    ).fetchall()

    for day, row in enumerate(rows, start=1):

        (
            check_date,
            latency,
            sentiment,
            morning,
            evening,
            call
        ) = row

        marker = ""

        if day == 12:
            marker = " <-- MISSED EVENING MED"
        elif day == 13:
            marker = " <-- CALL MISSED -> RETRY"
        elif day == 14:
            marker = " <-- ANOMALY"

        print(
            f"Day {day:02d} | "
            f"{check_date} | "
            f"latency={latency:5.1f}s | "
            f"sentiment={sentiment:5.2f} | "
            f"AM={morning} | "
            f"PM={evening} | "
            f"answered={call}"
            f"{marker}"
        )

    # -----------------------------------------------------
    # CALL ATTEMPT SUMMARY
    # -----------------------------------------------------

    print("\nCALL ATTEMPT HISTORY")
    print("-" * 75)

    attempts = conn.execute(
        """
        SELECT
            c.check_in_date,
            a.attempt_number,
            a.answered,
            a.response_latency_seconds
        FROM call_attempts a
        JOIN check_ins c
            ON a.check_in_id = c.id
        WHERE c.person_id = ?
        ORDER BY c.check_in_date, a.attempt_number
        """,
        (person_id,)
    ).fetchall()

    for row in attempts:
        print(row)

    print("\n" + "=" * 75)
    print(f"Database updated: {DB_PATH}")
    print("=" * 75)

    conn.close()


if __name__ == "__main__":
    main()