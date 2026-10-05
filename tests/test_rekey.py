"""Una revisión sobrevive a un reproceso que renumera las marcas: se mueve al
elemento con la misma identidad; lo que ya no existe queda huérfano."""

from klave_engine.costing.referencias import element_id
from klave_engine.costing.reviews import DetectionReview, ProjectReviews, rekey_reviews
from klave_engine.detection.results import DetectionType, make_detection


def _det(det_id, x, label):
    d = make_detection(det_id, DetectionType.fixture, "MUE", (x, 0, x + 0.5, 0.5), 0.9, [det_id],
                       "block", [], {}, "s.dxf")
    return d.model_copy(update={"display_label": label, "mark": ""})


def test_reviews_follow_their_element_when_labels_are_renumbered():
    antes = [_det("a1", 0.0, "MUE-01"), _det("a2", 5.0, "MUE-02"), _det("a3", 9.0, "MUE-03")]
    reviews = ProjectReviews(detections={
        "MUE-01": DetectionReview(status="excluded", element_id=element_id(antes[0], 1.0)),
        "MUE-02": DetectionReview(status="confirmed", element_id=element_id(antes[1], 1.0)),
        "MUE-03": DetectionReview(status="excluded", element_id=element_id(antes[2], 1.0)),
        "VIEJA": DetectionReview(status="excluded"),  # de antes de guardar identidad
    })
    # La nueva lectura renumera («MUE-001») y el tercer mueble ya no está.
    despues = [_det("b1", 0.0, "MUE-001"), _det("b2", 5.0, "MUE-002")]
    movidas, huerfanas = rekey_reviews(reviews, despues, 1.0)
    assert movidas == 2 and sorted(huerfanas) == ["MUE-03", "VIEJA"]
    assert reviews.detections["MUE-001"].status == "excluded"
    assert reviews.detections["MUE-002"].status == "confirmed"
    assert "MUE-01" not in reviews.detections
