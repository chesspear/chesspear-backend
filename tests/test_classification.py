from app.classification import classify_move, move_tags


def test_best_move_takes_precedence_over_loss():
    assert classify_move(0, best_move_played=True) == "best"
    assert classify_move(500, best_move_played=True) == "best"


def test_loss_thresholds():
    assert classify_move(0, False) == "excellent"
    assert classify_move(20, False) == "excellent"
    assert classify_move(21, False) == "good"
    assert classify_move(50, False) == "good"
    assert classify_move(51, False) == "inaccuracy"
    assert classify_move(100, False) == "inaccuracy"
    assert classify_move(101, False) == "mistake"
    assert classify_move(200, False) == "mistake"
    assert classify_move(201, False) == "blunder"


def test_move_tags():
    assert move_tags(
        is_capture=True,
        is_en_passant=True,
        is_castling=False,
        promotion=None,
        gives_check=True,
        is_checkmate=True,
    ) == ["capture", "en_passant", "check", "checkmate"]
