from types import SimpleNamespace as NS

from app.schemas.business import DIMENSION_KEYS
from app.services.recordings import effective_scores


def evaluation(missing=True):
    return NS(overall_score=None if missing else 80, calibrations=[], dimension_scores=[
        NS(dimension=key, score=None if missing and index == 0 else 80)
        for index, key in enumerate(DIMENSION_KEYS)
    ])


def calibration(id, dimensions=None, overall=None):
    return NS(id=id, dimension_scores=dimensions, overall_score=overall)


def test_filling_missing_dimension_derives_total_without_changing_model_score():
    item = evaluation()
    item.calibrations = [calibration(1, {DIMENSION_KEYS[0]: 50})]
    assert effective_scores(item)[0] == 75
    assert item.overall_score is None
    assert item.dimension_scores[0].score is None


def test_remaining_missing_dimension_keeps_total_empty():
    item = evaluation()
    item.calibrations = [calibration(1, {DIMENSION_KEYS[1]: 90})]
    assert effective_scores(item)[0] is None


def test_latest_dimension_calibration_and_zero_are_used():
    item = evaluation(False)
    item.calibrations = [calibration(1, {DIMENSION_KEYS[0]: 50}), calibration(2, {DIMENSION_KEYS[0]: 0})]
    assert effective_scores(item)[0] == 66.67


def test_explicit_total_takes_priority_even_when_zero():
    item = evaluation()
    item.calibrations = [calibration(1, overall=90), calibration(2, overall=0), calibration(3)]
    assert effective_scores(item)[0] == 0


def test_no_calibration_keeps_original_total():
    assert effective_scores(evaluation())[0] is None
    assert effective_scores(evaluation(False))[0] == 80


def test_new_dimension_edit_supersedes_older_explicit_total():
    item = evaluation()
    item.calibrations = [calibration(1, overall=0), calibration(2, {DIMENSION_KEYS[0]: 50}), calibration(3)]
    assert effective_scores(item)[0] == 75
