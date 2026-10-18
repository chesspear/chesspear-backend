import chess
import chess.engine

from app.engine import MATE_SCORE, _score_details, _terminal_evaluation, _terminal_status


def test_score_is_reported_in_white_and_side_to_move_perspectives():
    white_advantage = chess.engine.PovScore(chess.engine.Cp(135), chess.WHITE)

    details = _score_details(white_advantage, chess.BLACK)

    assert details["white"]["centipawns"] == 135
    assert details["side_to_move"]["centipawns"] == -135
    assert details["white"]["pawns"] == 1.35
    assert details["side_to_move"]["pawns"] == -1.35
    assert details["_white_numeric"] == 135


def test_terminal_checkmate_marks_white_win_correctly():
    # White queen and king have checkmated Black; Black is to move and has no legal moves.
    board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_checkmate()
    assert _terminal_status(board) == "checkmate"

    evaluation = _terminal_evaluation(board, "checkmate")

    assert evaluation["white"]["display"] == "+M0"
    assert evaluation["side_to_move"]["display"] == "-M0"
    assert evaluation["_white_numeric"] == MATE_SCORE


def test_terminal_checkmate_marks_black_win_correctly():
    white_mated = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1").mirror()
    assert white_mated.is_checkmate()
    assert white_mated.turn == chess.WHITE

    evaluation = _terminal_evaluation(white_mated, "checkmate")

    assert evaluation["white"]["display"] == "-M0"
    assert evaluation["side_to_move"]["display"] == "-M0"
    assert evaluation["_white_numeric"] == -MATE_SCORE
