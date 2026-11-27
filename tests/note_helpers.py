"""Helpers of the tests of the observation of a bioimpedance measurement: fake measurements with or without a note."""

from datetime import date

from flask import Flask

from app.models import SkinFolds, db

NOTE_MODAL_ID = "note-modal"
NOTE_TITLE = "Este paciente possui observações adicionais"
NOTE_BUTTON = "Entendi"


def add_measurement(app: Flask, patient_id: int, when: date, note: str | None = None, weight: float = 70.0) -> int:
    """Add a bioimpedance measurement to a patient; the ``case_patients`` fixture removes it with the patient.

    :param app: Flask application.
    :param patient_id: Id of the patient.
    :param when: Date of the measurement.
    :param note: Observation of the measurement, or None for no observation.
    :param weight: Weight of the measurement.
    :return: The id of the new measurement.
    """
    with app.app_context():
        row = SkinFolds(
            patient_id=patient_id,
            data_medicao=when,
            altura=1.7,
            peso=weight,
            massa_muscular=0,
            gordura=0,
            abdominal=0,
            cintura=0,
            quadril=0,
            idade_metabolica=0,
            pa="12/8",
            observacoes=note,
        )
        db.session.add(row)
        db.session.commit()
        return row.id
